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


def test_direct_desktop_action_tools_are_registered(registry: ToolRegistry) -> None:
    open_website = registry.get("open_website")
    open_and_type = registry.get("open_app_and_type")
    assert open_website is not None
    assert open_and_type is not None
    assert "browser" in open_website.description.lower()
    assert "never presses Enter" in open_and_type.description


def test_open_app_and_type_checks_focus_and_reports_failures(monkeypatch) -> None:
    from jarvis.control import input_ctl
    from jarvis.tools import builtin_tools

    class FakeLaptop:
        def __init__(self, active):
            self.active = active
            self.typed = []
            self.launched = []

        def open_app(self, name):
            self.launched.append(name)
            return {"success": True, "pid": 42}

        def get_active_window(self):
            return self.active

        def type_text(self, text):
            self.typed.append(text)
            return {"success": True, "typed_chars": len(text)}

    monkeypatch.setattr(builtin_tools.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(input_ctl, "is_available", lambda: True)
    focused = FakeLaptop({"success": True, "pid": 42, "process_name": "notepad.exe"})
    monkeypatch.setattr(builtin_tools, "get_laptop", lambda: focused)
    result = builtin_tools._open_app_and_type("notepad", "draft")
    assert result["success"] is True
    assert focused.typed == ["draft"]
    assert result["submitted"] is False

    wrong_focus = FakeLaptop({"success": True, "pid": 7, "process_name": "chrome.exe"})
    monkeypatch.setattr(builtin_tools, "get_laptop", lambda: wrong_focus)
    result = builtin_tools._open_app_and_type("notepad", "draft")
    assert result["success"] is False
    assert result["stage"] == "focus"
    assert wrong_focus.typed == []

    unavailable = FakeLaptop({"success": True, "pid": 42, "process_name": "notepad.exe"})
    monkeypatch.setattr(builtin_tools, "get_laptop", lambda: unavailable)
    monkeypatch.setattr(input_ctl, "is_available", lambda: False)
    result = builtin_tools._open_app_and_type("notepad", "draft")
    assert result["success"] is False
    assert result["stage"] == "automation"
    assert unavailable.launched == []


def test_registry_lookup_helpers(registry: ToolRegistry) -> None:
    assert "battery_status" in registry.names("system")
    assert registry.get("battery_status") is not None
    assert registry.get("definitely_not_a_tool") is None


def test_risky_tools_require_confirmation(registry: ToolRegistry) -> None:
    risky = registry.get("shutdown_pc")
    if risky is None:
        pytest.skip("shutdown_pc not registered")
    assert risky.confirm_required or risky.risk >= Risk.HIGH


def test_file_mutation_tools_require_confirmation(registry: ToolRegistry) -> None:
    for name in ("write_file", "copy_file", "move_file", "delete_file", "organize_folder"):
        tool = registry.get(name)
        assert tool is not None
        assert tool.confirm_required, f"{name} must ask before changing files"
        assert tool.confirmation_preview is not None, f"{name} must show impact before confirmation"
        assert not tool.allow_always, f"{name} must not bypass point-of-action confirmation"
        assert not tool.allow_auto_approve, f"{name} must not bypass explicit confirmation"


def test_copy_preview_is_shown_before_confirmation_and_cancel_prevents_copy(
    registry: ToolRegistry, tmp_path
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.txt").write_text("one", encoding="utf-8")
    (source / "two.txt").write_text("two", encoding="utf-8")
    destination = tmp_path / "destination"
    seen: list[dict] = []

    async def reject(_tool, args) -> bool:
        seen.append(args)
        return False

    result = asyncio.run(
        registry.execute(
            "copy_file",
            {"source": str(source), "destination": str(destination)},
            confirm=reject,
        )
    )

    assert result.cancelled is True
    assert len(seen) == 1
    assert seen[0]["source"] == str(source)
    assert seen[0]["destination"] == str(destination)
    assert seen[0]["_preview"]["estimated_affected_items"] == 3
    assert seen[0]["_preview"]["estimated_bytes"] == 6
    assert not destination.exists()


def test_file_mutation_fails_closed_without_a_confirmation_handler(
    registry: ToolRegistry, tmp_path
) -> None:
    target = tmp_path / "must-remain.txt"
    target.write_text("keep", encoding="utf-8")

    result = asyncio.run(
        registry.execute("delete_file", {"path": str(target)}, confirm=None)
    )

    assert result.ok is False
    assert "no confirmation handler" in (result.error or "").lower()
    assert target.read_text(encoding="utf-8") == "keep"


def test_file_mutation_does_not_accept_global_auto_approve(
    registry: ToolRegistry, tmp_path
) -> None:
    target = tmp_path / "must-remain.txt"
    target.write_text("keep", encoding="utf-8")

    result = asyncio.run(
        registry.execute(
            "delete_file",
            {"path": str(target)},
            confirm=None,
            auto_approve=True,
        )
    )

    assert result.ok is False
    assert "no confirmation handler" in (result.error or "").lower()
    assert target.read_text(encoding="utf-8") == "keep"


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


def test_brain_provider_candidates_order(monkeypatch) -> None:
    from jarvis.core.brain import JarvisBrain

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-key")
    monkeypatch.setenv("JARVIS_AI_PROVIDER", "auto")
    brain = JarvisBrain(api_key="gem-key")
    assert brain.provider_candidates() == ["gemini", "openrouter", "groq"]
    assert brain.configured is True
    assert brain.active_model == brain.model

    monkeypatch.setenv("JARVIS_AI_PROVIDER", "groq")
    brain2 = JarvisBrain(api_key="")
    assert brain2.provider_candidates() == ["groq", "gemini", "openrouter"]
    assert brain2.active_model == "llama-3.3-70b-versatile"


def test_brain_configured_without_any_key_is_false(monkeypatch) -> None:
    from jarvis.core import brain as brain_module
    from jarvis.core.brain import JarvisBrain

    # Stop .env from re-injecting keys after we clear them.
    monkeypatch.setattr(brain_module, "load_env", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    brain = JarvisBrain(api_key="")
    assert brain.provider_candidates() == []
    assert brain.configured is False


def test_brain_openai_history_maps_roles(monkeypatch) -> None:
    from jarvis.core.brain import JarvisBrain

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    brain = JarvisBrain(
        api_key="gem-key",
        history=[
            {"role": "user", "parts": [{"text": "hello"}]},
            {"role": "model", "parts": [{"text": "hi there"}]},
        ],
    )
    messages = brain._openai_history("sys prompt", "next")
    assert messages[0] == {"role": "system", "content": "sys prompt"}
    assert messages[1] == {"role": "user", "content": "hello"}
    assert messages[2] == {"role": "assistant", "content": "hi there"}
    assert messages[3] == {"role": "user", "content": "next"}


def test_brain_ask_without_providers_yields_error(monkeypatch) -> None:
    import asyncio

    from jarvis.core import brain as brain_module
    from jarvis.core.brain import JarvisBrain

    monkeypatch.setattr(brain_module, "load_env", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    brain = JarvisBrain(api_key="")

    async def collect():
        return [event async for event in brain.ask("hi")]

    events = asyncio.run(collect())
    assert events[0]["type"] == "error"
    assert "No AI provider configured" in events[0]["error"]


def test_brain_ask_falls_back_to_next_provider_before_output(monkeypatch) -> None:
    import asyncio

    from jarvis.core.brain import JarvisBrain

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-key")
    monkeypatch.setenv("JARVIS_AI_PROVIDER", "gemini")
    brain = JarvisBrain(api_key="gem-key")

    async def broken_gemini(*args, **kwargs):
        raise RuntimeError("503 UNAVAILABLE")
        yield  # pragma: no cover - make it an async generator

    async def fake_openai(provider, *args, **kwargs):
        yield {"type": "status", "message": "thinking"}
        yield {"type": "text_delta", "text": "fallback text"}
        brain._persist_turn("hi", "fallback text")
        yield {"type": "done", "text": "fallback text", "turns": 1, "tools_used": [], "elapsed": 0.1}

    monkeypatch.setattr(brain, "_ask_gemini", broken_gemini)
    monkeypatch.setattr(brain, "_ask_openai", fake_openai)

    async def collect():
        return [event async for event in brain.ask("hi")]

    events = asyncio.run(collect())
    kinds = [e["type"] for e in events]
    assert "text_delta" in kinds
    assert any(e.get("message", "").startswith("gemini failed") for e in events if e["type"] == "status")
    assert events[-1]["type"] == "done"
    assert events[-1]["text"] == "fallback text"
    # History persisted once by the successful provider.
    assert len(brain.history) == 2


# --------------------------------------------------------------- fail-closed gates
def test_confirm_required_tool_is_denied_without_a_confirm_callback(registry: ToolRegistry) -> None:
    """With no approval channel, a confirm-required tool must not run."""
    result = asyncio.run(registry.execute("shutdown_pc", {"delay": 60}))
    assert result.ok is False
    assert result.cancelled is True


def test_chained_shell_commands_are_never_classified_safe() -> None:
    from jarvis.control import shell

    assert shell.classify("dir") == "safe"
    for cmd in ("echo hi && del file.txt", "dir & whoami", "echo x | more", "echo x > out.txt", "echo $(whoami)"):
        assert shell.classify(cmd) == "confirm", cmd
    assert shell.classify("rm -rf /") == "blocked"


def test_entrypoint_scripts_compile() -> None:
    import pathlib
    import py_compile

    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("jarvis_daemon.py", "run_enhanced.py", "jarvis_cli.py"):
        py_compile.compile(str(root / name), doraise=True)
