"""Wiring tests: speech, memory and briefing tools in the shared registry."""

from __future__ import annotations

import pytest

from jarvis.tools.builtin_tools import build_registry, reset_controllers
from jarvis.tools.registry import Risk


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    # Keep every store hermetic: point HOME at a tmp dir before building tools.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    reset_controllers()
    return build_registry(force=True)


def test_new_tools_registered_with_sane_risk(registry):
    expected = {
        "speak_text": Risk.LOW,
        "speech_status": Risk.SAFE,
        "memory_add_folder": Risk.LOW,
        "memory_search": Risk.SAFE,
        "memory_folders": Risk.SAFE,
        "memory_forget_folder": Risk.LOW,
        "memory_reindex": Risk.SAFE,
        "schedule_daily_briefing": Risk.LOW,
        "briefing_schedule_status": Risk.SAFE,
        "cancel_daily_briefing": Risk.LOW,
        "run_due_briefings": Risk.SAFE,
    }
    for name, risk in expected.items():
        tool = registry.get(name)
        assert tool is not None, f"missing tool: {name}"
        assert tool.risk == risk, f"{name} risk {tool.risk} != {risk}"
        assert not tool.confirm_required, f"{name} should not need confirmation"


def test_memory_and_briefing_tools_roundtrip(registry, tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "k8s.md").write_text("# k8s\n\nA pod is the smallest unit.\n", encoding="utf-8")

    add = registry.get("memory_add_folder").handler(folder=str(notes))
    assert add["success"] and add["added"] == 1
    found = registry.get("memory_search").handler(query="smallest unit")
    assert found["success"] and found["results"][0]["citation"].endswith("k8s.md:3")

    scheduled = registry.get("schedule_daily_briefing").handler(
        time_of_day="07:30", timezone="Asia/Calcutta", name="daily",
    )
    assert scheduled["success"]
    status = registry.get("briefing_schedule_status").handler()
    assert status["success"] and status["jobs"][0]["timezone"] == "Asia/Calcutta"
    cancelled = registry.get("cancel_daily_briefing").handler(name="daily")
    assert cancelled["success"]

    forgotten = registry.get("memory_forget_folder").handler(folder=str(notes))
    assert forgotten["success"] and forgotten["forgotten_docs"] == 1


def test_speak_text_fails_cleanly_without_backends(registry):
    # No pyttsx3 in the test venv: the tool explains instead of crashing.
    result = registry.get("speak_text").handler(text="hello")
    assert result["success"] is True  # guard caught the SpeechError
    assert result["spoken"] is False
    assert "pyttsx3" in result["error"]


def test_bad_briefing_time_is_a_clean_error(registry):
    result = registry.get("schedule_daily_briefing").handler(time_of_day="25:99")
    assert result == {"success": False, "error": "Time must look like 07:30 (24-hour)."}
