"""Android input injection: tap, swipe, type, key events, gestures."""

from __future__ import annotations

from typing import Any

from jarvis.android_bridge import adb

KEY_ALIASES = {
    "home": "KEYCODE_HOME",
    "back": "KEYCODE_BACK",
    "recents": "KEYCODE_APP_SWITCH",
    "recent": "KEYCODE_APP_SWITCH",
    "app_switch": "KEYCODE_APP_SWITCH",
    "enter": "KEYCODE_ENTER",
    "return": "KEYCODE_ENTER",
    "tab": "KEYCODE_TAB",
    "space": "KEYCODE_SPACE",
    "escape": "KEYCODE_ESCAPE",
    "del": "KEYCODE_DEL",
    "delete": "KEYCODE_FORWARD_DEL",
    "backspace": "KEYCODE_DEL",
    "up": "KEYCODE_DPAD_UP",
    "down": "KEYCODE_DPAD_DOWN",
    "left": "KEYCODE_DPAD_LEFT",
    "right": "KEYCODE_DPAD_RIGHT",
    "center": "KEYCODE_DPAD_CENTER",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    "volume_mute": "KEYCODE_VOLUME_MUTE",
    "power": "KEYCODE_POWER",
    "camera": "KEYCODE_CAMERA",
    "search": "KEYCODE_SEARCH",
    "menu": "KEYCODE_MENU",
    "page_up": "KEYCODE_PAGE_UP",
    "page_down": "KEYCODE_PAGE_DOWN",
    "play_pause": "KEYCODE_MEDIA_PLAY_PAUSE",
    "play": "KEYCODE_MEDIA_PLAY",
    "pause": "KEYCODE_MEDIA_PAUSE",
    "next": "KEYCODE_MEDIA_NEXT",
    "previous": "KEYCODE_MEDIA_PREVIOUS",
    "stop": "KEYCODE_MEDIA_STOP",
    "bright_up": "KEYCODE_BRIGHTNESS_UP",
    "bright_down": "KEYCODE_BRIGHTNESS_DOWN",
    "a": "KEYCODE_A", "b": "KEYCODE_B", "c": "KEYCODE_C", "d": "KEYCODE_D",
    "e": "KEYCODE_E", "f": "KEYCODE_F", "g": "KEYCODE_G", "h": "KEYCODE_H",
    "i": "KEYCODE_I", "j": "KEYCODE_J", "k": "KEYCODE_K", "l": "KEYCODE_L",
    "m": "KEYCODE_M", "n": "KEYCODE_N", "o": "KEYCODE_O", "p": "KEYCODE_P",
    "q": "KEYCODE_Q", "r": "KEYCODE_R", "s": "KEYCODE_S", "t": "KEYCODE_T",
    "u": "KEYCODE_U", "v": "KEYCODE_V", "w": "KEYCODE_W", "x": "KEYCODE_X",
    "y": "KEYCODE_Y", "z": "KEYCODE_Z",
    "0": "KEYCODE_0", "1": "KEYCODE_1", "2": "KEYCODE_2", "3": "KEYCODE_3",
    "4": "KEYCODE_4", "5": "KEYCODE_5", "6": "KEYCODE_6", "7": "KEYCODE_7",
    "8": "KEYCODE_8", "9": "KEYCODE_9",
}


def resolve_key(key: str) -> str:
    key = key.strip()
    if key.upper().startswith("KEYCODE_"):
        return key.upper()
    return KEY_ALIASES.get(key.lower(), f"KEYCODE_{key.upper()}")


def tap(x: int, y: int, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["input", "tap", str(int(x)), str(int(y))], device=serial, timeout=15)
    return {**res, "action": "tap", "x": int(x), "y": int(y)} if res["success"] else res


def double_tap(x: int, y: int, serial: str | None = None) -> dict[str, Any]:
    first = tap(x, y, serial)
    if not first["success"]:
        return first
    import time

    time.sleep(0.12)
    second = tap(x, y, serial)
    return {"success": second["success"], "action": "double_tap", "x": int(x), "y": int(y)}


