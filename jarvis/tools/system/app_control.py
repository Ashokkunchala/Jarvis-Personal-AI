import logging
import os

from jarvis.config.settings import config

logger = logging.getLogger("jarvis.tools.app")


def open_app(app_name: str):
    """Open an application"""
    app_name_lower = app_name.lower()

    # Check if in allowed list
    allowed = False
    for allowed_app in config.allowed_apps:
        if allowed_app.lower() in app_name_lower or app_name_lower in allowed_app.lower():
            allowed = True
            break

    if not allowed and config.require_confirmation:
        # Still allow but will be confirmed by registry
        pass

    try:
        # Try common Windows apps
        app_map = {
            "chrome": "chrome.exe",
            "edge": "msedge.exe",
            "firefox": "firefox.exe",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "vscode": "code.exe",
            "visual studio": "devenv.exe",
            "explorer": "explorer.exe",
            "files": "explorer.exe"
        }

        exe = app_map.get(app_name_lower, app_name)
        if not exe.endswith('.exe') and '.' not in exe:
            exe += '.exe'

        os.startfile(exe)
        logger.info(f"Opened app: {exe}")
        return f"Opened {app_name}"
    except Exception as e:
        logger.error(f"Failed to open app {app_name}: {e}")
        raise


def close_app(app_name: str):
    """Close an application"""
    try:
        import psutil
        app_name_lower = app_name.lower()
        closed = []
        for proc in psutil.process_iter(['name']):
            try:
                if app_name_lower in proc.info['name'].lower():
                    proc.terminate()
                    closed.append(proc.info['name'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if closed:
            return f"Closed {', '.join(closed)}"
        else:
            return f"No processes found matching {app_name}"
    except Exception as e:
        logger.error(f"Failed to close app {app_name}: {e}")
        raise
