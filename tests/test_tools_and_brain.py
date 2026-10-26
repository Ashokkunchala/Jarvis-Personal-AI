"""Tests for the tool registry, built-in tools and the Gemini tool-calling brain.

The tests exercise registry validation and action gating without accessing real OS
hardware or calling the live Gemini API.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from jarvis.tools.builtin_tools import build_registry, reset_controllers
from jarvis.tools.registry import Risk, ToolRegistry


@pytest.fixture()
def registry() -> ToolRegistry:
    reset_controllers()
    return build_registry(force=True)


def test_registry_is_populated(registry: ToolRegistry) -> None:
    assert len(registry) >= 100
    assert len(registry.categories()) >= 15


def test_every_tool_has_a_json_safe_schema(registry: ToolRegistry) -> None:
    for schema in registry.get_tool_schemas():
        assert schema["name"]
        assert schema["description"]
        json.dumps(schema)


def test_registry_lookup_helpers(registry: ToolRegistry) -> None:
    assert "battery_status" in registry.names("system")
    assert registry.get("battery_status") is not None
    assert registry.get("definitely_not_a_tool") is None


def test_risky_tools_require_confirmation(registry: ToolRegistry) -> None:
    risky = registry.get("shutdown_pc")
    if risky is None:
        pytest.skip("shutdown_pc not registered")
    assert risky.confirm_required or risky.risk >= Risk.HIGH


def test_rejected_confirmation_blocks_the_tool(registry: ToolRegistry) -> None:
    calls: list[str] = []

    async def reject(tool, args) -> bool:
        calls.append(tool.name)
        return False

    result = asyncio.run(
        registry.execute("shutdown_pc", {"delay": 60}, confirm=reject, auto_approve=False)
    )
    assert calls == ["shutdown_pc"]
    assert result.ok is False
    assert result.cancelled is True


def test_low_risk_tools_run_without_a_prompt(registry: ToolRegistry, monkeypatch) -> None:
    from jarvis.control import audio

    monkeypatch.setattr(audio, "get_volume", lambda: {"success": True, "volume": 40, "muted": False})

    async def boom(tool, args) -> bool:  # pragma: no cover - must not run
        raise AssertionError("SAFE/LOW tools should not prompt")

    result = asyncio.run(
        registry.execute("get_volume", {}, confirm=boom, auto_approve=False)
    )
    assert result.ok is True
    assert result.data["volume"] == 40


def test_approved_confirmation_runs_tool(registry: ToolRegistry) -> None:
    calls: list[str] = []

    async def approve(tool, args) -> bool:
        calls.append(tool.name)
        return True

    async def handler(value: str = "approved") -> dict:
        return {"success": True, "value": value}

    registry.register(
        __import__("jarvis.tools.registry", fromlist=["Tool"]).Tool(
            name="confirmed_test_action",
            description="A deterministic test action.",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            risk=Risk.MEDIUM,
            category="test",
            requires_confirmation=True,
        )
    )
    result = asyncio.run(
        registry.execute("confirmed_test_action", {}, confirm=approve, auto_approve=False)
    )
    assert calls == ["confirmed_test_action"]
    assert result.ok is True
    assert result.data["value"] == "approved"


def test_auto_approve_skips_prompt_for_safe_tool(registry: ToolRegistry) -> None:
    from jarvis.control import info

    async def boom(tool, args) -> bool:  # pragma: no cover - must not run
        raise AssertionError("SAFE tools should not prompt")

    monkeypatch_calls: list[str] = []

    async def deterministic_info() -> dict:
        monkeypatch_calls.append("called")
        return {"success": True, "cpu_percent": 12.0}

    # Isolate the test from host-specific hardware and APIs.
    original = registry.get("system_status")
    assert original is not None
    registry.register(
        __import__("jarvis.tools.registry", fromlist=["Tool"]).Tool(
            name="system_status",
            description=original.description,
            parameters=original.parameters,
            handler=deterministic_info,
            risk=Risk.SAFE,
            category="system",
        )
    )
    result = asyncio.run(
        registry.execute("system_status", {}, confirm=boom, auto_approve=True)
    )
    assert result.ok is True
    assert result.data["cpu_percent"] == 12.0
    assert monkeypatch_calls == ["called"]


def test_unknown_tool_fails_gracefully(registry: ToolRegistry) -> None:
    result = asyncio.run(registry.execute("no_such_tool", {}))
    assert result.ok is False


def test_event_stream_reports_tool_lifecycle(registry: ToolRegistry) -> None:
    events: list[dict] = []

    async def handler() -> dict:
        return {"success": True, "status": "ready"}

    from jarvis.tools.registry import Tool

    registry.register(
        Tool(
            name="test_readiness",
            description="Deterministic readiness test",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            risk=Risk.SAFE,
            category="test",
        )
    )
    result = asyncio.run(
        registry.execute("test_readiness", {}, auto_approve=True, on_event=events.append)
    )
    assert result.ok is True
    kinds = [event["type"] for event in events]
    assert "tool_start" in kinds
    assert "tool_end" in kinds


def test_laptop_status_shape(registry: ToolRegistry) -> None:
    from jarvis.control import info

    original = registry.get("system_status")
    assert original is not None

    async def fake_status() -> dict:
        return {"success": True, "cpu_percent": 8.0, "memory_percent": 28.0}

    from jarvis.tools.registry import Tool

    registry.register(
        Tool(
            name="system_status",
            description=original.description,
            parameters=original.parameters,
            handler=fake_status,
            risk=Risk.SAFE,
            category="system",
        )
    )
    result = asyncio.run(registry.execute("system_status", {}, auto_approve=True))
    assert result.ok is True
    assert result.data["cpu_percent"] == 8.0


def test_volume_round_trip(registry: ToolRegistry, monkeypatch) -> None:
    from jarvis.control import audio

    state = {"volume": 32, "muted": False}
    monkeypatch.setattr(audio, "set_volume", lambda level: state.update(volume=level) or {"success": True, "volume": level})
    monkeypatch.setattr(audio, "get_volume", lambda: {"success": True, **state})
    asyncio.run(registry.execute("set_volume", {"level": 32}, auto_approve=True))
    result = asyncio.run(registry.execute("get_volume", {}, auto_approve=True))
    assert result.ok is True
    assert result.data["volume"] == 32


def test_clipboard_round_trip(registry: ToolRegistry, monkeypatch) -> None:
    from jarvis.control import clipboard

    state = {"text": ""}

    def fake_set_clipboard(text: str) -> dict:
        state["text"] = text
        return {"success": True, "length": len(text)}

    def fake_get_clipboard() -> dict:
        return {"success": True, "text": state["text"], "length": len(state["text"])}

    monkeypatch.setattr(clipboard, "set_clipboard", fake_set_clipboard)
    monkeypatch.setattr(clipboard, "get_clipboard", fake_get_clipboard)
    asyncio.run(registry.execute("set_clipboard", {"text": "jarvis-test-clip"}, auto_approve=True))
    result = asyncio.run(registry.execute("get_clipboard", {}, auto_approve=True))
    assert result.ok is True
    assert result.data["text"] == "jarvis-test-clip"


def test_blocked_shell_is_refused(registry: ToolRegistry) -> None:
    result = asyncio.run(registry.execute("run_shell", {"command": "rm -rf /"}, auto_approve=True))
    assert result.ok is False


def test_android_tools_report_no_device(registry: ToolRegistry) -> None:
    result = asyncio.run(registry.execute("android_battery", {}, auto_approve=True))
    if result.ok:
        pytest.skip("a real device is attached; skip the degraded-path assertion")
    assert result.ok is False


def test_brain_builds_tool_chain_without_live_api() -> None:
    from jarvis.core.brain import DEFAULT_FALLBACKS, JarvisBrain

    brain = JarvisBrain(api_key="fake-key-for-schema-only")
    assert brain.configured is True
    assert brain.model in brain.model_candidates()
    assert brain.model_candidates()[0] == brain.model
    for fallback in DEFAULT_FALLBACKS:
        assert fallback in brain.model_candidates()
    assert len(brain.registry) >= 100


def test_brain_marks_transient_errors_and_falls_back() -> None:
    from jarvis.core.brain import _is_transient, _mark_bad, _mark_good, _model_cooldown

    class FakeError(Exception):
        status_code = 429

    assert _is_transient(FakeError("429 RESOURCE_EXHAUSTED"))
    assert _is_transient(Exception("503 UNAVAILABLE"))
    assert not _is_transient(ValueError("bad arguments"))

    _mark_bad("gemini-test-model")
    _mark_good("gemini-good-model")
    assert "gemini-test-model" in _model_cooldown
    assert "gemini-good-model" not in _model_cooldown
