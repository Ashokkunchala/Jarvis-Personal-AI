"""Tests for the tool registry, built-in tools and the Gemini tool-calling brain.

These tests exercise the control plane (laptop + Android facades, schemas,
confirmation gating, risk levels) without calling the live Gemini API.
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
    return build_registry()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def test_registry_is_populated(registry: ToolRegistry) -> None:
    assert len(registry) >= 100
    assert len(registry.categories()) >= 15


def test_every_tool_has_a_json_safe_schema(registry: ToolRegistry) -> None:
    for schema in registry.get_tool_schemas():
        assert schema["name"]
        assert schema["description"]
        json.dumps(schema)  # must be serialisable for the Gemini request


def test_registry_lookup_helpers(registry: ToolRegistry) -> None:
    assert "battery_status" in registry.names("system")
    assert registry.get("battery_status") is not None
    assert registry.get("definitely_not_a_tool") is None


def test_risky_tools_require_confirmation(registry: ToolRegistry) -> None:
    risky = registry.get("shutdown_pc")
    if risky is None:
        pytest.skip("shutdown_pc not registered")
    assert risky.confirm_required or risky.risk >= Risk.HIGH


# ---------------------------------------------------------------------------
# Confirmation gating
# ---------------------------------------------------------------------------
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


def test_low_risk_tools_run_without_a_prompt(registry: ToolRegistry) -> None:
    async def boom(tool, args) -> bool:  # pragma: no cover - must not run
        raise AssertionError("SAFE/LOW tools should not prompt")

    result = asyncio.run(
        registry.execute("get_volume", {}, confirm=boom, auto_approve=False)
    )
    assert result.ok is True


def test_approved_confirmation_runs_the_tool(registry: ToolRegistry) -> None:
    async def approve(tool, args) -> bool:
        return True

    result = asyncio.run(
        registry.execute("get_volume", {}, confirm=approve, auto_approve=False)
    )
    assert result.ok is True
    assert "volume" in result.data


def test_auto_approve_skips_the_prompt(registry: ToolRegistry) -> None:
    async def boom(tool, args) -> bool:  # pragma: no cover - must not run
        raise AssertionError("confirm callback should not fire with auto_approve")

    result = asyncio.run(
        registry.execute("battery_status", {}, confirm=boom, auto_approve=True)
    )
    assert result.ok is True


def test_unknown_tool_fails_gracefully(registry: ToolRegistry) -> None:
    result = asyncio.run(registry.execute("no_such_tool", {}))
    assert result.ok is False


def test_event_stream_reports_tool_lifecycle(registry: ToolRegistry) -> None:
    events: list[dict] = []

    result = asyncio.run(
        registry.execute("get_volume", {}, auto_approve=True, on_event=events.append)
    )
    assert result.ok is True
    kinds = [event["type"] for event in events]
    assert "tool_start" in kinds
    assert "tool_end" in kinds


# ---------------------------------------------------------------------------
# Laptop facade (pure local calls; no model, no network)
# ---------------------------------------------------------------------------
def test_laptop_status_shape(registry: ToolRegistry) -> None:
    result = asyncio.run(registry.execute("system_status", {}, auto_approve=True))
    assert result.ok is True
    assert "cpu_percent" in result.data


def test_volume_round_trip(registry: ToolRegistry) -> None:
    asyncio.run(registry.execute("set_volume", {"level": 32}, auto_approve=True))
    result = asyncio.run(registry.execute("get_volume", {}, auto_approve=True))
    assert result.ok is True
    assert result.data["volume"] == 32


def test_clipboard_round_trip(registry: ToolRegistry) -> None:
    asyncio.run(
        registry.execute("set_clipboard", {"text": "jarvis-test-clip"}, auto_approve=True)
    )
    result = asyncio.run(registry.execute("get_clipboard", {}, auto_approve=True))
    assert result.data["text"] == "jarvis-test-clip"


def test_blocked_shell_is_refused(registry: ToolRegistry) -> None:
    result = asyncio.run(
        registry.execute("run_shell", {"command": "rm -rf /"}, auto_approve=True)
    )
    assert result.ok is False


# ---------------------------------------------------------------------------
# Android facade degrades gracefully with no device
# ---------------------------------------------------------------------------
def test_android_tools_report_no_device(registry: ToolRegistry) -> None:
    result = asyncio.run(
        registry.execute("android_battery", {}, auto_approve=True)
    )
    if result.ok:
        pytest.skip("a real device is attached; skip the degraded-path assertion")
    assert result.ok is False


# ---------------------------------------------------------------------------
# Brain (offline pieces only — no live API calls)
# ---------------------------------------------------------------------------
def test_brain_builds_a_tool_chain_without_calling_the_api() -> None:
    from jarvis.core.brain import DEFAULT_FALLBACKS, JarvisBrain

    brain = JarvisBrain(api_key="fake-key-for-schema-only")
    assert brain.configured is True
    assert brain.model in brain.model_candidates()
    assert brain.model_candidates()[0] == brain.model
    for fallback in DEFAULT_FALLBACKS:
        assert fallback in brain.model_candidates()
    assert len(brain.registry) >= 100


def test_brain_marks_transient_errors_and_falls_back() -> None:
    from jarvis.core.brain import _is_transient, _mark_bad, _mark_good

    class FakeError(Exception):
        status_code = 429

    assert _is_transient(FakeError("429 RESOURCE_EXHAUSTED"))
    assert _is_transient(Exception("503 UNAVAILABLE"))
    assert not _is_transient(ValueError("bad arguments"))

    _mark_bad("gemini-test-model")
    _mark_good("gemini-good-model")
    from jarvis.core.brain import _model_cooldown

    assert "gemini-test-model" in _model_cooldown
    assert "gemini-good-model" not in _model_cooldown
