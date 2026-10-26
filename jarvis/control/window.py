"""Window enumeration and manipulation (focus, move, resize, minimize)."""

from __future__ import annotations

import ctypes
import logging
from typing import Any

logger = logging.getLogger("jarvis.control.window")

try:  # pragma: no cover - platform specific
    import win32con
    import win32gui

    _WIN32 = True
except ImportError:  # pragma: no cover
    win32gui = win32con = None
    _WIN32 = False

SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
SW_SHOW = 5


def is_available() -> bool:
    return _WIN32


def _enum_windows() -> list[dict[str, Any]]:
    if not _WIN32:
        return []
    windows: list[dict[str, Any]] = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            _, pid = win32process_get_window_thread_process_id(hwnd)
        except Exception:
            pid = None
        windows.append(
            {
                "hwnd": hwnd,
                "title": title,
                "class": win32gui.GetClassName(hwnd),
                "pid": pid,
            }
        )

    win32gui.EnumWindows(callback, None)
    return windows


def win32process_get_window_thread_process_id(hwnd):
    import win32process

    return win32process.GetWindowThreadProcessId(hwnd)


def list_windows(minimized: bool | None = None) -> list[dict[str, Any]]:
    """Visible top-level windows with title, class and pid."""
    results = []
    for entry in _enum_windows():
        if minimized is None:
            results.append(entry)
            continue
        try:
            placement = win32gui.GetWindowPlacement(entry["hwnd"])
            is_min = placement[1] == SW_MINIMIZE
        except Exception:
            is_min = False
        if is_min == bool(minimized):
            results.append(entry)
    return results


def _find_window(title: str) -> int | None:
    title_l = title.lower().strip()
    exact, partial = None, None
    for entry in _enum_windows():
        win_title = entry["title"].lower()
        if win_title == title_l:
            exact = entry["hwnd"]
            break
        if title_l in win_title and partial is None:
            partial = entry["hwnd"]
    return exact or partial


def focus_window(title: str) -> dict[str, Any]:
    """Bring a window to the foreground."""
    if not _WIN32:
        return {"success": False, "error": "Window control requires Windows"}
    hwnd = _find_window(title)
    if hwnd is None:
        return {"success": False, "error": f"No visible window matching {title!r}"}
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == SW_MINIMIZE:
            win32gui.ShowWindow(hwnd, SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return {"success": True, "title": win32gui.GetWindowText(hwnd), "hwnd": hwnd}
    except Exception as exc:
        # Foreground-lock can raise; try the attach trick as a fallback
        try:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return {"success": True, "title": title, "hwnd": hwnd, "note": "fallback"}
        except Exception:
            return {"success": False, "error": str(exc)}


def minimize_window(title: str) -> dict[str, Any]:
    return _show(title, SW_MINIMIZE)


def maximize_window(title: str) -> dict[str, Any]:
    return _show(title, SW_MAXIMIZE)


def restore_window(title: str) -> dict[str, Any]:
    return _show(title, SW_RESTORE)


def _show(title: str, cmd: int) -> dict[str, Any]:
    if not _WIN32:
        return {"success": False, "error": "Window control requires Windows"}
    hwnd = _find_window(title)
    if hwnd is None:
        return {"success": False, "error": f"No visible window matching {title!r}"}
    try:
        win32gui.ShowWindow(hwnd, cmd)
        return {"success": True, "title": win32gui.GetWindowText(hwnd), "hwnd": hwnd}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def close_window(title: str) -> dict[str, Any]:
    if not _WIN32:
        return {"success": False, "error": "Window control requires Windows"}
    hwnd = _find_window(title)
    if hwnd is None:
        return {"success": False, "error": f"No visible window matching {title!r}"}
    try:
        win_title = win32gui.GetWindowText(hwnd)
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return {"success": True, "title": win_title}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def move_window(title: str, x: int, y: int, width: int | None = None, height: int | None = None) -> dict[str, Any]:
    if not _WIN32:
        return {"success": False, "error": "Window control requires Windows"}
    hwnd = _find_window(title)
    if hwnd is None:
        return {"success": False, "error": f"No visible window matching {title!r}"}
    try:
        if width is None or height is None:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = width or (right - left)
            height = height or (bottom - top)
        win32gui.MoveWindow(hwnd, int(x), int(y), int(width), int(height), True)
        return {"success": True, "hwnd": hwnd, "rect": [x, y, width, height]}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_active_window() -> dict[str, Any]:
    if not _WIN32:
        return {"success": False, "error": "Window control requires Windows"}
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process_get_window_thread_process_id(hwnd)
        return {
            "success": True,
            "title": win32gui.GetWindowText(hwnd),
            "class": win32gui.GetClassName(hwnd),
            "hwnd": hwnd,
            "pid": pid,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
