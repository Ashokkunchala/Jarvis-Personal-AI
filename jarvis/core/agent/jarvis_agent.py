import asyncio
import logging
from typing import Dict, Any, List, Optional
import json
from datetime import datetime

from jarvis.config.settings import config
from jarvis.core.audio.audio_io import AudioIO
from jarvis.core.vad.vad_processor import VADProcessor
from jarvis.core.wakeword.wakeword_detector import WakeWordDetector
from jarvis.core.voice.gemini_live_client import GeminiLiveClient

logger = logging.getLogger("jarvis.agent")


class JarvisAgent:
    def __init__(self):
        self.audio = AudioIO(sample_rate=config.sample_rate, channels=config.channels, chunk_size=config.chunk_size)
        self.vad = VADProcessor(aggressiveness=config.vad_aggressiveness, sample_rate=config.sample_rate)
        self.wakeword = WakeWordDetector(threshold=config.wakeword_threshold)
        self.live_client = None
        self.is_listening = False
        self.is_awake = False
        self.conversation_active = False
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._audio_frame_count = 0
        
    async def initialize(self):
        logger.info("Initializing JARVIS Agent...")
        if config.use_gemini_live and config.gemini_api_key:
            self.live_client = GeminiLiveClient(config.gemini_api_key)
            self.live_client.on_audio_received = self.on_audio_received
            self.live_client.on_text_received = self.on_text_received
            self.live_client.on_turn_complete = self.on_turn_complete
            await self.live_client.connect()
        logger.info("JARVIS Agent initialized")
    
    async def start(self):
        logger.info("Starting JARVIS - Always listening for 'Hey JARVIS'...")
        self._event_loop = asyncio.get_running_loop()
        self.audio.start_input(self.on_audio_frame)
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Shutting down JARVIS...")
            await self.stop()
    
    def on_audio_frame(self, audio_data):
        """Process each audio frame"""
        # Convert to int16 for processing
        import numpy as np
        self._audio_frame_count += 1
        if self._audio_frame_count % 50 == 0:
            level = float(np.sqrt(np.mean(np.square(audio_data, dtype=np.float64))))
            logger.info("Microphone input level %.4f", level)
        if audio_data.dtype == np.float32:
            audio_int16 = (audio_data * 32768).astype(np.int16)
        else:
            audio_int16 = audio_data
        
        if not self.is_awake and config.wakeword_enabled:
            # Check for wake word
            detected, score = self.wakeword.detect(audio_int16)
            if detected:
                logger.info("Wake word detected! JARVIS is awake.")
                self.is_awake = True
                self.conversation_active = True
                self.vad.reset()
                self.wakeword.reset()
                # Play acknowledgment sound or just listen
                self._schedule_coroutine(self.acknowledge_wake())
                return
        
        if self.is_awake:
            # Process with VAD
            is_speech, utterance_complete, utterance = self.vad.process_frame(audio_int16)
            if utterance_complete and utterance is not None:
                logger.info("Utterance captured, sending to JARVIS...")
                self._schedule_coroutine(self.process_utterance(utterance))
                self.is_awake = False  # Go back to wake word listening
                self.conversation_active = False

    def _schedule_coroutine(self, coroutine) -> None:
        """Schedule work from sounddevice's callback thread onto the agent loop."""
        loop = self._event_loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(asyncio.create_task, coroutine)
        else:
            coroutine.close()
    
    async def acknowledge_wake(self):
        """Acknowledge wake word detection"""
        # Could play a sound or send a quick response
        if self.live_client and self.live_client.connected:
            await self.live_client.send_text("Yes sir?")
    
    async def process_utterance(self, audio_data):
        """Process user utterance"""
        if self.live_client and self.live_client.connected:
            await self.live_client.send_audio(audio_data)
        else:
            logger.warning("No live client connected")
    
    async def on_audio_received(self, audio_data):
        """Handle audio response from Gemini"""
        logger.debug("Playing audio response")
        self.audio.play_audio(audio_data)
    
    async def on_text_received(self, text):
        """Handle text response from Gemini"""
        logger.info(f"JARVIS: {text}")
        # Could display in overlay
        
    async def on_turn_complete(self):
        """Turn completed"""
        logger.debug("Turn complete")
    
    async def stop(self):
        self.audio.stop_input()
        if self.live_client:
            await self.live_client.disconnect()
        logger.info("JARVIS stopped")


async def main():
    agent = JarvisAgent()
    await agent.initialize()
    await agent.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
