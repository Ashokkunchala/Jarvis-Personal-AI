"""Gemini Live session wrapper for the local realtime voice loop.

Uses the official google-genai bidirectional session so the local agent can:
  * stream 16 kHz PCM16 microphone frames to the model,
  * play back streamed audio (24 kHz PCM16 by default),
  * read user/model transcripts,
  * run local tool calls requested by the model.

The API key never leaves this process.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import numpy as np
from google import genai
from google.genai import types

logger = logging.getLogger("jarvis.gemini_live")

DEFAULT_PERSONA = """
You are JARVIS, a real-time voice assistant running locally on the user's computer.
Personality: warm, witty, concise and loyal — like Tony Stark's JARVIS. Speak naturally.
Language: use natural Indian English by default; understand Telugu and code-switch when
the user does; reply in the language the user uses.

Rules:
- You are in a live microphone conversation. Keep spoken replies short (1-3 sentences)
  unless the user asks for detail.
- You have local device tools (open apps, volume, screenshots, status, window focus,
  lock screen, current time). Use them when the user asks for an action.
- Never claim an action happened unless the tool reports success; if a tool fails,
  say so plainly.
- Do not ask for passwords, API keys or secrets.
- If the user's request is ambiguous or consequential, ask a short clarifying question
  instead of guessing.
