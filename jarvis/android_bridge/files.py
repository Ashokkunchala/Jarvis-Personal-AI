"""Android file system operations over ADB (push, pull, list, delete, read)."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from jarvis.android_bridge import adb


def list_dir(path: str = "/sdcard", serial: str | None = None, limit: int = 200) -> dict[str, Any]:
    res = adb.shell(["ls", "-la", path], device=serial, timeout=25)
    if not res["success"]:
        # Some devices use toybox ls without -la
        res = adb.shell(["ls", path], device=serial, timeout=25)
        if not res["success"]:
            return res
        entries = [line.strip() for line in res["stdout"].splitlines() if line.strip()][:limit]
        return {"success": True, "path": path, "entries": entries, "count": len(entries)}
    entries = [line.rstrip() for line in res["stdout"].splitlines() if line.strip()][:limit]
    return {"success": True, "path": path, "entries": entries, "count": len(entries)}


def push(local: str, remote: str, serial: str | None = None) -> dict[str, Any]:
    src = Path(local).expanduser()
    if not src.exists():
        return {"success": False, "error": f"Local path not found: {src}"}
    res = adb.run_adb(["push", str(src), remote], device=serial, timeout=adb.LONG_TIMEOUT)
    if res["success"]:
        return {"success": True, "local": str(src), "remote": remote, "size": src.stat().st_size if src.is_file() else None}
    return res


def pull(remote: str, local: str | None = None, serial: str | None = None) -> dict[str, Any]:
    if not local:
        out = Path("data/android_files")
        out.mkdir(parents=True, exist_ok=True)
        local = str(out / (remote.rstrip("/").split("/")[-1] or f"pull_{int(time.time())}"))
    Path(local).parent.mkdir(parents=True, exist_ok=True)
    res = adb.run_adb(["pull", remote, local], device=serial, timeout=adb.LONG_TIMEOUT)
    if res["success"]:
        return {"success": True, "remote": remote, "local": str(Path(local).resolve())}
    return res


def delete(path: str, recursive: bool = False, serial: str | None = None) -> dict[str, Any]:
    if path in {"/", "/sdcard", "/data", "/system", "/proc"} and not path.count("/") > 1:
        return {"success": False, "error": f"Refusing to delete {path!r}"}
    if recursive:
        res = adb.shell(["rm", "-rf", path], device=serial, timeout=30)
    else:
        res = adb.shell(["rm", path], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "path": path, "recursive": recursive}
    return res


def mkdir(path: str, parents: bool = True, serial: str | None = None) -> dict[str, Any]:
    args = ["mkdir"]
    if parents:
        args.append("-p")
    args.append(path)
    res = adb.shell(args, device=serial, timeout=15)
    if res["success"]:
        return {"success": True, "path": path}
    return res


def move(source: str, destination: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["mv", source, destination], device=serial, timeout=30)
    if res["success"]:
        return {"success": True, "source": source, "destination": destination}
    return res


def copy(source: str, destination: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["cp", source, destination], device=serial, timeout=30)
    if res["success"]:
        return {"success": True, "source": source, "destination": destination}
    return res


def read_text(path: str, max_bytes: int = 64000, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["cat", path], device=serial, timeout=30)
    if not res["success"]:
        return res
    text = res["stdout"]
    truncated = len(text.encode("utf-8", errors="replace")) >= max_bytes
    return {"success": True, "path": path, "content": text[:max_bytes], "truncated": truncated}


def file_info(path: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["stat", "-c", "%n|%s|%F|%Y", path], device=serial, timeout=15)
    if not res["success"]:
        res = adb.shell(["ls", "-ld", path], device=serial, timeout=15)
        if not res["success"]:
            return res
        return {"success": True, "path": path, "raw": res["stdout"].strip()}
    parts = res["stdout"].strip().split("|")
    if len(parts) == 4:
        return {
            "success": True,
            "path": parts[0],
            "size": int(parts[1]) if parts[1].isdigit() else parts[1],
            "type": parts[2],
            "modified": float(parts[3]) if parts[3].isdigit() else parts[3],
        }
    return {"success": True, "path": path, "raw": res["stdout"].strip()}


def search(path: str, name_pattern: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["find", path, "-name", f"*{name_pattern}*"], device=serial, timeout=45)
    if not res["success"]:
        return res
    matches = [line.strip() for line in res["stdout"].splitlines() if line.strip()][:80]
    return {"success": True, "matches": matches, "count": len(matches)}


def push_text(text: str, remote: str, serial: str | None = None) -> dict[str, Any]:
    """Write local text to a remote device file via a temp file."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        tmp = fh.name
    try:
        return push(tmp, remote, serial)
    finally:
        Path(tmp).unlink(missing_ok=True)


def storage_stats(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["df", "-h"], device=serial, timeout=20)
    if not res["success"]:
        return res
    rows = []
    for line in res["stdout"].splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6:
            rows.append(
                {
                    "filesystem": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "use": parts[4],
                    "mount": parts[5],
                }
            )
    return {"success": True, "volumes": rows}
