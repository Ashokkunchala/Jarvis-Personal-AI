"""Tests for the personal notes, expenses and habits store."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from jarvis.personal import PersonalStore
from jarvis.tools.builtin_tools import build_registry, reset_controllers


@pytest.fixture()
def store(tmp_path):
    return PersonalStore(tmp_path / "personal.db")


def test_notes_add_and_search(store):
    store.add_note("Renew the domain", "Work, Admin")
    store.add_note("Buy milk")
    assert [n["text"] for n in store.search_notes("domain")] == ["Renew the domain"]
    assert store.search_notes("admin")[0]["tags"] == "work,admin"
    assert len(store.search_notes("")) == 2
    with pytest.raises(ValueError):
        store.add_note("  ")


def test_expenses_validate_and_summarise(store):
    store.add_expense(250, "Food", spent_on="2026-11-02")
    store.add_expense(750.5, "food", "dinner", "2026-11-05")
    store.add_expense(4000, "rent", spent_on="2026-11-01")
    store.add_expense(100, "food", spent_on="2026-10-30")
    summary = store.expense_summary("2026-11")
    assert summary["total"] == 5000.5 and summary["count"] == 3
    assert summary["by_category"][0] == {"category": "rent", "total": 4000.0, "n": 1}
    for bad in (0, -5, "abc", 10**9):
        with pytest.raises(ValueError):
            store.add_expense(bad, "x")
    with pytest.raises(ValueError):
        store.add_expense(5, "x", spent_on="13/11/2026")
    with pytest.raises(ValueError):
        store.expense_summary("November")


def test_habit_streaks(store):
    today = date.today()
    for back in (0, 1, 2, 5, 6):
        store.log_habit("Gym", (today - timedelta(days=back)).isoformat())
    info = store.streak("gym")
    assert info["current_streak"] == 3 and info["best_streak"] == 3 and info["done_today"] is True
    store.log_habit("gym", today.isoformat())  # idempotent
    assert store.streak("gym")["total_days"] == 5
    with pytest.raises(ValueError):
        store.log_habit("gym", (today + timedelta(days=1)).isoformat())


def test_streak_survives_until_end_of_today(store):
    store.log_habit("read", (date.today() - timedelta(days=1)).isoformat())
    info = store.streak("read")
    assert info["current_streak"] == 1 and info["done_today"] is False


def test_briefing(store):
    store.log_habit("gym", (date.today() - timedelta(days=1)).isoformat())
    store.add_expense(300, "food")
    result = store.briefing([{"text": "Call bank", "overdue": True}])
    assert result["habits_pending"] == ["gym"]
    assert result["overdue_commitments"] == 1 and result["spent_today"] == 300
    assert "Call bank" in result["summary"]


def test_personal_tools_registered(monkeypatch, tmp_path):
    from jarvis import personal

    monkeypatch.setattr(personal, "_default", PersonalStore(tmp_path / "p.db"))
    reset_controllers()
    reg = build_registry(force=True)
    for name in ("add_note", "search_notes", "log_expense", "expense_summary", "log_habit", "habit_streaks", "daily_briefing"):
        tool = reg.get(name)
        assert tool is not None and not tool.confirm_required
    out = reg.get("log_expense").handler(amount=-1, category="x")
    assert out["success"] is False
    assert reg.get("log_expense").handler(amount=50, category="food")["success"] is True
