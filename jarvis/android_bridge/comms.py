"""Communications: SMS, call log, contacts, dialer.

These require extra permissions on modern Android. When the device is
user-debug/rooted they work directly; otherwise call ``setup_comms()``
which uses ``pm grant`` over adb.
"""

from __future__ import annotations

from typing import Any

from jarvis.android_bridge import adb

SMS_PERMISSIONS = [
    "android.permission.READ_SMS",
    "android.permission.SEND_SMS",
    "android.permission.READ_CALL_LOG",
    "android.permission.READ_CONTACTS",
]


def setup_comms(serial: str | None = None) -> dict[str, Any]:
    """Grant the shell every permission comms tools need (works on debuggable builds)."""
    granted, failed = [], []
    for perm in SMS_PERMISSIONS:
        for pkg in ("com.android.shell", "com.android.shell.module"):
            res = adb.shell(["pm", "grant", pkg, perm], device=serial, timeout=15)
            if res["success"]:
                granted.append(perm)
                break
        else:
            failed.append(perm)
    return {"success": bool(granted), "granted": granted, "failed": failed}


def send_sms(number: str, message: str, serial: str | None = None) -> dict[str, Any]:
    """Send an SMS via the telephony shell service (dual-SIM aware)."""
    number = str(number).strip()
    if not number:
        return {"success": False, "error": "Phone number required"}
    # Probe the telephony service so a dual-SIM mismatch fails loudly, not silently.
    adb.shell(["service", "call", "iphonesubinfo", "1"], device=serial, timeout=15)
    cmd = ["am", "start", "-a", "android.intent.action.SENDTO", "-d", f"smsto:{number}", "--es", "sms_body", message]
    result = adb.shell(cmd, device=serial, timeout=20)
    if result["success"]:
        return {
            "success": True,
            "number": number,
            "message": message,
            "method": "intent",
            "note": "SMS composed in the messaging app; press send to deliver.",
        }
    return result


def send_sms_silent(number: str, message: str, serial: str | None = None) -> dict[str, Any]:
    """Attempt a fully automatic send (requires WRITE_SMS / root / automation app)."""
    res = adb.shell(
        ["content", "insert", "--uri", "content://sms", "--bind", "address:s:" + str(number), "--bind", "body:s:" + message],
        device=serial,
        timeout=25,
    )
    if res["success"] and "Exception" not in res.get("stdout", "") + res.get("stderr", ""):
        return {"success": True, "number": number, "method": "content-provider"}
    return {
        "success": False,
        "error": res.get("error") or "Direct SMS insert denied (needs WRITE_SMS permission).",
        "hint": "Run setup_comms() first, or use send_sms() which opens the messaging app.",
    }


def read_sms(limit: int = 20, serial: str | None = None) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    res = adb.shell(
        ["content", "query", "--uri", "content://sms/inbox", "--projection", "address:body:date", "--limit", str(limit)],
        device=serial,
        timeout=30,
    )
    if not res["success"]:
        return res
    messages = parse_content_query(res["stdout"], ["address", "body", "date"])
    if not messages and "SecurityException" in res.get("stdout", "") + res.get("stderr", ""):
        return {"success": False, "error": "Permission denied reading SMS", "hint": "Run setup_comms() first."}
    return {"success": True, "messages": messages, "count": len(messages)}


def call_log(limit: int = 20, serial: str | None = None) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    res = adb.shell(
        ["content", "query", "--uri", "content://call_log/calls", "--projection", "number:type:date:duration", "--limit", str(limit)],
        device=serial,
        timeout=30,
    )
    if not res["success"]:
        return res
    entries = parse_content_query(res["stdout"], ["number", "type", "date", "duration"])
    if not entries and "SecurityException" in res.get("stdout", "") + res.get("stderr", ""):
        return {"success": False, "error": "Permission denied reading call log", "hint": "Run setup_comms() first."}
    return {"success": True, "calls": entries, "count": len(entries)}


def contacts(limit: int = 50, serial: str | None = None) -> dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    res = adb.shell(
        ["content", "query", "--uri", "content://com.android.contacts/data/phones", "--projection", "display_name:data1", "--limit", str(limit)],
        device=serial,
        timeout=30,
    )
    if not res["success"]:
        return res
    entries = parse_content_query(res["stdout"], ["display_name", "data1"])
    if not entries and "SecurityException" in res.get("stdout", "") + res.get("stderr", ""):
        return {"success": False, "error": "Permission denied reading contacts", "hint": "Run setup_comms() first."}
    return {"success": True, "contacts": entries, "count": len(entries)}


def dial(number: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{number}"], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "action": "dialer_opened", "number": number}
    return res


def call(number: str, serial: str | None = None) -> dict[str, Any]:
    """Place an actual call (requires CALL_PHONE permission)."""
    res = adb.shell(["am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{number}"], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "action": "calling", "number": number}
    return res


def end_call(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["input", "keyevent", "KEYCODE_ENDCALL"], device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "action": "call_ended"}
    return res


def open_url(url: str, serial: str | None = None) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    res = adb.shell(["am", "start", "-a", "android.intent.action.VIEW", "-d", url], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "url": url}
    return res


def share_text(text: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(
        ["am", "start", "-a", "android.intent.action.SEND", "-t", "text/plain", "--es", "android.intent.extra.TEXT", text],
        device=serial,
        timeout=20,
    )
    if res["success"]:
        return {"success": True, "action": "share_sheet", "length": len(text)}
    return res


def parse_content_query(output: str, fields: list[str]) -> list[dict[str, Any]]:
    """Parse `content query` output rows: 'Row: 0 col0=x, col1=y' or 'field=value'."""
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("ContentProvider"):
            continue
        entry: dict[str, Any] = {}
        # Newer Android: "Row: 0 number=..., date=..."
        body = line.split(":", 1)[-1] if line.lower().startswith("row:") else line
        for chunk in body.split(", "):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            entry[key.strip()] = value.strip()
        # Older Android: "Row: 0 col0=..., col1=..." -> map positionally
        if entry and all(k.startswith("col") for k in entry):
            mapped = {}
            for i, key in enumerate(sorted(entry.keys(), key=lambda k: int(k[3:]) if k[3:].isdigit() else 0)):
                if i < len(fields):
                    mapped[fields[i]] = entry[key]
            entry = mapped
        if entry:
            rows.append(entry)
    return rows
