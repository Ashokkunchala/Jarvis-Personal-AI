#!/usr/bin/env python3
"""JARVIS floating robot - a tiny, dependency-free terminal animation.

This replaces the old Textual command-centre UI with one self-contained
standard-library module. It draws a small robot that hovers up and down,
blinks, pulses its antenna and flickers its thruster, with a live clock and
a rotating status line.

It needs no API key, no network and no third-party package:

    python -m jarvis.terminal.robot
    jarvis robot            # after `pip install -e .`
    jarvis tui              # backwards-compatible alias

A compact laptop gauge (CPU / RAM / battery / free disk) is drawn under the
robot via the optional ``psutil`` package. Press ``v`` to dial a live Gemini
voice call in a background thread: the robot keeps animating, the call runs
without a wake word, and transcripts appear in the speech line. The audio stack
is imported only when a call starts, so the animation still works on machines
where it is not installed.

Keys while running
-----------------
    q / Esc / Ctrl+C   quit
    space              pause / resume the float
    v                  start / end a live voice call
    a                  toggle ASCII art
    h                  toggle the footer hints
    + / - (or = / _)   faster / slower

Environment
-----------
    JARVIS_ROBOT_ASCII=1     force plain ASCII art
    JARVIS_ROBOT_NO_COLOR=1  disable colour
    NO_COLOR                 standard no-colour opt-out
"""

from __future__ import annotations

import argparse
import contextlib
import math
import os
import re
import shutil
import sys
import time
from datetime import datetime

__all__ = ["render_frame", "run", "main", "LaptopStats", "format_laptop"]

# --- ANSI helpers -----------------------------------------------------------
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR = "\x1b[2J\x1b[H"
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# --- Robot art --------------------------------------------------------------
# ``@`` is the eye token and ``%`` the antenna bulb token. Every line shares
# the same left origin, so padding the block to one width keeps it aligned.
_UNICODE_ART = r"""
         %
         │
     ╭───────╮
  ╭──┤ @   @ ├──╮
  │  │   ‿   │  │
  ╰──╰──┬─┬──╯──╯
        │ │
      ╭─┴─┴─╮
      │     │
      ╰──┬──╯
         ╰╯
"""

_ASCII_ART = r"""
         *
         |
     +-------+
  +--| O   O |--+
  |  |   _   |  |
  +--+--+-+--+--+
        | |
      +-+-+-+
      |     |
      +--+--+
         \/
"""

_EYE_OPEN_UNICODE = "\u25c9"  # ◉
_EYE_BLINK_UNICODE = "\u2500"  # ─
_MOUTH_UNICODE = "\u203f"  # ‿

_EYE_OPEN_ASCII = "O"
_EYE_BLINK_ASCII = "-"
_MOUTH_ASCII = "_"

_ANTENNA_ON_UNICODE = "\u2726"  # ✦
_ANTENNA_OFF_UNICODE = "\u00b7"  # ·
_ANTENNA_ON_ASCII = "*"
_ANTENNA_OFF_ASCII = "."

_TITLE = "J A R V I S"

_CAPTIONS = (
    "All systems nominal",
    "Hovering steadily",
    "Sensors online",
    "Awaiting your command",
    "Running diagnostics",
    "At your service",
)

# Flame frames are stored content-only; ``_center`` positions them under the
# nozzle so leading spaces are never counted twice.
_FLAME_UNICODE = (
    ("\u2726", "\u2726\u2726"),
    ("\u2726\u2726", "\u2726"),
    ("\u2726", "\u2726\u2726\u2726"),
)
_FLAME_ASCII = (
    ("*", "**"),
    ("**", "*"),
    ("*", "***"),
)


# --- Small helpers ----------------------------------------------------------
def _visible_len(text: str) -> int:
    """Length of *text* ignoring ANSI escape sequences."""
    return len(_ANSI_RE.sub("", text))


