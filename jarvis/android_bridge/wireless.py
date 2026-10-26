"""Wireless ADB: enable tcpip mode, connect/disconnect over Wi-Fi."""

from __future__ import annotations

import re
from typing import Any

from jarvis.android_bridge import adb


def enable_tcpip(port: int = 5555, serial: str | None = None) -> dict[str, Any]:
    port = max(1024, min(int(port), 65535))
    res = adb.run_adb(["tcpip", str(port)], device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "port": port, "message": "Listening for wireless connections. Find the phone's IP in Settings → About."}
    return res


def connect(host: str, port: int = 5555) -> dict[str, Any]:
    host = host.strip().replace("adb://", "")
    if ":" in host and port == 5555:
        host, port_str = host.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            return {"success": False, "error": f"Invalid host:port {host}:{port_str}"}
    res = adb.run_adb(["connect", f"{host}:{port}"], timeout=20)
    if res["success"] and "connected" in res.get("stdout", "").lower() and "cannot" not in res.get("stdout", "").lower():
        adb.refresh_devices()
        return {"success": True, "endpoint": f"{host}:{port}", "output": res["stdout"]}
    if "already connected" in res.get("stdout", ""):
        adb.refresh_devices()
        return {"success": True, "endpoint": f"{host}:{port}", "already_connected": True}
    return {"success": False, "error": res.get("stdout") or res.get("error") or "Connection failed"}


def disconnect(host: str | None = None) -> dict[str, Any]:
    args = ["disconnect"] + ([host] if host else [])
    res = adb.run_adb(args, timeout=15)
    adb.refresh_devices()
    if res["success"]:
        return {"success": True, "output": res["stdout"]}
    return res


def pair(host: str, code: str, port: int = 37123) -> dict[str, Any]:
    """Android 11+ wireless debugging pairing (host:port + 6-digit code)."""
    endpoint = host if ":" in host else f"{host}:{port}"
    res = adb.run_adb(["pair", endpoint, code], timeout=25)
    if res["success"] and "successfully" in res.get("stdout", "").lower():
        return {"success": True, "endpoint": endpoint, "output": res["stdout"]}
    return {"success": False, "error": res.get("stdout") or res.get("error") or "Pairing failed"}


def wireless_devices() -> dict[str, Any]:
    devices = adb.list_devices(refresh=True)
    wireless = [d for d in devices if ":" in d]
    usb = [d for d in devices if ":" not in d]
    return {"success": True, "wireless": wireless, "usb": usb, "all": devices}


def ip_address(serial: str | None = None) -> dict[str, Any]:
    """Find the device's LAN IP for wireless adb."""
    res = adb.shell(["ip", "route"], device=serial, timeout=15)
    if not res["success"]:
        res = adb.shell(["ifconfig", "wlan0"], device=serial, timeout=15)
        if not res["success"]:
            return res
        m = re.search(r"inet addr:(\d+\.\d+\.\d+\.\d+)", res["stdout"])
        if m:
            return {"success": True, "ip": m.group(1)}
        return {"success": False, "error": "Could not determine device IP"}

    for line in res["stdout"].splitlines():
        if line.startswith("wlan0") or "wlan0" in line:
            m = re.search(r"src\s+(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                return {"success": True, "ip": m.group(1), "interface": "wlan0"}
    m = re.search(r"src\s+(\d+\.\d+\.\d+\.\d+)", res["stdout"])
    if m:
        return {"success": True, "ip": m.group(1)}
    return {"success": False, "error": "No IP found in routing table"}


def setup_wireless(serial: str | None = None) -> dict[str, Any]:
    """Convenience: enable tcpip, read the IP and connect to it."""
    tcp = enable_tcpip(5555, serial)
    if not tcp["success"]:
        return tcp
    ip = ip_address(serial)
    if not ip.get("success"):
        return {"success": False, "error": "Could not read device IP", "tcpip": tcp}
    conn = connect(ip["ip"], 5555)
    return {
        "success": conn["success"],
        "tcpip": tcp,
        "ip": ip["ip"],
        "connect": conn,
        "message": f"Wireless ADB ready at {ip['ip']}:5555" if conn["success"] else conn.get("error"),
    }
