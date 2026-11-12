from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.personal_data import _connect, _now
from app.scheduler import ScheduleRunner
from jarvis.tools.registry import Risk, Tool, ToolRegistry


def _create_due_schedule() -> int:
    due = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with _connect() as db:
        cursor = db.execute(
            "INSERT INTO scheduled_runs(title,tool,args_json,interval_minutes,next_run_at,enabled,state,created_at,updated_at) "
            "VALUES('test metric','system_status','{}',5,?,1,'scheduled',?,?)",
            (due, _now(), _now()),
        )
        return int(cursor.lastrowid)


def _registry(handler) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(
        name="system_status", description="test metric", parameters={"type": "object", "properties": {}},
        handler=handler, risk=Risk.SAFE,
    ))
    return registry


@pytest.mark.asyncio
async def test_scheduler_runs_only_safe_metric_and_persists_status_without_result(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "schedules.sqlite3"))
    schedule_id = _create_due_schedule()
    runner = ScheduleRunner(registry_factory=lambda: _registry(lambda: {"cpu_percent": 17}))

    tasks = await runner.run_due_once()
    assert len(tasks) == 1
    await asyncio.gather(*tasks)

    with _connect() as db:
        schedule = db.execute("SELECT * FROM scheduled_runs WHERE id=?", (schedule_id,)).fetchone()
        events = db.execute("SELECT event,status FROM schedule_history WHERE schedule_id=? ORDER BY id",
                            (schedule_id,)).fetchall()
    assert schedule["state"] == "scheduled"
    assert schedule["last_status"] == "success"
    assert [tuple(event) for event in events] == [("started", "running"), ("finished", "success")]
    assert "cpu_percent" not in repr([dict(event) for event in events])


@pytest.mark.asyncio
async def test_disabling_schedule_cancels_active_task_and_leaves_it_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "schedules.sqlite3"))
    schedule_id = _create_due_schedule()
    started = asyncio.Event()

    async def wait_for_cancel():
        started.set()
        await asyncio.Event().wait()

    runner = ScheduleRunner(registry_factory=lambda: _registry(wait_for_cancel))
    tasks = await runner.run_due_once()
    await asyncio.wait_for(started.wait(), timeout=1)
    with _connect() as db:
        db.execute("UPDATE scheduled_runs SET enabled=0,state='disabled' WHERE id=?", (schedule_id,))
    await runner.cancel_schedule(schedule_id)
    await asyncio.gather(*tasks, return_exceptions=True)

    with _connect() as db:
        schedule = db.execute("SELECT state,last_status FROM scheduled_runs WHERE id=?", (schedule_id,)).fetchone()
        last_event = db.execute("SELECT event,status FROM schedule_history WHERE schedule_id=? ORDER BY id DESC LIMIT 1",
                                (schedule_id,)).fetchone()
    assert tuple(schedule) == ("disabled", "cancelled")
    assert tuple(last_event) == ("finished", "cancelled")


@pytest.mark.asyncio
async def test_scheduler_refuses_database_tampering_to_use_unallowlisted_tool(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "schedules.sqlite3"))
    schedule_id = _create_due_schedule()
    with _connect() as db:
        db.execute("UPDATE scheduled_runs SET tool='read_file' WHERE id=?", (schedule_id,))
    runner = ScheduleRunner(registry_factory=lambda: _registry(lambda: pytest.fail("unsafe tool executed")))
    tasks = await runner.run_due_once()
    await asyncio.gather(*tasks)
    with _connect() as db:
        status = db.execute("SELECT last_status FROM scheduled_runs WHERE id=?", (schedule_id,)).fetchone()[0]
    assert status == "failed"
