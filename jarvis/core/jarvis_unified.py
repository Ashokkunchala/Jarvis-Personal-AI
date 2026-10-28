"""
Unified JARVIS - realtime voice + system control + Android bridge.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from jarvis.android_bridge.adb_controller import AndroidController
from jarvis.config.settings import config
from jarvis.control.laptop import LaptopController
from jarvis.control.system_controller import SystemController
from jarvis.core.agent.jarvis_agent import JarvisAgent

logger = logging.getLogger("jarvis.unified")


class JarvisUnified:
    def __init__(self, on_event: Callable[[str, dict[str, Any]], None] | None = None):
        self.system = SystemController()
        self.laptop = LaptopController()
        self.android = AndroidController()
        self.agent = JarvisAgent(machine=self.laptop, on_event=on_event)
        self.memory = None  # created lazily; chromadb is optional and heavy
        self.running = False

        logger.info("JARVIS Unified initialized")
        logger.info("System Control: ONLINE")
        logger.info("Android Devices: %d", len(self.android.devices))

    async def initialize(self):
        await self.agent.initialize()
        logger.info("All systems online")

    @property
    def memory_store(self):
        if self.memory is None and config.memory_enabled:
            from jarvis.memory.vector_store import VectorMemory

            self.memory = VectorMemory()
        return self.memory

    async def process_command(self, command: str) -> dict[str, Any]:
        """Process natural language command (typed fallback, no server needed)."""
        logger.info("Processing: %s", command)
        cmd_lower = command.lower()

        # System commands
        if "open" in cmd_lower:
            for app in ["chrome", "edge", "firefox", "notepad", "calculator", "vscode", "cmd"]:
                if app in cmd_lower:
                    result = self.laptop.open_app(app)
                    return {"response": f"Opening {app}", "result": result}

        if "volume" in cmd_lower:
            if "up" in cmd_lower or "increase" in cmd_lower:
                vol = self.laptop.get_volume()
                if vol.get("success"):
                    new_vol = min(100, int(vol.get("volume", 0)) + 10)
                    self.laptop.set_volume(new_vol)
                    return {"response": f"Volume increased to {new_vol}%"}
            elif "down" in cmd_lower or "decrease" in cmd_lower:
                vol = self.laptop.get_volume()
                if vol.get("success"):
                    new_vol = max(0, int(vol.get("volume", 0)) - 10)
                    self.laptop.set_volume(new_vol)
                    return {"response": f"Volume decreased to {new_vol}%"}
            elif "mute" in cmd_lower:
                self.laptop.set_mute(True)
                return {"response": "Muted"}
            elif "unmute" in cmd_lower:
                self.laptop.set_mute(False)
                return {"response": "Unmuted"}

        if "screenshot" in cmd_lower:
            result = self.laptop.screenshot()
            return {"response": "Screenshot taken", "result": result}

        if "shutdown" in cmd_lower:
            self.laptop.shutdown(10)
            return {"response": "Shutting down in 10 seconds"}

        if "restart" in cmd_lower:
            self.laptop.restart(10)
            return {"response": "Restarting in 10 seconds"}

        if "lock" in cmd_lower:
            self.laptop.lock()
            return {"response": "Locking system"}

        # Android commands
        if "android" in cmd_lower and self.android.devices:
            if "screenshot" in cmd_lower:
                result = self.android.screenshot()
                return {"response": "Android screenshot taken", "result": result}
            if "home" in cmd_lower:
                self.android.home()
                return {"response": "Pressed home on Android"}
            if "back" in cmd_lower:
                self.android.back()
                return {"response": "Pressed back on Android"}

        return {"response": "Command processed", "command": command}

    async def start_realtime(self):
        """Start real-time voice mode (blocks until cancelled)."""
        self.running = True
        logger.info("Starting real-time JARVIS mode...")
        await self.agent.start()

    async def stop(self):
        self.running = False
        await self.agent.stop()
        logger.info("JARVIS stopped")


async def main():
    logging.basicConfig(level=logging.INFO)
    jarvis = JarvisUnified()
    await jarvis.initialize()
    print("\n" + "=" * 60)
    print("JARVIS UNIFIED SYSTEM ONLINE")
    print("=" * 60)
    print("System Control: READY")
    print(f"Android Devices: {len(jarvis.android.devices)}")
    print(f"Voice Mode: {'ENABLED' if config.wakeword_enabled else 'DISABLED'}")
    print("=" * 60)
    print("\nSay 'Hey JARVIS' or use terminal interface")
    print("Press Ctrl+C to exit\n")

    try:
        await jarvis.start_realtime()
    except KeyboardInterrupt:
        await jarvis.stop()


if __name__ == "__main__":
    asyncio.run(main())
