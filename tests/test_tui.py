"""Headless checks for the realtime Textual UI using a stubbed brain."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from textual.widgets import Input

from jarvis.terminal.jarvis_tui import JarvisTUI
from jarvis.tools.registry import Risk, Tool


class StubRegistry:
    """Minimal stand-in for ToolRegistry (just what the TUI reads)."""

    def __init__(self) -> None:
        self._tools = {
            "battery_status": Tool(
                name="battery_status",
                description="Read battery level.",
                parameters={"type": "object", "properties": {}},
                handler=lambda: {"success": True},
                risk=Risk.SAFE,
                category="system",
            )
        }

    def __len__(self) -> int:
        return len(self._tools)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self, category: str) -> list[str]:
        return [t.name for t in self._tools.values() if t.category == category]

    def categories(self) -> dict[str, list[str]]:
        return {cat: self.names(cat) for cat in {t.category for t in self._tools.values()}}


class StubBrain:
    """Emits a canned tool-using turn without touching Gemini."""

    def __init__(self) -> None:
        self.configured = True
        self.model = "stub-model"
        self.registry = StubRegistry()
        self.history: list[dict[str, Any]] = []

    @property
    def active_model(self) -> str:
        return self.model

    def provider_candidates(self) -> list[str]:
        return ["gemini"]

    def snapshot(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "tools": len(self.registry),
            "laptop": {"success": False, "error": "stub"},
            "android": {"success": False, "connected": False, "devices": []},
        }

    def reset(self) -> None:
        self.history.clear()

    async def ask(self, message: str, confirm=None, auto_approve: bool = False,
                  extra_system: str | None = None) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "status", "message": "thinking"}
        yield {"type": "tool_start", "tool": "battery_status", "args": {},
               "risk": "SAFE", "category": "system"}
        yield {"type": "tool_end", "tool": "battery_status", "ok": True,
               "summary": "percent=100", "elapsed": 0.0}
        yield {"type": "text_delta", "text": "Battery "}
        yield {"type": "text_delta", "text": "is fine."}
        yield {"type": "done", "text": "Battery is fine.", "turns": 1,
               "tools_used": ["battery_status"], "elapsed": 0.1}


def _visible_text(app: JarvisTUI) -> str:
    """Flatten every mounted widget's rendered text for assertions."""
    chunks: list[str] = []
    for widget in app.history_widgets:
        try:
            chunks.append(str(widget.render()))
        except Exception:
            chunks.append(str(widget))
    return "\n".join(chunks)


async def test_tui_streams_a_tool_turn() -> None:
    app = JarvisTUI(brain=StubBrain())
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.brain.model == "stub-model"

        await pilot.click("#cmd")
        await pilot.pause()
        app.query_one("#cmd", Input).value = "battery status"
        await pilot.press("enter")
        await pilot.pause(0.6)

        assert app.last_reply == "Battery is fine."
        assert "battery status" in _visible_text(app)

        from jarvis.terminal.jarvis_tui import ToolEntry

        entries = list(app.query(ToolEntry))
        assert len(entries) >= 1
        assert entries[0].tool_name == "battery_status"


async def test_tui_rejects_unknown_slash_command() -> None:
    app = JarvisTUI(brain=StubBrain())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#cmd", Input).value = "/nope"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert "unknown command" in _visible_text(app)


async def test_tui_clear_resets_conversation() -> None:
    app = JarvisTUI(brain=StubBrain())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#cmd", Input).value = "/clear"
        await pilot.press("enter")
        await pilot.pause(0.3)
        # Only the post-clear system line remains.
        assert len(app.history_widgets) <= 2


def test_tui_module_imports_cleanly() -> None:
    import jarvis.terminal.jarvis_tui as module

    assert hasattr(module, "JarvisTUI")
    assert hasattr(module, "ConfirmModal")


# ---------------------------------------------------------------------------
# Cinematic command-centre layout
# ---------------------------------------------------------------------------
def test_core_lines_are_a_pure_function_of_frame_and_state() -> None:
    from jarvis.terminal.jarvis_tui import CORE_H, CORE_W, core_lines

    a = [t.plain for t in core_lines(3, "READY")]
    assert a == [t.plain for t in core_lines(3, "READY")]
    assert len(a) == CORE_H and all(len(row) == CORE_W for row in a)
    assert any("J A R V I S" in row for row in a)
    assert a != [t.plain for t in core_lines(9, "THINKING")]
    plain = core_lines(0, "ERROR", simple=True)
    assert len(plain) == 1 and "ERROR" in plain[0].plain


def test_bar_never_invents_a_value() -> None:
    from jarvis.terminal.jarvis_tui import _bar

    assert "--" in _bar(None).plain
    assert "50%" in _bar(50).plain
    assert "100%" in _bar(400).plain


async def test_panels_show_real_state_and_pending_approval() -> None:
    import asyncio

    from textual.widgets import Static

    app = JarvisTUI(brain=StubBrain(), simple=True)
    async with app.run_test(size=(150, 42)) as pilot:
        await pilot.pause(0.4)
        assert "Nothing waiting" in str(app.query_one("#needs", Static).render())
        tool = app.brain.registry.get("battery_status")
        fut = asyncio.get_running_loop().create_future()
        app._show_confirm(tool, {}, fut)
        await pilot.pause(0.3)
        assert app.pending_tool == "battery_status"
        await pilot.press("n")
        await pilot.pause(0.3)
        assert fut.result() is False  # rejection is the fail-closed outcome
        assert app.pending_tool is None


async def test_layout_degrades_on_small_terminals() -> None:
    app = JarvisTUI(brain=StubBrain(), simple=True)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause(0.3)
        assert app.has_class("compact") and app.has_class("short")
        assert app.query_one("#sidebar").display is False
        assert app.query_one("#cmd").display is True
