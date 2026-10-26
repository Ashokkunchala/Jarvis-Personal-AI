"""System metrics: CPU, memory, disk, battery, GPU, OS details."""

from __future__ import annotations

import logging
import platform
import shutil
from typing import Any

logger = logging.getLogger("jarvis.control.info")


def os_info() -> dict[str, Any]:
    return {
        "success": True,
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "hostname": platform.node(),
    }


def cpu_usage(interval: float = 0.5) -> dict[str, Any]:
    import psutil

    try:
        per_core = psutil.cpu_percent(interval=interval, percpu=True)
        return {
            "success": True,
            "percent": psutil.cpu_percent(interval=0),
            "per_core": per_core,
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "frequency_mhz": round(psutil.cpu_freq().current, 0) if psutil.cpu_freq() else None,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def memory_usage() -> dict[str, Any]:
    import psutil

    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "success": True,
        "total_gb": round(vm.total / (1024 ** 3), 2),
        "available_gb": round(vm.available / (1024 ** 3), 2),
        "used_gb": round(vm.used / (1024 ** 3), 2),
        "percent": vm.percent,
        "swap_total_gb": round(swap.total / (1024 ** 3), 2),
        "swap_percent": swap.percent,
    }


def disk_usage(path: str = "C:\\") -> dict[str, Any]:
    import psutil

    results: list[dict[str, Any]] = []
    drives = [path] if path else []
    if not drives:
        for letter in "CDEFGH":
            drive = f"{letter}:\\"
            if shutil.which(drive[0]) or (len(drive) and __import__("os").path.exists(drive)):
                drives.append(drive)
    for drive in drives:
        try:
            usage = psutil.disk_usage(drive)
            results.append(
                {
                    "path": drive,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent": usage.percent,
                }
            )
        except (OSError, PermissionError):
            continue
    if not results:
        return {"success": False, "error": "No drives readable"}
    return {"success": True, "drives": results}


def battery() -> dict[str, Any]:
    import psutil

    if not hasattr(psutil, "sensors_battery"):
        return {"success": False, "error": "Battery info unavailable on this platform"}
    bat = psutil.sensors_battery()
    if bat is None:
        return {"success": True, "present": False}
    return {
        "success": True,
        "present": True,
        "percent": bat.percent,
        "plugged": bat.power_plugged,
        "seconds_left": int(bat.secsleft) if bat.secsleft > 0 else None,
        "status": "charging" if bat.power_plugged else "discharging",
    }


def gpu_info() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    try:
        import subprocess

        result = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name,driverversion", "/format:csv"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            for line in lines[1:]:  # skip header
                parts = line.split(",")
                if len(parts) >= 3:
                    gpus.append({"name": parts[-2].strip(), "driver": parts[-1].strip()})
    except Exception as exc:
        logger.debug("GPU query failed: %s", exc)
    return gpus


def top_processes(limit: int = 10) -> list[dict[str, Any]]:
    import psutil

    procs = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mem = proc.info["memory_info"]
            procs.append(
                {
                    "pid": proc.info["pid"],
                    "name": proc.info["name"],
                    "memory_mb": round(mem.rss / (1024 * 1024), 1) if mem else 0,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda p: p["memory_mb"], reverse=True)
    return procs[:limit]


def summary() -> dict[str, Any]:
    """Compact snapshot for status bars and dashboards."""
    import psutil

    try:
        vm = psutil.virtual_memory()
        bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        return {
            "success": True,
            "os": f"{platform.system()} {platform.release()}",
            "hostname": platform.node(),
            "cpu_percent": psutil.cpu_percent(interval=0.3),
            "memory_percent": vm.percent,
            "memory_used_gb": round(vm.used / (1024 ** 3), 1),
            "memory_total_gb": round(vm.total / (1024 ** 3), 1),
            "battery_percent": bat.percent if bat else None,
            "battery_plugged": bat.power_plugged if bat else None,
            "disk_free_gb": round(shutil.disk_usage("C:\\").free / (1024 ** 3), 1) if shutil.disk_usage else None,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
