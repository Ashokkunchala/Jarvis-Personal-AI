from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app

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
