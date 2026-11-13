"""Persistent, timezone-aware daily briefing scheduler.

Turns the existing ``daily_briefing`` tool into a real scheduled job: the
briefing is generated automatically at a chosen local time every day, stored
locally, and shown on demand. All state lives in the same SQLite database as
the personal store, so jobs survive restarts - after a crash or reboot the
next ``run_due`` call simply picks up whatever came due while JARVIS was off.

Design points:

* timezone-aware: each job stores an IANA timezone (or "" for system-local);
  next runs are computed with zoneinfo so DST changes are handled
* dedup: at most one recorded briefing per job per local day, enforced by a
  UNIQUE constraint, so a double-fire never double-records
* missed-run policy per job: ``catchup`` (run once when JARVIS next wakes)
  or ``skip`` (record the miss and move to the next slot)
* local data only: briefings are built from notes, habits, expenses and
  commitments. Nothing is emailed, messaged or sent anywhere.
* full audit history in ``briefing_runs``; jobs can be listed, disabled and
  cancelled, and the next run time is always user-visible
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jarvis import personal
from jarvis.ownership import OwnershipStore

__all__ = ["BriefingScheduler"]

MAX_NAME_CHARS = 60
VALID_CATCHUP = ("catchup", "skip")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS briefing_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    time_of_day TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT '',
    catchup TEXT NOT NULL DEFAULT 'catchup',
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS briefing_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    local_date TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    UNIQUE (job_id, local_date)
);
"""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


