"""Regression tests for the authenticated browser WebSocket bridge."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main_enhanced import app

TOKEN = "test-token-that-is-at-least-32-characters"


@pytest.fixture(autouse=True)
def _configured_token(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_websocket_rejects_invalid_token():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws?token=invalid"):
                pass

    assert exc_info.value.code == 4401


def test_websocket_reports_provider_timeout(monkeypatch):
    class EmptyRegistry:
        def __len__(self):
            return 0

        def get_tool_schemas(self):
            return []

    class FakeBrain:
        active_model = "test-model"
        registry = EmptyRegistry()
        configured = True

        @staticmethod
        def provider_candidates():
            return ["test-provider"]

        async def ask(self, *_args, **_kwargs):
            raise TimeoutError("provider timed out")
            yield  # Make this an async generator like the real brain.

    monkeypatch.setattr("app.ws.JarvisBrain", FakeBrain)

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?token={TOKEN}") as websocket:
            assert websocket.receive_json()["type"] == "ready"
            websocket.send_json({"type": "chat", "message": "hello"})
            response = websocket.receive_json()

    assert response == {"type": "error", "error": "provider timed out"}
