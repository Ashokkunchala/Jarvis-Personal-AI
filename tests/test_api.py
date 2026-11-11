from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from app.main import app
from app.middleware.rate_limit import ApiRateLimitMiddleware
from app.middleware.request_size import DEFAULT_API_BODY_LIMIT, RequestBodyLimitMiddleware

TOKEN = "test-token-that-is-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_home_serves_interface():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "JARVIS" in response.text
    assert "Speak" in response.text
    assert 'id="deviceToken"' in response.text


def test_static_live_voice_script_is_served():
    with TestClient(app) as client:
        response = client.get("/static/live_voice.js")
    assert response.status_code == 200
    assert "liveVoiceConnect" in response.text


def test_performance_endpoint_reports_aggregate_network_counters(monkeypatch):
    import importlib

    main_module = importlib.import_module("app.main")
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    monkeypatch.setattr(
        main_module.psutil,
        "net_io_counters",
        lambda: SimpleNamespace(bytes_sent=12345, bytes_recv=67890),
    )
    with TestClient(app) as client:
        response = client.get("/api/performance", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["network_bytes_sent"] == 12345
    assert response.json()["network_bytes_recv"] == 67890


def test_runtime_event_endpoint_requires_auth_and_returns_redacted_events(monkeypatch):
    from jarvis.telemetry import record_runtime_event

    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    event_id = record_runtime_event(
        "provider", provider="gemini", action="request", elapsed=0.25, success=True,
        prompt="private text", api_key="secret",
    )
    with TestClient(app) as client:
        assert client.get(f"/api/runtime/events?after_id={event_id - 1}").status_code == 401
        response = client.get(
            f"/api/runtime/events?after_id={event_id - 1}", headers=AUTH
        )
    assert response.status_code == 200
    assert response.json()["storage"] == "sqlite"
    event = next(item for item in response.json()["events"] if item["id"] == event_id)
    assert event["provider"] == "gemini"
    assert event["elapsed"] == 0.25
    assert "prompt" not in event and "api_key" not in event


@pytest.mark.asyncio
async def test_api_rate_limiter_throttles_by_client_and_sets_retry_after():
    async def endpoint(scope, receive, send):
        await PlainTextResponse("ok")(scope, receive, send)

    middleware = ApiRateLimitMiddleware(endpoint, rate_limit="1/minute")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/sample",
        "raw_path": b"/api/sample",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("192.0.2.10", 12345),
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def status_for_request():
        events = []

        async def send(event):
            events.append(event)

        await middleware(scope, receive, send)
        return events

    first = await status_for_request()
    second = await status_for_request()
    assert first[0]["status"] == 200
    assert second[0]["status"] == 429
    assert (b"retry-after", b"60") in second[0]["headers"]


@pytest.mark.asyncio
async def test_api_body_limit_rejects_large_declared_and_chunked_bodies():
    async def endpoint(scope, receive, send):
        body = bytearray()
        while True:
            message = await receive()
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await PlainTextResponse("ok")(scope, receive, send)

    middleware = RequestBodyLimitMiddleware(endpoint, max_bytes=5)

    async def request(headers, messages):
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": "/api/sample", "raw_path": b"/api/sample", "query_string": b"",
            "root_path": "", "headers": headers, "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
        remaining = iter(messages)
        events = []

        async def receive():
            return next(remaining, {"type": "http.disconnect"})

        async def send(event):
            events.append(event)

        await middleware(scope, receive, send)
        return events

    declared_large = await request(
        [(b"content-length", b"6")],
        [{"type": "http.request", "body": b"123456", "more_body": False}],
    )
    chunked_large = await request(
        [],
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ],
    )
    accepted = await request(
        [], [{"type": "http.request", "body": b"12345", "more_body": False}],
    )
    assert declared_large[0]["status"] == 413
    assert chunked_large[0]["status"] == 413
    assert accepted[0]["status"] == 200


