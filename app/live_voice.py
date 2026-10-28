"""Authenticated WebSocket bridge for real-time Gemini Live audio.

The provider API key stays on the server. A client uses a short-lived session
connection to exchange 16 kHz PCM16 mono frames for streamed 24 kHz PCM16 audio.

JSON client frames:
  {"type":"audio","data":"<base64 PCM16 16kHz mono>"}
  {"type":"text","text":"..."}
  {"type":"audio_end"}
  {"type":"stop"}
  {"type":"ping"}

JSON server events:
  ready, audio, text, transcript, turn_complete, interrupted, error

This is a server-brokered session; the client never receives the Gemini key.
The browser exchanges its bearer token for a single-use, 60-second WebSocket ticket.
Keep the server private until HTTPS, rate limits, and production device pairing are in place.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import secrets
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
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
LIVE_TICKET_TTL_SECONDS = 60
_live_tickets: dict[str, float] = {}


def _issue_live_ticket() -> str:
    """Issue a one-use, short-lived WebSocket ticket."""
    now = time.monotonic()
    for ticket, expires_at in list(_live_tickets.items()):
        if expires_at <= now:
            _live_tickets.pop(ticket, None)
    ticket = secrets.token_urlsafe(32)
    _live_tickets[ticket] = now + LIVE_TICKET_TTL_SECONDS
    return ticket


def _consume_live_ticket(ticket: str) -> bool:
    """Consume a ticket exactly once and reject missing or expired tickets."""
    expires_at = _live_tickets.pop(ticket, None)
    return expires_at is not None and expires_at > time.monotonic()


@router.post("/api/live-voice-ticket", dependencies=[Depends(require_device_token)])
def create_live_voice_ticket():
    """Mint a 60-second single-use ticket after bearer-token authentication."""
    return {"ticket": _issue_live_ticket(), "expires_in": LIVE_TICKET_TTL_SECONDS}


def _origin_is_allowed(origin: str | None, host: str | None, allowed_origins: set[str]) -> bool:
    """Allow configured origins and the exact same-origin app served by this backend."""
    if not origin:
        return True  # Native clients still require the device token below.
    if origin in allowed_origins:
        return True
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and bool(host) and parsed.netloc == host


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
    settings = get_settings()
    expected_origins = set(settings.allowed_origins)
    origin = websocket.headers.get("origin")
    # The UI is served by this same backend in the default deployment, so its
    # own origin (e.g. http://127.0.0.1:8000) must work even when CORS lists
    # only a separate development frontend. Other origins must be explicitly allowed.
    if not _origin_is_allowed(origin, websocket.headers.get("host"), expected_origins):
        await websocket.close(code=4403, reason="origin not allowed")
        return

    ticket = websocket.query_params.get("ticket", "")
    if not ticket or not _consume_live_ticket(ticket):
        await websocket.close(code=4401, reason="invalid or expired session ticket")
        return

    if not settings.gemini_api_key or settings.gemini_api_key.startswith("replace_"):
        await websocket.close(code=1013, reason="Gemini API is not configured")
        return

    await websocket.accept()
    client = genai.Client(api_key=settings.gemini_api_key)
    receive_task: asyncio.Task | None = None
    try:
        config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": SYSTEM_INSTRUCTIONS + (
                "\nSpeak naturally and concisely as JARVIS, a personal assistant. "
                "Do not claim an action was performed unless the connected tool reports success. "
                "For consequential actions, ask for explicit confirmation."
            ),
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": settings.gemini_live_voice}}},
            "input_audio_transcription": {},
            "output_audio_transcription": {},
        }
        async with client.aio.live.connect(model=settings.gemini_live_model, config=config) as session:
            await _send(websocket, {
                "type": "ready",
                "model": settings.gemini_live_model,
                "input_mime": "audio/pcm;rate=16000",
                "output_sample_rate": 24000,
                "voice": settings.gemini_live_voice,
            })

            async def pump_provider():
                try:
                    # session.receive() ends its generator after every
                    # turn_complete; re-enter it so later turns keep flowing.
                    while True:
                        async for response in session.receive():
                            server_content = getattr(response, "server_content", None)
                            if not server_content:
                                continue
                            input_tx = getattr(server_content, "input_transcription", None)
                            if input_tx and getattr(input_tx, "text", None):
                                await _send(websocket, {"type": "transcript", "source": "user", "text": input_tx.text})
                            output_tx = getattr(server_content, "output_transcription", None)
                            if output_tx and getattr(output_tx, "text", None):
                                await _send(websocket, {"type": "transcript", "source": "assistant", "text": output_tx.text})
                            model_turn = getattr(server_content, "model_turn", None)
                            if model_turn:
                                for part in getattr(model_turn, "parts", []) or []:
                                    inline = getattr(part, "inline_data", None)
                                    data = getattr(inline, "data", None) if inline else None
                                    if data:
                                        encoded = data if isinstance(data, str) else base64.b64encode(data).decode("ascii")
                                        await _send(websocket, {"type": "audio", "data": encoded})
                                    text_part = getattr(part, "text", None)
                                    if text_part:
                                        await _send(websocket, {"type": "text", "text": text_part})
                            if getattr(server_content, "interrupted", False):
                                await _send(websocket, {"type": "interrupted"})
                            if getattr(server_content, "turn_complete", False):
                                await _send(websocket, {"type": "turn_complete"})
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Gemini Live receive loop failed")
                    await _send(websocket, {"type": "error", "message": "Live voice connection ended. Reconnect and retry."})
                finally:
                    await _send(websocket, {"type": "closed"})

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
                    # Server-side voice activity should interrupt the model. The UI
                    # must also stop/flush local audio playback immediately.
                    await session.send_realtime_input(text="Stop speaking now.")
                elif kind == "text":
                    text = message.get("text")
                    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
                        await _send(websocket, {"type": "error", "message": "Text is empty or too long."})
                        continue
                    await session.send_realtime_input(text=text.strip())
                elif kind == "audio":
                    encoded = message.get("data")
                    max_encoded_size = ((MAX_AUDIO_BYTES + 2) // 3) * 4 + 8
                    if not isinstance(encoded, str) or len(encoded) > max_encoded_size:
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
                    await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))
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
