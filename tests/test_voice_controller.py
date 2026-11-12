"""Offline tests for the robot's background voice-call controller."""

from __future__ import annotations

import asyncio
import time

from jarvis.terminal import voice as voice_mod
from jarvis.terminal.voice import VoiceCall, VoiceView


class FakeAgent:
    def __init__(self) -> None:
        self.initialized = False
        self.call_mode: bool | None = None
        self.stopped = False

    async def initialize(self) -> None:
        self.initialized = True

    async def start(self, call_mode: bool = False) -> None:
        self.call_mode = call_mode
        try:
            while True:
                await asyncio.sleep(0.02)
        finally:
            self.stopped = True

    async def stop(self) -> None:
        self.stopped = True


def _wait_for(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_missing_voice_packages_returns_a_list() -> None:
    assert isinstance(voice_mod.missing_voice_packages(), list)


def test_has_api_key_returns_bool() -> None:
    assert isinstance(voice_mod.has_api_key(), bool)


def test_preflight_reports_a_missing_key(monkeypatch) -> None:
    monkeypatch.setattr(voice_mod, "missing_voice_packages", lambda: [])
    monkeypatch.setattr(voice_mod, "has_api_key", lambda: False)

    call = VoiceCall()
    problem = call.start()

    assert "GEMINI_API_KEY" in problem
    assert call.view().state == "error"
    assert call.is_active() is False


def test_preflight_reports_missing_packages(monkeypatch) -> None:
    monkeypatch.setattr(voice_mod, "missing_voice_packages", lambda: ["numpy", "scipy"])
    monkeypatch.setattr(voice_mod, "has_api_key", lambda: True)

    call = VoiceCall()
    problem = call.start()

    assert "numpy" in problem and "scipy" in problem
    assert call.view().state == "error"
    assert call.is_active() is False


def test_event_mirroring_builds_the_render_view() -> None:
    call = VoiceCall(preflight=False)

    call._on_event("ready", {"call_mode": True})
    assert call.view().state == "live"

    call._on_event("transcript", {"source": "user", "text": "open chrome"})
    assert call.view().user == "open chrome"
    assert call.view().reply == ""

    call._on_event("transcript", {"source": "model", "text": "Opening Chrome."})
    assert call.view().reply == "Opening Chrome."

    call._on_event("tool", {"name": "open_app"})
    assert call.view().tool == "open_app"

    call._on_event("interrupted", {})
    assert call.view().reply == ""

    call._on_event("error", {"message": "microphone busy"})
    view = call.view()
    assert view.state == "error"
    assert "microphone busy" in view.detail
    assert isinstance(view, VoiceView)
    assert call.view().active is False  # error is ambient, not a live call


def test_call_runs_in_a_background_thread_and_hangs_up() -> None:
    agent = FakeAgent()
    call = VoiceCall(agent_factory=lambda: agent, preflight=False, join_timeout=5.0)

    assert call.start() == ""
    assert _wait_for(lambda: agent.initialized and agent.call_mode is True)
    assert call.is_active() is True

    call._on_event("wake", {"mode": "call"})
    assert call.view().state == "live"
    assert call.view().detail == "call live"

    call.stop()
    assert call.is_active() is False
    assert call.view().state == "off"
    assert agent.stopped is True