class BriefingScheduler:
    """Manage and execute scheduled daily briefings."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        store: personal.PersonalStore | None = None,
        ownership: OwnershipStore | None = None,
    ) -> None:
        # Default: share the personal store's database file so all local
        # life-data lives in one place the user can back up or delete.
        self._owns_store = store is None
        self.store = store or personal.PersonalStore(db_path)
        self.ownership = ownership
        self.path = self.store.path
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    # ------------------------------------------------------------- validation
    @staticmethod
    def _parse_time(value: str) -> time:
        match = _TIME_RE.match((value or "").strip())
        if not match:
            raise ValueError("Time must look like 07:30 (24-hour).")
        return time(int(match.group(1)), int(match.group(2)))

    @staticmethod
    def _parse_tz(name: str) -> ZoneInfo | None:
        """None means system-local; otherwise a validated IANA timezone."""
        name = (name or "").strip()
        if not name:
            return None
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
            raise ValueError(
                f"Unknown timezone '{name}'. Use an IANA name like Asia/Calcutta, "
                "or leave it empty for the system timezone."
            ) from exc

    @staticmethod
    def _tz(job: sqlite3.Row | dict[str, Any]):
        return ZoneInfo(job["timezone"]) if job["timezone"] else None

    @staticmethod
    def _next_after(after: datetime, at: time, tz) -> datetime:
        """First local wall-clock occurrence of `at` strictly after `after`."""
        local = after.astimezone(tz) if tz else after.astimezone()
        candidate = datetime.combine(local.date(), at, tzinfo=local.tzinfo)
        if candidate <= after.astimezone(candidate.tzinfo):
            candidate = datetime.combine(local.date() + timedelta(days=1), at, tzinfo=local.tzinfo)
        return candidate

    # ------------------------------------------------------------------- jobs
    def set_daily(
        self,
        name: str = "daily",
        time_of_day: str = "07:30",
        timezone: str = "",
        *,
        catchup: str = "catchup",
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create or update a daily briefing job (dedup by name)."""
        name = (name or "").strip().lower()
        if not name:
            raise ValueError("Give the schedule a name, e.g. morning.")
        if len(name) > MAX_NAME_CHARS:
            raise ValueError(f"Keep the name to {MAX_NAME_CHARS} characters or fewer.")
        at = self._parse_time(time_of_day)
        tz = self._parse_tz(timezone)
        if catchup not in VALID_CATCHUP:
            raise ValueError(f"Missed-run policy must be one of: {', '.join(VALID_CATCHUP)}.")
        normalized_time = f"{at.hour:02d}:{at.minute:02d}"
        tz_name = "" if tz is None else str(tz)
        now = _utcnow()
        next_run = self._next_after(now, at, tz)
        with self._connect() as db:
            db.execute(
                "INSERT INTO briefing_jobs (name, time_of_day, timezone, catchup, enabled, "
                "next_run_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET time_of_day=excluded.time_of_day, "
                "timezone=excluded.timezone, catchup=excluded.catchup, enabled=excluded.enabled, "
                "next_run_at=excluded.next_run_at, updated_at=excluded.updated_at",
                (name, normalized_time, tz_name, catchup, int(enabled), _iso(next_run),
                 _iso(now), _iso(now)),
            )
        return self.get(name)

    def get(self, name: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM briefing_jobs WHERE name = ?", ((name or "").strip().lower(),)
            ).fetchone()
        if row is None:
            raise ValueError(f"No briefing schedule named '{name}'.")
        return self._describe(row)

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM briefing_jobs ORDER BY name").fetchall()
        return [self._describe(r) for r in rows]

    def cancel(self, name: str) -> dict[str, Any]:
        """Delete a schedule. Its past briefing history is kept."""
        with self._connect() as db:
            cur = db.execute(
                "DELETE FROM briefing_jobs WHERE name = ?", ((name or "").strip().lower(),)
            )
        if not cur.rowcount:
            raise ValueError(f"No briefing schedule named '{name}'.")
        return {"cancelled": name.strip().lower()}

    def enable(self, name: str, enabled: bool = True) -> dict[str, Any]:
        job = self.get(name)
        with self._connect() as db:
            next_run = None
            if enabled:
                at = self._parse_time(job["time_of_day"])
                next_run = _iso(self._next_after(_utcnow(), at, self._tz(job)))
            db.execute(
                "UPDATE briefing_jobs SET enabled=?, next_run_at=COALESCE(?, next_run_at), "
                "updated_at=? WHERE name=?",
                (int(enabled), next_run, _iso(_utcnow()), job["name"]),
            )
        return self.get(name)

    # -------------------------------------------------------------- describe
    def _describe(self, row: sqlite3.Row) -> dict[str, Any]:
        job = dict(row)
        next_run_at = job.get("next_run_at")
        next_local = None
        if next_run_at:
            dt = datetime.fromisoformat(next_run_at)
            tz = self._tz(job)
            next_local = (dt.astimezone(tz) if tz else dt.astimezone()).isoformat(timespec="seconds")
        return {
            "name": job["name"],
            "time_of_day": job["time_of_day"],
            "timezone": job["timezone"] or "system",
            "catchup": job["catchup"],
            "enabled": bool(job["enabled"]),
            "next_run_at": next_run_at,
            "next_run_local": next_local,
        }

    def next_run_text(self, name: str = "daily") -> str:
        """User-visible next run, e.g. 'daily: next briefing 2026-11-14 07:30 (system)'."""
        job = self.get(name)
        if not job["enabled"] or not job["next_run_local"]:
            return f"{job['name']}: disabled."
        local = datetime.fromisoformat(job["next_run_local"])
        return (
            f"{job['name']}: next briefing {local.strftime('%Y-%m-%d %H:%M')} "
            f"({job['timezone']})."
        )

    # ------------------------------------------------------------------- run
    def _generate(self) -> str:
        commitments = self.ownership.list() if self.ownership is not None else []
        return str(self.store.briefing(commitments)["summary"])

    def run_due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Run every enabled job whose time has come. Safe to call repeatedly."""
        now = (now or _utcnow()).astimezone(UTC)
        outcomes: list[dict[str, Any]] = []
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM briefing_jobs WHERE enabled=1 AND next_run_at IS NOT NULL "
                "AND next_run_at <= ? ORDER BY next_run_at, id",
                (_iso(now),),
            ).fetchall()
            for row in rows:
                outcomes.append(self._run_one(db, row, now))
        return outcomes

    def _run_one(self, db: sqlite3.Connection, row: sqlite3.Row, now: datetime) -> dict[str, Any]:
        job_id = int(row["id"])
        tz = self._tz(row)
        local_now = now.astimezone(tz) if tz else now.astimezone()
        local_date = local_now.date().isoformat()
        due_at = datetime.fromisoformat(row["next_run_at"])
        missed_by = now - due_at

        # Missed-run policy: 'skip' records the miss without generating a
        # briefing when we are well past the slot; 'catchup' runs once.
        if row["catchup"] == "skip" and missed_by > timedelta(hours=1):
            status, summary = "skipped", "Missed the scheduled time; skipped per policy."
        else:
            try:
                summary = self._generate()
                status = "catchup" if missed_by > timedelta(minutes=5) else "ok"
            except Exception:  # noqa: BLE001 - audit must not store exception details
                status, summary = "error", "Briefing generation failed; see application logs."

        # Dedup: one recorded briefing per job per local day, enforced by the
        # UNIQUE(job_id, local_date) constraint. A repeat on the same day just
        # advances the schedule.
        cur = db.execute(
            "INSERT OR IGNORE INTO briefing_runs (job_id, local_date, ran_at, status, summary) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, local_date, _iso(now), status, summary),
        )
        recorded = cur.rowcount > 0

        at = self._parse_time(row["time_of_day"])
        next_run = self._next_after(now, at, tz)
        db.execute(
            "UPDATE briefing_jobs SET next_run_at=?, updated_at=? WHERE id=?",
            (_iso(next_run), _iso(now), job_id),
        )
        return {
            "name": row["name"],
            "status": status if recorded else "already-recorded",
            "local_date": local_date,
            "summary": summary if recorded else "",
            "next_run_local": self._describe(
                db.execute("SELECT * FROM briefing_jobs WHERE id=?", (job_id,)).fetchone()
            )["next_run_local"],
        }

    def history(self, name: str | None = None, limit: int = 14) -> list[dict[str, Any]]:
        """Audit trail of generated/missed briefings, newest first."""
        limit = max(1, min(int(limit), 100))
        with self._connect() as db:
            if name:
                rows = db.execute(
                    "SELECT r.* FROM briefing_runs r JOIN briefing_jobs j ON j.id = r.job_id "
                    "WHERE j.name = ? ORDER BY r.id DESC LIMIT ?",
                    ((name or "").strip().lower(), limit),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT r.* FROM briefing_runs r ORDER BY r.id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [
            {
                "job_id": r["job_id"],
                "local_date": r["local_date"],
                "ran_at": r["ran_at"],
                "status": r["status"],
                "summary": r["summary"],
            }
            for r in rows
        ]

    def latest(self, name: str = "daily") -> dict[str, Any] | None:
        """The most recent recorded briefing for display at startup or on ask."""
        rows = self.history(name, limit=1)
        return rows[0] if rows else None

    def status(self) -> dict[str, Any]:
        """Compact state for `jarvis doctor`."""
        jobs = self.list()
        with self._connect() as db:
            runs = db.execute("SELECT COUNT(*) AS n FROM briefing_runs").fetchone()["n"]
        return {
            "jobs": jobs,
            "recorded_runs": runs,
            "next": [self.next_run_text(j["name"]) for j in jobs if j["enabled"]],
        }
