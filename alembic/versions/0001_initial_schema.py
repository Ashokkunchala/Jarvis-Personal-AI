"""Baseline schema for the local SQLite database.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-10

The application historically created its tables lazily with
``CREATE TABLE IF NOT EXISTS``. This baseline migration reproduces exactly the
same schema so ``alembic upgrade head`` works for both a fresh database and an
existing database created by older builds. All statements are idempotent.
"""

from __future__ import annotations

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

_TABLES = (
    "memories",
    "reminders",
    "workouts",
    "plans",
    "plan_history",
    "scheduled_runs",
    "schedule_history",
    "devices",
    "auth_audit",
    "runtime_event_history",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_at TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            recurrence TEXT NOT NULL DEFAULT 'none'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            performed_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            due_at TEXT,
            reminder_id INTEGER,
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            tool TEXT NOT NULL,
            args_json TEXT NOT NULL DEFAULT '{}',
            interval_minutes INTEGER NOT NULL,
            next_run_at TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'disabled',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_run_at TEXT,
            last_status TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            status TEXT NOT NULL,
            elapsed REAL,
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            last_seen TEXT,
            revoked_at TEXT,
            user_agent TEXT,
            ip_address TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            action TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            timestamp TEXT NOT NULL,
            success INTEGER NOT NULL,
            details TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_event_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