""".strip()


class GeminiLiveClient:
    """Thin async wrapper around one google-genai Live session."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.8-live",
        voice: str = "Aoede",
        system_instruction: str = DEFAULT_PERSONA,
        tools: list[dict[str, Any]] | None = None,
        output_sample_rate: int = 24000,
        manual_activity_detection: bool = False,
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.system_instruction = system_instruction
        self.tools = tools or []
        self.output_sample_rate = output_sample_rate
        # When True the server-side VAD is disabled and the client must send
        # activity_start/activity_end around each user utterance.
        self.manual_activity_detection = manual_activity_detection

        self.connected = False
        self._client: genai.Client | None = None
        self._session: Any | None = None
        self._session_cm: Any | None = None
        self._receive_task: asyncio.Task | None = None

        # Callbacks (may be async); assigned by the agent.
        self.on_ready: Callable[[], Awaitable[None] | None] | None = None
        self.on_audio: Callable[[bytes, int], Awaitable[None] | None] | None = None
        self.on_text: Callable[[str], Awaitable[None] | None] | None = None
        self.on_transcript: Callable[[str, str], Awaitable[None] | None] | None = None
        self.on_turn_complete: Callable[[], Awaitable[None] | None] | None = None
        self.on_interrupted: Callable[[], Awaitable[None] | None] | None = None
        self.on_tool_call: Callable[[types.FunctionCall], Awaitable[dict]] | None = None
        self.on_error: Callable[[str], Awaitable[None] | None] | None = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    async def connect(self) -> bool:
        if not self.api_key:
            logger.error("Gemini API key is not configured")
            return False
        base_config: dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "system_instruction": self.system_instruction,
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": self.voice}}
            },
        }
        full_config: dict[str, Any] = {
            **base_config,
            "input_audio_transcription": {},
            "output_audio_transcription": {},
        }
        if self.tools:
            full_config["tools"] = [{"function_declarations": self.tools}]
            base_config["tools"] = [{"function_declarations": self.tools}]
        if self.manual_activity_detection:
            manual_cfg = {
                "automatic_activity_detection": {"disabled": True},
            }
            full_config["realtime_input_config"] = manual_cfg
            base_config["realtime_input_config"] = manual_cfg

        # Some preview models reject transcription or voice settings; fall back
        # to a minimal audio session rather than failing outright.
        attempts = [full_config, base_config]
        last_error: Exception | None = None
        for config in attempts:
            try:
                self._client = genai.Client(api_key=self.api_key)
                # connect() is an async context manager; enter it manually so
                # the session outlives this method (closed in disconnect()).
                self._session_cm = self._client.aio.live.connect(
                    model=self.model, config=config
                )
                self._session = await self._session_cm.__aenter__()
                self.connected = True
                self._receive_task = asyncio.create_task(self._receive_loop())
                logger.info(
                    "Connected to Gemini Live (model=%s, voice=%s)",
                    self.model,
                    self.voice,
                )
                await self._emit(self.on_ready)
                return True
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Gemini Live connect attempt failed: %s", exc)
                self._session = None
                self._session_cm = None
                if self._client is not None:
                    try:
                        await self._client.aio.aclose()
                    except Exception:  # noqa: BLE001
                        pass
                    self._client = None
        logger.error("Failed to connect to Gemini Live: %s", last_error)
        self.connected = False
        await self._emit(self.on_error, f"Gemini Live connect failed: {last_error}")
        return False

    async def disconnect(self) -> None:
        task = self._receive_task
        self._receive_task = None
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        session_cm, self._session_cm = self._session_cm, None
        self._session = None
        client, self._client = self._client, None
        self.connected = False
        try:
            if session_cm is not None:
                await session_cm.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        try:
            if client is not None:
                await client.aio.aclose()
        except Exception:  # noqa: BLE001
            pass
        logger.info("Disconnected from Gemini Live")

    # ------------------------------------------------------------------
    # sending
    # ------------------------------------------------------------------
    async def send_audio(self, audio: np.ndarray | bytes) -> None:
        """Stream one PCM16 mono chunk (16 kHz) to the model."""
        if not self.connected or self._session is None:
            return
        if isinstance(audio, np.ndarray):
            if audio.dtype == np.float32:
                audio = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
            else:
                audio = audio.astype(np.int16, copy=False)
            payload = audio.tobytes()
        else:
            payload = audio
        if not payload:
            return
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(data=payload, mime_type="audio/pcm;rate=16000")
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("send_audio failed: %s", exc)

    async def send_text(self, text: str) -> None:
        if not self.connected or self._session is None:
            return
        try:
            await self._session.send_realtime_input(text=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("send_text failed: %s", exc)

    async def activity_start(self) -> None:
        """Mark the start of user speech (manual activity detection only)."""
        if not self.connected or self._session is None:
            return
        try:
            await self._session.send_realtime_input(activity_start={})
        except Exception as exc:  # noqa: BLE001
            logger.warning("activity_start failed: %s", exc)

    async def activity_end(self) -> None:
        """Mark the end of user speech; the model replies after this."""
        if not self.connected or self._session is None:
            return
        try:
            await self._session.send_realtime_input(activity_end={})
        except Exception as exc:  # noqa: BLE001
            logger.warning("activity_end failed: %s", exc)

    # ------------------------------------------------------------------
    # receiving
    # ------------------------------------------------------------------
    async def _receive_loop(self) -> None:
        assert self._session is not None
        try:
            # AsyncSession.receive() ends its generator after every
            # turn_complete, so re-enter it for each subsequent turn.
            while self.connected and self._session is not None:
                async for message in self._session.receive():
                    await self._handle_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Gemini Live receive loop ended: %s", exc)
            await self._emit(self.on_error, f"Live session ended: {exc}")
        finally:
            self.connected = False

    async def _handle_message(self, message: types.LiveServerMessage) -> None:
        if message.setup_complete:
            logger.info("Gemini Live setup complete")

        content = message.server_content
        if content:
            input_tx = getattr(content, "input_transcription", None)
            if input_tx and getattr(input_tx, "text", None):
                await self._emit(self.on_transcript, "user", input_tx.text)
            output_tx = getattr(content, "output_transcription", None)
            if output_tx and getattr(output_tx, "text", None):
                await self._emit(self.on_transcript, "assistant", output_tx.text)

            model_turn = getattr(content, "model_turn", None)
            if model_turn:
                for part in getattr(model_turn, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    data = getattr(inline, "data", None) if inline else None
                    if data:
                        raw = data if isinstance(data, bytes) else base64.b64decode(data)
                        await self._emit(self.on_audio, raw, self.output_sample_rate)
                    text = getattr(part, "text", None)
                    if text:
                        await self._emit(self.on_text, text)

            if getattr(content, "interrupted", False):
                await self._emit(self.on_interrupted)
            if getattr(content, "turn_complete", False):
                await self._emit(self.on_turn_complete)

        if message.tool_call:
            await self._handle_tool_call(message.tool_call)
        if message.tool_call_cancellation:
            logger.info("Tool call cancelled by model: %s", message.tool_call_cancellation)

        if message.go_away:
            logger.warning("Gemini Live asked the client to go away: %s", message.go_away)

    async def _handle_tool_call(self, tool_call: types.LiveServerToolCall) -> None:
        responses: list[types.FunctionResponse] = []
        for call in tool_call.function_calls or []:
            name = call.name or "unknown"
            args = dict(call.args or {})
            result: dict[str, Any]
            if self.on_tool_call is None:
                result = {"success": False, "error": f"tool {name} is not wired up"}
            else:
                try:
                    result = await self.on_tool_call(call) or {}
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Tool %s failed", name)
                    result = {"success": False, "error": str(exc)}
            logger.info("Tool %s(%s) -> %s", name, args, result)
            responses.append(
                types.FunctionResponse(id=call.id, name=name, response=result)
            )
        if responses and self._session is not None:
            try:
                await self._session.send_tool_response(function_responses=responses)
            except Exception as exc:  # noqa: BLE001
                logger.warning("send_tool_response failed: %s", exc)

    # ------------------------------------------------------------------
    async def _emit(self, callback, *args) -> None:
        if callback is None:
            return
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                await result
        except Exception:  # noqa: BLE001
            logger.exception("Live client callback failed")
