"""Authenticated local personal-data APIs backed by SQLite.

This module deliberately refuses access until JARVIS_API_TOKEN is configured.
Keep the server bound to localhost until TLS and device pairing are deployed.
"""
import hmac
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from app.research import search_web
from app.config import Settings

router = APIRouter(prefix="/api", tags=["personal data"])


def _db_path() -> Path:
    return Path(Settings().jarvis_db_path)


def _connect():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'general', created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        due_at TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, activity TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT '',
        performed_at TEXT NOT NULL, created_at TEXT NOT NULL
      );
    """)
    return conn


def require_device_token(authorization: str | None = Header(default=None)):
    expected = Settings().jarvis_api_token
    if len(expected) < 32 or expected.startswith("replace_"):
        raise HTTPException(status_code=503, detail="Set a random JARVIS_API_TOKEN of at least 32 characters before using personal-data APIs.")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid device token.")


def _now():
    return datetime.now(timezone.utc).isoformat()


class MemoryCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    category: str = Field(default="general", min_length=1, max_length=40)


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime


class WorkoutCreate(BaseModel):
    activity: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(ge=1, le=1440)
    notes: str = Field(default="", max_length=2000)
    performed_at: datetime | None = None


@router.get("/memories", dependencies=[Depends(require_device_token)])
def list_memories():
    with _connect() as db:
        rows = db.execute("SELECT * FROM memories ORDER BY id DESC LIMIT 500").fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/memories", status_code=201, dependencies=[Depends(require_device_token)])
def create_memory(item: MemoryCreate):
    with _connect() as db:
        cur = db.execute("INSERT INTO memories(text,category,created_at) VALUES(?,?,?)",
                         (item.text.strip(), item.category.strip(), _now()))
        row = db.execute("SELECT * FROM memories WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.put("/memories/{memory_id}", dependencies=[Depends(require_device_token)])
def update_memory(memory_id: int, item: MemoryCreate):
    with _connect() as db:
        cur = db.execute(
            "UPDATE memories SET text=?, category=? WHERE id=?",
            (item.text.strip(), item.category.strip(), memory_id),
        )
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail="Memory not found.")
        row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
    return dict(row)


@router.delete("/memories/{memory_id}", status_code=204, dependencies=[Depends(require_device_token)])
def delete_memory(memory_id: int):
    with _connect() as db:
        cur = db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail="Memory not found.")


@router.delete("/memories", status_code=204, dependencies=[Depends(require_device_token)])
def delete_all_memories():
    with _connect() as db:
        db.execute("DELETE FROM memories")


@router.get("/reminders", dependencies=[Depends(require_device_token)])
def list_reminders():
    with _connect() as db:
        rows = db.execute("SELECT * FROM reminders ORDER BY due_at LIMIT 500").fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/reminders", status_code=201, dependencies=[Depends(require_device_token)])
def create_reminder(item: ReminderCreate):
    if item.due_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="due_at must include a timezone, e.g. +05:30.")
    with _connect() as db:
        cur = db.execute("INSERT INTO reminders(title,due_at,created_at) VALUES(?,?,?)",
                         (item.title.strip(), item.due_at.astimezone(timezone.utc).isoformat(), _now()))
        row = db.execute("SELECT * FROM reminders WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.get("/reminders/due", dependencies=[Depends(require_device_token)])
def due_reminders():
    """Poll from a trusted local notification worker; returns uncompleted reminders due now."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        rows = db.execute("SELECT * FROM reminders WHERE completed=0 AND due_at<=? ORDER BY due_at", (now,)).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/reminders/{reminder_id}/complete", dependencies=[Depends(require_device_token)])
def complete_reminder(reminder_id: int):
    with _connect() as db:
        cur = db.execute("UPDATE reminders SET completed=1 WHERE id=?", (reminder_id,))
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"id": reminder_id, "completed": True}


@router.delete("/reminders/{reminder_id}", status_code=204, dependencies=[Depends(require_device_token)])
def delete_reminder(reminder_id: int):
    with _connect() as db:
        cur = db.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail="Reminder not found.")


@router.get("/workouts", dependencies=[Depends(require_device_token)])
def list_workouts():
    with _connect() as db:
        rows = db.execute("SELECT * FROM workouts ORDER BY performed_at DESC LIMIT 500").fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/workouts", status_code=201, dependencies=[Depends(require_device_token)])
def create_workout(item: WorkoutCreate):
    performed = item.performed_at or datetime.now(timezone.utc)
    if performed.tzinfo is None:
        raise HTTPException(status_code=422, detail="performed_at must include a timezone.")
    with _connect() as db:
        cur = db.execute(
            "INSERT INTO workouts(activity,duration_minutes,notes,performed_at,created_at) VALUES(?,?,?,?,?)",
            (item.activity.strip(), item.duration_minutes, item.notes.strip(), performed.astimezone(timezone.utc).isoformat(), _now()))
        row = db.execute("SELECT * FROM workouts WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.delete("/workouts/{workout_id}", status_code=204, dependencies=[Depends(require_device_token)])
def delete_workout(workout_id: int):
    with _connect() as db:
        cur = db.execute("DELETE FROM workouts WHERE id=?", (workout_id,))
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail="Workout not found.")


@router.get("/export", dependencies=[Depends(require_device_token)])
def export_personal_data():
    """Export personal data owned by this local JARVIS instance for user review/backup."""
    with _connect() as db:
        memories = [dict(row) for row in db.execute("SELECT * FROM memories ORDER BY id").fetchall()]
        reminders = [dict(row) for row in db.execute("SELECT * FROM reminders ORDER BY due_at").fetchall()]
        workouts = [dict(row) for row in db.execute("SELECT * FROM workouts ORDER BY performed_at").fetchall()]
    return {
        "exported_at": _now(),
        "scope": "local JARVIS SQLite database",
        "memories": memories,
        "reminders": reminders,
        "workouts": workouts,
    }


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    limit: int = Field(default=5, ge=1, le=8)


@router.post("/research", dependencies=[Depends(require_device_token)])
def research(item: ResearchRequest):
    """User-triggered search. Results are untrusted external content; URLs are included for attribution."""
    try:
        results = search_web(item.query.strip(), item.limit)
    except Exception:
        raise HTTPException(status_code=502, detail="Web search failed or timed out. Try again later.")
    return {"query": item.query.strip(), "results": results, "note": "Verify sources; webpage text is untrusted and may be inaccurate."}
