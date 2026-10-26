"""Device-level state: battery, brightness, connectivity, ringer, DND, screen."""

from __future__ import annotations

import re
from typing import Any

from jarvis.android_bridge import adb


def _parse_dumpsys_battery(stdout: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if key in {"level", "scale", "temperature", "voltage", "status", "health", "plugged"}:
            try:
                info[key] = int(value)
            except ValueError:
                info[key] = value
    return info


_STATUS_MAP = {1: "unknown", 2: "charging", 3: "discharging", 4: "not_charging", 5: "full"}
_HEALTH_MAP = {1: "unknown", 2: "good", 3: "overheat", 4: "dead", 5: "over_voltage", 6: "failure", 7: "cold"}


def battery(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell("dumpsys battery", device=serial, timeout=20)
    if not res["success"]:
        return res
    raw = _parse_dumpsys_battery(res["stdout"])
    level = raw.get("level")
    scale = raw.get("scale") or 100
    percent = round(level * 100 / scale) if level is not None else None
    temperature = raw.get("temperature")
    return {
        "success": True,
        "percent": percent,
        "status": _STATUS_MAP.get(raw.get("status"), raw.get("status")),
        "health": _HEALTH_MAP.get(raw.get("health"), raw.get("health")),
        "plugged": {2: "ac", 4: "usb", 8: "wireless"}.get(raw.get("plugged"), raw.get("plugged")),
        "temperature_c": round(temperature / 10, 1) if temperature else None,
        "voltage_mv": raw.get("voltage"),
    }


def screen_state(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell("dumpsys power | findstr /C:\"mWakefulness\" /C:\"Display Power\"", device=serial, timeout=15)
    text = res.get("stdout", "")
    awake = "mWakefulness=Awake" in text or "state=ON" in text
    return {"success": res["success"], "awake": awake, "raw": text.strip()[:400]}


def wake(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["input", "keyevent", "KEYCODE_WAKEUP"], device=serial)
    if res["success"]:
        return {"success": True, "action": "wake"}
    return res


def sleep_screen(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["input", "keyevent", "KEYCODE_SLEEP"], device=serial)
    if res["success"]:
        return {"success": True, "action": "sleep"}
    return res


def toggle_screen(serial: str | None = None) -> dict[str, Any]:
    current = screen_state(serial)
    if current.get("awake"):
        return sleep_screen(serial)
    return wake(serial)


def set_brightness(level: int, serial: str | None = None) -> dict[str, Any]:
    level = max(0, min(255, int(level)))
    adb.shell(["settings", "put", "system", "screen_brightness_mode", "0"], device=serial)
    res = adb.shell(["settings", "put", "system", "screen_brightness", str(level)], device=serial)
    if res["success"]:
        return {"success": True, "brightness": level, "percent": round(level * 100 / 255)}
    return res


def get_brightness(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["settings", "get", "system", "screen_brightness"], device=serial)
    if res["success"]:
        try:
            value = int(res["stdout"].strip())
            return {"success": True, "brightness": value, "percent": round(value * 100 / 255)}
        except ValueError:
            return {"success": False, "error": f"Unexpected brightness value: {res['stdout']!r}"}
    return res


def adjust_brightness(delta: int, serial: str | None = None) -> dict[str, Any]:
    current = get_brightness(serial)
    if not current.get("success"):
        return current
    return set_brightness(int(current["brightness"]) + int(delta), serial)


def wifi(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["settings", "get", "global", "wifi_on"], device=serial)
    if res["success"]:
        enabled = res["stdout"].strip() == "1"
        status = adb.shell(["dumpsys", "wifi"], device=serial, timeout=20)
        ssid = None
        m = re.search(r"mWifiInfo.*?SSID:\s*([^,]+)", status.get("stdout", ""))
        if m:
            ssid = m.group(1).strip()
        signal = None
        m2 = re.search(r"level:\s*(-?\d+)", status.get("stdout", ""))
        if m2:
            signal = int(m2.group(1))
        return {"success": True, "enabled": enabled, "ssid": ssid, "signal_level": signal}
    return res


def set_wifi(enabled: bool, serial: str | None = None) -> dict[str, Any]:
    # svc requires WRITE_SECURE_SETTINGS (granted via `adb shell pm grant` or adb root)
    res = adb.shell(["svc", "wifi", "enable" if enabled else "disable"], device=serial)
    if res["success"]:
        return {"success": True, "wifi": bool(enabled)}
    return res


def bluetooth(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["settings", "get", "global", "bluetooth_on"], device=serial)
    if res["success"]:
        return {"success": True, "enabled": res["stdout"].strip() == "1"}
    return res


def set_bluetooth(enabled: bool, serial: str | None = None) -> dict[str, Any]:
    return adb.shell(["svc", "bluetooth", "enable" if enabled else "disable"], device=serial)


def ringer_mode(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["cmd", "audio", "get-mode"], device=serial)
    if res["success"]:
        return {"success": True, "mode": res["stdout"].strip()}
    res2 = adb.shell(["settings", "get", "global", "mode_ringer"], device=serial)
    if res2["success"]:
        mapping = {"0": "silent", "1": "normal", "2": "vibrate"}
        value = res2["stdout"].strip()
        return {"success": True, "mode": mapping.get(value, value)}
    return res2


def set_ringer_mode(mode: str, serial: str | None = None) -> dict[str, Any]:
    """mode: normal | vibrate | silent"""
    mode = mode.lower()
    if mode not in {"normal", "vibrate", "silent"}:
        return {"success": False, "error": "mode must be normal, vibrate or silent"}
    res = adb.shell(["cmd", "audio", "set-mode", mode], device=serial)
    if res["success"]:
        return {"success": True, "mode": mode}
    return res


def set_volume(stream: str, level: int, serial: str | None = None) -> dict[str, Any]:
    streams = {"ring": 2, "notification": 5, "music": 3, "alarm": 4, "system": 1, "voice_call": 0}
    if stream not in streams:
        return {"success": False, "error": f"stream must be one of {sorted(streams)}"}
    level = max(0, min(int(level), 15))
    res = adb.shell(["cmd", "media_session", "volume", "--stream", str(streams[stream]), "--set", str(level)], device=serial)
    if res["success"]:
        return {"success": True, "stream": stream, "level": level}
    res2 = adb.shell(["media", "volume", "--stream", str(streams[stream]), "--set", str(level)], device=serial)
    if res2["success"]:
        return {"success": True, "stream": stream, "level": level}
    return res2 if not res2["success"] else res


def get_volume(stream: str, serial: str | None = None) -> dict[str, Any]:
    streams = {"ring": 2, "notification": 5, "music": 3, "alarm": 4, "system": 1, "voice_call": 0}
    if stream not in streams:
        return {"success": False, "error": f"stream must be one of {sorted(streams)}"}
    res = adb.shell(["cmd", "media_session", "volume", "--stream", str(streams[stream]), "--get"], device=serial)
    return {"success": res["success"], "stream": stream, "output": res.get("stdout", ""), "error": res.get("error")}


def airplane_mode(enabled: bool, serial: str | None = None) -> dict[str, Any]:
    value = "1" if enabled else "0"
    res = adb.shell(["settings", "put", "global", "airplane_mode_on", value], device=serial)
    if res["success"]:
        adb.shell(
            ["am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "true" if enabled else "false"],
            device=serial,
        )
        return {"success": True, "airplane_mode": bool(enabled), "note": "May require reboot to take effect"}
    return res


def do_not_disturb(enabled: bool, serial: str | None = None) -> dict[str, Any]:
    value = "1" if enabled else "0"
    res = adb.shell(["cmd", "notification", "set_dnd", "on" if enabled else "off"], device=serial)
    if res["success"]:
        return {"success": True, "dnd": bool(enabled)}
    res2 = adb.shell(["settings", "put", "secure", "zen_mode", value], device=serial)
    if res2["success"]:
        return {"success": True, "dnd": bool(enabled), "method": "settings"}
    return res2


def device_info(serial: str | None = None) -> dict[str, Any]:
    props = {
        "model": "ro.product.model",
        "brand": "ro.product.brand",
        "device": "ro.product.device",
        "android_version": "ro.build.version.release",
        "sdk": "ro.build.version.sdk",
        "build": "ro.build.display.id",
        "serial": "ro.serialno",
        "manufacturer": "ro.product.manufacturer",
        "cpu_abi": "ro.product.cpu.abi",
        "resolution": None,
    }
    info: dict[str, Any] = {}
    for key, prop in props.items():
        if prop is None:
            continue
        res = adb.shell(["getprop", prop], device=serial, timeout=10)
        if res["success"]:
            info[key] = res["stdout"].strip()
    res = adb.shell(["wm", "size"], device=serial, timeout=10)
    if res["success"]:
        info["resolution"] = res["stdout"].strip()
    res = adb.shell(["wm", "density"], device=serial, timeout=10)
    if res["success"]:
        info["density"] = res["stdout"].strip()
    return {"success": True, **info}


def storage(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["df", "-h", "/data"], device=serial, timeout=15)
    if not res["success"]:
        return res
    lines = [line.split() for line in res["stdout"].splitlines() if line.strip()]
    if len(lines) >= 2 and len(lines[1]) >= 5:
        row = lines[1]
        return {"success": True, "filesystem": row[0], "size": row[1], "used": row[2], "available": row[3], "use_percent": row[4]}
    return {"success": True, "raw": res["stdout"].strip()}


def installed_app_list(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["pm", "list", "packages", "-3"], device=serial, timeout=30)
    if res["success"]:
        packages = sorted(line.replace("package:", "").strip() for line in res["stdout"].splitlines() if line.startswith("package:"))
        return {"success": True, "packages": packages, "count": len(packages)}
    return res
