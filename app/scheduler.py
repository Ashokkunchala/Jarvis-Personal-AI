"""Persistent, opt-in scheduler for a small set of read-only system metrics."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import Settings
from app.personal_data import _connect, _now, _record_schedule_history
from jarvis.telemetry import record_runtime_event
from jarvis.tools.builtin_tools import build_registry
from jarvis.tools.orchestrator import ToolTask, ToolTaskOrchestrator
from jarvis.tools.registry import Risk, ToolRegistry

ALLOWED_SCHEDULE_TOOLS = frozenset({
    "system_status", "cpu_usage", "memory_usage", "disk_usage", "battery_status",
})
MAX_CONCURRENT_SCHEDULES = 2


class ScheduleRunner:
    """Poll SQLite schedules and execute only explicitly allowed SAFE metrics."""

    def __init__(self, poll_seconds: float = 5.0, registry_factory=build_registry):
        self.poll_seconds = max(0.25, poll_seconds)
        self.registry_factory = registry_factory
        self.registry: ToolRegistry | None = None
        self._loop_task: asyncio.Task | None = None
        self._active: dict[int, asyncio.Task] = {}
        from jarvis.proactive import ProactiveRunner

        self.proactive = ProactiveRunner()

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        if Path(Settings().jarvis_db_path).exists():
            self._recover_interrupted()
        self._loop_task = asyncio.create_task(self._run_loop(), name="jarvis-schedule-runner")

    async def stop(self) -> None:
        loop_task, self._loop_task = self._loop_task, None
        if loop_task is not None:
            loop_task.cancel()
            await asyncio.gather(loop_task, return_exceptions=True)
        active = list(self._active.values())
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    async def cancel_schedule(self, schedule_id: int) -> None:
        task = self._active.get(schedule_id)
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def run_due_once(self) -> list[asyncio.Task]:
        """Claim currently due entries and return tasks, primarily for tests/operations."""
        if not Path(Settings().jarvis_db_path).exists():
            return []
        capacity = MAX_CONCURRENT_SCHEDULES - len(self._active)
        if capacity <= 0:
            return []
        now = datetime.now(UTC)
        with _connect() as db:
            rows = db.execute(
                "SELECT * FROM scheduled_runs WHERE enabled=1 AND state='scheduled' "
                "AND next_run_at<=? ORDER BY next_run_at,id LIMIT ?",
                (now.isoformat(), capacity),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                cur = db.execute(
                    "UPDATE scheduled_runs SET state='running',updated_at=? "
                    "WHERE id=? AND enabled=1 AND state='scheduled' AND next_run_at<=?",
                    (_now(), row["id"], now.isoformat()),
                )
                if cur.rowcount:
                    claimed.append(dict(row))
                    _record_schedule_history(db, row["id"], "started", "running")
        tasks = []
        for schedule in claimed:
            schedule_id = int(schedule["id"])
            task = asyncio.create_task(self._execute(schedule), name=f"jarvis-schedule-{schedule_id}")
            self._active[schedule_id] = task
            task.add_done_callback(lambda done, key=schedule_id: self._active.pop(key, None))
            tasks.append(task)
        return tasks

    async def _run_loop(self) -> None:
        while True:
            await self.run_due_once()
            try:
                await asyncio.to_thread(self.proactive.tick)
            except Exception:
                # Never let a missing sensor or local DB issue stop other schedules.
                logging.getLogger(__name__).warning("Proactive local check failed", exc_info=False)
            await asyncio.sleep(self.poll_seconds)

    async def _execute(self, schedule: dict[str, Any]) -> None:
        schedule_id = int(schedule["id"])
        tool_name = str(schedule["tool"])
        started = time.monotonic()
        status = "failed"
        elapsed: float | None = None
        try:
            args = json.loads(schedule["args_json"])
            if tool_name not in ALLOWED_SCHEDULE_TOOLS or not isinstance(args, dict):
                raise ValueError("Schedule is outside the allowed read-only tool set")
            if tool_name != "cpu_usage" and args:
                raise ValueError("Scheduled metric arguments are not allowed")
            if tool_name == "cpu_usage" and set(args) - {"interval"}:
                raise ValueError("Scheduled CPU arguments are not allowed")
            if self.registry is None:
                self.registry = self.registry_factory()
            tool = self.registry.get(tool_name)
            if tool is None or tool.risk != Risk.SAFE or tool.confirm_required:
                raise ValueError("Scheduled tool is no longer SAFE")

            def on_event(event: dict[str, Any]) -> None:
                kind = event.get("type", "task")
                record_runtime_event(
                    "task", action=str(kind), tool=tool_name,
                    task_id=f"schedule-{schedule_id}",
                    success=event.get("success") if isinstance(event.get("success"), bool) else None,
                    elapsed=event.get("elapsed"),
                )

            result = (await ToolTaskOrchestrator(self.registry, max_parallel=1).run(
                [ToolTask(task_id=f"schedule-{schedule_id}", tool=tool_name, args=args,
                          timeout_seconds=20)],
                on_event=on_event,
            ))[f"schedule-{schedule_id}"]
            status = "success" if result.ok else "failed"
            elapsed = round(time.monotonic() - started, 3)
        except asyncio.CancelledError:
            status = "cancelled"
            elapsed = round(time.monotonic() - started, 3)
            raise
        except Exception:
            # Do not persist provider/tool exception text or output in schedule history.
            status = "failed"
            elapsed = round(time.monotonic() - started, 3)
        finally:
            self._finish(schedule, status, elapsed)

    def _finish(self, schedule: dict[str, Any], status: str, elapsed: float | None) -> None:
        schedule_id = int(schedule["id"])
        now = datetime.now(UTC)
        with _connect() as db:
            current = db.execute(
                "SELECT enabled,interval_minutes,next_run_at FROM scheduled_runs WHERE id=?",
                (schedule_id,),
            ).fetchone()
            _record_schedule_history(db, schedule_id, "finished", status, elapsed)
            if current is None:
                return
            if current["enabled"]:
                next_run = datetime.fromisoformat(current["next_run_at"])
                interval = timedelta(minutes=int(current["interval_minutes"]))
                while next_run <= now:
                    next_run += interval
                db.execute(
                    "UPDATE scheduled_runs SET state='scheduled',next_run_at=?,last_run_at=?,"
                    "last_status=?,updated_at=? WHERE id=? AND enabled=1",
                    (next_run.astimezone(UTC).isoformat(), now.isoformat(), status, now.isoformat(), schedule_id),
                )
            else:
                db.execute(
                    "UPDATE scheduled_runs SET state='disabled',last_run_at=?,last_status=?,updated_at=? "
                    "WHERE id=?",
                    (now.isoformat(), status, now.isoformat(), schedule_id),
                )

    def _recover_interrupted(self) -> None:
        """Return persisted running entries to their scheduled/disabled state after restart."""
        with _connect() as db:
            rows = db.execute("SELECT id,enabled FROM scheduled_runs WHERE state='running'").fetchall()
            for row in rows:
                state = "scheduled" if row["enabled"] else "disabled"
                db.execute(
                    "UPDATE scheduled_runs SET state=?,updated_at=? WHERE id=?",
                    (state, _now(), row["id"]),
                )
                _record_schedule_history(db, row["id"], "recovered", state)
