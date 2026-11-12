"""Tests for the enhanced backend (the app behind ``jarvis serve``)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main_enhanced import app
from app.middleware.request_size import DEFAULT_API_BODY_LIMIT

TOKEN = "test-token-that-is-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch, tmp_path):
    """Point the cached server settings at this test's token."""
    from app.core.auth import token_auth
    from app.core.config import get_settings

    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "jarvis.sqlite3"))
    get_settings.cache_clear()
    token_auth._init_device_table()
    yield
    get_settings.cache_clear()


def test_health_reports_configured_providers(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    # Health should report the provider configured in this isolated test.
    monkeypatch.setattr("app.main_enhanced.configured_provider_order", lambda _settings: ["openrouter"])
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["providers"], list)
    assert "gemini" in body["providers"] or "openrouter" in body["providers"] or "groq" in body["providers"]


def test_enhanced_app_serves_dashboard_and_static_voice_assets():
    with TestClient(app) as client:
        dashboard = client.get("/dashboard")
        voice_script = client.get("/static/live_voice.js")
    assert dashboard.status_code == 200
    assert 'id="runtimeFeed"' in dashboard.text
    assert voice_script.status_code == 200
    assert "liveVoiceConnect" in voice_script.text


def test_enhanced_app_applies_the_global_api_rate_limiter():
    from app.middleware.rate_limit import ApiRateLimitMiddleware

    assert any(
        getattr(middleware, "cls", None) is ApiRateLimitMiddleware
        for middleware in app.user_middleware
    )


def test_coaching_responses_include_disclaimers(monkeypatch):
    def fake_complete(*_args, **_kwargs):
        return "gemini/fake-model", "general guidance"

    monkeypatch.setattr("app.main_enhanced.complete_chat", fake_complete)
    monkeypatch.setattr("app.main_enhanced.configured_provider_order", lambda _settings: ["gemini"])

    with TestClient(app) as client:
        workout = client.post(
            "/api/coach/workout",
            headers=AUTH,
            json={"goal": "get fit", "fitness_level": "beginner", "days_per_week": 3},
        )
        nutrition = client.post(
            "/api/coach/nutrition",
            headers=AUTH,
            json={"goal": "eat balanced meals"},
        )

    assert workout.status_code == 200
    assert workout.json()["plan"] == "general guidance"
    assert workout.json()["disclaimer"]
    assert nutrition.status_code == 200
    assert nutrition.json()["suggestions"] == "general guidance"
    assert nutrition.json()["disclaimer"]


def test_enhanced_runtime_event_endpoint_is_authenticated():
    with TestClient(app) as client:
        denied = client.get("/api/runtime/events")
        allowed = client.get("/api/runtime/events", headers=AUTH)
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert "events" in allowed.json()


def test_enhanced_app_rejects_oversized_api_body_with_secure_headers():
    with TestClient(app) as client:
        response = client.post(
            "/api/chat", headers=AUTH,
            content=b"x" * (DEFAULT_API_BODY_LIMIT + 1),
        )
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"


def test_chat_works_with_gemini_client(monkeypatch):
    from app.services.gemini_service import gemini_service

    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="Namaste from enhanced")

    class FakeClient:
        models = FakeModels()

    original = gemini_service.client
    try:
        with TestClient(app) as client:
            # The lifespan re-initialises the real client; swap in the fake after boot.
            gemini_service.client = FakeClient()
            response = client.post(
                "/api/chat",
                headers=AUTH,
                json={"message": "Hello", "language": "en"},
            )
    finally:
        gemini_service.client = original

    assert response.status_code == 200
    assert response.json()["reply"] == "Namaste from enhanced"
    assert response.json()["model"].startswith("gemini/")
    # System prompt travels as system_instruction, not as a contents entry.
    assert "Namaste" not in str(captured.get("contents", ""))
    assert captured["config"]["system_instruction"]


def test_chat_falls_back_to_openrouter_when_gemini_unavailable(monkeypatch):
    from app.services.gemini_service import gemini_service

    original = gemini_service.client

    def fake_complete(settings, order, messages, temperature=0.8, gemini_client=None):
        assert gemini_client is None
        assert "openrouter" in order
        return "openrouter/openai/gpt-4o-mini", "reply from openrouter"

    monkeypatch.setattr("app.main_enhanced.complete_chat", fake_complete)
    # A stubbed OpenRouter response requires OpenRouter in the provider order.
    monkeypatch.setattr("app.main_enhanced.configured_provider_order", lambda _settings: ["openrouter"])
    try:
        with TestClient(app) as client:
            gemini_service.client = None  # simulate missing/invalid Gemini client
            response = client.post(
                "/api/chat",
                headers=AUTH,
                json={"message": "Hello"},
            )
    finally:
        gemini_service.client = original

    assert response.status_code == 200
    assert response.json()["reply"] == "reply from openrouter"
    assert response.json()["model"] == "openrouter/openai/gpt-4o-mini"


def test_chat_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_admin_can_issue_list_and_revoke_device_tokens():
    with TestClient(app) as client:
        issued = client.post(
            "/api/devices/issue",
            headers=AUTH,
            json={"name": "test phone"},
        )
        assert issued.status_code == 200
        device = issued.json()
        device_auth = {"Authorization": f"Bearer {device['token']}"}

        listed = client.get("/api/devices", headers=AUTH)
        assert listed.status_code == 200
        assert any(item["device_id"] == device["device_id"] for item in listed.json()["devices"])
        assert client.get("/api/health/detailed", headers=device_auth).status_code == 200
        assert client.post(
            "/api/memories",
            headers=device_auth,
            json={"text": "Paired-device memory", "category": "test"},
        ).status_code == 201
        assert client.post("/api/live-voice-ticket", headers=device_auth).status_code == 200
        assert client.get("/api/devices", headers=device_auth).status_code == 403
        assert client.post(
            "/api/devices/issue",
            headers=device_auth,
            json={"name": "unapproved child"},
        ).status_code == 403
        assert client.delete(
            f"/api/devices/{device['device_id']}",
            headers=device_auth,
        ).status_code == 403

        revoked = client.delete(f"/api/devices/{device['device_id']}", headers=AUTH)
        assert revoked.status_code == 200
        assert revoked.json()["revoked"] is True
        assert client.get("/api/health/detailed", headers=device_auth).status_code == 401

def test_enhanced_app_registers_live_voice_routes_once():
    from collections import Counter

    from app.live_voice import router as live_voice_router

    expected = Counter(route.path for route in live_voice_router.routes)
    registered = Counter(
        route.path for route in app.routes if getattr(route, "path", None) in expected
    )
    assert registered == expected
