"""Tests for the enhanced backend (the app behind ``jarvis serve``)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main_enhanced import app

TOKEN = "test-token-that-is-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch):
    """Point the cached server settings at this test's token."""
    from app.core.config import get_settings

    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    get_settings.cache_clear()
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