def long_press(x: int, y: int, duration_ms: int = 800, serial: str | None = None) -> dict[str, Any]:
    duration_ms = max(100, min(int(duration_ms), 5000))
    res = adb.shell(
        ["input", "swipe", str(int(x)), str(int(y)), str(int(x)), str(int(y)), str(duration_ms)],
        device=serial,
        timeout=15,
    )
    return {**res, "action": "long_press", "x": int(x), "y": int(y), "duration_ms": duration_ms} if res["success"] else res


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300, serial: str | None = None) -> dict[str, Any]:
    duration_ms = max(50, min(int(duration_ms), 5000))
    res = adb.shell(
        ["input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(duration_ms)],
        device=serial,
        timeout=15,
    )
    return {**res, "action": "swipe"} if res["success"] else res


def swipe_direction(direction: str, distance: int = 400, duration_ms: int = 300, serial: str | None = None) -> dict[str, Any]:
    screen = adb.shell(["wm", "size"], device=serial, timeout=10)
    width, height = 720, 1280
    if screen["success"] and "x" in screen["stdout"]:
        try:
            size = screen["stdout"].split("x")
            width = int("".join(ch for ch in size[-1] if ch.isdigit()))
            height = int("".join(ch for ch in screen["stdout"].split("x")[0].split()[-1] if ch.isdigit()))
        except (ValueError, IndexError):
            pass
    cx, cy = width // 2, height // 2
    distance = max(50, min(int(distance), min(width, height)))
    moves = {
        "up": (cx, cy + distance // 2, cx, cy - distance // 2),
        "down": (cx, cy - distance // 2, cx, cy + distance // 2),
        "left": (cx + distance // 2, cy, cx - distance // 2, cy),
        "right": (cx - distance // 2, cy, cx + distance // 2, cy),
    }
    if direction.lower() not in moves:
        return {"success": False, "error": "direction must be up, down, left or right"}
    x1, y1, x2, y2 = moves[direction.lower()]
    return swipe(x1, y1, x2, y2, duration_ms, serial)


def type_text(text: str, serial: str | None = None) -> dict[str, Any]:
    # `input text` cannot send newlines or some special chars directly.
    escaped = (
        text.replace("\\", "\\\\")
        .replace(" ", "%s")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("&", "\\&")
        .replace("|", "\\|")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace(";", "\\;")
        .replace(":", "\\:")
        .replace("*", "\\*")
        .replace("?", "\\?")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("%", "%%")
        .replace("#", "\\#")
    )
    lines = text.split("\n")
    if len(lines) > 1:
        results = []
        for i, line in enumerate(lines):
            res = type_text(line, serial)
            if not res["success"]:
                return res
            results.append(res)
            if i < len(lines) - 1:
                press_key("enter", serial)
        return {"success": True, "action": "type", "chars": len(text), "lines": len(lines)}
    res = adb.shell(["input", "text", escaped], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "action": "type", "chars": len(text)}
    return res


def press_key(key: str, serial: str | None = None) -> dict[str, Any]:
    code = resolve_key(key)
    res = adb.shell(["input", "keyevent", code], device=serial, timeout=15)
    return {**res, "action": "key", "key": code} if res["success"] else res


def press_keys(keys: list[str], serial: str | None = None) -> dict[str, Any]:
    results = []
    for key in keys:
        res = press_key(key, serial)
        results.append(res)
        if not res["success"]:
            return res
    return {"success": True, "action": "key_sequence", "keys": [r.get("key") for r in results]}


def combo(*keys: str, serial: str | None = None) -> dict[str, Any]:
    """Android key combinations, e.g. combo('meta', 'a') for Meta+A."""
    codes = [resolve_key(k) for k in keys]
    if len(codes) < 2:
        return {"success": False, "error": "combo requires at least 2 keys"}
    res = adb.shell(["input", "keycombination", *codes], device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "action": "key_combination", "keys": codes}
    return res


def clipboard_set(text: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["am", "broadcast", "-a", "clipper.set", "--es", "text", text], device=serial, timeout=15)
    if res["success"] and "error" not in res.get("stdout", "").lower():
        return {"success": True, "action": "clipboard_set", "length": len(text)}
    res2 = adb.shell(["input", "text", text.replace(" ", "%s")], device=serial, timeout=15)
    if res2["success"]:
        return {"success": True, "action": "typed_instead", "note": "clipper not installed; typed into focused field"}
    return res


def back(serial: str | None = None) -> dict[str, Any]:
    return press_key("back", serial)


def home(serial: str | None = None) -> dict[str, Any]:
    return press_key("home", serial)


def recents(serial: str | None = None) -> dict[str, Any]:
    return press_key("recents", serial)


def notifications_panel(serial: str | None = None) -> dict[str, Any]:
    screen = adb.shell(["wm", "size"], device=serial, timeout=10)
    width = 1080
    if screen["success"] and "x" in screen["stdout"]:
        try:
            width = int("".join(ch for ch in screen["stdout"].split("x")[-1] if ch.isdigit()))
        except ValueError:
            pass
    return swipe(width // 2, 0, width // 2, 1400, 350, serial)


def quick_settings(serial: str | None = None) -> dict[str, Any]:
    screen = adb.shell(["wm", "size"], device=serial, timeout=10)
    width = 1080
    if screen["success"] and "x" in screen["stdout"]:
        try:
            width = int("".join(ch for ch in screen["stdout"].split("x")[-1] if ch.isdigit()))
        except ValueError:
            pass
    return swipe(width // 2, 0, width // 2, 1400, 350, serial)


def split_screen(package: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(
        ["am", "start", "--windowingMode", "3", "-n", f"{package}/.MainActivity"],
        device=serial,
        timeout=20,
    )
    if res["success"]:
        return {"success": True, "package": package, "windowing_mode": 3}
    return res


def picture_in_picture(package: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["am", "enter-pip", package], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "package": package, "mode": "pip"}
    return res
