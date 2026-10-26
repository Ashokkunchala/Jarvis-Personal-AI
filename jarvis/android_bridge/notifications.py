"""Read and act on Android notifications."""

from __future__ import annotations

import re
from typing import Any

from jarvis.android_bridge import adb

_LISTENER_PKGS = [
    "com.android.shell",
]


def notification_listeners(serial: str | None = None) -> list[str]:
    res = adb.shell(["settings", "get", "secure", "enabled_notification_listeners"], device=serial, timeout=15)
    if not res["success"]:
        return []
    raw = res["stdout"].strip()
    if raw in {"", "null"}:
        return []
    return [p.split("/")[0] for p in raw.split(":") if p]


def recent_notifications(serial: str | None = None) -> dict[str, Any]:
    """Best-effort dump of currently posted notifications via dumpsys."""
    res = adb.shell(["dumpsys", "notification"], device=serial, timeout=30)
    if not res["success"]:
        return res
    text = res["stdout"]
    notifications: list[dict[str, Any]] = []
    # NotificationRecord blocks look like: NotificationRecord(0x... : pkg=com.x user=0 id=... tag=...)
    blocks = re.split(r"(?=NotificationRecord\()", text)
    for block in blocks[1:]:
        entry: dict[str, Any] = {}
        m = re.search(r"pkg=([\w.]+)", block)
        if m:
            entry["package"] = m.group(1)
        m = re.search(r"id=(\d+)", block)
        if m:
            entry["id"] = int(m.group(1))
        m = re.search(r"android.title(?:=|\s+)([^\r\n]+)", block)
        if m:
            entry["title"] = m.group(1).strip()
        m = re.search(r"android.text(?:=|\s+)([^\r\n]+)", block)
        if m:
            entry["text"] = m.group(1).strip()
        m = re.search(r"when=(\d+)", block)
        if m:
            entry["when"] = int(m.group(1))
        if entry.get("package"):
            notifications.append(entry)
    listeners = notification_listeners(serial)
    return {
        "success": True,
        "notifications": notifications[:50],
        "count": len(notifications),
        "listeners": listeners,
        "note": "For full notification access, grant a listener via Settings → Notification access.",
    }


def clear_all_notifications(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["service", "call", "statusbar", "1"], device=serial, timeout=15)
    if res["success"]:
        adb.shell(["cmd", "statusbar", "collapse"], device=serial, timeout=15)
        return {"success": True, "action": "panel_collapsed"}
    return res


def open_notification_settings(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(
        ["am", "start", "-a", "android.settings.APP_NOTIFICATION_SETTINGS"],
        device=serial,
        timeout=20,
    )
    if res["success"]:
        return {"success": True, "action": "opened_notification_settings"}
    return res


def set_app_notifications(package: str, enabled: bool, serial: str | None = None) -> dict[str, Any]:
    value = "1" if enabled else "0"
    res = adb.shell(["cmd", "notification", "allow_listener" if enabled else "disallow_listener", package], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "package": package, "notifications": bool(enabled)}
    res2 = adb.shell(["settings", "put", "secure", f"enabled_notification_listeners_{package}", value], device=serial, timeout=15)
    return res2 if not res2["success"] else {"success": True, "package": package, "notifications": bool(enabled)}
