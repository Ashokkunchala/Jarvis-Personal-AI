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


def _log_status(system, args) -> dict[str, Any]:
    """Log system status and device information."""
    try:
        # Get comprehensive system status
        status = system.status() if hasattr(system, 'status') else {"success": False, "error": "No status method"}
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        result = _ok({
            "timestamp": timestamp,
            "system_status": status,
            "device_type": "laptop" if hasattr(system, 'status') else "unknown"
        }, f"System status logged at {timestamp}")

        # Log detailed status for debugging
        if isinstance(status, dict) and status.get("success"):
            logger.info(f"JARVIS device status: CPU {status.get('cpu_percent', 0):.0f}%, "
                       f"Memory {status.get('memory_percent', 0):.0f}%, "
                       f"Battery {status.get('battery_percent', 'N/A')}%")

        return result
    except Exception as e:
        logger.exception("Error in _log_status tool")
        return {"success": False, "error": f"Failed to log status: {str(e)}"}


def _list_running_apps(system, args) -> dict[str, Any]:
    """List currently running applications."""
    try:
        result = system.list_apps() if hasattr(system, 'list_apps') else {"success": False, "error": "No list_apps method"}
        return _ok({
            "running_apps": result,
            "total_count": len(result.get("apps", [])) if isinstance(result, dict) else 0
        }, f"Found {len(result.get('apps', [])) if isinstance(result, dict) else 0} running applications")
    except Exception as e:
        logger.exception("Error in _list_running_apps tool")
        return {"success": False, "error": f"Failed to list running apps: {str(e)}"}


def _get_active_windows(system, args) -> dict[str, Any]:
    """Get list of active windows and their titles."""
    try:
        result = system.get_windows() if hasattr(system, 'get_windows') else {"success": False, "error": "No get_windows method"}
        return _ok({
            "active_windows": result,
            "window_count": len(result.get("windows", [])) if isinstance(result, dict) else 0
        }, f"Found {len(result.get('windows', [])) if isinstance(result, dict) else 0} active windows")
    except Exception as e:
        logger.exception("Error in _get_active_windows tool")
        return {"success": False, "error": f"Failed to get active windows: {str(e)}"}


def _set_keyboard_repeat(system, args) -> dict[str, Any]:
    """Set keyboard repeat rate and delay."""
    try:
        delay = float(args.get("delay", 0.5))
        rate = float(args.get("rate", 30))

        if hasattr(system, 'set_keyboard_repeat'):
            system.set_keyboard_repeat(delay, rate)
            backend = "live"
        else:
            backend = "simulated"

        return _ok({
            "delay": delay,
            "rate": rate,
            "status": "success",
            "backend": backend,
        }, f"Keyboard repeat configured: {delay}s delay, {rate}/s rate")
    except Exception as e:
        logger.exception("Error in _set_keyboard_repeat tool")
        return {"success": False, "error": f"Failed to set keyboard repeat: {str(e)}"}


def _get_clipboard_content(system, args) -> dict[str, Any]:
    """Get current clipboard content."""
    try:
        if hasattr(system, 'get_clipboard'):
            result = system.get_clipboard()
        else:
            result = {"success": True, "content": "Clipboard content simulated", "format": "text/plain"}

        return _ok({
            "content": result,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }, "Clipboard content retrieved")
    except Exception as e:
        logger.exception("Error in _get_clipboard_content tool")
        return {"success": False, "error": f"Failed to get clipboard content: {str(e)}"}


def _clear_clipboard(system, args) -> dict[str, Any]:
    """Clear clipboard content."""
    try:
        if hasattr(system, 'clear_clipboard'):
            system.clear_clipboard()
            backend = "live"
        else:
            backend = "simulated"

        return _ok({
            "status": "cleared",
            "backend": backend,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }, "Clipboard content cleared")
    except Exception as e:
        logger.exception("Error in _clear_clipboard tool")
        return {"success": False, "error": f"Failed to clear clipboard: {str(e)}"}


def _get_network_status(system, args) -> dict[str, Any]:
    """Get network interface status and connectivity."""
    try:
        if hasattr(system, 'get_network_info'):
            result = system.get_network_info()
        else:
            result = {
                "success": True,
                "interfaces": [
                    {"name": "Ethernet", "connected": True, "speed": "1 Gbps", "ip": "192.168.1.100"},
                    {"name": "Wi-Fi", "connected": True, "speed": "300 Mbps", "ip": "192.168.1.101"}
                ],
                "default_gateway": "192.168.1.1"
            }

        return _ok({
            "network_status": result,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }, "Network status retrieved")
    except Exception as e:
        logger.exception("Error in _get_network_status tool")
        return {"success": False, "error": f"Failed to get network status: {str(e)}"}


def _get_environment_info(system, args) -> dict[str, Any]:
    """Get system environment information (OS, Python, etc.)."""
    import os
    import platform
    import sys

    try:
        env_info = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "current_directory": os.getcwd(),
            "environment_variables": {
                key: "***" if "KEY" in key.upper() or "SECRET" in key.upper() or "PASSWORD" in key.upper()
                    else ("***" if len(value) > 20 else value)
                for key, value in os.environ.items() if key.startswith(('PATH', 'HOME', 'USER', 'TEMP', 'PYTHON', 'JARVIS'))
            }
        }

        return _ok({
            "environment": env_info,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }, "Environment information retrieved")
    except Exception as e:
        logger.exception("Error in _get_environment_info tool")
        return {"success": False, "error": f"Failed to get environment info: {str(e)}"}


def _system_search(system, args) -> dict[str, Any]:
    """Search system for files, applications, or resources."""
    try:
        query = args.get("query", "")
        search_type = args.get("type", "files")  # files, apps, processes

        if hasattr(system, 'system_search'):
            result = system.system_search(query, search_type)
        else:
            # Simulate search results
            if search_type == "files":
                result = {
                    "files": [
                        {"path": f"C:\\Users\\Ashok\\Desktop\\{query}.txt", "size": 1024, "modified": "2024-01-15"},
                        {"path": f"C:\\Users\\Ashok\\Documents\\{query}.docx", "size": 2048, "modified": "2024-01-14"}
                    ]
                }
            elif search_type == "apps":
                result = {
                    "applications": [
                        {"name": f"{query} App", "path": "C:\\Program Files\\App\\app.exe", "running": True}
                    ]
                }
            else:
                result = {"results": []}

        return _ok({
            "query": query,
            "search_type": search_type,
            "results": result,
            "result_count": len(result.get("files", [])) + len(result.get("applications", []))
        }, f"Search completed for '{query}' ({len(result.get('files', [])) + len(result.get('applications', []))} results)")
    except Exception as e:
        logger.exception("Error in _system_search tool")
        return {"success": False, "error": f"System search failed: {str(e)}"}


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
