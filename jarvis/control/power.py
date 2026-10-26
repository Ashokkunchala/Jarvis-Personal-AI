"""Power actions: lock, sleep, hibernate, shutdown, restart, logoff, cancel."""

from __future__ import annotations

import ctypes
import logging
import subprocess
from typing import Any

logger = logging.getLogger("jarvis.control.power")

HT_BOOT = 0
HT_SHUTDOWN = 1
HT_REBOOT = 2
HT_SLEEP = 3
HT_HIBERNATE = 4

SE_SHUTDOWN_NAME = "SeShutdownPrivilege"


def _run(args: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def lock() -> dict[str, Any]:
    try:
        ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
        return {"success": True, "action": "lock"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def sleep_() -> dict[str, Any]:
    try:
        ctypes.windll.PowrProf.SetSuspendState(0, 0, 0)  # type: ignore[attr-defined]
        return {"success": True, "action": "sleep"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def hibernate() -> dict[str, Any]:
    try:
        ctypes.windll.PowrProf.SetSuspendState(1, 0, 0)  # type: ignore[attr-defined]
        return {"success": True, "action": "hibernate"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def shutdown(delay: int = 10) -> dict[str, Any]:
    delay = max(0, int(delay))
    return {**_run(["shutdown", "/s", "/t", str(delay)]), "action": "shutdown", "delay": delay}


def restart(delay: int = 10) -> dict[str, Any]:
    delay = max(0, int(delay))
    return {**_run(["shutdown", "/r", "/t", str(delay)]), "action": "restart", "delay": delay}


def logoff(delay: int = 0) -> dict[str, Any]:
    delay = max(0, int(delay))
    return {**_run(["shutdown", "/l"]), "action": "logoff", "delay": delay}


def cancel() -> dict[str, Any]:
    """Cancel a pending scheduled shutdown/restart."""
    return {**_run(["shutdown", "/a"]), "action": "cancel"}


def sign_out_apps() -> dict[str, Any]:
    return {**_run(["shutdown", "/l"]), "action": "logoff"}
