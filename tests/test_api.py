from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


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


def test_chat_rejects_empty_message():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_rejects_oversized_history():
    history = [{"role": "user", "content": "hello"}] * 21
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"message": "hello", "history": history},
        )
    assert response.status_code == 422


def test_chat_reports_missing_api_key():
    with TestClient(app) as client:
        app.state.gemini_client = None
        response = client.post("/api/chat", json={"message": "Hello JARVIS"})
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_chat_uses_gemini_and_conversation_context():
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
    monkeypatch.setenv("JARVIS_API_TOKEN", "test-token-that-is-at-least-32-characters")
    class FakeModels:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text="Warm up, walk, and cool down.")
    class FakeClient:
        models = FakeModels()
    with TestClient(app) as client:
        app.state.gemini_client = FakeClient()
        response = client.post(
            "/api/coach/workout",
            headers={"Authorization": "Bearer test-token-that-is-at-least-32-characters"},
            json={"goal": "Improve stamina", "fitness_level": "beginner", "days_per_week": 3},
        )
    assert response.status_code == 200
    assert "Warm up" in response.json()["plan"]



def test_chat_requires_configured_device_token(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "test-token-that-is-at-least-32-characters")
    with TestClient(app) as client:
        unauthorized = client.post("/api/chat", json={"message": "hello"})
        assert unauthorized.status_code == 401
        app.state.gemini_client = None
        authorized = client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token-that-is-at-least-32-characters"},
            json={"message": "hello"},
        )
        # Token was accepted; the response proceeds to the configured-provider check.
        assert authorized.status_code == 503
