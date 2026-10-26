"""Low-level ADB runner shared by every Android control module."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.android.adb")

DEFAULT_TIMEOUT = 30
LONG_TIMEOUT = 180

_adb_path: str | None = None
_devices_cache: list[str] = []
_devices_lock = threading.Lock()
_devices_ts = 0.0
_DEVICES_TTL = 3.0

# Where `jarvis android setup` installs a private copy of platform-tools
BUNDLE_DIR = Path(__file__).resolve().parents[2] / "tools" / "platform-tools"
PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"


def find_adb() -> str:
    """Locate the adb binary: PATH, Android SDK defaults, bundled copy."""
    global _adb_path
    if _adb_path:
        return _adb_path

    candidates: list[str] = ["adb", str(BUNDLE_DIR / "adb.exe")]

    sdk_root = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if sdk_root:
        candidates.append(str(Path(sdk_root) / "platform-tools" / "adb.exe"))

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidates.append(str(Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe"))

    for path in (
        r"C:\Android\platform-tools\adb.exe",
        r"C:\platform-tools\adb.exe",
        r"C:\Program Files\Android\platform-tools\adb.exe",
        r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe",
        r"D:\Android\Sdk\platform-tools\adb.exe",
    ):
        candidates.append(path)

    for candidate in candidates:
        expanded = os.path.expandvars(candidate)
        executable = shutil.which(expanded) if os.sep not in expanded else (expanded if os.path.isfile(expanded) else None)
        if executable is None and Path(expanded).is_file():
            executable = expanded
        if not executable:
            continue
        try:
            probe = subprocess.run([executable, "version"], capture_output=True, timeout=8)
            if probe.returncode == 0:
                _adb_path = executable
                logger.info("Using adb at %s", executable)
                return _adb_path
        except Exception:
            continue

    _adb_path = "adb"
    return _adb_path


def is_adb_available() -> bool:
    adb = find_adb()
    if adb != "adb":
        return True
    return shutil.which("adb") is not None


def bootstrap_adb() -> dict[str, Any]:
    """Download a private copy of Android platform-tools if adb is missing.

    Installs into ``tools/platform-tools/`` inside the repo, then re-resolves
    ``find_adb()``. Safe to call repeatedly (no-op when adb already exists).
    """
    global _adb_path
    if is_adb_available() and _adb_path != "adb":
        return {"success": True, "adb": find_adb(), "installed": False, "message": "adb already available"}

    bundle_adb = BUNDLE_DIR / ("adb.exe" if os.name == "nt" else "adb")
    if bundle_adb.is_file():
        _adb_path = None
        find_adb()
        if is_adb_available():
            return {"success": True, "adb": find_adb(), "installed": False, "message": "bundled adb found"}

    import zipfile

    BUNDLE_DIR.parent.mkdir(parents=True, exist_ok=True)
    zip_path = BUNDLE_DIR.parent / "platform-tools.zip"
    try:
        logger.info("Downloading Android platform-tools…")
        import httpx

        with httpx.stream("GET", PLATFORM_TOOLS_URL, timeout=120, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                    fh.write(chunk)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(BUNDLE_DIR.parent)
        zip_path.unlink(missing_ok=True)
    except Exception as exc:
        return {
            "success": False,
            "error": f"Could not download platform-tools: {exc}",
            "hint": "Install manually: https://developer.android.com/tools/releases/platform-tools, then re-run 'jarvis android setup'.",
        }

    _adb_path = None
    find_adb()
    if is_adb_available():
        return {"success": True, "adb": find_adb(), "installed": True, "path": str(BUNDLE_DIR)}
    return {
        "success": False,
        "error": "platform-tools downloaded but adb still not runnable",
        "path": str(BUNDLE_DIR),
    }


def run_adb(
    args: list[str],
    device: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    serial: str | None = None,
) -> dict[str, Any]:
    """Run an adb subcommand and return a standard result dict."""
    adb = find_adb()
    target = serial or device
    cmd = [adb]
    if target:
        cmd += ["-s", target]
    elif not args or args[0] not in {"devices", "version", "start-server", "kill-server", "connect", "disconnect", "tcpip", "usb"}:
        devices = list_devices(refresh=False)
        if len(devices) == 1:
            cmd += ["-s", devices[0]]
        elif len(devices) > 1:
            return {
                "success": False,
                "error": "Multiple devices connected; pass device=<serial>",
                "devices": devices,
            }

    cmd += [str(a) for a in args]
    try:
        started = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        elapsed = round(time.time() - started, 2)
        ok = result.returncode == 0
        payload = {
            "success": ok,
            "returncode": result.returncode,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
            "elapsed": elapsed,
            "command": " ".join(cmd[1:]),
        }
        if not ok and payload["stderr"]:
            payload["error"] = payload["stderr"]
        elif not ok:
            payload["error"] = payload["stdout"] or f"adb exited with {result.returncode}"
        return payload
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"adb timed out after {timeout}s", "command": " ".join(args)}
    except FileNotFoundError:
        return {"success": False, "error": "adb not found. Install Android platform-tools and add them to PATH."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def shell(
    command: str | list[str],
    device: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    as_root: bool = False,
) -> dict[str, Any]:
    """Run a device shell command (string or argv list)."""
    if isinstance(command, str):
        args = ["shell", command]
    else:
        args = ["shell", *command]
    if as_root:
        args = ["shell", "su", "-c", " ".join(command) if isinstance(command, (list, tuple)) else command]
    return run_adb(args, device=device, timeout=timeout)


def list_devices(refresh: bool = True) -> list[str]:
    """Return serials of devices in state 'device' (authorized & online)."""
    global _devices_cache, _devices_ts
    with _devices_lock:
        if not refresh and _devices_cache and time.time() - _devices_ts < _DEVICES_TTL:
            return list(_devices_cache)
        result = run_adb(["devices"], timeout=10)
        devices: list[str] = []
        if result["success"]:
            for line in result["stdout"].splitlines()[1:]:
                line = line.strip()
                if not line or line.startswith("*"):
                    continue
                parts = line.split("\t")
                if len(parts) == 2 and parts[1].strip() == "device":
                    devices.append(parts[0].strip())
        _devices_cache = devices
        _devices_ts = time.time()
        return list(devices)


def refresh_devices() -> list[str]:
    return list_devices(refresh=True)


def pick_device(serial: str | None = None) -> str | None:
    """Resolve which device to act on: explicit serial > sole device > None."""
    if serial:
        return serial
    devices = list_devices()
    if len(devices) >= 1:
        return devices[0]
    return None


def device_state(serial: str | None = None) -> dict[str, Any]:
    devices = list_devices(refresh=True)
    target = serial or (devices[0] if devices else None)
    return {
        "success": True,
        "adb_available": is_adb_available(),
        "devices": devices,
        "selected": target,
        "count": len(devices),
    }


def require_device(serial: str | None = None) -> tuple[str | None, dict[str, Any] | None]:
    """Return (serial, None) or (None, error_result)."""
    devices = list_devices()
    target = serial or (devices[0] if devices else None)
    if not target:
        return None, {
            "success": False,
            "error": "No Android device connected. Enable USB debugging and plug in the device.",
            "hint": "Run 'adb devices' to check, or connect wirelessly with android_wireless_connect.",
            "devices": [],
        }
    return target, None
