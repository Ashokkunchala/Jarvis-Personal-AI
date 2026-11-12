import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app


def setup_client(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_TOKEN", "test-token-that-is-at-least-32-characters")
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "jarvis.sqlite3"))
    return TestClient(app)


def test_personal_apis_require_device_token(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_TOKEN", "")
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


def test_recurring_reminder_reschedules_after_completion(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        created = client.post(
            "/api/reminders",
            headers=headers,
            json={
                "title": "Weekly review",
                "due_at": "2026-01-01T08:00:00+00:00",
                "recurrence": "weekly",
            },
        )
        assert created.status_code == 201
        reminder_id = created.json()["id"]
        assert created.json()["recurrence"] == "weekly"

        completed = client.post(f"/api/reminders/{reminder_id}/complete", headers=headers)

        assert completed.status_code == 200
        assert completed.json()["completed"] is False
        assert completed.json()["recurrence"] == "weekly"
        updated = client.get("/api/reminders", headers=headers).json()["items"][0]
        assert updated["due_at"] == completed.json()["next_due_at"]
        assert updated["completed"] == 0


def test_reminder_recurrence_is_restricted(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        response = client.post(
            "/api/reminders",
            headers=headers,
            json={
                "title": "Unsupported repeat",
                "due_at": "2026-11-01T08:00:00+00:00",
                "recurrence": "hourly",
            },
        )
        assert response.status_code == 422


def test_existing_reminder_database_gets_recurrence_default(monkeypatch, tmp_path):
    database = tmp_path / "jarvis.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE reminders (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
            "due_at TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO reminders(title,due_at,created_at) VALUES(?,?,?)",
            ("Legacy reminder", "2026-11-01T08:00:00+00:00", "2026-10-31T00:00:00+00:00"),
        )
    monkeypatch.setenv("JARVIS_API_TOKEN", "test-token-that-is-at-least-32-characters")
    monkeypatch.setenv("JARVIS_DB_PATH", str(database))
    with TestClient(app) as client:
        response = client.get(
            "/api/reminders",
            headers={"Authorization": "Bearer test-token-that-is-at-least-32-characters"},
        )
    assert response.status_code == 200
    assert response.json()["items"][0]["recurrence"] == "none"


def test_workout_can_be_recorded(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        response = client.post("/api/workouts", headers=headers,
                               json={"activity": "Walking", "duration_minutes": 30, "notes": "Easy pace"})
        assert response.status_code == 201
        assert response.json()["duration_minutes"] == 30
        assert client.get("/api/workouts", headers=headers).json()["items"][0]["activity"] == "Walking"



def test_memory_edit_and_personal_data_export(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        created = client.post(
            "/api/memories", headers=headers,
            json={"text": "Old preference", "category": "general"},
        )
        memory_id = created.json()["id"]
        updated = client.put(
            f"/api/memories/{memory_id}", headers=headers,
            json={"text": "Prefers Telugu", "category": "language"},
        )
        assert updated.status_code == 200
        assert updated.json()["text"] == "Prefers Telugu"
        exported = client.get("/api/export", headers=headers)
        assert exported.status_code == 200
        assert exported.json()["memories"][0]["category"] == "language"


def test_delete_all_memories(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        for value in ("One", "Two"):
            assert client.post(
                "/api/memories", headers=headers,
                json={"text": value, "category": "test"},
            ).status_code == 201
        assert client.delete("/api/memories", headers=headers).status_code == 204
        assert client.get("/api/memories", headers=headers).json()["items"] == []


def test_saved_plan_is_persistent_editable_cancellable_and_exported(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        created = client.post(
            "/api/plans", headers=headers,
            json={
                "title": "Interview preparation",
                "steps": ["Review fundamentals", "Practice questions"],
                "due_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            },
        )
        assert created.status_code == 201
        plan = created.json()
        assert plan["steps"] == ["Review fundamentals", "Practice questions"]
        assert plan["status"] == "planned"
        assert plan["reminder_id"] is not None
        assert client.get("/api/reminders", headers=headers).json()["items"][0]["title"] == "Plan due: Interview preparation"
        due = client.get("/api/reminders/due", headers=headers).json()["items"]
        assert any(reminder["id"] == plan["reminder_id"] for reminder in due)

    # Reopen the API client to check that the plan is in SQLite, not process memory.
    with setup_client(monkeypatch, tmp_path) as client:
        assert client.get("/api/plans", headers=headers).json()["items"][0]["id"] == plan["id"]
        history_url = f"/api/plans/{plan['id']}/history"
        created_history = client.get(history_url, headers=headers).json()["items"]
        assert [event["event"] for event in created_history] == ["created"]
        assert "title" not in created_history[0] and "steps" not in created_history[0]
        started = client.patch(
            f"/api/plans/{plan['id']}", headers=headers,
            json={"status": "in_progress"},
        )
        assert started.json()["status"] == "in_progress"
        cancelled = client.patch(
            f"/api/plans/{plan['id']}", headers=headers,
            json={"status": "cancelled"},
        )
        assert cancelled.json()["status"] == "cancelled"
        history = client.get(history_url, headers=headers).json()["items"]
        assert [event["to_status"] for event in history] == ["planned", "in_progress", "cancelled"]
        reminders = client.get("/api/reminders", headers=headers).json()["items"]
        assert reminders[0]["completed"] == 1
        assert client.get("/api/reminders/due", headers=headers).json()["items"] == []
        assert client.get("/api/export", headers=headers).json()["plans"][0]["title"] == "Interview preparation"
        assert client.delete(f"/api/plans/{plan['id']}", headers=headers).status_code == 204
        assert client.get("/api/plans", headers=headers).json()["items"] == []
        assert client.get("/api/reminders", headers=headers).json()["items"] == []
        deleted_history = client.get(history_url, headers=headers).json()["items"]
        assert deleted_history[-1]["event"] == "deleted"
        assert len(client.get("/api/export", headers=headers).json()["plan_history"]) == 4


def test_saved_plan_requires_auth_and_valid_steps_and_timezone(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        assert client.get("/api/plans").status_code == 401
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        missing_timezone = client.post(
            "/api/plans", headers=headers,
            json={"title": "Plan", "steps": ["Step"], "due_at": "2026-11-05T18:00:00"},
        )
        assert missing_timezone.status_code == 422
        blank_step = client.post(
            "/api/plans", headers=headers,
            json={"title": "Plan", "steps": [" "]},
        )
        assert blank_step.status_code == 422


def test_existing_dated_plans_are_migrated_to_notification_reminders(monkeypatch, tmp_path):
    database = tmp_path / "jarvis.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE plans (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
            "steps_json TEXT NOT NULL, due_at TEXT, status TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO plans(title,steps_json,due_at,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            ("Legacy plan", '["Review"]', "2026-11-05T12:30:00+00:00", "planned",
             "2026-10-31T00:00:00+00:00", "2026-10-31T00:00:00+00:00"),
        )
    monkeypatch.setenv("JARVIS_API_TOKEN", "test-token-that-is-at-least-32-characters")
    monkeypatch.setenv("JARVIS_DB_PATH", str(database))
    headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
    with TestClient(app) as client:
        plan = client.get("/api/plans", headers=headers).json()["items"][0]
        reminders = client.get("/api/reminders", headers=headers).json()["items"]
    assert plan["reminder_id"] is not None
    assert [reminder["title"] for reminder in reminders] == ["Plan due: Legacy plan"]


def test_schedule_is_disabled_until_enabled_and_history_survives_delete(monkeypatch, tmp_path):
    first_run = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        assert client.get("/api/schedules").status_code == 401
        created = client.post(
            "/api/schedules", headers=headers,
            json={
                "title": "Monitor resources",
                "tool": "system_status",
                "interval_minutes": 60,
                "first_run_at": first_run,
            },
        )
        assert created.status_code == 201
        item = created.json()
        assert item["enabled"] == 0 and item["state"] == "disabled"
        history_path = f"/api/schedules/{item['id']}/history"
        assert client.patch(
            f"/api/schedules/{item['id']}", headers=headers,
            json={"enabled": True},
        ).json()["state"] == "scheduled"
        with sqlite3.connect(tmp_path / "jarvis.sqlite3") as db:
            db.execute("UPDATE scheduled_runs SET state='running' WHERE id=?", (item["id"],))
        assert client.patch(
            f"/api/schedules/{item['id']}", headers=headers,
            json={"enabled": True},
        ).json()["state"] == "running"
        assert client.patch(
            f"/api/schedules/{item['id']}", headers=headers,
            json={"enabled": False},
        ).json()["state"] == "disabled"
        assert [e["event"] for e in client.get(history_path, headers=headers).json()["items"]] == [
            "created", "enabled", "disabled",
        ]
        exported = client.get("/api/export", headers=headers).json()
        assert exported["schedules"][0]["title"] == "Monitor resources"
        assert len(exported["schedule_history"]) == 3
        assert client.delete(f"/api/schedules/{item['id']}", headers=headers).status_code == 204
        assert client.get("/api/schedules", headers=headers).json()["items"] == []
        assert client.get(history_path, headers=headers).json()["items"][-1]["event"] == "deleted"


def test_schedule_api_only_accepts_allowlisted_read_only_tools(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        base = {
            "title": "Read files automatically",
            "interval_minutes": 60,
            "first_run_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }
        assert client.post("/api/schedules", headers=headers,
                           json={**base, "tool": "read_file"}).status_code == 422
        assert client.post("/api/schedules", headers=headers,
                           json={**base, "tool": "cpu_usage", "args": {"path": "secret.txt"}}).status_code == 422
        assert client.post("/api/schedules", headers=headers,
                           json={**base, "tool": "system_status", "args": {"device": "phone"}}).status_code == 422



def test_workout_summary_reports_recent_and_all_time_totals(monkeypatch, tmp_path):
    with setup_client(monkeypatch, tmp_path) as client:
        headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
        for activity, duration in (("Walking", 20), ("Cycling", 40)):
            response = client.post(
                "/api/workouts", headers=headers,
                json={"activity": activity, "duration_minutes": duration},
            )
            assert response.status_code == 201
        summary = client.get("/api/workouts/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["last_7_days"]["sessions"] == 2
        assert summary.json()["last_7_days"]["minutes"] == 60
        assert summary.json()["all_time"]["minutes"] == 60
