"""Ownership: commitments JARVIS makes to the user and follows up on.

When the user gives JARVIS a task or JARVIS promises to check on something
("I'll keep an eye on the deployment", "remind me to call the bank"), it is
recorded here so nothing is silently dropped. JARVIS is proactive about
following up, but bounded: it always asks before sensitive or irreversible
actions, and it never marks a commitment done it did not actually finish.

Storage is a small SQLite database (``~/.jarvis/ownership.db`` by default),
separate from the web app's personal-data store so the CLI and TUI can use
it without the server.
"""

from __future__ import annotations

import builtins
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.ownership")

MAX_TEXT_CHARS = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT,
    created_at TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT
);
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class OwnershipStore:
    """SQLite-backed commitment tracker."""

    def __init__(self, path: Path | str | None = None):
        self.path = str(path or (Path.home() / ".jarvis" / "ownership.db"))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)
            db.execute('BEGIN IMMEDIATE')
            if 'priority' not in {row[1] for row in db.execute('PRAGMA table_info(commitments)')}:
                db.execute('ALTER TABLE commitments ADD COLUMN priority INTEGER NOT NULL DEFAULT 3')

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _due(value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError('timezone missing')
            return parsed.astimezone(UTC).isoformat(timespec='seconds')
        except (ValueError, TypeError) as exc:
            raise ValueError('due_at must be an ISO 8601 date-time with an explicit timezone.') from exc

    @staticmethod
    def _row(row: sqlite3.Row, now: str) -> dict[str, Any]:
        due_at = row["due_at"]
        try:
            normalized = OwnershipStore._due(due_at)
            date_warning = None
        except ValueError:
            normalized = None
            date_warning = 'Legacy due date has no valid timezone; edit it before relying on follow-ups.'
        return {
            "id": row["id"],
            "text": row["text"],
            "due_at": due_at,
            "created_at": row["created_at"],
            "done": bool(row["done"]),
            "done_at": row["done_at"],
            "priority": row["priority"],
            "date_warning": date_warning,
            "overdue": normalized is not None and not row["done"] and normalized <= now,
        }

    def add(self, text: str, due_at: str | None = None) -> dict[str, Any]:
        """Record a commitment. *due_at* is an optional ISO 8601 date-time."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Commitment text is required.")
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"Keep the commitment to {MAX_TEXT_CHARS} characters or fewer.")
        due_at = self._due(due_at.strip() if due_at is not None else None)
        now = _now_iso()
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO commitments (text, due_at, created_at) VALUES (?, ?, ?)",
                (text, due_at, now),
            )
            row = db.execute("SELECT * FROM commitments WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._row(row, now)

    def list(self, include_done: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        now = _now_iso()
        limit = max(1, min(int(limit), 200))
        query = "SELECT * FROM commitments"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY done, priority, COALESCE(julianday(due_at), 99999999), id LIMIT ?"
        with self._connect() as db:
            rows = db.execute(query, (limit,)).fetchall()
        return [self._row(r, now) for r in rows]

    def complete(self, commitment_id: int) -> dict[str, Any] | None:
        """Mark a commitment done. Returns the updated row, or None if unknown."""
        now = _now_iso()
        with self._connect() as db:
            row = db.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
            if row is None:
                return None
            if not row["done"]:
                db.execute("UPDATE commitments SET done = 1, done_at = ? WHERE id = ?", (now, commitment_id))
            row = db.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        return self._row(row, now)

    def due_followups(self, limit: int = 20) -> builtins.list[dict[str, Any]]:
        """Open commitments whose due time has passed - these need follow-up now."""
        now = _now_iso()
        limit = max(1, min(int(limit), 200))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM commitments WHERE done = 0 AND due_at IS NOT NULL AND julianday(due_at) <= julianday(?) "
                "ORDER BY priority, julianday(due_at) LIMIT ?",
                (now, limit),
            ).fetchall()
        return [item for row in rows if (item := self._row(row, now))["overdue"]]

    def edit(self, commitment_id: int, text: str | None = None,
             due_at: str | None = None, clear_due: bool = False,
             priority: int | None = None) -> dict[str, Any]:
        """Correct, prioritize or postpone an open task without marking it done."""
        if type(commitment_id) is not int or commitment_id < 1:
            raise ValueError('Choose an integer commitment ID from list_commitments.')
        if type(clear_due) is not bool or (clear_due and due_at is not None):
            raise ValueError('Use either due_at or clear_due=true, not both.')
        changes: dict[str, Any] = {}
        if text is not None:
            text = text.strip()
            if not text or len(text) > MAX_TEXT_CHARS:
                raise ValueError(f'Task text must contain 1-{MAX_TEXT_CHARS} characters.')
            changes['text'] = text
        if priority is not None:
            if type(priority) is not int or not 1 <= priority <= 5:
                raise ValueError('Priority must be an integer from 1 (highest) to 5 (lowest).')
            changes['priority'] = priority
        if due_at is not None:
            if not due_at.strip():
                raise ValueError('Use clear_due=true to remove a due date.')
            changes['due_at'] = self._due(due_at)
        elif clear_due:
            changes['due_at'] = None
        if not changes:
            raise ValueError('Supply text, due_at, clear_due or priority.')
        with self._connect() as db:
            clauses = ', '.join(f'{key}=?' for key in changes)
            changed = db.execute(f'UPDATE commitments SET {clauses} WHERE id=? AND done=0', (*changes.values(), commitment_id)).rowcount
            if not changed:
                raise ValueError('Task not found or already completed. Completed tasks cannot be silently reopened.')
            row = db.execute('SELECT * FROM commitments WHERE id=?', (commitment_id,)).fetchone()
        return self._row(row, _now_iso())


def register_task_edit_tools(registry):
    from jarvis.tools.registry import Risk, Tool
    registry.register(Tool(
        name='edit_commitment',
        description='Edit, prioritize or postpone an open task. Keeps it open. Due dates require an explicit timezone. Does not send reminders or change an external calendar.',
        parameters={'type': 'object', 'properties': {
            'commitment_id': {'type': 'integer'}, 'text': {'type': 'string'},
            'due_at': {'type': 'string', 'description': 'New ISO date-time with timezone, e.g. 2026-11-15T09:00:00+05:30'},
            'clear_due': {'type': 'boolean'}, 'priority': {'type': 'integer', 'minimum': 1, 'maximum': 5}},
            'required': ['commitment_id']},
        handler=lambda **kwargs: {'success': True, 'commitment': default_store().edit(**kwargs)},
        risk=Risk.LOW, category='ownership'))


_default_store: OwnershipStore | None = None


def default_store() -> OwnershipStore:
    global _default_store
    if _default_store is None:
        _default_store = OwnershipStore()
    return _default_store
