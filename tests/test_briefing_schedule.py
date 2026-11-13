"""Tests for the persistent timezone-aware briefing scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.briefing_schedule import BriefingScheduler
from jarvis.personal import PersonalStore


@pytest.fixture()
def scheduler(tmp_path, monkeypatch):
    # Pin registration before the fixed simulated execution time.
    monkeypatch.setattr("jarvis.briefing_schedule._utcnow", lambda: at(0, 0))
    store = PersonalStore(tmp_path / "personal.db")
    return BriefingScheduler(store=store)


def at(hour, minute=0, day_offset=0):
    base = datetime(2026, 11, 13, hour, minute, tzinfo=UTC)
    return base + timedelta(days=day_offset)


def test_set_daily_computes_next_run_in_utc(scheduler):
    job = scheduler.set_daily("morning", "07:30", "Asia/Calcutta")
    assert job["timezone"] == "Asia/Calcutta"
    assert job["enabled"] is True
    # 07:30 IST is 02:00 UTC the same day.
    assert "T02:00:00+00:00" in job["next_run_at"]
    assert "07:30" in job["next_run_local"]
    assert "next briefing" in scheduler.next_run_text("morning")


def test_system_local_timezone_is_allowed(scheduler):
    job = scheduler.set_daily("local", "06:00", "")
    assert job["timezone"] == "system"
    assert job["next_run_local"]


def test_validation(scheduler):
    with pytest.raises(ValueError, match="07:30"):
        scheduler.set_daily("bad", "7.30")
    with pytest.raises(ValueError, match="Unknown timezone"):
        scheduler.set_daily("bad", "07:30", "Mars/Olympus")
    with pytest.raises(ValueError, match="Missed-run policy"):
        scheduler.set_daily("bad", "07:30", "", catchup="forever")
    with pytest.raises(ValueError, match="name"):
        scheduler.set_daily("  ", "07:30")
    with pytest.raises(ValueError, match="No briefing schedule"):
        scheduler.get("missing")


def test_set_daily_upserts_by_name(scheduler):
    scheduler.set_daily("morning", "07:30")
    scheduler.set_daily("morning", "08:00")
    jobs = scheduler.list()
    assert len(jobs) == 1 and jobs[0]["time_of_day"] == "08:00"


def test_run_due_generates_and_records_once_per_day(scheduler):
    scheduler.set_daily("morning", "07:30", "UTC")
    scheduler.store.add_note("Drink water")
    now = at(8, 0)
    outcomes = scheduler.run_due(now)
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "catchup"  # fired 30 min after the slot
    assert "Spent today" in outcomes[0]["summary"]

    # A second run_due on the same day records nothing new (dedup).
    again = scheduler.run_due(now + timedelta(minutes=10))
    assert again == []

    history = scheduler.history("morning")
    assert len(history) == 1
    assert history[0]["local_date"] == "2026-11-13"

    # Next day the job fires again.
    following = scheduler.run_due(at(7, 31, day_offset=1))
    assert len(following) == 1
    assert len(scheduler.history("morning")) == 2


def test_next_run_advances_after_each_fire(scheduler):
    scheduler.set_daily("morning", "07:30", "UTC")
    scheduler.run_due(at(8, 0))
    job = scheduler.get("morning")
    assert job["next_run_local"].startswith("2026-11-14")


def test_missed_run_skip_policy(scheduler):
    scheduler.set_daily("quiet", "06:00", "UTC", catchup="skip")
    outcomes = scheduler.run_due(at(12, 0))  # 6 hours late
    assert outcomes[0]["status"] == "skipped"
    assert "skipped" in outcomes[0]["summary"].lower()
    # Still advances to tomorrow.
    assert scheduler.get("quiet")["next_run_local"].startswith("2026-11-14")


def test_restart_recovery_is_just_state(scheduler, tmp_path):
    """A fresh scheduler over the same DB sees pending jobs - that is recovery."""
    scheduler.set_daily("morning", "07:30", "UTC")
    reopened = BriefingScheduler(store=PersonalStore(tmp_path / "personal.db"))
    outcomes = reopened.run_due(at(9, 0))
    assert len(outcomes) == 1 and outcomes[0]["name"] == "morning"


def test_cancel_and_enable_disable(scheduler):
    scheduler.set_daily("morning", "07:30", "UTC")
    scheduler.enable("morning", False)
    assert scheduler.run_due(at(9, 0)) == []
    assert "disabled" in scheduler.next_run_text("morning")
    scheduler.enable("morning", True)
    assert scheduler.get("morning")["enabled"] is True
    scheduler.cancel("morning")
    assert scheduler.list() == []
    with pytest.raises(ValueError):
        scheduler.cancel("morning")


def test_briefing_uses_local_data_only(scheduler):
    from datetime import date

    scheduler.store.add_expense(120, "food")
    # Logged yesterday, not today: it should show up as pending today.
    scheduler.store.log_habit("reading", day=(date.today() - timedelta(days=1)).isoformat())
    scheduler.set_daily("morning", "07:30", "UTC")
    outcomes = scheduler.run_due(at(8, 0))
    summary = outcomes[0]["summary"]
    assert "Spent today: 120" in summary
    assert "reading" in summary  # habit not done today shows as pending


def test_status_for_doctor(scheduler):
    assert scheduler.status()["jobs"] == []
    scheduler.set_daily("morning", "07:30", "Asia/Calcutta")
    status = scheduler.status()
    assert len(status["jobs"]) == 1
    assert status["next"][0].startswith("morning:")
