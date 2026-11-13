"""Tests for `jarvis doctor` health checks."""

from __future__ import annotations

import pytest

from jarvis.doctor import _redact_environment, run_checks


def test_doctor_runs_everywhere_without_raising():
    report = run_checks()
    names = [c.name for c in report.checks]
    for expected in (
        "python", "model-key", "voice-packages", "audio-devices",
        "elevenlabs-key", "android", "storage", "personal-db",
        "doc-memory", "scheduler",
    ):
        assert expected in names, f"missing check: {expected}"
    # The report always has a verdict.
    assert isinstance(report.ok, bool)
    rendered = report.as_dict()
    assert rendered["ok"] == report.ok
    assert len(rendered["checks"]) == len(report.checks)


def test_doctor_never_prints_secret_values(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "doctor-test-secret-xyz")
    monkeypatch.setenv("GEMINI_API_KEY", "doctor-test-gemini-xyz")
    report = run_checks()
    rendered = str(report.as_dict())
    assert "doctor-test-secret-xyz" not in rendered
    assert "doctor-test-gemini-xyz" not in rendered


def test_redact_environment():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ELEVENLABS_API_KEY", "abc123")
    try:
        assert "abc123" not in _redact_environment("token abc123 leaked")
        assert "<redacted>" in _redact_environment("token abc123 leaked")
    finally:
        monkeypatch.undo()


def test_elevenlabs_key_check_reports_presence_only(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "doctor-test-secret-xyz")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-1")
    report = run_checks()
    check = next(c for c in report.checks if c.name == "elevenlabs-key")
    assert check.ok
    assert "set" in check.detail
    assert "doctor-test-secret-xyz" not in check.detail
