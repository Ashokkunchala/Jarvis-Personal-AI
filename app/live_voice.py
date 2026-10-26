"""Authenticated WebSocket bridge for real-time Gemini Live audio.

The provider API key stays on the server. Clients send compact JSON envelopes:
{"type":"audio","data":"<base64 PCM16 16kHz mono>"}
{"type":"text","text":"..."}
{"type":"stop"}
{"type":"ping"}

Server events are JSON:
{"type":"ready","input_mime":"audio/pcm;rate=16000","output_sample_rate":24000}
{"type":"audio","data":"<base64 PCM16 24kHz mono>"}
{"type":"text","text":"..."}
{"type":"transcript","text":"...","source":"user|assistant"}
{"type":"turn_complete"}
{"type":"error","message":"..."}

This is a server-brokered session: the caller never receives the Gemini key.
Keep the API bound to localhost until HTTPS, per-device auth, rate limits, and
abuse controls are deployed.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from starlette.websockets import WebSocketState

from app.config import get_settings
from app.personal_data import require_device_token
from app.personality import SYSTEM_INSTRUCTIONS

logger = logging.getLogger("jarvis.live_voice")
router = APIRouter()

MAX_AUDIO_BYTES = 64 * 1024
MAX_TEXT_CHARS = 4000
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
VOICE = "Aoede"


async def _send(websocket: WebSocket, payload: dict) -> bool:
    if websocket.client_state != WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_text(json.dumps(payload, ensure_ascii=False))
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


@router.websocket("/api/live-voice")
async def live_voice(websocket: WebSocket):
    """Create one authenticated, bidirectional voice session per WebSocket."""
    try:
        # Browsers may not attach Authorization headers to WebSocket upgrades.
        # Require the same token in a short-lived URL token only until the
        # session broker can use signed one-time session tickets.
        supplied = websocket.query_params.get("token", "")
        require_device_token(authorization=f"Bearer {supplied}" if supplied else None)
    except Exception:
        await websocket.close(code=4401, reason="unauthorized")
        return

    settings = get_settings()
    if not settings.gemini_api_key or settings.gemini_api_key.startswith("replace_"):
        await websocket.close(code=1013, reason="Gemini API is not configured")
        return

    await websocket.accept()
    client = genai.Client(api_key=settings.gemini_api_key)
    session = None
    receive_task: asyncio.Task | None = None
    try:
        config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": SYSTEM_INSTRUCTIONS + (
                "\nSpeak naturally and concisely as JARVIS, a personal assistant. "
                "Do not claim an action was performed unless the connected tool reports success. "
                "For consequential actions, ask for explicit confirmation."
            ),
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": VOICE}}
            },
            "input_audio_transcription": {},
            "output_audio_transcription": {},
        }
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            await _send(websocket, {
                "type": "ready",
                "model": MODEL,
                "input_mime": "audio/pcm;rate=16000",
                "output_sample_rate": 24000,
                "voice": VOICE,
            })

            async def pump_provider():
                try:
                    async for response in session.receive():
                        server_content = getattr(response, "server_content", None)
                        if server_content:
                            input_tx = getattr(server_content, "input_transcription", None)
                            if input_tx and getattr(input_tx, "text", None):
                                await _send(websocket, {
                                    "type": "transcript",
                                    "source": "user",
                                    "text": input_tx.text,
                                })
                            output_tx = getattr(server_content, "output_transcription", None)
                            if output_tx and getattr(output_tx, "text", None):
                                await _send(websocket, {
                                    "type": "transcript",
                                    "source": "assistant",
                                    "text": output_tx.text,
                                })
                            model_turn = getattr(server_content, "model_turn", None)
                            if model_turn:
                                for part in getattr(model_turn, "parts", []) or []:
                                    inline = getattr(part, "inline_data", None)
                                    data = getattr(inline, "data", None) if inline else None
                                    if data:
                                        if isinstance(data, str):
                                            encoded = data
                                        else:
                                            encoded = base64.b64encode(data).decode("ascii")
                                        await _send(websocket, {"type": "audio", "data": encoded})
                                    txt = getattr(part, "text", None)
                                    if txt:
                                        await _send(websocket, {"type": "text", "text": txt})
                            if getattr(server_content, "interrupted", False):
                                await _send(websocket, {"type": "interrupted"})
                            if getattr(server_content, "turn_complete", False):
                                await _send(websocket, {"type": "turn_complete"})
                        tool_call = getattr(response, "tool_call", None)
                        if tool_call:
                            # No device actions are executed by the voice socket.
                            # A separate confirmed tool broker is required.
                            await _send(websocket, {
                                "type": "error",
                                "message": "Voice-session tool calls are not enabled. Use the confirmed JARVIS action flow.",
                            })
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Gemini Live receive loop failed")
                    await _send(websocket, {"type": "error", "message": "Live voice connection ended. Reconnect and retry."})

            receive_task = asyncio.create_task(pump_provider())
            while True:
                raw = await websocket.receive_text()
                if len(raw) > (MAX_AUDIO_BYTES * 2):
                    await _send(websocket, {"type": "error", "message": "Frame too large."})
                    continue
                try:
                    message = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    await _send(websocket, {"type": "error", "message": "Invalid JSON message."})
                    continue
                if not isinstance(message, dict):
                    await _send(websocket, {"type": "error", "message": "Expected a JSON object."})
                    continue
                kind = message.get("type")
                if kind == "ping":
                    await _send(websocket, {"type": "pong"})
                elif kind == "stop":
                    # Stop local playback and provider response; fresh speech may follow.
                    await session.send_realtime_input(text="Stop speaking now.")
                elif kind == "text":
                    text = message.get("text")
                    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
                        await _send(websocket, {"type": "error", "message": "Text is empty or too long."})
                        continue
                    await session.send_realtime_input(text=text.strip())
                elif kind == "audio":
                    encoded = message.get("data")
                    if not isinstance(encoded, str) or len(encoded) > ((MAX_AUDIO_BYTES + 2) // 3) * 4 + 8:
                        await _send(websocket, {"type": "error", "message": "Invalid or oversized audio frame."})
                        continue
                    try:
                        pcm = base64.b64decode(encoded, validate=True)
                    except (binascii.Error, ValueError):
                        await _send(websocket, {"type": "error", "message": "Audio data is not valid base64."})
                        continue
                    if not pcm or len(pcm) > MAX_AUDIO_BYTES or len(pcm) % 2:
                        await _send(websocket, {"type": "error", "message": "Audio must be non-empty PCM16 frames within the frame limit."})
                        continue
                    await session.send_realtime_input(
                        audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
                    )
                elif kind == "audio_end":
                    await session.send_realtime_input(audio_stream_end=True)
                else:
                    await _send(websocket, {"type": "error", "message": "Unknown message type."})
    except WebSocketDisconnect:
        logger.debug("Live voice client disconnected")
    except Exception:
        logger.exception("Live voice session failed")
        await _send(websocket, {"type": "error", "message": "Live voice session failed. Check server configuration."})
    finally:
        if receive_task and not receive_task.done():
            receive_task.cancel()
            try:
                await receive_task
            except (asyncio.CancelledError, Exception):
                pass
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass
