"""WebSocket bridge for the browser UI and any remote client.

Speaks the same event vocabulary as ``JarvisBrain.ask`` so a browser gets the
realtime experience the terminal gets: streamed text, tool lifecycle events,
and an interactive confirmation dialog before anything risky runs.

Protocol (JSON text frames)
---------------------------
client → server
    {"type": "chat", "message": "...", "auto_approve": false}
    {"type": "approve", "id": "<confirm-id>", "approved": true}
    {"type": "cancel",  "id": "<turn-id>"}
    {"type": "status"}
    {"type": "tools"}
    {"type": "ping"}

server → client
    {"type": "ready", "model": ..., "tools": ...}
    {"type": "status", "message": ...}            # thinking / model fallback
    {"type": "text_delta", "text": ...}
    {"type": "tool_start" | "tool_end" | "tool_error" | "tool_cancelled", ...}
    {"type": "confirm", "id": ..., "tool": ..., "args": ..., "risk": ...}
    {"type": "done", "text": ..., "tools_used": [...], "elapsed": ...}
    {"type": "error", "error": ...}
    {"type": "status_snapshot", ...}
    {"type": "tools_list", ...}
    {"type": "pong"}

Auth: pass the device/API token as ``?token=...`` (browsers cannot set
Authorization headers on WebSocket handshakes).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.auth import token_auth
from jarvis.core.brain import JarvisBrain

logger = logging.getLogger("jarvis.ws")

router = APIRouter()

# Free-tier Gemini quotas are tiny; never let one browser melt them.
MAX_CONCURRENT_TURNS = 2
_turn_gate = asyncio.Semaphore(MAX_CONCURRENT_TURNS)


def _sendable(event: dict[str, Any]) -> dict[str, Any]:
    """Make a brain event JSON-safe (Args/Path objects etc.)."""
    clean: dict[str, Any] = {}
    for key, value in event.items():
        try:
            json.dumps(value)
            clean[key] = value
        except (TypeError, ValueError):
            clean[key] = str(value)
    return clean


async def _emit(websocket: WebSocket, payload: dict[str, Any]) -> bool:
    """Send one frame; returns False when the socket is gone."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_text(json.dumps(_sendable(payload), ensure_ascii=False, default=str))
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False
    except Exception:  # pragma: no cover - defensive
        logger.debug("WebSocket send failed", exc_info=True)
        return False


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket, token: str = Query(default="")):
    """Streaming JARVIS session: chat, tools, confirmations, live status."""
    try:
        token_auth.validate_token(f"Bearer {token}" if token else None)
    except Exception as exc:
        await websocket.close(code=4401, reason="unauthorized")
        logger.debug("WS handshake rejected: %s", exc)
        return

    await websocket.accept()
    brain = JarvisBrain()
    pending_confirm: dict[str, asyncio.Future[bool]] = {}
    turn_task: asyncio.Task | None = None
    turn_cancel = asyncio.Event()

    await _emit(websocket, {
        "type": "ready",
        "model": brain.model,
        "tools": len(brain.registry),
        "configured": brain.configured,
    })

    async def confirm(tool, args: dict[str, Any]) -> bool:
        if turn_cancel.is_set():
            return False
        confirm_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        pending_confirm[confirm_id] = future
        try:
            await _emit(websocket, {
                "type": "confirm",
                "id": confirm_id,
                "tool": tool.name,
                "description": tool.description,
                "category": tool.category,
                "risk": tool.risk.name,
                "args": args,
            })
            return await future
        finally:
            pending_confirm.pop(confirm_id, None)

    async def run_turn(message: str, auto_approve: bool) -> None:
        nonlocal turn_task
        turn_cancel.clear()
        try:
            async with _turn_gate:
                async for event in brain.ask(message, confirm=None if auto_approve else confirm,
                                             auto_approve=auto_approve):
                    if turn_cancel.is_set():
                        await _emit(websocket, {"type": "status", "message": "stopped by user"})
                        break
                    if not await _emit(websocket, event):
                        turn_cancel.set()
                        break
        except asyncio.CancelledError:
            await _emit(websocket, {"type": "error", "error": "turn cancelled"})
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("WS turn failed")
            await _emit(websocket, {"type": "error", "error": str(exc)})
        finally:
            turn_task = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except ValueError:
                await _emit(websocket, {"type": "error", "error": "invalid JSON frame"})
                continue
            if not isinstance(message, dict):
                await _emit(websocket, {"type": "error", "error": "expected a JSON object"})
                continue

            kind = str(message.get("type", "")).lower()

            if kind == "ping":
                await _emit(websocket, {"type": "pong"})

            elif kind == "status":
                snapshot = await asyncio.to_thread(brain.snapshot)
                await _emit(websocket, {"type": "status_snapshot", **snapshot})

            elif kind == "tools":
                await _emit(websocket, {"type": "tools_list", "tools": brain.registry.get_tool_schemas()})

            elif kind == "approve":
                confirm_id = str(message.get("id", ""))
                future = pending_confirm.get(confirm_id)
                if future and not future.done():
                    future.set_result(bool(message.get("approved", True)))

            elif kind == "cancel":
                turn_cancel.set()
                if turn_task and not turn_task.done():
                    turn_task.cancel()

            elif kind == "chat":
                text = str(message.get("message", "")).strip()
                if not text:
                    await _emit(websocket, {"type": "error", "error": "empty message"})
                    continue
                if turn_task and not turn_task.done():
                    await _emit(websocket, {"type": "error", "error": "a turn is already running"})
                    continue
                turn_task = asyncio.create_task(run_turn(text, bool(message.get("auto_approve", False))))

            else:
                await _emit(websocket, {"type": "error", "error": f"unknown frame type {kind!r}"})

    except WebSocketDisconnect:
        logger.debug("WS client disconnected")
    finally:
        turn_cancel.set()
        for future in pending_confirm.values():
            if not future.done():
                future.set_result(False)
        pending_confirm.clear()
        if turn_task and not turn_task.done():
            turn_task.cancel()
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:  # pragma: no cover - defensive
            pass
