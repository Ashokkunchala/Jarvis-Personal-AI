"""Clipboard read/write."""

from __future__ import annotations

import logging

logger = logging.getLogger("jarvis.control.clipboard")


def get_clipboard() -> dict:
    try:
        import pyperclip

        text = pyperclip.paste()
        return {"success": True, "text": text, "length": len(text)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def set_clipboard(text: str) -> dict:
    try:
        import pyperclip

        pyperclip.copy(text)
        return {"success": True, "length": len(text)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def clear_clipboard() -> dict:
    return set_clipboard("")
