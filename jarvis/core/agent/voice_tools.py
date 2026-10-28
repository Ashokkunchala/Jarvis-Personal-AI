"""Local device tools exposed to the Gemini Live voice session.

Only non-destructive, reversible actions are registered. Power actions
(shutdown/restart) stay behind the typed CLI so a stray voice turn can never
turn the machine off.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

logger = logging.getLogger("jarvis.voice_tools")

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "get_current_time",
        "description": "Get the current local date and time on this computer.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_system_status",
        "description": "Get CPU, memory, disk, battery and OS status of this computer.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "open_app",
        "description": "Open an application on this computer (e.g. chrome, notepad, calculator, vscode, explorer).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Application name to open."}
            },
            "required": ["name"],
        },
    },
    {
        "name": "set_volume",
        "description": "Set the system volume level.",
        "parameters": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Volume level from 0 to 100.",
                    "minimum": 0,
                    "maximum": 100,
                }
            },
            "required": ["level"],
        },
    },
    {
        "name": "set_mute",
        "description": "Mute or unmute the system audio.",
        "parameters": {
            "type": "object",
            "properties": {
                "muted": {"type": "boolean", "description": "True to mute, false to unmute."}
            },
            "required": ["muted"],
        },
    },
    {
        "name": "take_screenshot",
        "description": "Capture a screenshot of the screen and save it as a PNG file.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "focus_window",
        "description": "Bring a window to the front by a part of its title (e.g. 'chrome').",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Text contained in the window title."}
            },
            "required": ["title"],
        },
    },
    {
        "name": "lock_screen",
        "description": "Lock the computer workstation.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def build_tool_executor(system) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Return an executor that runs a named voice tool against SystemController."""

    def execute(name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = _HANDLERS.get(name)
        if handler is None:
            return {"success": False, "error": f"unknown tool: {name}"}
        try:
            return handler(system, args)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Voice tool %s crashed", name)
            return {"success": False, "error": str(exc)}

    return execute


def _ok(payload: dict[str, Any] | None = None, message: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {"success": True}
    if message:
        result["message"] = message
    if payload:
        result.update(payload)
    return result


def _time(system, args) -> dict[str, Any]:
    now = datetime.now()
    return _ok(
        {"datetime": now.isoformat(timespec="seconds"), "weekday": now.strftime("%A")},
        now.strftime("%A, %d %B %Y %H:%M"),
    )


def _status(system, args) -> dict[str, Any]:
    result = system.status()
    if isinstance(result, dict) and result.get("success"):
        summary = (
            f"CPU {result.get('cpu_percent', 0):.0f}%, "
            f"memory {result.get('memory_percent', 0):.0f}%, "
            f"disk free {result.get('disk_free_gb')} GB"
        )
        if result.get("battery_percent") is not None:
            summary += f", battery {result.get('battery_percent')}%"
        return _ok(result, summary)
    return {"success": False, "error": (result or {}).get("error", "status unavailable")}


def _open_app(system, args) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    if not name:
        return {"success": False, "error": "app name is required"}
    return system.open_app(name)


def _set_volume(system, args) -> dict[str, Any]:
    try:
        level = int(args.get("level"))
    except (TypeError, ValueError):
        return {"success": False, "error": "level must be an integer 0-100"}
    level = max(0, min(100, level))
    return system.set_volume(level)


def _set_mute(system, args) -> dict[str, Any]:
    muted = bool(args.get("muted", True))
    return system.set_mute(muted)


def _screenshot(system, args) -> dict[str, Any]:
    result = system.screenshot()
    if isinstance(result, dict) and result.get("success"):
        return _ok(result, f"screenshot saved to {result.get('file', 'disk')}")
    return {"success": False, "error": (result or {}).get("error", "screenshot failed")}


def _focus_window(system, args) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        return {"success": False, "error": "window title is required"}
    return system.focus_window(title)


def _lock(system, args) -> dict[str, Any]:
    return system.lock()


_HANDLERS: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]] = {
    "get_current_time": _time,
    "get_system_status": _status,
    "open_app": _open_app,
    "set_volume": _set_volume,
    "set_mute": _set_mute,
    "take_screenshot": _screenshot,
    "focus_window": _focus_window,
    "lock_screen": _lock,
}


def response_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Make a tool result JSON-safe for the Live function response."""
    try:
        json.dumps(result)
        return result
    except (TypeError, ValueError):
        return {"success": bool(result.get("success")), "message": str(result.get("message", ""))}
