import base64

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.live_voice import _decode_audio_frame, _origin_is_allowed
from app.main import app


def test_live_voice_allows_configured_origin():
    assert _origin_is_allowed("http://localhost:3000", "127.0.0.1:8000", {"http://localhost:3000"})


def test_live_voice_allows_same_origin_backend_ui():
    assert _origin_is_allowed("http://127.0.0.1:8000", "127.0.0.1:8000", set())


def test_live_voice_rejects_unconfigured_cross_origin():
    assert not _origin_is_allowed("https://attacker.example", "127.0.0.1:8000", set())


def test_live_voice_allows_token_authenticated_native_client_without_origin():
    assert _origin_is_allowed(None, "127.0.0.1:8000", set())



def test_live_voice_ticket_is_single_use():
    from app.live_voice import _consume_live_ticket, _issue_live_ticket

    ticket = _issue_live_ticket()
    assert _consume_live_ticket(ticket) is True
    assert _consume_live_ticket(ticket) is False


def test_live_voice_concurrent_session_limit_is_atomic_and_released():
    import uuid

    import app.live_voice as live_voice

    client_key = f"test-{uuid.uuid4()}"
    slots = live_voice.MAX_CONCURRENT_LIVE_SESSIONS_PER_IP
    reserved = [live_voice._reserve_live_session(client_key) for _ in range(slots)]
    assert all(reserved)
    assert live_voice._reserve_live_session(client_key) is False

    live_voice._release_live_session(client_key)
    assert live_voice._reserve_live_session(client_key) is True
    for _ in range(slots):
        live_voice._release_live_session(client_key)
    assert live_voice._active_live_sessions.get(client_key, 0) == 0


def test_live_voice_ticket_endpoint_requires_device_token(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("JARVIS_API_TOKEN", "test-token-that-is-at-least-32-characters")
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "jarvis.sqlite3"))
    with TestClient(app) as client:
        denied = client.post("/api/live-voice-ticket")
        assert denied.status_code == 401
        response = client.post(
            "/api/live-voice-ticket",
            headers={"Authorization": "Bearer test-token-that-is-at-least-32-characters"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["expires_in"] == 60
        assert len(payload["ticket"]) >= 32


def test_live_voice_ticket_expiry(monkeypatch):
    import app.live_voice as live_voice

    clock = {"now": 100.0}
    monkeypatch.setattr(live_voice.time, "monotonic", lambda: clock["now"])
    ticket = live_voice._issue_live_ticket()
    clock["now"] += live_voice.LIVE_TICKET_TTL_SECONDS + 1
    assert live_voice._consume_live_ticket(ticket) is False


def test_live_voice_audio_frame_is_validated():
    frame = b"\x00\x01" * 32
    assert _decode_audio_frame(base64.b64encode(frame).decode("ascii")) == frame


@pytest.mark.parametrize("encoded", [None, "@@@", "", "AQ=="])
def test_live_voice_rejects_malformed_audio_frames(encoded):
    with pytest.raises(ValueError):
        _decode_audio_frame(encoded)


def test_live_voice_rejects_audio_frames_over_the_limit():
    encoded = base64.b64encode(b"\x00\x01" * 40_000).decode("ascii")
    with pytest.raises(ValueError, match="oversized"):
        _decode_audio_frame(encoded)


def test_live_voice_websocket_rejects_disallowed_origin():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                "/api/live-voice?ticket=unused",
                headers={"origin": "https://attacker.example", "host": "testserver"},
            ):
                pass
    assert error.value.code == 4403


def test_live_voice_websocket_rejects_invalid_ticket():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                "/api/live-voice?ticket=invalid",
                headers={"origin": "http://testserver", "host": "testserver"},
            ):
                pass
    assert error.value.code == 4401
