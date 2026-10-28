import ctypes
import logging
import os
import subprocess
import time
from ctypes import POINTER, cast
from typing import Any

import psutil
import pyautogui
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

logger = logging.getLogger("jarvis.control")


class SystemController:
    def __init__(self):
        pyautogui.FAILSAFE = False
        self._setup_audio()

    def _setup_audio(self):
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.volume = cast(interface, POINTER(IAudioEndpointVolume))
        except Exception as e:
            logger.warning(f"Audio control unavailable: {e}")
            self.volume = None

    def open_app(self, app_name: str) -> dict[str, Any]:
        try:
            app_map = {
                "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
                "notepad": "notepad.exe",
                "calculator": "calc.exe",
                "cmd": "cmd.exe",
                "powershell": "powershell.exe",
                "taskmgr": "taskmgr.exe",
                "file explorer": "explorer.exe",
            }
            app_lower = app_name.lower()
            if app_lower in app_map:
                path = os.path.expandvars(app_map[app_lower])
                if path.endswith(':'):
                    os.startfile(path)
                else:
                    try:
                        os.startfile(path)
                    except OSError:
                        subprocess.Popen([path])
            else:
                os.startfile(app_name)
            return {"success": True, "message": f"Opened {app_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_app(self, app_name: str) -> dict[str, Any]:
        try:
            closed = []
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if app_name.lower() in proc.info['name'].lower():
                        proc.terminate()
                        closed.append(proc.info['name'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return {"success": True, "closed": closed}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_volume(self, level: int) -> dict[str, Any]:
        try:
            if self.volume:
                level = max(0, min(100, level))
                self.volume.SetMasterVolumeLevelScalar(level / 100, None)
                return {"success": True, "volume": level}
            return {"success": False, "error": "Audio control unavailable"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_volume(self) -> dict[str, Any]:
        try:
            if self.volume:
                vol = self.volume.GetMasterVolumeLevelScalar()
                return {"success": True, "volume": int(vol * 100)}
            return {"success": False}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def mute(self, mute: bool = True) -> dict[str, Any]:
        try:
            if self.volume:
                self.volume.SetMute(1 if mute else 0, None)
                return {"success": True, "muted": mute}
            return {"success": False}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def screenshot(self, filename: str = None) -> dict[str, Any]:
        try:
            import mss
            if not filename:
                filename = f"screenshot_{int(time.time())}.png"
            with mss.mss() as sct:
                sct.shot(output=filename)
            return {"success": True, "file": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def shutdown(self, delay: int = 0) -> dict[str, Any]:
        try:
            os.system(f"shutdown /s /t {delay}")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def restart(self, delay: int = 0) -> dict[str, Any]:
        try:
            os.system(f"shutdown /r /t {delay}")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def lock(self) -> dict[str, Any]:
        try:
            ctypes.windll.user32.LockWorkStation()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