def _center(text: str, width: int) -> str:
    """Centre a plain string inside *width* columns."""
    if len(text) >= width:
        return text[:width]
    pad = width - len(text)
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def _center_ansi(text: str, width: int) -> str:
    """Centre a string that may contain ANSI colour codes."""
    visible = _visible_len(text)
    if visible >= width:
        return text
    pad = width - visible
    left = pad // 2
    return " " * left + text


def _truncate(text: str, width: int) -> str:
    """Trim a plain label to *width* columns with an ASCII ellipsis."""
    if width <= 3:
        return text[: max(0, width)]
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def _supports_unicode() -> bool:
    """Best-effort check that the console can render box-drawing glyphs."""
    override = os.getenv("JARVIS_ROBOT_ASCII", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return False
    if override in {"0", "false", "no", "off"}:
        return True
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in encoding


def _wants_color() -> bool:
    """Colour only for a real terminal, honouring the standard opt-outs."""
    if os.getenv("NO_COLOR") is not None:
        return False
    if os.getenv("JARVIS_ROBOT_NO_COLOR", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _enable_windows_ansi() -> None:
    """Turn on virtual-terminal processing for legacy Windows consoles."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(
                handle, mode.value | 0x0004
            )  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        # A console that refuses the flag simply keeps its default handling.
        pass


def _fg(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


class _Palette:
    """ANSI colours for one frame; every attribute is empty when colour is off."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.body = _fg(54, 214, 255) if enabled else ""
        self.eye = BOLD + _fg(228, 243, 255) if enabled else ""
        self.antenna = BOLD + _fg(56, 232, 160) if enabled else ""
        self.mouth = _fg(54, 214, 255) if enabled else ""
        self.flame = _fg(255, 159, 67) if enabled else ""
        self.text = _fg(200, 225, 245) if enabled else ""
        self.title = BOLD + _fg(56, 232, 160) if enabled else ""
        self.dim = _fg(91, 122, 153) if enabled else ""
        self.ok = _fg(56, 232, 160) if enabled else ""
        self.call = BOLD + _fg(255, 210, 90) if enabled else ""
        self.error = _fg(255, 110, 120) if enabled else ""


def _paint(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if code else text


def _paint_robot(line: str, specials: dict[str, str], default: str) -> str:
    """Colour a robot line, grouping runs so the output stays compact."""
    if not default:
        return line
    out: list[str] = []
    run: list[str] = []
    current = default
    for char in line:
        code = specials.get(char, default)
        if code != current:
            if run:
                out.append(f"{current}{''.join(run)}{RESET}")
                run = []
            current = code
        run.append(char)
    if run:
        out.append(f"{current}{''.join(run)}{RESET}")
    return "".join(out)


# --- Robot geometry ---------------------------------------------------------
def _is_blinking(tick: int, paused: bool) -> bool:
    """A short blink roughly every three seconds at the default speed."""
    if paused:
        return False
    return (tick % 64) in range(56, 60)


def _float_offset(tick: int, paused: bool) -> int:
    """Whole-row vertical bob in the range -2..2."""
    if paused:
        return 0
    return int(round(math.sin(tick * 0.30) * 1.5))


def _sway_offset(tick: int, paused: bool, width: int) -> int:
    """Gentle horizontal drift, capped so it never leaves the frame."""
    if paused:
        return 0
    amplitude = max(1, min(8, width // 12))
    return int(round(math.sin(tick * 0.16) * amplitude))


def _flame_lines(tick: int, ascii_mode: bool) -> tuple[str, str]:
    frames = _FLAME_ASCII if ascii_mode else _FLAME_UNICODE
    return frames[(tick // 2) % len(frames)]


def _eye_and_antenna(tick: int, ascii_mode: bool, paused: bool) -> tuple[str, str]:
    """Return the (eye, antenna) glyphs for one frame."""
    if ascii_mode:
        eye = _EYE_BLINK_ASCII if _is_blinking(tick, paused) else _EYE_OPEN_ASCII
        antenna = _ANTENNA_ON_ASCII if (paused or (tick // 3) % 2 == 0) else _ANTENNA_OFF_ASCII
    else:
        eye = _EYE_BLINK_UNICODE if _is_blinking(tick, paused) else _EYE_OPEN_UNICODE
        antenna = _ANTENNA_ON_UNICODE if (paused or (tick // 3) % 2 == 0) else _ANTENNA_OFF_UNICODE
    return eye, antenna


def _body_lines(tick: int, ascii_mode: bool, paused: bool, *, tokens: bool = False) -> list[str]:
    """Build the padded head/body block, optionally keeping ``@``/``%`` tokens."""
    template = _ASCII_ART if ascii_mode else _UNICODE_ART
    lines = template.strip("\n").splitlines()
    if not tokens:
        eye, antenna = _eye_and_antenna(tick, ascii_mode, paused)
        lines = [line.replace("@", eye).replace("%", antenna) for line in lines]
    width = max(len(line) for line in lines)
    return [line.ljust(width) for line in lines]


def robot_art(tick: int, ascii_mode: bool, paused: bool = False) -> list[str]:
    """Build the padded robot block (body plus thruster) for one frame.

    Exposed (without a leading underscore) because the tests use it directly.
    """
    body = _body_lines(tick, ascii_mode, paused)
    width = max(len(line) for line in body)
    flames = [_center(line, width) for line in _flame_lines(tick, ascii_mode)]
    return body + flames


def _specials(ascii_mode: bool) -> dict[str, str]:
    """Map the still-unreplaced art tokens to palette roles."""
    mouth = _MOUTH_ASCII if ascii_mode else _MOUTH_UNICODE
    return {"@": "eye", "%": "antenna", mouth: "mouth"}


# --- Laptop gauge -----------------------------------------------------------
def format_laptop(values: dict[str, float | int | bool | None]) -> str:
    """Format a CPU/RAM/battery/disk snapshot into one compact ASCII line."""
    parts: list[str] = []
    cpu = values.get("cpu_percent")
    if isinstance(cpu, (int, float)):
        parts.append(f"CPU {float(cpu):.0f}%")
    memory = values.get("memory_percent")
    if isinstance(memory, (int, float)):
        parts.append(f"RAM {float(memory):.0f}%")
    battery = values.get("battery_percent")
    if isinstance(battery, (int, float)):
        label = f"BAT {float(battery):.0f}%"
        if values.get("battery_plugged"):
            label += " AC"
        parts.append(label)
    disk = values.get("disk_free_gb")
    if isinstance(disk, (int, float)):
        parts.append(f"DISK {float(disk):.0f}G free")
    return "  ".join(parts)


class LaptopStats:
    """Cached laptop gauges for the animation loop.

    ``psutil`` is optional and imported on demand. Samples are refreshed at most
    once per interval, so a frame never waits on the operating system.
    """

    def __init__(self, interval: float = 2.0) -> None:
        self.interval = max(0.5, float(interval))
        self._next = 0.0
        self._text: str | None = None
        try:
            import psutil
        except Exception:  # noqa: BLE001 - the gauge is optional
            self._psutil = None
        else:
            self._psutil = psutil
            with contextlib.suppress(Exception):
                # One short blocking read gives the first frame a real CPU
                # figure; every later refresh is non-blocking and cached.
                self._text = self._sample(blocking=True)
                self._next = time.monotonic() + self.interval

    @property
    def available(self) -> bool:
        return self._psutil is not None

    def text(self) -> str | None:
        """Return the cached gauge line, refreshing it when it is stale."""
        if self._psutil is None:
            return None
        now = time.monotonic()
        if self._text is None or now >= self._next:
            self._next = now + self.interval
            try:
                self._text = self._sample()
            except Exception:  # noqa: BLE001 - never break the animation
                self._text = None
        return self._text

    def _sample(self, *, blocking: bool = False) -> str | None:
        psutil = self._psutil
        values: dict[str, float | int | bool | None] = {
            "cpu_percent": psutil.cpu_percent(interval=0.1 if blocking else None),
            "memory_percent": psutil.virtual_memory().percent,
        }
        try:
            battery = psutil.sensors_battery()
        except Exception:  # noqa: BLE001 - desktops and some VMs have none
            battery = None
        if battery is not None:
            values["battery_percent"] = battery.percent
            values["battery_plugged"] = bool(battery.power_plugged)
        try:
            values["disk_free_gb"] = psutil.disk_usage(os.path.abspath(os.sep)).free / 1e9
        except OSError:
            pass
        return format_laptop(values) or None


# --- Frame rendering --------------------------------------------------------
def render_frame(
    tick: int,
    width: int,
    height: int,
    *,
    ascii_mode: bool = False,
    color: bool = False,
    paused: bool = False,
    show_help: bool = True,
    fps: float = 20.0,
    now: datetime | None = None,
    laptop: str | None = None,
    voice_state: str = "off",
    voice_detail: str = "",
    voice_user: str = "",
    voice_reply: str = "",
    voice_tool: str = "",
) -> str:
    """Render one complete frame as a newline-joined string.

    Pure function of its arguments, apart from the optional clock, so it can be
    tested and screenshotted without starting the animation loop. ``laptop`` and
    the ``voice_*`` fields are pre-formatted strings; the renderer never touches
    the OS or the audio stack itself.
    """
    width = max(20, int(width))
    height = max(8, int(height))
    now = now or datetime.now()
    palette = _Palette(color)

    body = _body_lines(tick, ascii_mode, paused, tokens=True)
    block_width = max(_visible_len(line) for line in body)
    flames = [_center(line, block_width) for line in _flame_lines(tick, ascii_mode)]
    block = body + flames
    block_height = len(block)

    rows = [""] * height
    has_laptop = bool(laptop)
    reserve = 4 if has_laptop else 3
    roomy = height >= block_height + reserve + 3

    # Vertical placement: centre the block, then add the float offset.
    title_row = 1 if roomy else 0
    bottom_reserve = reserve if roomy else 1
    area_top = title_row + 2 if roomy else 0
    area_bottom = height - bottom_reserve
    top = area_top + max(
        0, (area_bottom - area_top - block_height) // 2 + _float_offset(tick, paused)
    )
    top = max(0, min(top, height - block_height - bottom_reserve))
    left = max(0, (width - block_width) // 2 + _sway_offset(tick, paused, width))

    special_names = _specials(ascii_mode)
    special_codes = {char: getattr(palette, role) for char, role in special_names.items()}
    eye, antenna = _eye_and_antenna(tick, ascii_mode, paused)

    for index, line in enumerate(block):
        row = top + index
        if 0 <= row < height:
            if index < len(body):
                painted = _paint_robot(line.rstrip(), special_codes, palette.body)
                painted = painted.replace("@", eye).replace("%", antenna)
            else:
                painted = _paint(line.rstrip(), palette.flame)
            rows[row] = " " * left + painted

    if roomy:
        rows[title_row] = _center_ansi(_paint(_TITLE, palette.title), width)

    if voice_state not in {"connecting", "live", "error"}:
        voice_state = "off"

    dot = "o" if ascii_mode else "\u25cf"
    speed = f"{max(1.0, min(60.0, float(fps))):g} fps"
    clock = now.strftime("%H:%M:%S")
    separator = " | " if ascii_mode else "  \u00b7  "

    if voice_state == "connecting":
        state, state_color = "DIALING", palette.call
    elif voice_state == "live":
        state, state_color = "CALL", palette.ok
    elif voice_state == "error":
        state, state_color = "VOICE ERR", palette.error
    else:
        state, state_color = ("PAUSED", palette.dim) if paused else ("ONLINE", palette.ok)
    status = _paint(f"{dot} {state}", state_color)
    status += _paint(f"{separator}{clock}{separator}{speed}", palette.dim)

    if voice_state == "connecting":
        message, message_color = "Dialing voice call...", palette.call
    elif voice_state == "live":
        if voice_reply:
            message = f"JARVIS: {voice_reply}"
        elif voice_user:
            message = f"You: {voice_user}"
        elif voice_tool:
            message = f"Running tool: {voice_tool}"
        else:
            message = "Call live - speak any time"
        message_color = palette.text
    elif voice_state == "error":
        message = f"Voice: {voice_detail or 'unavailable'}"
        message_color = palette.error
    elif paused:
        message, message_color = "Paused", palette.text
    else:
        message = _CAPTIONS[(tick // 50) % len(_CAPTIONS)]
        message_color = palette.text

    if roomy:
        if has_laptop:
            label = _truncate(laptop or "", width - 2)
            rows[height - 4] = _center_ansi(_paint(label, palette.dim), width)
        rows[height - 3] = _center_ansi(
            _paint(_truncate(message, width - 2), message_color), width
        )
        rows[height - 2] = _center_ansi(status, width)
        hints = (
            "q quit  \u00b7  space pause  \u00b7  v call  \u00b7  a ascii  \u00b7  +/- speed"
            if not ascii_mode
            else "q quit  |  space pause  |  v call  |  a ascii  |  +/- speed"
        )
        rows[height - 1] = _center_ansi(
            _paint(_truncate(hints if show_help else "", width - 2), palette.dim), width
        )
    else:
        rows[height - 1] = _center_ansi(status, width)

    return "\n".join(rows)


# --- Keyboard input ---------------------------------------------------------
class _KeyReader:
    """Non-blocking single-key reader that restores the terminal on exit."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._fd: int | None = None
        self._old: list[object] | None = None
        self._msvcrt = None

    def __enter__(self) -> _KeyReader:
        if not self.enabled:
            return self
        if os.name == "nt":
            import msvcrt

            self._msvcrt = msvcrt
        else:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def poll(self) -> str | None:
        if not self.enabled:
            return None
        if os.name == "nt":
            if not self._msvcrt.kbhit():
                return None
            char = self._msvcrt.getwch()
            if char in {"\x00", "\xe0"}:  # arrow/function-key prefix
                if self._msvcrt.kbhit():
                    self._msvcrt.getwch()
                return ""
            return char
        import select

        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        return sys.stdin.read(1)

    def __exit__(self, *exc_info: object) -> None:
        if self._fd is not None and self._old is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
            self._fd = None
            self._old = None


# --- Animation loop ---------------------------------------------------------
def run(
    *,
    frames: int | None = None,
    fps: float = 20.0,
    ascii_mode: bool | None = None,
    color: bool | None = None,
    dump: bool = False,
    laptop: bool = True,
    start_call: bool = False,
) -> int:
    """Run the floating robot.

    ``frames`` stops after that many frames (handy for tests and screenshots).
    ``dump`` prints frames one after another instead of redrawing in place.
    ``laptop`` draws the CPU/RAM/battery/disk gauge; ``start_call`` dials the
    voice call immediately instead of waiting for the ``v`` key.
    """
    if ascii_mode is None:
        ascii_mode = not _supports_unicode()
    interactive = bool(getattr(sys.stdin, "isatty", lambda: False)()) and bool(
        getattr(sys.stdout, "isatty", lambda: False)()
    )
    if color is None:
        color = interactive and _wants_color()

    if frames is None and not interactive:
        frames, dump, color = 1, True, False
    if frames is not None:
        frames = max(1, int(frames))

    if color or interactive:
        _enable_windows_ansi()

    # A piped stdout on Windows defaults to a legacy code page. If Unicode art
    # was explicitly requested, switch the stream to UTF-8 rather than crash.
    if not ascii_mode:
        encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
        if encoding:
            try:
                _ANTENNA_ON_UNICODE.encode(encoding)
            except (UnicodeEncodeError, LookupError):
                reconfigure = getattr(sys.stdout, "reconfigure", None)
                if reconfigure is not None:
                    try:
                        reconfigure(encoding="utf-8", errors="replace")
                    except (ValueError, OSError):
                        pass

    speed = max(1.0, min(60.0, float(fps)))
    tick = 0
    paused = False
    show_help = True
    voice_toggle_at = 0.0
    clear = CLEAR if not dump else ""

    gauge = LaptopStats() if laptop else None
    voice = None
    if interactive or start_call:
        try:
            from jarvis.terminal.voice import VoiceCall

            voice = VoiceCall()
        except Exception:  # noqa: BLE001 - voice is optional
            voice = None
    if voice is not None and start_call:
        voice.start()

    out = sys.stdout
    try:
        with _KeyReader(interactive) as keys:
            if interactive and not dump:
                out.write(HIDE_CURSOR)
                out.flush()
            next_frame = time.monotonic()
            while True:
                width, height = shutil.get_terminal_size(fallback=(80, 24))
                view = voice.view() if voice is not None else None
                frame = render_frame(
                    tick,
                    width,
                    height,
                    ascii_mode=ascii_mode,
                    color=color,
                    paused=paused,
                    show_help=show_help,
                    fps=speed,
                    laptop=gauge.text() if gauge is not None else None,
                    voice_state=view.state if view is not None else "off",
                    voice_detail=view.detail if view is not None else "",
                    voice_user=view.user if view is not None else "",
                    voice_reply=view.reply if view is not None else "",
                    voice_tool=view.tool if view is not None else "",
                )
                out.write(clear + frame + "\n")
                out.flush()
                tick += 1
                if frames is not None and tick >= frames:
                    break

                key = keys.poll()
                if key is not None:
                    if key in {"q", "Q", "\x03", "\x1b"}:
                        break
                    if key == " ":
                        paused = not paused
                    elif key in {"v", "V"} and voice is not None:
                        now = time.monotonic()
                        if now - voice_toggle_at >= 0.6:  # ignore key repeat
                            voice_toggle_at = now
                            if voice.is_active():
                                voice.stop()
                            else:
                                voice.start()
                    elif key in {"a", "A"}:
                        ascii_mode = not ascii_mode
                    elif key in {"h", "H"}:
                        show_help = not show_help
                    elif key in {"+", "="}:
                        speed = min(60.0, speed + 5.0)
                    elif key in {"-", "_"}:
                        speed = max(1.0, speed - 5.0)

                next_frame += 1.0 / speed
                delay = next_frame - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_frame = time.monotonic()
    except KeyboardInterrupt:
        pass
    finally:
        if voice is not None:
            voice.stop()
        if interactive and not dump:
            out.write(SHOW_CURSOR + RESET + "\n")
        else:
            out.write(RESET + "\n")
        out.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-robot",
        description="JARVIS floating robot: a tiny animated terminal robot.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=None,
        metavar="N",
        help="Render N frames then exit (default: animate forever).",
    )
    parser.add_argument(
        "--fps", type=float, default=20.0, metavar="FPS", help="Frames per second (default: 20)."
    )
    parser.add_argument("--ascii", action="store_true", help="Force plain ASCII art.")
    parser.add_argument("--unicode", action="store_true", help="Force Unicode box art.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colour.")
    parser.add_argument(
        "--dump",
        action="store_true",
        help="Print frames sequentially instead of redrawing in place.",
    )
    parser.add_argument(
        "--no-laptop",
        action="store_true",
        help="Hide the CPU/RAM/battery/disk gauge.",
    )
    parser.add_argument(
        "--call",
        action="store_true",
        help="Dial the live voice call as soon as the robot starts.",
    )
    args = parser.parse_args(argv)

    ascii_mode: bool | None = None
    if args.ascii:
        ascii_mode = True
    elif args.unicode:
        ascii_mode = False

    return run(
        frames=args.frames,
        fps=args.fps,
        ascii_mode=ascii_mode,
        color=False if args.no_color else None,
        dump=args.dump,
        laptop=not args.no_laptop,
        start_call=args.call,
    )


if __name__ == "__main__":
    raise SystemExit(main())
