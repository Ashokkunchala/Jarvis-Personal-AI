from app.live_voice import _origin_is_allowed


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
