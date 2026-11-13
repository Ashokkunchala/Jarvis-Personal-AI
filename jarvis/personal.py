"""Personal life store: quick notes, expenses and habit streaks.

Local SQLite only (``~/.jarvis/personal.db`` by default). Nothing leaves the
machine. Amounts are plain numbers in the user's own currency (rupees by
default in summaries); JARVIS never moves money, it only records what the user
tells it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

MAX_TEXT_CHARS = 1000
MAX_AMOUNT = 100_000_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    spent_on TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS habit_logs (
    habit TEXT NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (habit, day)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean(text: str, field: str, required: bool = True) -> str:
    if not isinstance(text, str):
        raise ValueError(f"{field} must be text.")
    text = text.strip()
    if required and not text:
        raise ValueError(f"{field} is required.")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"Keep {field} to {MAX_TEXT_CHARS} characters or fewer.")
    return text


def _parse_day(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("Dates must look like 2026-11-13.") from exc


class PersonalStore:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or (Path.home() / ".jarvis" / "personal.db"))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    # ------------------------------------------------------------------ notes
    def add_note(self, text: str, tags: str = "") -> dict[str, Any]:
        text = _clean(text, "Note text")
        tags = ",".join(t.strip().lower() for t in _clean(tags, "Tags", False).split(",") if t.strip())
        with self._connect() as db:
            cur = db.execute("INSERT INTO notes (text, tags, created_at) VALUES (?, ?, ?)", (text, tags, _now()))
            row = db.execute("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def search_notes(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        query = _clean(query, "Search query", False).lower()
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM notes WHERE instr(lower(text),?)>0 OR instr(tags,?)>0 ORDER BY id DESC LIMIT ?",
                (query, query, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def edit_note(self, note_id: int, expected_text: str, expected_tags: str,
                  text: str | None = None, tags: str | None = None) -> dict[str, Any]:
        """Correct a reviewed note, rejecting stale edits including tag-only races."""
        if type(note_id) is not int or note_id < 1:
            raise ValueError('Choose a positive integer note ID from search_notes.')
        if not isinstance(expected_text, str) or not isinstance(expected_tags, str):
            raise ValueError('Supply the exact current text and tags from search_notes.')
        if text is None and tags is None:
            raise ValueError('Supply corrected text, tags, or both.')
        new_text = _clean(text, 'Note text') if text is not None else None
        new_tags = None
        if tags is not None:
            new_tags = ','.join(t.strip().lower() for t in _clean(tags, 'Tags', False).split(',') if t.strip())
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
            if row is None:
                raise ValueError('Note not found.')
            if row['text'] != expected_text or row['tags'] != expected_tags:
                raise ValueError('Note changed. Search notes again before editing; no change made.')
            updated_text = row['text'] if new_text is None else new_text
            updated_tags = row['tags'] if new_tags is None else new_tags
            if (updated_text, updated_tags) == (row['text'], row['tags']):
                raise ValueError('The edit must change text or tags.')
            db.execute('UPDATE notes SET text=?,tags=? WHERE id=?', (updated_text, updated_tags, note_id))
            result = dict(db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone())
        return result

    # --------------------------------------------------------------- expenses
    def add_expense(self, amount: float, category: str, note: str = "", spent_on: str | None = None) -> dict[str, Any]:
        if isinstance(amount, bool):
            raise ValueError("Amount must be a finite number, not a boolean.")
        try:
            amount = round(float(amount), 2)
        except (TypeError, ValueError) as exc:
            raise ValueError("Amount must be a number.") from exc
        if not math.isfinite(amount) or amount <= 0 or amount > MAX_AMOUNT:
            raise ValueError("Amount must be above zero and below 100,000,000.")
        category = _clean(category, "Category").lower()
        note = _clean(note, "Note", False)
        day = _parse_day(spent_on).isoformat()
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO expenses (amount, category, note, spent_on, created_at) VALUES (?, ?, ?, ?, ?)",
                (amount, category, note, day, _now()),
            )
            row = db.execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    @staticmethod
    def _expense_record(row) -> dict[str, Any]:
        record = dict(row)
        payload = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return {**record, 'revision': hashlib.sha256(payload.encode()).hexdigest()}

    def list_expenses(self, month: str | None = None, limit: int = 50) -> dict[str, Any]:
        month = self._expense_month(month)
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('limit must be an integer from 1 to 200.')
        with self._connect() as db:
            rows = db.execute('SELECT * FROM expenses WHERE substr(spent_on,1,7)=? ORDER BY spent_on DESC,id DESC LIMIT ?',
                              (month, limit + 1)).fetchall()
        return {'month': month, 'expenses': [self._expense_record(row) for row in rows[:limit]],
                'truncated': len(rows) > limit,
                'notice': 'Local manually entered bookkeeping only. Revision tokens detect a changed row, not identity or authorization. Amounts have no currency metadata; do not infer or combine currencies.'}

    @staticmethod
    def _expense_month(month: str | None = None) -> str:
        value = date.today().strftime('%Y-%m') if month is None else month
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}', value):
            raise ValueError('Month must look like 2026-11.')
        try:
            date.fromisoformat(value + '-01')
        except ValueError as exc:
            raise ValueError('Choose a valid YYYY-MM month.') from exc
        return value

    def edit_expense(self, expense_id: int, expected_revision: str, amount: float | None = None,
                     category: str | None = None, note: str | None = None,
                     spent_on: str | None = None) -> dict[str, Any]:
        if type(expense_id) is not int or expense_id < 1:
            raise ValueError('Choose a positive expense ID from list_expenses.')
        if not isinstance(expected_revision, str) or not re.fullmatch('[0-9a-f]{64}', expected_revision):
            raise ValueError('Use the exact revision from list_expenses.')
        if all(value is None for value in (amount, category, note, spent_on)):
            raise ValueError('Supply at least one corrected expense field.')
        values: dict[str, Any] = {}
        if amount is not None:
            if isinstance(amount, bool):
                raise ValueError('Amount must be a finite number, not a boolean.')
            try:
                clean_amount = round(float(amount), 2)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError('Amount must be a finite number.') from exc
            if not math.isfinite(clean_amount) or not 0 < clean_amount <= MAX_AMOUNT:
                raise ValueError('Amount must be above zero and at most 100,000,000.')
            values['amount'] = clean_amount
        if category is not None:
            values['category'] = _clean(category, 'Category').lower()
        if note is not None:
            values['note'] = _clean(note, 'Note', False)
        if spent_on is not None:
            if not isinstance(spent_on, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', spent_on):
                raise ValueError('spent_on must be YYYY-MM-DD.')
            values['spent_on'] = _parse_day(spent_on).isoformat()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM expenses WHERE id=?', (expense_id,)).fetchone()
            if row is None:
                raise ValueError('Expense not found.')
            current = self._expense_record(row)
            if current['revision'] != expected_revision:
                raise ValueError('Expense changed. List expenses again before editing; no change made.')
            if all(current[key] == value for key, value in values.items()):
                raise ValueError('The edit must change an expense field.')
            updated = {**dict(row), **values}
            db.execute('UPDATE expenses SET amount=?,category=?,note=?,spent_on=? WHERE id=?',
                       (updated['amount'], updated['category'], updated['note'], updated['spent_on'], expense_id))
            result = self._expense_record(db.execute('SELECT * FROM expenses WHERE id=?', (expense_id,)).fetchone())
        return {'expense': result,
                'notice': 'Corrected only this local bookkeeping row. Identity and creation time are preserved. No money moved, external account changed, currency conversion or deletion performed. Existing summaries now reflect the corrected entry.'}

    def expense_summary(self, month: str | None = None) -> dict[str, Any]:
        """Totals by category for a month given as YYYY-MM (default: this month)."""
        month = self._expense_month(month)
        with self._connect() as db:
            rows = db.execute(
                "SELECT category, ROUND(SUM(amount), 2) AS total, COUNT(*) AS n FROM expenses "
                "WHERE substr(spent_on, 1, 7) = ? GROUP BY category ORDER BY total DESC",
                (month,),
            ).fetchall()
        by_category = [dict(r) for r in rows]
        return {
            "month": month,
            "total": round(sum(r["total"] for r in by_category), 2),
            "count": sum(r["n"] for r in by_category),
            "by_category": by_category,
        }

    # ----------------------------------------------------------------- habits
    def log_habit(self, habit: str, day: str | None = None) -> dict[str, Any]:
        habit = _clean(habit, "Habit").lower()
        d = _parse_day(day)
        if d > date.today():
            raise ValueError("Cannot log a habit for a future day.")
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO habit_logs (habit, day) VALUES (?, ?)", (habit, d.isoformat()))
        return {"habit": habit, "day": d.isoformat(), **self.streak(habit)}

    def streak(self, habit: str) -> dict[str, Any]:
        """Current streak: consecutive days ending today, or yesterday if today is not logged yet."""
        habit = habit.strip().lower()
        with self._connect() as db:
            days = {r["day"] for r in db.execute("SELECT day FROM habit_logs WHERE habit = ?", (habit,))}
        today = date.today()
        cursor = today if today.isoformat() in days else today - timedelta(days=1)
        current = 0
        while cursor.isoformat() in days:
            current += 1
            cursor -= timedelta(days=1)
        best = run = 0
        previous: date | None = None
        for d in sorted(date.fromisoformat(x) for x in days):
            run = run + 1 if previous and (d - previous).days == 1 else 1
            best = max(best, run)
            previous = d
        return {"current_streak": current, "best_streak": best, "done_today": today.isoformat() in days, "total_days": len(days)}

    def habits(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            names = [r["habit"] for r in db.execute("SELECT DISTINCT habit FROM habit_logs ORDER BY habit")]
        return [{"habit": n, **self.streak(n)} for n in names]

    # --------------------------------------------------------------- briefing
    def briefing(self, open_commitments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """One-screen summary for 'what is my day look like'. Commitments come from the ownership store."""
        commitments = open_commitments or []
        habits = self.habits()
        today_spend = 0.0
        with self._connect() as db:
            row = db.execute("SELECT COALESCE(SUM(amount), 0) AS t FROM expenses WHERE spent_on = ?", (date.today().isoformat(),)).fetchone()
            today_spend = round(row["t"], 2)
        lines = []
        overdue = [c for c in commitments if c.get("overdue")]
        if overdue:
            lines.append(f"{len(overdue)} overdue: " + "; ".join(c["text"] for c in overdue[:3]))
        if commitments:
            lines.append(f"{len(commitments)} open commitment(s).")
        pending = [h["habit"] for h in habits if not h["done_today"]]
        if pending:
            lines.append("Habits not done yet today: " + ", ".join(pending) + ".")
        lines.append(f"Spent today: {today_spend:g}.")
        month = self.expense_summary()
        lines.append(f"Spent this month: {month['total']:g}.")
        return {
            "date": date.today().isoformat(),
            "overdue_commitments": len(overdue),
            "open_commitments": len(commitments),
            "habits_pending": pending,
            "spent_today": today_spend,
            "spent_this_month": month["total"],
            "summary": " ".join(lines),
        }


_default: PersonalStore | None = None


def default_store() -> PersonalStore:
    global _default
    if _default is None:
        _default = PersonalStore()
    return _default
