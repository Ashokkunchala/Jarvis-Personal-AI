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

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _row(row: sqlite3.Row, now: str) -> dict[str, Any]:
        due_at = row["due_at"]
        return {
            "id": row["id"],
            "text": row["text"],
            "due_at": due_at,
            "created_at": row["created_at"],
            "done": bool(row["done"]),
            "done_at": row["done_at"],
            "overdue": bool(due_at) and not row["done"] and due_at <= now,
        }

    def add(self, text: str, due_at: str | None = None) -> dict[str, Any]:
        """Record a commitment. *due_at* is an optional ISO 8601 date-time."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Commitment text is required.")
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"Keep the commitment to {MAX_TEXT_CHARS} characters or fewer.")
        if due_at is not None:
            due_at = due_at.strip() or None
            if due_at is not None:
                try:
                    datetime.fromisoformat(due_at)
                except ValueError as exc:
                    raise ValueError("due_at must be an ISO 8601 date-time, e.g. 2026-11-13T09:00:00+05:30.") from exc
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
        query += " ORDER BY done, COALESCE(due_at, '9999'), id LIMIT ?"
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

    def due_followups(self, limit: int = 20) -> list[dict[str, Any]]:
        """Open commitments whose due time has passed - these need follow-up now."""
        now = _now_iso()
        limit = max(1, min(int(limit), 200))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM commitments WHERE done = 0 AND due_at IS NOT NULL AND due_at <= ? "
                "ORDER BY due_at LIMIT ?",
                (now, limit),
            ).fetchall()
        return [self._row(r, now) for r in rows]


_default_store: OwnershipStore | None = None


def default_store() -> OwnershipStore:
    global _default_store
    if _default_store is None:
        _default_store = OwnershipStore()
    return _default_store
