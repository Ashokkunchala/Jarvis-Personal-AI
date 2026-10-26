"""Tool registry: every action JARVIS can perform, exposed to the AI.

Tools are declared with JSON-schema parameters (Gemini function-declaration
shape), a handler, a risk level and an optional confirmation requirement.
The same registry serves the Gemini tool loop, the CLI and the TUI.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger("jarvis.tools")


class Risk(IntEnum):
    """Ascending danger. Confirmation policy keys off this."""

    SAFE = 0        # read-only: status, search, list
    LOW = 1         # reversible actions: open app, set volume, type text
    MEDIUM = 2      # state changes: close app, delete file, install apk
    HIGH = 3        # destructive/system: shutdown, reboot, kill, format


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    risk: Risk = Risk.LOW
    category: str = "general"
    requires_confirmation: bool = False
    requires_device: bool = False
    examples: list[str] = field(default_factory=list)

    @property
    def confirm_required(self) -> bool:
        return self.requires_confirmation or self.risk >= Risk.HIGH

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolResult:
    """Normalised execution result."""

    __slots__ = ("ok", "data", "error", "elapsed", "tool", "cancelled")

    def __init__(self, tool: str, ok: bool, data: Any = None, error: str | None = None, elapsed: float = 0.0, cancelled: bool = False):
        self.tool = tool
        self.ok = ok
        self.data = data
        self.error = error
        self.elapsed = elapsed
        self.cancelled = cancelled

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"success": self.ok, "tool": self.tool, "elapsed": round(self.elapsed, 3)}
        if self.cancelled:
            payload["cancelled"] = True
            payload["success"] = False
            payload["error"] = "Cancelled by user"
        elif self.ok:
            payload["result"] = self.data
        else:
            payload["error"] = self.error or "Tool failed"
        return payload

    def for_model(self) -> str:
        """Compact JSON the model reads back as the function response."""
        if self.cancelled:
            return json.dumps({"success": False, "error": "User cancelled this action."})
        if not self.ok:
            return json.dumps({"success": False, "error": self.error or "Tool failed"})
        data = self.data
        if isinstance(data, (dict, list)):
            text = json.dumps(data, ensure_ascii=False, default=str)
        else:
            text = str(data)
        if len(text) > 8000:
            text = text[:8000] + "…[truncated]"
        return json.dumps({"success": True, "data": text if not isinstance(data, (dict, list)) else data},
                          ensure_ascii=False, default=str)


class ToolRegistry:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}
        self._built = False

    # -------------------------------------------------------------- register
    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            logger.debug("Replacing existing tool %s", tool.name)
        self.tools[tool.name] = tool

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        risk: Risk = Risk.LOW,
        category: str = "general",
        requires_confirmation: bool = False,
        requires_device: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator form of :meth:`register`."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                Tool(
                    name=name,
                    description=description,
                    parameters=parameters,
                    handler=func,
                    risk=risk,
                    category=category,
                    requires_confirmation=requires_confirmation,
                    requires_device=requires_device,
                )
            )
            return func

        return decorator

    # ----------------------------------------------------------------- query
    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def __len__(self) -> int:
        return len(self.tools)

    def names(self, category: str | None = None) -> list[str]:
        return [t.name for t in self.tools.values() if category is None or t.category == category]

    def categories(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for tool in self.tools.values():
            out.setdefault(tool.category, []).append(tool.name)
        return out

    def get_tool_schemas(self, categories: list[str] | None = None) -> list[dict[str, Any]]:
        """Gemini ``FunctionDeclaration`` list."""
        return [
            t.schema()
            for t in self.tools.values()
            if categories is None or t.category in categories
        ]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "category": t.category,
                "risk": t.risk.name,
                "confirm": t.confirm_required,
                "description": t.description,
                "params": list(t.parameters.get("properties", {}).keys()),
            }
            for t in sorted(self.tools.values(), key=lambda x: (x.category, x.name))
        ]

    # --------------------------------------------------------------- execute
    async def execute(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        confirm: Callable[[Tool, dict[str, Any]], Awaitable[bool]] | None = None,
        auto_approve: bool = False,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolResult:
        """Run a tool, honouring confirmation and emitting progress events."""
        started = time.time()
        args = dict(args or {})

        def emit(event: dict[str, Any]) -> None:
            if on_event:
                try:
                    on_event(event)
                except Exception:
                    logger.debug("on_event callback failed", exc_info=True)

        tool = self.tools.get(name)
        if tool is None:
            emit({"type": "tool_error", "tool": name, "error": "unknown tool"})
            return ToolResult(name, False, error=f"Unknown tool: {name}")

        emit({"type": "tool_start", "tool": name, "args": args, "risk": tool.risk.name, "category": tool.category})

        if tool.confirm_required and confirm is not None and not auto_approve:
            try:
                approved = await confirm(tool, args)
            except Exception:
                logger.exception("Confirmation callback failed")
                approved = False
            if not approved:
                emit({"type": "tool_cancelled", "tool": name})
                return ToolResult(name, False, elapsed=time.time() - started, cancelled=True)

        try:
            if tool.requires_device:
                args = dict(args)
                args.setdefault("device", None)
            result = await _invoke(tool.handler, args)
            elapsed = time.time() - started
            tool_result = _normalise(name, result, elapsed)
            emit(
                {
                    "type": "tool_end" if tool_result.ok else "tool_error",
                    "tool": name,
                    "ok": tool_result.ok,
                    "elapsed": round(elapsed, 3),
                    "summary": _summarise(result) if tool_result.ok else tool_result.error,
                }
            )
            logger.info("Tool %s -> %s (%.2fs)", name, "ok" if tool_result.ok else "fail", elapsed)
            return tool_result
        except Exception as exc:
            elapsed = time.time() - started
            logger.exception("Tool %s crashed", name)
            emit({"type": "tool_error", "tool": name, "error": str(exc), "elapsed": round(elapsed, 3)})
            return ToolResult(name, False, error=str(exc), elapsed=elapsed)


def _normalise(name: str, result: Any, elapsed: float) -> ToolResult:
    if isinstance(result, ToolResult):
        return result
    if isinstance(result, dict):
        if "success" in result:
            ok = bool(result["success"])
            error = result.get("error")
            if ok:
                data = {k: v for k, v in result.items() if k not in {"success", "error"}}
                return ToolResult(name, True, data=data, elapsed=elapsed)
            return ToolResult(name, False, error=str(error or "Tool reported failure"), elapsed=elapsed)
        return ToolResult(name, True, data=result, elapsed=elapsed)
    if isinstance(result, bool):
        return ToolResult(name, result, data=result, elapsed=elapsed)
    if result is None:
        return ToolResult(name, True, data=None, elapsed=elapsed)
    if isinstance(result, list):
        return ToolResult(name, True, data=result, elapsed=elapsed)
    return ToolResult(name, True, data=str(result), elapsed=elapsed)


def _summarise(result: Any) -> str:
    try:
        if isinstance(result, dict):
            if result.get("success") is False:
                return str(result.get("error", "failed"))
            for key in ("message", "action", "path", "name", "volume", "percent", "count"):
                if key in result:
                    return f"{key}={result[key]}"
            return "ok"
        if isinstance(result, list):
            return f"{len(result)} item(s)"
        if isinstance(result, bool):
            return "ok" if result else "failed"
        return str(result)[:120]
    except Exception:
        return "ok"


async def _invoke(handler: Callable[..., Any], args: dict[str, Any]) -> Any:
    """Call sync or async handlers; run sync ones off the event loop."""
    try:
        sig = inspect.signature(handler)
        accepted = {k: v for k, v in args.items() if k in sig.parameters}
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            accepted = dict(args)
    except (TypeError, ValueError):
        accepted = dict(args)

    if inspect.iscoroutinefunction(handler):
        return await handler(**accepted)
    return await asyncio.to_thread(handler, **accepted)