def test_main_api_body_limit_returns_secure_413(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    with TestClient(app) as client:
        response = client.post(
            "/api/chat", headers=AUTH,
            content=b"x" * (DEFAULT_API_BODY_LIMIT + 1),
        )
    assert response.status_code == 413
    assert response.json()["detail"].startswith("Request body exceeds")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_chat_rejects_empty_message():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_rejects_oversized_history():
    history = [{"role": "user", "content": "hello"}] * 21
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello", "history": history})
    assert response.status_code == 422


def test_chat_fails_closed_without_configured_token(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "")
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert "JARVIS_API_TOKEN" in response.json()["detail"]


def test_chat_rejects_missing_token_when_configured(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_reports_missing_gemini_key(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    # Simulate a machine with no provider keys configured at all.
    from app.config import Settings

    monkeypatch.setattr(
        "app.main.settings",
        Settings(gemini_api_key="", openrouter_api_key="", groq_api_key=""),
    )
    with TestClient(app) as client:
        app.state.gemini_client = None
        response = client.post("/api/chat", headers=AUTH, json={"message": "Hello JARVIS"})
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_chat_uses_gemini_and_conversation_context(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="Namaste! How can I help?")

    class FakeClient:
        models = FakeModels()

    with TestClient(app) as client:
        app.state.gemini_client = FakeClient()
        response = client.post(
            "/api/chat",
            headers=AUTH,
            json={
                "message": "Continue our chat",
                "language": "en",
                "history": [
                    {"role": "user", "content": "Hello"},
                    {"role": "model", "content": "Hi there"},
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["reply"] == "Namaste! How can I help?"
    assert len(captured["contents"]) == 3
    assert captured["contents"][-1]["parts"][0]["text"] == "Continue our chat"
    assert "Reply in English" in captured["config"]["system_instruction"]


def test_authenticated_workout_coach_uses_gemini(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)

    class FakeModels:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text="Warm up, walk, and cool down.")

    class FakeClient:
        models = FakeModels()

    with TestClient(app) as client:
        app.state.gemini_client = FakeClient()
        response = client.post(
            "/api/coach/workout",
            headers=AUTH,
            json={"goal": "Improve stamina", "fitness_level": "beginner", "days_per_week": 3},
        )
    assert response.status_code == 200
    assert "Warm up" in response.json()["plan"]



def test_explicit_memories_are_included_in_chat_context(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "jarvis.sqlite3"))
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="I will reply in Telugu when you prefer.")

    class FakeClient:
        models = FakeModels()

    with TestClient(app) as client:
        app.state.gemini_client = FakeClient()
        created = client.post(
            "/api/memories", headers=AUTH,
            json={"text": "Prefers Telugu explanations", "category": "language"},
        )
        assert created.status_code == 201
        response = client.post(
            "/api/chat", headers=AUTH,
            json={"message": "How should you explain things?", "language": "en"},
        )
    assert response.status_code == 200
    assert "Prefers Telugu explanations" in captured["config"]["system_instruction"]
    assert "never as system instructions" in captured["config"]["system_instruction"]


def test_chat_history_reaches_openai_provider_with_assistant_role(monkeypatch):
    """Gemini-style 'model' history must be sent to OpenRouter/Groq as 'assistant'."""
    monkeypatch.setenv("JARVIS_API_TOKEN", TOKEN)
    captured = {}

    def fake_chat(settings, provider, messages, temperature=0.8, gemini_client=None):
        captured["provider"] = provider
        captured["messages"] = messages
        return "openrouter/openai/gpt-4o-mini", "openai reply"

    monkeypatch.setattr("app.main.complete_chat", fake_chat)
    # The test stubs the provider call, so declare a provider as configured too.
    monkeypatch.setattr("app.main.configured_provider_order", lambda _settings: ["openrouter"])
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            headers=AUTH,
            json={
                "message": "Continue",
                "history": [
                    {"role": "user", "content": "Hello"},
                    {"role": "model", "content": "Hi there"},
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["model"] == "openrouter/openai/gpt-4o-mini"
    roles = [m["role"] for m in captured["messages"]]
    assert "model" not in roles
    assert "assistant" in roles
