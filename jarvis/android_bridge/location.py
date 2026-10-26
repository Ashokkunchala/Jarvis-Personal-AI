"""Location: read last known location and set mock GPS fixes."""

from __future__ import annotations

import re
from typing import Any

from jarvis.android_bridge import adb


def last_known_location(serial: str | None = None) -> dict[str, Any]:
    """Read the last location recorded by dumpsys (no extra app required)."""
    res = adb.shell(["dumpsys", "location"], device=serial, timeout=25)
    if not res["success"]:
        return res
    text = res["stdout"]
    patterns = [
        r"last location=.*?(\-?\d+\.\d+),\s*(\-?\d+\.\d+)",
        r"Location\[\s*(\-?\d+\.\d+),\s*(\-?\d+\.\d+)",
        r"lastKnownLocation=.*?(\-?\d+\.\d+),(\-?\d+\.\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return {"success": True, "latitude": float(m.group(1)), "longitude": float(m.group(2)), "source": "dumpsys"}
    m = re.search(r"latitude=(\-?\d+\.\d+).*?longitude=(\-?\d+\.\d+)", text, re.DOTALL)
    if m:
        return {"success": True, "latitude": float(m.group(1)), "longitude": float(m.group(2)), "source": "dumpsys"}
    return {"success": False, "error": "No location fix found in dumpsys location"}


def enable_mock_location(serial: str | None = None) -> dict[str, Any]:
    """Select the shell as the mock-location app (requires developer options)."""
    res = adb.shell(["appops", "set", "com.android.shell", "android:mock_location", "allow"], device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "mock_provider": "com.android.shell", "action": "allowed"}
    return res


def set_mock_location(latitude: float, longitude: float, accuracy: float = 5.0, serial: str | None = None) -> dict[str, Any]:
    """Send a mock GPS fix using the Android test GPS provider."""
    enable_mock_location(serial)
    # Route through the built-in test provider
    provider = "gps"
    res = adb.shell(
        [
            "appops", "set", "--uid", "com.android.shell", "android:mock_location", "allow",
        ],
        device=serial,
        timeout=15,
    )
    # Preferred approach: use `cmd location` (Android 12+)
    cmd = [
        "cmd", "location", "providers", "set-provider-location", provider,
        "--location", f"{latitude},{longitude}", "--accuracy", str(accuracy),
    ]
    res = adb.shell(cmd, device=serial, timeout=20)
    if res["success"] and "Unknown command" not in res.get("stdout", "") + res.get("stderr", ""):
        return {"success": True, "latitude": latitude, "longitude": longitude, "method": "cmd location"}

    # Fallback: test provider broadcast for older devices / emulators
    res2 = adb.shell(
        ["am", "broadcast", "-a", "android.intent.action.SET_MOCK_LOCATION", "--es", "lat", str(latitude), "--es", "lng", str(longitude)],
        device=serial,
        timeout=20,
    )
    if res2["success"]:
        return {"success": True, "latitude": latitude, "longitude": longitude, "method": "broadcast"}
    return {
        "success": False,
        "error": "Device rejected mock location (needs developer options + mock location app set).",
        "hint": "On the phone: Settings → Developer options → Select mock location app → shell (or your app).",
    }


def stop_mock_location(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["cmd", "location", "providers", "remove-provider-location", "gps"], device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "action": "mock_removed"}
    return {"success": False, "error": res.get("error") or "Could not remove mock location"}


def set_gps_enabled(enabled: bool, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["settings", "put", "secure", "location_mode", "3" if enabled else "0"], device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "gps": bool(enabled)}
    res2 = adb.shell(["cmd", "location", "set-location-enabled", "true" if enabled else "false"], device=serial, timeout=15)
    if res2["success"]:
        return {"success": True, "gps": bool(enabled)}
    return res2
