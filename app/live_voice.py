"""Authenticated WebSocket bridge for real-time Gemini Live audio.

The provider API key stays on the server. A client uses a short-lived session
connection to exchange 16 kHz PCM16 mono frames for streamed 24 kHz PCM16 audio.

JSON client frames:
  {"type":"audio","data":"<base64 PCM16 16kHz mono>"}
  {"type":"text","text":"..."}
  {"type":"audio_end"}
  {"type":"stop"}
  {"type":"ping"}
  {"type":"approval","id":"<request id>","approve":true|false}

A state-changing voice tool (create_reminder) is held until the client answers
an approval_request. No answer within APPROVAL_TIMEOUT_SECONDS, a disconnect, or
anything other than approve=true is a denial.

JSON server events:
  ready, audio, text, transcript, turn_complete, interrupted, tool, approval_request, error

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
import os
import secrets
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from starlette.websockets import WebSocketState

from app import live_tools
from app.config import get_settings
from app.personal_data import require_device_token
from app.personality import SYSTEM_INSTRUCTIONS

logger = logging.getLogger("jarvis.live_voice")
router = APIRouter()

MAX_AUDIO_BYTES = 64 * 1024
MAX_TEXT_CHARS = 4000
LIVE_TICKET_TTL_SECONDS = 60
_live_tickets: dict[str, float] = {}

# Per-session guardrails. They bound cost and exposure; override with env vars.
MAX_SESSION_SECONDS = int(os.getenv("JARVIS_LIVE_MAX_SESSION_SECONDS", "900"))
IDLE_TIMEOUT_SECONDS = int(os.getenv("JARVIS_LIVE_IDLE_TIMEOUT_SECONDS", "120"))
# 16 kHz mono PCM16 is 32,000 bytes per second; allow 1.5x real time per minute.
MAX_AUDIO_BYTES_PER_MINUTE = int(os.getenv("JARVIS_LIVE_MAX_AUDIO_BYTES_PER_MINUTE", str(32_000 * 60 * 3 // 2)))
APPROVAL_TIMEOUT_SECONDS = int(os.getenv("JARVIS_LIVE_APPROVAL_TIMEOUT_SECONDS", "60"))
MAX_CONCURRENT_SESSIONS = int(os.getenv("JARVIS_LIVE_MAX_CONCURRENT_SESSIONS", "2"))
_active_sessions = 0


class SessionGuard:
    """Tracks one live session's age, idleness and audio volume."""

    def __init__(self, now=time.monotonic, max_seconds: int | None = None, idle_seconds: int | None = None,
                 max_audio_bytes_per_minute: int | None = None):
        self._now = now
        self.max_seconds = MAX_SESSION_SECONDS if max_seconds is None else max_seconds
        self.idle_seconds = IDLE_TIMEOUT_SECONDS if idle_seconds is None else idle_seconds
        self.max_audio = MAX_AUDIO_BYTES_PER_MINUTE if max_audio_bytes_per_minute is None else max_audio_bytes_per_minute
        self.started = now()
        self.last_activity = self.started
        self._window_start = self.started
        self._window_bytes = 0

    def touch(self) -> None:
        """Record real user activity (audio or text). Pings do not count."""
        self.last_activity = self._now()

    def remaining(self) -> float:
        """Seconds until the session must end for age or idleness."""
        now = self._now()
        return min(self.started + self.max_seconds - now, self.last_activity + self.idle_seconds - now)

    def expiry_reason(self) -> str | None:
        now = self._now()
        if now - self.started >= self.max_seconds:
            return "Session time limit reached."
        if now - self.last_activity >= self.idle_seconds:
            return "Session closed after being idle."
        return None

    def allow_audio(self, nbytes: int) -> bool:
        """Rate-limit audio sent to the provider per rolling minute."""
        now = self._now()
        if now - self._window_start >= 60:
            self._window_start, self._window_bytes = now, 0
        if self._window_bytes + nbytes > self.max_audio:
            return False
        self._window_bytes += nbytes
        return True


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

    global _active_sessions
    if _active_sessions >= MAX_CONCURRENT_SESSIONS:
        await websocket.close(code=1013, reason="too many live voice sessions")
        return
    guard = SessionGuard()

    await websocket.accept()
    client = genai.Client(api_key=settings.gemini_api_key)
    receive_task: asyncio.Task | None = None
    pending_approvals: dict[str, asyncio.Future] = {}

    async def run_tool(name: str, args: dict) -> dict:
        """Run an allow-listed tool; hold approval-gated ones for an explicit yes."""
        if name not in live_tools.APPROVAL_TOOL_NAMES:
            return live_tools.response_payload(await asyncio.to_thread(live_tools.execute, name, args))
        prepared, summary = live_tools.prepare_approval(name, args)
        if prepared is None:
            return {"success": False, "error": summary}
        if pending_approvals:
            return {"success": False, "error": "Another approval is already waiting."}
        request_id = secrets.token_urlsafe(9)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        pending_approvals[request_id] = future
        try:
            await _send(websocket, {"type": "approval_request", "id": request_id, "name": name,
                                    "summary": summary, "expires_in": APPROVAL_TIMEOUT_SECONDS})
            try:
                approved = await asyncio.wait_for(future, timeout=APPROVAL_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                approved = False
        finally:
            pending_approvals.pop(request_id, None)
        if approved is not True:
            return {"success": False, "error": "The user did not approve. Nothing was changed."}
        return live_tools.response_payload(await asyncio.to_thread(live_tools.execute_approved, name, prepared))
    _active_sessions += 1
    try:
        config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": SYSTEM_INSTRUCTIONS + (
                "\nSpeak naturally and concisely as JARVIS, a personal assistant. "
                "Do not claim an action was performed unless the connected tool reports success. "
                "For consequential actions, ask for explicit confirmation."
                + live_tools.VOICE_TOOL_INSTRUCTION
            ),
            "tools": [{"function_declarations": live_tools.ALL_DECLARATIONS}],
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
                            tool_call = getattr(response, "tool_call", None)
                            if tool_call and getattr(tool_call, "function_calls", None):
                                responses = []
                                for fc in tool_call.function_calls:
                                    result = await run_tool(fc.name, dict(fc.args or {}))
                                    await _send(websocket, {"type": "tool", "name": fc.name, "ok": bool(result.get("success"))})
                                    responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"output": result}))
                                await session.send_tool_response(function_responses=responses)
                                continue
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
                reason = guard.expiry_reason()
                if reason is None:
                    try:
                        raw = await asyncio.wait_for(websocket.receive_text(), timeout=max(guard.remaining(), 0.01))
                    except asyncio.TimeoutError:
                        reason = guard.expiry_reason() or "Session closed after being idle."
                if reason is not None:
                    await _send(websocket, {"type": "error", "message": reason + " Start a new session to continue."})
                    break
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
                elif kind == "approval":
                    pending = pending_approvals.get(message.get("id")) if isinstance(message.get("id"), str) else None
                    if pending is None or pending.done():
                        await _send(websocket, {"type": "error", "message": "No matching approval request."})
                    else:
                        guard.touch()
                        pending.set_result(message.get("approve") is True)
                elif kind == "stop":
                    # Server-side voice activity should interrupt the model. The UI
                    # must also stop/flush local audio playback immediately.
                    await session.send_realtime_input(text="Stop speaking now.")
                    guard.touch()
                elif kind == "text":
                    text = message.get("text")
                    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
                        await _send(websocket, {"type": "error", "message": "Text is empty or too long."})
                        continue
                    guard.touch()
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
                    if not guard.allow_audio(len(pcm)):
                        await _send(websocket, {"type": "error", "message": "Audio rate limit exceeded; slow down."})
                        continue
                    guard.touch()
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
        _active_sessions = max(0, _active_sessions - 1)
        for fut in pending_approvals.values():
            if not fut.done():
                fut.set_result(False)
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
