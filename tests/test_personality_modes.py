"""Tests for conversation personality modes and song performance."""

from __future__ import annotations

import pytest

from jarvis import personality_modes
from jarvis.personality_modes import MODES, ModeStore, overlay_for, prepare_song


class TestModes:
    def test_expected_modes_exist(self):
        assert {"assistant", "friend", "teacher", "storyteller", "doctor"} <= set(MODES)

    def test_every_mode_has_overlay_and_style(self):
        for mode in MODES.values():
            assert mode.overlay.strip()
            assert mode.label
            assert mode.description
            assert mode.voice_style

    def test_doctor_mode_is_bounded(self):
        overlay = MODES["doctor"].overlay.lower()
        assert "not a doctor" in overlay or "never a substitute" in overlay or "not medical advice" in overlay
        assert "never diagnose" in overlay
        assert "emergency" in overlay

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown personality mode"):
            personality_modes.get_mode("wizard")

    def test_overlay_falls_back_safely(self):
        assert overlay_for(None) == MODES["assistant"].overlay
        assert overlay_for("") == MODES["assistant"].overlay
        assert overlay_for("wizard") == MODES["assistant"].overlay

    def test_list_modes_shape(self):
        modes = personality_modes.list_modes()
        assert len(modes) == len(MODES)
        assert all({"name", "label", "description"} <= set(m) for m in modes)


class TestModeStore:
    def test_default_when_missing(self, tmp_path):
        store = ModeStore(tmp_path / "mode.json")
        assert store.get() == "assistant"

    def test_set_and_get_roundtrip(self, tmp_path):
        store = ModeStore(tmp_path / "mode.json")
        chosen = store.set("Storyteller")
        assert chosen.name == "storyteller"
        assert store.get() == "storyteller"

    def test_unknown_mode_not_persisted(self, tmp_path):
        store = ModeStore(tmp_path / "mode.json")
        store.set("friend")
        with pytest.raises(ValueError):
            store.set("wizard")
        assert store.get() == "friend"

    def test_corrupt_file_falls_back(self, tmp_path):
        path = tmp_path / "mode.json"
        path.write_text("not json")
        assert ModeStore(path).get() == "assistant"


class TestPrepareSong:
    LYRICS = "Boot sequence hums at dawn\nCoffee joins the silicon song\nLights awake on every screen\nJarvis tends his humble dream"

    def test_success_shape(self):
        result = prepare_song(self.LYRICS, mood="playful")
        assert result["success"] is True
        assert result["line_count"] == 4
        assert result["mood"] == "playful"
        assert result["lines"][0]["line"].startswith("Boot sequence")
        assert result["lines"][3]["pause_after"] == "long"
        assert "approximation" in result["performance_note"]
        assert "copyrighted" in result["originality_note"]

    def test_empty_lyrics_rejected(self):
        assert prepare_song("")["success"] is False
        assert prepare_song("   \n  ")["success"] is False

    def test_too_many_lines_rejected(self):
        lyrics = "\n".join(f"line {i}" for i in range(personality_modes.MAX_SONG_LINES + 1))
        assert prepare_song(lyrics)["success"] is False

    def test_long_line_rejected(self):
        assert prepare_song("x" * 300)["success"] is False


class TestRegistryIntegration:
    def test_personality_tools_registered(self):
        from jarvis.tools.builtin_tools import build_registry

        registry = build_registry()
        for name in ("list_personality_modes", "get_personality_mode", "set_personality_mode", "perform_song"):
            assert registry.get(name) is not None, name

    def test_set_mode_tool_roundtrip(self, tmp_path, monkeypatch):
        store = ModeStore(tmp_path / "mode.json")
        monkeypatch.setattr(personality_modes, "_default_store", store)
        from jarvis.tools.builtin_tools import build_registry

        registry = build_registry()
        result = registry.get("set_personality_mode").handler("friend")
        assert result["success"] is True
        assert result["mode"] == "friend"
        assert store.get() == "friend"
        bad = registry.get("set_personality_mode").handler("wizard")
        assert bad["success"] is False
