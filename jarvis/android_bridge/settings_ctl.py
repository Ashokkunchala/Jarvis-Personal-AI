"""Android system settings (secure/system/global) get/put helpers."""

from __future__ import annotations

from typing import Any

from jarvis.android_bridge import adb

NAMESPACES = ("system", "secure", "global")


def get(namespace: str, key: str, serial: str | None = None) -> dict[str, Any]:
    if namespace not in NAMESPACES:
        return {"success": False, "error": f"namespace must be one of {NAMESPACES}"}
    res = adb.shell(["settings", "get", namespace, key], device=serial, timeout=15)
    if not res["success"]:
        return res
    raw = res["stdout"].strip()
    if raw == "null":
        return {"success": True, "namespace": namespace, "key": key, "value": None}
    return {"success": True, "namespace": namespace, "key": key, "value": raw}


def put(namespace: str, key: str, value: str, serial: str | None = None) -> dict[str, Any]:
    if namespace not in NAMESPACES:
        return {"success": False, "error": f"namespace must be one of {NAMESPACES}"}
    res = adb.shell(["settings", "put", namespace, key, str(value)], device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "namespace": namespace, "key": key, "value": str(value)}
    return res


def delete(namespace: str, key: str, serial: str | None = None) -> dict[str, Any]:
    if namespace not in NAMESPACES:
        return {"success": False, "error": f"namespace must be one of {NAMESPACES}"}
    res = adb.shell(["settings", "delete", namespace, key], device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "namespace": namespace, "key": key, "deleted": True}
    return res


def list_namespace(namespace: str, limit: int = 100, serial: str | None = None) -> dict[str, Any]:
    if namespace not in NAMESPACES:
        return {"success": False, "error": f"namespace must be one of {NAMESPACES}"}
    res = adb.shell(["settings", "list", namespace], device=serial, timeout=30)
    if not res["success"]:
        return res
    entries = {}
    for line in res["stdout"].splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            entries[key.strip()] = value.strip()
            if len(entries) >= limit:
                break
    return {"success": True, "namespace": namespace, "entries": entries, "count": len(entries)}


def screen_timeout_ms(serial: str | None = None) -> dict[str, Any]:
    return get("system", "screen_off_timeout", serial)


def set_screen_timeout_ms(ms: int, serial: str | None = None) -> dict[str, Any]:
    ms = max(15000, min(int(ms), 1800000))
    return put("system", "screen_off_timeout", str(ms), serial)


def font_scale(serial: str | None = None) -> dict[str, Any]:
    return get("system", "font_scale", serial)


def set_font_scale(scale: float, serial: str | None = None) -> dict[str, Any]:
    scale = max(0.5, min(float(scale), 2.5))
    return put("system", "font_scale", str(scale), serial)


def animation_scale(which: str = "transition", scale: float = 1.0, serial: str | None = None) -> dict[str, Any]:
    key = f"animation_scale_{which}"
    if which not in {"window", "transition", "animator"}:
        return {"success": False, "error": "which must be window, transition or animator"}
    scale = max(0.0, min(float(scale), 10.0))
    return put("global", key, str(scale), serial)
