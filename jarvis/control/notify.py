"""Windows toast notifications."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("jarvis.control.notify")


def notify(title: str, message: str, icon: str = "info", duration: int = 5) -> dict[str, Any]:
    """Show a Windows toast notification (best available backend)."""
    # 1. winotify (preferred)
    try:
        from winotify import Notification, audio

        toast = Notification(
            app_id="JARVIS Personal AI",
            title=title,
            msg=message,
            duration="short" if duration <= 5 else "long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        return {"success": True, "backend": "winotify"}
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("winotify failed: %s", exc)

    # 2. plyer fallback
    try:
        from plyer import notification

        notification.notify(title=title, message=message, timeout=max(2, min(duration, 30)))
        return {"success": True, "backend": "plyer"}
    except Exception as exc:
        logger.debug("plyer failed: %s", exc)

    # 3. PowerShell balloon tip fallback
    try:
        import subprocess

        escaped_title = title.replace("'", "''")
        escaped_msg = message.replace("'", "''")
        script = (
            "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
            "$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Information;"
            "$n.Visible=$true;"
            f"$n.ShowBalloonTip({int(duration)*1000},'{escaped_title}','{escaped_msg}','Info')"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=15)
        return {"success": True, "backend": "powershell-balloon"}
    except Exception as exc:
        return {"success": False, "error": f"No notification backend available: {exc}"}
