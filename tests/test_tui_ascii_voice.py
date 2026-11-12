"""Voice-first startup and ASCII glyph fallback for the terminal UI.

On Windows the default console code page renders box-drawing and block
glyphs as tofu squares, so the TUI must fall back to plain ASCII there.
Voice mode must also be the default startup path.
"""

import types

import pytest

from jarvis.terminal import jarvis_tui


class TestAsciiDetection:
    def test_env_override_forces_ascii(self, monkeypatch):
        monkeypatch.setenv("JARVIS_TUI_ASCII", "1")
        assert jarvis_tui._detect_ascii_mode() is True

    def test_env_override_forces_unicode(self, monkeypatch):
        monkeypatch.setenv("JARVIS_TUI_ASCII", "0")
        assert jarvis_tui._detect_ascii_mode() is False

    def test_non_utf8_console_detected(self, monkeypatch):
        monkeypatch.delenv("JARVIS_TUI_ASCII", raising=False)
        monkeypatch.setattr(jarvis_tui.sys, "stdout", types.SimpleNamespace(encoding="cp850"))
        assert jarvis_tui._detect_ascii_mode() is True

    def test_utf8_console_keeps_unicode(self, monkeypatch):
        monkeypatch.delenv("JARVIS_TUI_ASCII", raising=False)
        monkeypatch.setattr(jarvis_tui.sys, "stdout", types.SimpleNamespace(encoding="utf-8"))
        assert jarvis_tui._detect_ascii_mode() is False


class TestGlyphFallback:
    def test_ascii_map_covers_unicode_keys(self):
        assert set(jarvis_tui._GLYPHS_ASCII) == set(jarvis_tui._GLYPHS_UNICODE)

    def test_ascii_map_is_pure_ascii(self):
        for value in jarvis_tui._GLYPHS_ASCII.values():
            assert all(ord(ch) < 128 for ch in value)

    def test_glyph_switches_with_mode(self, monkeypatch):
        monkeypatch.setattr(jarvis_tui, "ascii_mode", True)
        assert all(ord(ch) < 128 for ch in jarvis_tui.glyph("dot"))
        monkeypatch.setattr(jarvis_tui, "ascii_mode", False)
        assert jarvis_tui.glyph("dot") == "\u25cf"


class TestAsciiRendering:
    @pytest.mark.parametrize("state", ["READY", "LISTENING", "THINKING", "EXECUTING", "ERROR"])
    def test_core_lines_pure_ascii(self, monkeypatch, state):
        monkeypatch.setattr(jarvis_tui, "ascii_mode", True)
        for frame in (0, 3, 7):
            for line in jarvis_tui.core_lines(frame, state):
                assert all(ord(ch) < 128 for ch in line.plain)

    @pytest.mark.parametrize("value", [None, 0.0, 42.0, 100.0])
    def test_bar_pure_ascii(self, monkeypatch, value):
        monkeypatch.setattr(jarvis_tui, "ascii_mode", True)
        assert all(ord(ch) < 128 for ch in jarvis_tui._bar(value).plain)


class TestVoiceFirst:
    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("JARVIS_TUI_VOICE_FIRST", raising=False)
        assert jarvis_tui._detect_voice_first() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off"])
    def test_env_opts_out(self, monkeypatch, value):
        monkeypatch.setenv("JARVIS_TUI_VOICE_FIRST", value)
        assert jarvis_tui._detect_voice_first() is False
