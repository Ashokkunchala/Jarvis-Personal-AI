"""System audio control (volume, mute, devices) via pycaw.

Supports both the classic pycaw API (``AudioUtilities.GetSpeakers().Activate``)
and the newer ``AudioDevice.EndpointVolume``/``volume_percent`` interface.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("jarvis.control.audio")

_endpoint = None
_initialised = False


def _get_endpoint():
    global _endpoint, _initialised
    if _initialised:
        return _endpoint
    _initialised = True
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        device = AudioUtilities.GetSpeakers()
        # New pycaw: AudioDevice exposes .EndpointVolume directly
        endpoint = getattr(device, "EndpointVolume", None)
        if endpoint is None:
            # Classic pycaw: activate the interface from the device
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL

            raw = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            endpoint = cast(raw, POINTER(IAudioEndpointVolume))
        _endpoint = endpoint
    except Exception as exc:  # pragma: no cover - hardware dependent
        logger.warning("Audio control unavailable: %s", exc)
        _endpoint = None
    return _endpoint


def is_available() -> bool:
    return _get_endpoint() is not None


def get_volume() -> dict[str, Any]:
    endpoint = _get_endpoint()
    if endpoint is None:
        return {"success": False, "error": "Audio control unavailable"}
    try:
        level = endpoint.GetMasterVolumeLevelScalar()
        muted = bool(endpoint.GetMute())
        return {"success": True, "volume": int(round(level * 100)), "muted": muted}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def set_volume(level: int) -> dict[str, Any]:
    endpoint = _get_endpoint()
    if endpoint is None:
        return {"success": False, "error": "Audio control unavailable"}
    try:
        level = max(0, min(100, int(level)))
        endpoint.SetMasterVolumeLevelScalar(level / 100.0, None)
        return {"success": True, "volume": level}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def adjust_volume(delta: int) -> dict[str, Any]:
    current = get_volume()
    if not current.get("success"):
        return current
    return set_volume(int(current["volume"]) + int(delta))


def set_mute(muted: bool) -> dict[str, Any]:
    endpoint = _get_endpoint()
    if endpoint is None:
        return {"success": False, "error": "Audio control unavailable"}
    try:
        endpoint.SetMute(1 if muted else 0, None)
        return {"success": True, "muted": bool(muted)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def toggle_mute() -> dict[str, Any]:
    current = get_volume()
    if not current.get("success"):
        return current
    return set_mute(not current.get("muted", False))


def list_sessions() -> list[dict[str, Any]]:
    """Per-application audio sessions (name, volume, mute)."""
    try:
        from pycaw.pycaw import AudioUtilities

        sessions: list[dict[str, Any]] = []
        for session in AudioUtilities.GetAllSessions():
            process = session.Process
            level = muted = None
            try:
                volume = session.SimpleAudioVolume
                level = volume.GetMasterVolume()
                muted = bool(volume.GetMute())
            except Exception:
                pass
            sessions.append(
                {
                    "name": process.name() if process else "unknown",
                    "pid": process.pid if process else None,
                    "volume": int(round(level * 100)) if level is not None else None,
                    "muted": muted,
                    "active": bool(getattr(session, "State", 0)),
                }
            )
        return sessions
    except Exception as exc:
        logger.debug("Could not enumerate audio sessions: %s", exc)
        return []
