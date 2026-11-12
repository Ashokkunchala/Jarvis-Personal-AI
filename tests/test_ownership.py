"""Tests for the ownership/commitment tracker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis import ownership
from jarvis.ownership import OwnershipStore


@pytest.fixture()
def store(tmp_path):
    return OwnershipStore(tmp_path / "ownership.db")


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


class TestCommitments:
    def test_add_and_list(self, store):
        item = store.add("Watch the ECS deployment")
        assert item["id"] >= 1
        assert item["done"] is False
        assert item["overdue"] is False
        open_items = store.list()
        assert [i["text"] for i in open_items] == ["Watch the ECS deployment"]

    def test_add_requires_text(self, store):
        with pytest.raises(ValueError):
            store.add("   ")

    def test_text_length_capped(self, store):
        with pytest.raises(ValueError):
            store.add("x" * (ownership.MAX_TEXT_CHARS + 1))

    def test_due_at_must_be_iso(self, store):
        with pytest.raises(ValueError):
            store.add("Check the logs", due_at="next Tuesday")

    def test_complete_marks_done(self, store):
        item = store.add("Follow up with Priya")
        done = store.complete(item["id"])
        assert done["done"] is True
        assert done["done_at"] is not None
        assert store.list() == []
        assert len(store.list(include_done=True)) == 1

    def test_complete_unknown_id_returns_none(self, store):
        assert store.complete(9999) is None

    def test_due_followups_only_overdue_open(self, store):
        past = _iso(datetime.now(UTC) - timedelta(hours=1))
        future = _iso(datetime.now(UTC) + timedelta(hours=1))
        overdue = store.add("Ping the on-call channel", due_at=past)
        store.add("Review the sprint board", due_at=future)
        store.add("No date commitment")
        finished = store.add("Already handled", due_at=past)
        store.complete(finished["id"])
        due = store.due_followups()
        assert [d["id"] for d in due] == [overdue["id"]]
        assert due[0]["overdue"] is True


class TestRegistryIntegration:
    def test_ownership_tools_registered(self):
        from jarvis.tools.builtin_tools import build_registry

        registry = build_registry()
        for name in ("track_commitment", "list_commitments", "complete_commitment", "check_followups"):
            assert registry.get(name) is not None, name

    def test_track_tool_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ownership, "_default_store", OwnershipStore(tmp_path / "o.db"))
        from jarvis.tools.builtin_tools import build_registry

        registry = build_registry()
        added = registry.get("track_commitment").handler("Ship the release notes")
        assert added["success"] is True
        listed = registry.get("list_commitments").handler()
        assert listed["commitments"][0]["text"] == "Ship the release notes"
        bad = registry.get("track_commitment").handler("")
        assert bad["success"] is False
