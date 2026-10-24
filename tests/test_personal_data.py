import os
from fastapi.testclient import TestClient

from app.main import app


def setup_client(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_TOKEN", "test-token-that-is-at-least-32-characters")
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "jarvis.sqlite3"))
    return TestClient(app)


def test_personal_apis_require_device_token(monkeypatch, tmp_path):
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "jarvis.sqlite3"))
    with TestClient(app) as client:
        response = client.get("/api/memories")
    assert response.status_code == 503


def test_memory_can_be_reviewed_and_deleted(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        created = client.post("/api/memories", headers=headers,
                              json={"text": "Prefers Telugu replies", "category": "preference"})
        assert created.status_code == 201
        memory_id = created.json()["id"]
        assert client.get("/api/memories", headers=headers).json()["items"][0]["text"] == "Prefers Telugu replies"
        assert client.delete(f"/api/memories/{memory_id}", headers=headers).status_code == 204
        assert client.get("/api/memories", headers=headers).json()["items"] == []


def test_reminder_requires_timezone_and_can_be_completed(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        bad = client.post("/api/reminders", headers=headers,
                          json={"title": "Workout", "due_at": "2026-10-25T08:00:00"})
        assert bad.status_code == 422
        created = client.post("/api/reminders", headers=headers,
                              json={"title": "Workout", "due_at": "2026-10-25T08:00:00+05:30"})
        assert created.status_code == 201
        reminder_id = created.json()["id"]
        done = client.post(f"/api/reminders/{reminder_id}/complete", headers=headers)
        assert done.json()["completed"] is True


def test_workout_can_be_recorded(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        response = client.post("/api/workouts", headers=headers,
                               json={"activity": "Walking", "duration_minutes": 30, "notes": "Easy pace"})
        assert response.status_code == 201
        assert response.json()["duration_minutes"] == 30
        assert client.get("/api/workouts", headers=headers).json()["items"][0]["activity"] == "Walking"
