"""Fail-closed tool boundary invariants.

These tests guard the security posture of the whole registry rather than one
tool: destructive tools must always ask, file mutations must show an exact
preview first, and a tool that needs approval must never run when there is
no way to ask. The registry entrypoints (voice agent, TUI, scheduler) all go
through ToolRegistry.execute, so holding the line there covers every caller.
"""

from __future__ import annotations

import pytest

from jarvis.tools.builtin_tools import build_registry, reset_controllers
from jarvis.tools.registry import Risk


@pytest.fixture()
def registry():
    reset_controllers()
    return build_registry(force=True)


def _all(registry):
    return list(registry.tools.values())


def test_every_high_risk_tool_requires_confirmation(registry):
    offenders = [t.name for t in _all(registry) if t.risk >= Risk.HIGH and not t.requires_confirmation]
    assert offenders == [], f"HIGH tools without confirmation: {offenders}"


def test_every_mutating_medium_tool_asks_first(registry):
    """MEDIUM tools change state; each must require confirmation (fail closed)."""
    offenders = [
        t.name for t in _all(registry)
        if t.risk == Risk.MEDIUM and not t.requires_confirmation
    ]
    assert offenders == [], f"MEDIUM tools without confirmation: {offenders}"


def test_local_file_mutations_always_show_an_exact_preview(registry):
    """Write/copy/move/delete/organize must preview the exact change first."""
    mutation_tools = {"write_file", "copy_file", "move_file", "delete_file", "organize_folder"}
    for name in mutation_tools:
        tool = registry.get(name)
        assert tool is not None
        assert tool.confirmation_preview is not None, f"{name} has no preview"
        assert not tool.allow_auto_approve, f"{name} must never auto-approve"


def test_unknown_tool_fails_closed(registry):
    import asyncio

    result = asyncio.run(registry.execute("definitely_not_a_tool", {}))
    assert not result.ok and "Unknown tool" in result.error


def test_confirmation_required_tool_never_runs_without_a_confirm_callback(registry):
    """Fail closed: no way to ask the user means the action does not happen."""
    import asyncio

    ran = {"called": False}

    def handler():
        ran["called"] = True
        return {"success": True}

    from jarvis.tools.registry import Tool, ToolRegistry

    reg = ToolRegistry()
    reg.register(Tool(
        name="danger", description="x", parameters={"type": "object", "properties": {}},
        handler=handler, risk=Risk.HIGH, requires_confirmation=True,
    ))
    result = asyncio.run(reg.execute("danger", {}, confirm=None))
    assert not result.ok and result.cancelled
    assert ran["called"] is False


def test_scheduler_only_allows_read_only_metric_tools():
    """The app scheduler's allowlist must stay read-only (SAFE metrics only)."""
    from app.scheduler import ALLOWED_SCHEDULE_TOOLS

    registry = build_registry(force=True)
    for name in ALLOWED_SCHEDULE_TOOLS:
        tool = registry.get(name)
        assert tool is not None
        assert tool.risk == Risk.SAFE and not tool.confirm_required, name
