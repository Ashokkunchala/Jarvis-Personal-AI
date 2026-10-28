"""Realtime voice agent: wake word -> Gemini Live session -> local tools -> sleep.

State machine
-------------
sleeping  microphone frames only feed the local "hey jarvis" wake-word model.
awake     microphone frames stream to Gemini Live; replies play through the
          speaker; model tool calls run against the local machine. After a
          configurable idle timeout with nothing said or played, JARVIS goes
          back to sleep and waits for the wake word again.

Everything that must run on the asyncio loop is marshalled off the PortAudio
callback thread with ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from jarvis.config.settings import config
from jarvis.core.agent.voice_tools import (
    TOOL_DECLARATIONS,
    build_tool_executor,
    response_payload,
)
from jarvis.core.audio.audio_io import AudioIO
from jarvis.core.vad.vad_processor import VADProcessor
from jarvis.core.voice.gemini_live_client import GeminiLiveClient
from jarvis.core.wakeword.wakeword_detector import WakeWordDetector

logger = logging.getLogger("jarvis.agent")

SLEEPING = "sleeping"
AWAKE = "awake"

EventCallback = Callable[[str, dict[str, Any]], None] | None


class JarvisAgent:
    def __init__(self, machine: Any = None, on_event: EventCallback = None):
        self.machine = machine
        self.on_event = on_event
        self.audio = AudioIO(
            sample_rate=config.sample_rate,
            channels=config.channels,
            chunk_size=config.chunk_size,
        )
        self.vad = VADProcessor(
            aggressiveness=config.vad_aggressiveness, sample_rate=config.sample_rate
        )
        self.wakeword = WakeWordDetector(threshold=config.wakeword_threshold)
        self.live_client: GeminiLiveClient | None = None
        self._tool_executor = build_tool_executor(machine) if machine else None

        self.state = SLEEPING
        self.is_listening = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mic_queue: asyncio.Queue[bytes] | None = None
        self._pump_task: asyncio.Task | None = None
        self._last_activity = 0.0
        self._frames = 0

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        logger.info("Initializing JARVIS voice agent...")
        self.audio.start_output(config.live_output_sample_rate)
        self._mic_queue = asyncio.Queue(maxsize=100)

        if config.use_gemini_live and config.gemini_api_key:
            tools = (
                TOOL_DECLARATIONS
                if config.voice_tools_enabled and self._tool_executor is not None
                else None
            )
            self.live_client = GeminiLiveClient(
                api_key=config.gemini_api_key,
                model=config.gemini_live_model,
                voice=config.gemini_live_voice,
                tools=tools,
                output_sample_rate=config.live_output_sample_rate,
            )
            self.live_client.on_ready = self._on_ready
            self.live_client.on_audio = self._on_audio
            self.live_client.on_text = self._on_text
            self.live_client.on_transcript = self._on_transcript
            self.live_client.on_turn_complete = self._on_turn_complete
            self.live_client.on_interrupted = self._on_interrupted
            self.live_client.on_tool_call = self._on_tool_call
            self.live_client.on_error = self._on_error
            connected = await self.live_client.connect()
            if not connected:
                raise RuntimeError(
                    "Could not open a Gemini Live voice session - check "
                    "GEMINI_API_KEY and GEMINI_LIVE_MODEL in .env"
                )
        else:
            logger.warning(
                "Gemini Live disabled or GEMINI_API_KEY missing - voice replies are off"
            )

        self._pump_task = asyncio.create_task(self._mic_pump())
        logger.info("JARVIS voice agent initialized")

    async def start(self) -> None:
        """Run the realtime loop until cancelled."""
        self._loop = asyncio.get_running_loop()
        self.is_listening = True
        self.audio.start_input(self.on_audio_frame)
        self._emit(
            "ready",
            {
                "wake_word": "hey jarvis" if config.wakeword_enabled else "voice start",
                "model": config.gemini_live_model,
                "tools": len(TOOL_DECLARATIONS)
                if config.voice_tools_enabled and self._tool_executor
                else 0,
                "awake_timeout": config.awake_timeout_seconds,
            },
        )
        logger.info("Always listening for 'Hey JARVIS'...")
        try:
            while True:
                await asyncio.sleep(0.2)
                await self._check_idle()
        except asyncio.CancelledError:
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        self.is_listening = False
        try:
            self.audio.stop_input()
        except Exception:  # noqa: BLE001
            pass
        if self._pump_task:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._pump_task = None
        if self.live_client:
            await self.live_client.disconnect()
        self.audio.stop_output()
        self.state = SLEEPING
        logger.info("JARVIS agent stopped")

    # ------------------------------------------------------------------
    # microphone path (PortAudio thread)
    # ------------------------------------------------------------------
    def on_audio_frame(self, audio_data: np.ndarray) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        if audio_data.dtype == np.float32:
            pcm = (np.clip(audio_data, -1.0, 1.0) * 32767.0).astype(np.int16)
        else:
            pcm = np.asarray(audio_data, dtype=np.int16)
        pcm = pcm.reshape(-1)

        self._frames += 1

        if self.state == SLEEPING:
            if not config.wakeword_enabled:
                return
            detected, score = self.wakeword.detect(pcm)
            if detected:
                try:
                    loop.call_soon_threadsafe(
                        asyncio.create_task, self._wake(float(score))
                    )
                except RuntimeError:
                    pass
            return

        # Awake: keep the live stream fed in real time (silence included so the
        # server-side VAD can spot the end of a turn and enable barge-in).
        try:
            loop.call_soon_threadsafe(self._enqueue_mic, pcm.tobytes())
        except RuntimeError:
            return
        if self.vad.is_speech(pcm):
            self._last_activity = time.monotonic()

    def _enqueue_mic(self, payload: bytes) -> None:
        queue = self._mic_queue
        if queue is None or self.state != AWAKE:
            return
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()  # drop the oldest frame, keep it real-time
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def _mic_pump(self) -> None:
        assert self._mic_queue is not None
        while True:
            payload = await self._mic_queue.get()
            if self.state != AWAKE or not self.live_client:
                continue
            await self.live_client.send_audio(payload)

    # ------------------------------------------------------------------
    # state transitions
    # ------------------------------------------------------------------
    async def _wake(self, confidence: float) -> None:
        if self.state != SLEEPING or not self.is_listening:
            return
        self.state = AWAKE
        self._last_activity = time.monotonic()
        self.vad.reset()
        self.wakeword.reset()
        self.audio.play_chime()
        self._emit("wake", {"confidence": round(confidence, 3)})
        logger.info("Wake word detected (score %.3f) - JARVIS is awake", confidence)

    async def _sleep(self) -> None:
        if self.state != AWAKE:
            return
        self.state = SLEEPING
        if self._mic_queue:
            while True:
                try:
                    self._mic_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        self.audio.clear_output()
        self.vad.reset()
        self._emit("sleep", {})
        logger.info("JARVIS went back to sleep")

    async def _check_idle(self) -> None:
        if self.state != AWAKE:
            return
        if self.audio.output_pending():
            return  # still speaking
        if time.monotonic() - self._last_activity >= config.awake_timeout_seconds:
            await self._sleep()

    # ------------------------------------------------------------------
    # live session callbacks
    # ------------------------------------------------------------------
    async def _on_ready(self) -> None:
        self._emit("live_ready", {"model": config.gemini_live_model})

    async def _on_audio(self, data: bytes, sample_rate: int) -> None:
        self._last_activity = time.monotonic()
        self.audio.enqueue(data, sample_rate=sample_rate)

    async def _on_text(self, text: str) -> None:
        self._last_activity = time.monotonic()
        self._emit("text", {"text": text})

    async def _on_transcript(self, source: str, text: str) -> None:
        self._last_activity = time.monotonic()
        self._emit("transcript", {"source": source, "text": text})

    async def _on_turn_complete(self) -> None:
        self._last_activity = time.monotonic()
        self._emit("turn_complete", {})

    async def _on_interrupted(self) -> None:
        self.audio.clear_output()
        self._emit("interrupted", {})

    async def _on_error(self, message: str) -> None:
        self._emit("error", {"message": message})

    async def _on_tool_call(self, call) -> dict[str, Any]:
        name = call.name or "unknown"
        args = dict(call.args or {})
        executor = self._tool_executor
        if executor is None:
            result: dict[str, Any] = {"success": False, "error": "device tools are disabled"}
        else:
            result = await asyncio.to_thread(executor, name, args)
        self._last_activity = time.monotonic()
        self._emit("tool", {"name": name, "args": args, "result": result})
        return response_payload(result)

    # ------------------------------------------------------------------
    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(kind, payload)
        except Exception:  # noqa: BLE001
            logger.exception("event handler failed for %s", kind)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from jarvis.control.laptop import LaptopController

    agent = JarvisAgent(machine=LaptopController())
    await agent.initialize()
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
