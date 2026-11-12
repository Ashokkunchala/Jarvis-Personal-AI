from __future__ import annotations

import pytest

from jarvis.telemetry import record_runtime_event, runtime_events


@pytest.fixture(autouse=True)
def isolated_runtime_history(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "runtime.sqlite3"))


def test_history_survives_loss_of_process_buffer(monkeypatch, tmp_path):
    from jarvis import telemetry

    event_id = record_runtime_event("task", action="task_end", success=True)
    telemetry._events.clear()
    snapshot = telemetry.runtime_events(after_id=event_id - 1)
    assert snapshot["storage"] == "sqlite"
    assert snapshot["events"][-1]["id"] == event_id
    assert snapshot["events"][-1]["action"] == "task_end"


def test_runtime_events_keep_only_allowlisted_bounded_summaries():
    first_id = record_runtime_event(
        "tool",
        action="task_end",
        tool="system_status",
        success=True,
        elapsed=0.12549,
        prompt="private prompt text",
        args={"token": "secret"},
        error="raw exception with private content",
    )
    snapshot = runtime_events(after_id=first_id - 1, limit=5)
    event = next(item for item in snapshot["events"] if item["id"] == first_id)
    assert event["category"] == "tool"
    assert event["tool"] == "system_status"
    assert event["elapsed"] == 0.125
    assert "prompt" not in event
    assert "args" not in event
    assert "error" not in event
    assert "secret" not in repr(event)


def test_runtime_event_reader_clamps_limits_and_retention():
    ids = [record_runtime_event("provider", provider="test", success=True) for _ in range(205)]
    snapshot = runtime_events(after_id=ids[-205] - 1, limit=999)
    assert snapshot["retained"] == 200
    assert len(snapshot["events"]) <= 100
    assert snapshot["oldest_id"] > ids[0]
    assert snapshot["latest_id"] == ids[-1]
    assert runtime_events(after_id=-100, limit=0)["events"]


def test_unknown_runtime_event_categories_are_ignored():
    assert record_runtime_event("prompt", text="do not store") == 0
