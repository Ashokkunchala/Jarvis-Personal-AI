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
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
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
