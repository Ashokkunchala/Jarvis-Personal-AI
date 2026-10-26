"""
Unified JARVIS - Terminal + UI + Full System Control + Android
"""

import asyncio
import logging
from typing import Dict, Any
import sys

from jarvis.control.system_controller import SystemController
from jarvis.android_bridge.adb_controller import AndroidController
from jarvis.core.agent.jarvis_agent import JarvisAgent
from jarvis.tools.registry import ToolRegistry
from jarvis.memory.vector_store import VectorMemory
from jarvis.config.settings import config

logger = logging.getLogger("jarvis.unified")


class JarvisUnified:
    def __init__(self):
        self.system = SystemController()
        self.android = AndroidController()
        self.agent = JarvisAgent()
        self.tools = ToolRegistry()
        self.memory = VectorMemory() if config.memory_enabled else None
        self.running = False
        
        logger.info("JARVIS Unified initialized")
        logger.info(f"System Control: ONLINE")
        logger.info(f"Android Devices: {len(self.android.devices)}")
    
    async def initialize(self):
        await self.agent.initialize()
        # Register system control tools
        self._register_system_tools()
        logger.info("All systems online")
    
    def _register_system_tools(self):
        # Add system control to tool registry
        pass
    
    async def process_command(self, command: str) -> Dict[str, Any]:
        """Process natural language command"""
        logger.info(f"Processing: {command}")
        cmd_lower = command.lower()
        
        # System commands
        if "open" in cmd_lower:
            # Extract app name
            for app in ["chrome", "edge", "firefox", "notepad", "calculator", "vscode", "cmd"]:
                if app in cmd_lower:
                    result = self.system.open_app(app)
                    return {"response": f"Opening {app}", "result": result}
        
        if "volume" in cmd_lower:
            if "up" in cmd_lower or "increase" in cmd_lower:
                vol = self.system.get_volume()
                if vol["success"]:
                    new_vol = min(100, vol["volume"] + 10)
                    self.system.set_volume(new_vol)
                    return {"response": f"Volume increased to {new_vol}%"}
            elif "down" in cmd_lower or "decrease" in cmd_lower:
                vol = self.system.get_volume()
                if vol["success"]:
                    new_vol = max(0, vol["volume"] - 10)
                    self.system.set_volume(new_vol)
                    return {"response": f"Volume decreased to {new_vol}%"}
            elif "mute" in cmd_lower:
                self.system.mute(True)
                return {"response": "Muted"}
            elif "unmute" in cmd_lower:
                self.system.mute(False)
                return {"response": "Unmuted"}
        
        if "screenshot" in cmd_lower:
            result = self.system.screenshot()
            return {"response": "Screenshot taken", "result": result}
        
        if "shutdown" in cmd_lower:
            self.system.shutdown(10)
            return {"response": "Shutting down in 10 seconds"}
        
        if "restart" in cmd_lower:
            self.system.restart(10)
            return {"response": "Restarting in 10 seconds"}
        
        if "lock" in cmd_lower:
            self.system.lock()
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
        
        # Default to agent
        return {"response": "Command processed", "command": command}
    
    async def start_realtime(self):
        """Start real-time voice mode"""
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
    print("\n" + "="*60)
    print("JARVIS UNIFIED SYSTEM ONLINE")
    print("="*60)
    print(f"System Control: READY")
    print(f"Android Devices: {len(jarvis.android.devices)}")
    print(f"Voice Mode: {'ENABLED' if config.wakeword_enabled else 'DISABLED'}")
    print("="*60)
    print("\nSay 'Hey JARVIS' or use terminal interface")
    print("Press Ctrl+C to exit\n")
    
    try:
        await jarvis.start_realtime()
    except KeyboardInterrupt:
        await jarvis.stop()


if __name__ == "__main__":
    asyncio.run(main())
