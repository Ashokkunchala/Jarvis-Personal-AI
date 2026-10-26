"""Network inspection: IP addresses, Wi-Fi, ping, port scan, connections."""

from __future__ import annotations

import logging
import socket
import subprocess
from typing import Any

logger = logging.getLogger("jarvis.control.network")


def _run(args: list[str], timeout: int = 20) -> dict[str, Any]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def public_ip() -> dict[str, Any]:
    try:
        import httpx

        resp = httpx.get("https://api.ipify.org?format=json", timeout=8)
        return {"success": True, "ip": resp.json().get("ip")}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def local_ip() -> dict[str, Any]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        hostname = socket.gethostname()
        return {"success": True, "ip": ip, "hostname": hostname}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def ping(host: str = "8.8.8.8", count: int = 4) -> dict[str, Any]:
    result = _run(["ping", "-n", str(max(1, min(int(count), 10))), host], timeout=30)
    output = (result.get("stdout") or "") + (result.get("stderr") or "")
    avg = None
    for line in output.splitlines():
        if "Average" in line or "Mittelwert" in line:
            avg = line.split(":")[-1].strip()
    return {"success": result["success"], "host": host, "average": avg, "output": output.strip()[:2000]}


def wifi_networks() -> dict[str, Any]:
    result = _run(["netsh", "wlan", "show", "networks", "mode=bssid"], timeout=25)
    if not result["success"]:
        return {"success": False, "error": (result.get("stderr") or result.get("error") or "netsh failed").strip()}
    networks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in (result["stdout"] or "").splitlines():
        line = line.strip()
        if line.startswith("SSID ") and ":" in line:
            current = {"ssid": line.split(":", 1)[1].strip()}
            networks.append(current)
        elif current and ":" in line:
            key, value = line.split(":", 1)
            current[key.strip().lower().replace(" ", "_")] = value.strip()
    return {"success": True, "networks": networks}


def current_wifi() -> dict[str, Any]:
    result = _run(["netsh", "wlan", "show", "interfaces"], timeout=20)
    if not result["success"]:
        return {"success": False, "error": "Could not query Wi-Fi interfaces"}
    info: dict[str, str] = {}
    for line in (result["stdout"] or "").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    return {"success": True, "interface": {k: info.get(k) for k in ("SSID", "State", "Signal", "Channel", "Radio type") if k in info}}


def scan_ports(host: str = "127.0.0.1", ports: list[int] | None = None, timeout: float = 0.4) -> dict[str, Any]:
    """TCP connect scan of a small port list (defaults to common service ports)."""
    if ports is None:
        ports = [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445, 993, 995, 1433, 1723, 3306, 3389, 5432, 5900, 8080, 8443]
    ports = [int(p) for p in ports][:200]
    open_ports: list[int] = []
    for port in ports:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                open_ports.append(port)
        except (TimeoutError, OSError):
            continue
    return {"success": True, "host": host, "scanned": len(ports), "open": open_ports}


def listening_ports() -> list[dict[str, Any]]:
    import psutil

    results = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN" and conn.laddr:
                results.append(
                    {
                        "address": conn.laddr.ip,
                        "port": conn.laddr.port,
                        "pid": conn.pid,
                        "status": conn.status,
                    }
                )
    except (psutil.AccessDenied, PermissionError):
        return []
    seen, unique = set(), []
    for r in results:
        key = (r["address"], r["port"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return sorted(unique, key=lambda r: r["port"])


def active_connections() -> list[dict[str, Any]]:
    import psutil

    results = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "ESTABLISHED" and conn.raddr:
                results.append(
                    {
                        "remote": f"{conn.raddr.ip}:{conn.raddr.port}",
                        "local": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                        "pid": conn.pid,
                        "status": conn.status,
                    }
                )
    except (psutil.AccessDenied, PermissionError):
        return []
    return results[:100]
