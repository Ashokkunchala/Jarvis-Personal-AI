"""Dependency-aware, bounded execution for typed JARVIS tool tasks."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from jarvis.tools.registry import Risk, Tool, ToolRegistry, ToolResult

TaskEvent = Callable[[dict[str, Any]], None]
ConfirmHandler = Callable[[Tool, dict[str, Any]], Awaitable[bool]] | None
MAX_TASKS_PER_PLAN = 100


@dataclass(frozen=True)
class ToolTask:
    """One typed tool action and the tasks that must succeed before it runs."""

    task_id: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    retries: int = 0


class ToolTaskOrchestrator:
    """Run tool plans with dependencies, bounded read-only parallelism and events.

    Mutating or confirmation-gated actions run one at a time. Retries are
    restricted to SAFE tools because retrying a write could duplicate effects.
    """

    def __init__(self, registry: ToolRegistry, max_parallel: int = 3):
        if max_parallel < 1:
            raise ValueError("max_parallel must be at least 1")
        self.registry = registry
        self.max_parallel = max_parallel

    async def run(
        self,
        tasks: Iterable[ToolTask],
        *,
        confirm: ConfirmHandler = None,
        auto_approve: bool = False,
        on_event: TaskEvent | None = None,
    ) -> dict[str, ToolResult]:
        plan = list(tasks)
        self._validate(plan)
        results: dict[str, ToolResult] = {}
        pending = {task.task_id: task for task in plan}

        while pending:
            ready = [
                task for task in plan
                if task.task_id in pending
                and all(dep in results for dep in task.depends_on)
            ]
            if not ready:
                raise ValueError("Task plan contains a dependency cycle")

            runnable: list[ToolTask] = []
            for task in ready:
                failed_deps = [dep for dep in task.depends_on if not results[dep].ok]
                if failed_deps:
                    result = ToolResult(
                        task.tool,
                        False,
                        error="Skipped because prerequisite task(s) failed: " + ", ".join(failed_deps),
                    )
                    results[task.task_id] = result
                    pending.pop(task.task_id)
                    self._emit(on_event, {"type": "task_skipped", "task_id": task.task_id,
                                          "tool": task.tool, "error": result.error})
                else:
                    runnable.append(task)

            if not runnable:
                continue

            # Keep actions requiring confirmation or changing state serial.
            first = runnable[0]
            tool = self.registry.get(first.tool)
            if tool is not None and tool.risk == Risk.SAFE and not tool.confirm_required:
                batch = [
                    task for task in runnable
                    if (self.registry.get(task.tool) is not None
                        and self.registry.get(task.tool).risk == Risk.SAFE
                        and not self.registry.get(task.tool).confirm_required)
                ][: self.max_parallel]
                completed = await asyncio.gather(*(
                    self._run_one(task, confirm, auto_approve, on_event)
                    for task in batch
                ))
                for task, result in zip(batch, completed):
                    results[task.task_id] = result
                    pending.pop(task.task_id)
            else:
                result = await self._run_one(first, confirm, auto_approve, on_event)
                results[first.task_id] = result
                pending.pop(first.task_id)

        return results

    def _validate(self, plan: list[ToolTask]) -> None:
        if len(plan) > MAX_TASKS_PER_PLAN:
            raise ValueError(f"Task plans are limited to {MAX_TASKS_PER_PLAN} steps")
        ids = [task.task_id for task in plan]
        if any(not task_id for task_id in ids) or len(ids) != len(set(ids)):
            raise ValueError("Task IDs must be non-empty and unique")
        known = set(ids)
        for task in plan:
            if not task.tool:
                raise ValueError(f"Task {task.task_id} has no tool")
            if any(dep not in known for dep in task.depends_on):
                raise ValueError(f"Task {task.task_id} references an unknown dependency")
            if task.task_id in task.depends_on:
                raise ValueError(f"Task {task.task_id} cannot depend on itself")
            if not 0.1 <= task.timeout_seconds <= 300:
                raise ValueError("Task timeout must be between 0.1 and 300 seconds")
            if not 0 <= task.retries <= 2:
                raise ValueError("Task retries must be between 0 and 2")
            tool = self.registry.get(task.tool)
            if task.retries and (tool is None or tool.risk != Risk.SAFE or tool.confirm_required):
                raise ValueError("Retries are allowed only for SAFE, non-confirmed tools")

        # Check acyclicity before any side effect can run.
        resolved: set[str] = set()
        remaining = {task.task_id: set(task.depends_on) for task in plan}
        while remaining:
            ready = {task_id for task_id, deps in remaining.items() if deps <= resolved}
            if not ready:
                raise ValueError("Task plan contains a dependency cycle")
            resolved.update(ready)
            for task_id in ready:
                remaining.pop(task_id)

    async def _run_one(
        self,
        task: ToolTask,
        confirm: ConfirmHandler,
        auto_approve: bool,
        on_event: TaskEvent | None,
    ) -> ToolResult:
        self._emit(on_event, {"type": "task_start", "task_id": task.task_id,
                              "tool": task.tool, "depends_on": list(task.depends_on)})
        started = time.monotonic()
        attempts = task.retries + 1
        tool = self.registry.get(task.tool)
        for attempt in range(1, attempts + 1):
            try:
                execution = self.registry.execute(task.tool, task.args, confirm=confirm,
                                                   auto_approve=auto_approve)
                if tool is not None and tool.risk == Risk.SAFE and not tool.confirm_required:
                    result = await asyncio.wait_for(execution, timeout=task.timeout_seconds)
                else:
                    # A timed-out sync mutation may keep running in its worker
                    # thread. Never report such an action as stopped by timeout.
                    result = await execution
            except TimeoutError:
                result = ToolResult(task.tool, False, error="Task timed out",
                                    elapsed=time.monotonic() - started)
            except asyncio.CancelledError:
                self._emit(on_event, {"type": "task_cancelled", "task_id": task.task_id,
                                      "tool": task.tool})
                raise
            if result.ok or attempt == attempts or not self._is_transient(result.error):
                if result.ok and isinstance(result.data, dict):
                    summary = next((f"{key}={result.data[key]}" for key in
                                    ("message", "action", "path", "name", "count", "value")
                                    if key in result.data), "tool reported success")
                else:
                    summary = result.error or "tool reported failure"
                self._emit(on_event, {"type": "task_end", "task_id": task.task_id,
                                      "tool": task.tool, "success": result.ok,
                                      "elapsed": round(time.monotonic() - started, 3),
                                      "summary": summary,
                                      "error": result.error})
                return result
            self._emit(on_event, {"type": "task_retry", "task_id": task.task_id,
                                  "tool": task.tool, "attempt": attempt + 1})
        return result

    @staticmethod
    def _is_transient(error: str | None) -> bool:
        message = (error or "").lower()
        return any(marker in message for marker in
                   ("timeout", "temporarily", "429", "503", "connection reset", "unavailable"))

    @staticmethod
    def _emit(callback: TaskEvent | None, event: dict[str, Any]) -> None:
        if callback:
            try:
                callback(event)
            except Exception:
                pass
