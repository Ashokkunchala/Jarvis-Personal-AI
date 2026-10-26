"""Android screen capture: screenshot, screen recording, UI hierarchy dump."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from jarvis.android_bridge import adb


def screenshot(path: str | None = None, serial: str | None = None) -> dict[str, Any]:
    if not path:
        out = Path("data/screenshots")
        out.mkdir(parents=True, exist_ok=True)
        path = str(out / f"android_{int(time.time())}.png")
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    remote = "/sdcard/jarvis_screenshot.png"
    res = adb.shell(["screencap", "-p", remote], device=serial, timeout=30)
    if not res["success"]:
        return res
    pull = adb.run_adb(["pull", remote, path], device=serial, timeout=30)
    adb.shell(["rm", remote], device=serial, timeout=10)
    if pull["success"]:
        return {"success": True, "path": str(Path(path).resolve()), "device": serial}
    return pull


def record_screen(duration: int = 10, path: str | None = None, bit_rate: int = 8_000_000, serial: str | None = None) -> dict[str, Any]:
    duration = max(3, min(int(duration), 180))
    if not path:
        out = Path("data/recordings")
        out.mkdir(parents=True, exist_ok=True)
        path = str(out / f"android_{int(time.time())}.mp4")
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    remote = "/sdcard/jarvis_record.mp4"
    # screenrecord blocks until done; give adb generous timeout + buffer
    res = adb.shell(
        ["screenrecord", f"--time-limit={duration}", f"--bit-rate={bit_rate}", remote],
        device=serial,
        timeout=duration + 45,
    )
    if not res["success"] and "error" in res.get("stdout", "").lower() + res.get("stderr", "").lower():
        return res
    pull = adb.run_adb(["pull", remote, path], device=serial, timeout=60)
    adb.shell(["rm", remote], device=serial, timeout=10)
    if pull["success"]:
        return {"success": True, "path": str(Path(path).resolve()), "duration": duration}
    return pull


def ui_dump(path: str | None = None, serial: str | None = None) -> dict[str, Any]:
    """Dump the current UI hierarchy (uiautomator) as XML."""
    if not path:
        out = Path("data/ui_dumps")
        out.mkdir(parents=True, exist_ok=True)
        path = str(out / f"ui_{int(time.time())}.xml")
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    remote = "/sdcard/jarvis_ui.xml"
    res = adb.shell(["uiautomator", "dump", remote], device=serial, timeout=30)
    if not res["success"]:
        return res
    pull = adb.run_adb(["pull", remote, path], device=serial, timeout=30)
    adb.shell(["rm", remote], device=serial, timeout=10)
    if not pull["success"]:
        return pull

    # Parse into a compact node list (bounds, text, resource-id, clickable...)
    try:
        import xml.etree.ElementTree as ET

        tree = ET.parse(path)
        nodes = []
        for el in tree.iter("node"):
            attrib = el.attrib
            if attrib.get("text") or attrib.get("resource-id") or attrib.get("content-desc"):
                nodes.append(
                    {
                        "text": attrib.get("text", ""),
                        "resource_id": attrib.get("resource-id", ""),
                        "class": attrib.get("class", ""),
                        "desc": attrib.get("content-desc", ""),
                        "bounds": attrib.get("bounds", ""),
                        "clickable": attrib.get("clickable") == "true",
                        "enabled": attrib.get("enabled") == "true",
                    }
                )
        return {"success": True, "path": str(Path(path).resolve()), "nodes": nodes[:300], "count": len(nodes)}
    except Exception as exc:
        return {"success": True, "path": str(Path(path).resolve()), "error": f"Could not parse UI dump: {exc}"}


def screen_size(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["wm", "size"], device=serial, timeout=10)
    if not res["success"]:
        return res
    raw = res["stdout"].strip()
    try:
        size = raw.split("x")
        height = int("".join(c for c in size[-1] if c.isdigit()))
        width = int("".join(c for c in size[0].split()[-1] if c.isdigit()))
        return {"success": True, "width": width, "height": height, "raw": raw}
    except (ValueError, IndexError):
        return {"success": True, "raw": raw}


def screen_record_status(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["pidof", "screenrecord"], device=serial, timeout=10)
    running = res["success"] and bool(res["stdout"].strip())
    return {"success": True, "recording": running, "pid": res["stdout"].strip() or None}
