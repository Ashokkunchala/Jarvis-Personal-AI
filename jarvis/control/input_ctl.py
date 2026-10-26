"""Keyboard and mouse automation with safety interlocks."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("jarvis.control.input")

try:  # pragma: no cover - optional
    import pyautogui

    pyautogui.FAILSAFE = True  # slam mouse into a corner to abort
    pyautogui.PAUSE = 0.05
    _HAS_PYAUTOGUI = True
except Exception:  # pragma: no cover
    pyautogui = None
    _HAS_PYAUTOGUI = False

try:  # pragma: no cover - optional
    import keyboard as _keyboard

    _HAS_KEYBOARD = True
except Exception:  # pragma: no cover
    _keyboard = None
    _HAS_KEYBOARD = False

# Screen corner abort position (pyautogui failsafe)
FAILSAFE_CORNER = (0, 0)


def is_available() -> bool:
    return _HAS_PYAUTOGUI or _HAS_KEYBOARD


def type_text(text: str, interval: float = 0.02) -> dict[str, Any]:
    """Type text as if from a keyboard (uses the focused window)."""
    if _HAS_PYAUTOGUI:
        try:
            pyautogui.typewrite(text, interval=max(0.0, float(interval)))
            return {"success": True, "typed_chars": len(text)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
    if _HAS_KEYBOARD:
        try:
            _keyboard.write(text, delay=0.02)
            return {"success": True, "typed_chars": len(text)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
    return {"success": False, "error": "No input automation library available"}


def press_keys(keys: list[str], interval: float = 0.05) -> dict[str, Any]:
    """Press a sequence of keys, e.g. ['ctrl', 'c'] presses Ctrl+C."""
    if not keys:
        return {"success": False, "error": "No keys supplied"}
    if _HAS_PYAUTOGUI:
        try:
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)
            return {"success": True, "keys": keys}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
    if _HAS_KEYBOARD:
        try:
            if len(keys) == 1:
                _keyboard.press_and_release(keys[0])
            else:
                _keyboard.press_and_release("+".join(keys))
            return {"success": True, "keys": keys}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
    return {"success": False, "error": "No input automation library available"}


def hotkey(*keys: str) -> dict[str, Any]:
    return press_keys(list(keys))


def click(x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1) -> dict[str, Any]:
    if not _HAS_PYAUTOGUI:
        return {"success": False, "error": "pyautogui unavailable"}
    try:
        if x is None or y is None:
            pyautogui.click(button=button, clicks=clicks)
            pos = pyautogui.position()
        else:
            pyautogui.click(int(x), int(y), button=button, clicks=clicks)
            pos = (int(x), int(y))
        return {"success": True, "x": pos[0], "y": pos[1], "button": button}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def double_click(x: int, y: int) -> dict[str, Any]:
    return click(x, y, clicks=2)


def right_click(x: int, y: int) -> dict[str, Any]:
    return click(x, y, button="right")


def move_mouse(x: int, y: int, duration: float = 0.2) -> dict[str, Any]:
    if not _HAS_PYAUTOGUI:
        return {"success": False, "error": "pyautogui unavailable"}
    try:
        pyautogui.moveTo(int(x), int(y), duration=max(0.0, float(duration)))
        return {"success": True, "x": int(x), "y": int(y)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def scroll(direction: str = "down", amount: int = 3) -> dict[str, Any]:
    if not _HAS_PYAUTOGUI:
        return {"success": False, "error": "pyautogui unavailable"}
    try:
        amount = max(-20, min(20, int(amount)))
        delta = -amount if direction.lower() == "down" else amount
        pyautogui.scroll(delta)
        return {"success": True, "direction": direction, "amount": amount}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.3) -> dict[str, Any]:
    if not _HAS_PYAUTOGUI:
        return {"success": False, "error": "pyautogui unavailable"}
    try:
        pyautogui.moveTo(int(x1), int(y1))
        pyautogui.dragTo(int(x2), int(y2), duration=max(0.0, float(duration)))
        return {"success": True, "from": [x1, y1], "to": [x2, y2]}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def mouse_position() -> dict[str, Any]:
    if not _HAS_PYAUTOGUI:
        return {"success": False, "error": "pyautogui unavailable"}
    pos = pyautogui.position()
    return {"success": True, "x": pos[0], "y": pos[1]}


def press_media(key: str) -> dict[str, Any]:
    """Media keys: play_pause, next, prev, volume_up, volume_down, volume_mute."""
    valid = {"play_pause", "nexttrack", "prevtrack", "volumeup", "volumedown", "volumemute"}
    key_norm = key.lower().replace(" ", "_")
    alias = {
        "play_pause": "playpause",
        "play": "playpause",
        "pause": "playpause",
        "next": "nexttrack",
        "previous": "prevtrack",
        "prev": "prevtrack",
        "volume_up": "volumeup",
        "volume_down": "volumedown",
        "mute": "volumemute",
    }
    resolved = alias.get(key_norm, key_norm)
    if resolved not in valid and resolved not in {"playpause", "nexttrack", "prevtrack"}:
        return {"success": False, "error": f"Unknown media key {key!r}", "supported": sorted(valid)}
    if _HAS_KEYBOARD:
        try:
            _keyboard.press_and_release(resolved)
            return {"success": True, "key": resolved}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
    if _HAS_PYAUTOGUI:
        try:
            pyautogui.press(resolved)
            return {"success": True, "key": resolved}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
    return {"success": False, "error": "No input automation library available"}
