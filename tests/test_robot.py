"""Tests for the dependency-free floating robot terminal animation."""

from __future__ import annotations

import re
from datetime import datetime

from jarvis.terminal import robot

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _plain(frame: str) -> str:
    return _ANSI.sub("", frame)


def test_render_frame_is_deterministic() -> None:
    fixed = datetime(2026, 11, 12, 20, 30, 0)
    first = robot.render_frame(7, 80, 24, ascii_mode=True, now=fixed)
    second = robot.render_frame(7, 80, 24, ascii_mode=True, now=fixed)
    assert first == second
    assert len(first.splitlines()) == 24


def test_frame_contains_title_clock_and_hints() -> None:
    frame = _plain(
        robot.render_frame(0, 80, 24, ascii_mode=True, now=datetime(2026, 11, 12, 20, 30, 0))
    )
    assert "J A R V I S" in frame
    assert "20:30:00" in frame
    assert "ONLINE" in frame
    assert "space pause" in frame


def test_ascii_mode_is_pure_ascii() -> None:
    for tick in range(0, 70, 7):
        frame = _plain(robot.render_frame(tick, 100, 30, ascii_mode=True))
        assert all(ord(char) < 128 for char in frame), f"non-ASCII at tick {tick}"


def test_unicode_mode_uses_box_art_and_eye() -> None:
    frame = _plain(robot.render_frame(0, 100, 30, ascii_mode=False))
    assert "\u25c9" in frame  # ◉ open eye
    assert "\u256d" in frame  # ╭ box-drawing corner


def test_color_mode_highlights_only_the_two_eyes() -> None:
    frame = robot.render_frame(0, 80, 24, ascii_mode=False, color=True)
    eye_code = robot.BOLD + robot._fg(228, 243, 255)
    assert frame.count(eye_code) == 2


def test_blinking_swaps_the_eye_glyph() -> None:
    assert robot._is_blinking(0, paused=False) is False
    assert robot._is_blinking(57, paused=False) is True
    open_frame = _plain(robot.render_frame(0, 80, 24, ascii_mode=False))
    blink_frame = _plain(robot.render_frame(57, 80, 24, ascii_mode=False))
    assert "\u25c9" in open_frame
    assert "\u25c9" not in blink_frame.split("All")[0]
    assert "\u2500" in blink_frame  # ─ blink bar


def test_float_and_sway_stay_small_and_freeze_when_paused() -> None:
    offsets = [robot._float_offset(tick, paused=False) for tick in range(0, 64)]
    assert min(offsets) >= -2 and max(offsets) <= 2
    assert any(value != 0 for value in offsets)
    assert all(robot._float_offset(tick, paused=True) == 0 for tick in offsets)

    sways = [robot._sway_offset(tick, paused=False, width=80) for tick in range(0, 64)]
    assert max(abs(value) for value in sways) <= 8
    assert all(robot._sway_offset(tick, paused=True, width=80) == 0 for tick in offsets)


def test_animation_changes_between_ticks() -> None:
    fixed = datetime(2026, 11, 12, 20, 30, 0)
    frames = {
        robot.render_frame(tick, 80, 24, ascii_mode=True, now=fixed) for tick in range(0, 16, 2)
    }
    assert len(frames) > 2


def test_frames_fit_the_requested_width() -> None:
    for width in (80, 120):
        for tick in (0, 11, 33):
            frame = _plain(robot.render_frame(tick, width, 30, ascii_mode=False))
            for line in frame.splitlines():
                assert len(line) <= width, f"line wider than {width}: {line!r}"


def test_paused_frame_reports_paused() -> None:
    frame = _plain(robot.render_frame(10, 80, 24, ascii_mode=True, paused=True))
    assert "PAUSED" in frame


def test_laptop_gauge_is_rendered_under_the_robot() -> None:
    gauge = robot.format_laptop(
        {
            "cpu_percent": 12.4,
            "memory_percent": 48.6,
            "battery_percent": 87.2,
            "battery_plugged": True,
            "disk_free_gb": 123.4,
        }
    )
    assert gauge == "CPU 12%  RAM 49%  BAT 87% AC  DISK 123G free"
    frame = _plain(robot.render_frame(0, 100, 30, ascii_mode=True, laptop=gauge))
    assert "CPU 12%" in frame
    assert "DISK 123G free" in frame


def test_voice_state_is_shown_in_the_frame() -> None:
    live = _plain(
        robot.render_frame(
            0,
            100,
            30,
            ascii_mode=True,
            voice_state="live",
            voice_user="open chrome",
            voice_reply="Opening Chrome now.",
        )
    )
    assert "CALL" in live
    assert "JARVIS: Opening Chrome now." in live

    error = _plain(
        robot.render_frame(
            0,
            100,
            30,
            ascii_mode=True,
            voice_state="error",
            voice_detail="GEMINI_API_KEY is not set in .env",
        )
    )
    assert "VOICE ERR" in error
    assert "GEMINI_API_KEY" in error


def test_long_labels_are_truncated_to_the_terminal_width() -> None:
    frame = _plain(
        robot.render_frame(
            0,
            40,
            24,
            ascii_mode=True,
            laptop="CPU 100%  RAM 100%  BAT 100% AC  DISK 9999G free",
            voice_state="error",
            voice_detail="a very long failure reason that would otherwise overflow",
        )
    )
    assert all(len(line) <= 40 for line in frame.splitlines())
    assert "..." in frame


def test_run_dump_prints_frames_and_exits_cleanly(capsys) -> None:
    code = robot.run(frames=2, ascii_mode=True, color=False, dump=True)
    assert code == 0
    output = capsys.readouterr().out
    assert output.count("J A R V I S") >= 2


def test_main_smoke(capsys) -> None:
    code = robot.main(["--frames", "1", "--ascii", "--no-color", "--dump"])
    assert code == 0
    assert "J A R V I S" in capsys.readouterr().out


def test_source_has_no_emoji_glyphs() -> None:
    import pathlib

    text = pathlib.Path(robot.__file__).read_text(encoding="utf-8")
    assert not [char for char in text if ord(char) > 0x1F000]
