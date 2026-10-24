from fastapi.testclient import TestClient
from app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_rejects_empty_message():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_reports_missing_api_key(monkeypatch):
    with TestClient(app) as client:
        app.state.gemini_client = None
        response = client.post("/api/chat", json={"message": "Hello JARVIS"})
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]
