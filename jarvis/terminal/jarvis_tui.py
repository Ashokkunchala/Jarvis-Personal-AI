"""JARVIS terminal UI - realtime streaming chat with live tool execution.

Talks straight to the local multi-provider tool loop (no server required), renders
replies as they stream, shows every tool call as it happens, and asks for
confirmation before anything risky runs.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import sys
import time
from datetime import datetime
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Static

from jarvis.core.brain import JarvisBrain
from jarvis.tools.registry import Tool

MAX_CONVERSATION_WIDGETS = 120
STREAM_THROTTLE = 0.05  # seconds between markdown re-renders while streaming


# ---------------------------------------------------------------------------
# Glyph rendering: Unicode box art with a plain-ASCII fallback
# ---------------------------------------------------------------------------
def _detect_ascii_mode() -> bool:
    """Plain ASCII when the terminal cannot show Unicode box art.

    Default Windows consoles (legacy code pages such as cp850/cp437) render
    box-drawing and block glyphs as tofu squares. Set JARVIS_TUI_ASCII=1 to
    force plain output or JARVIS_TUI_ASCII=0 to force Unicode. For the full
    cinematic look use Windows Terminal with a Nerd Font - optional polish,
    never a requirement.
    """
    override = os.getenv("JARVIS_TUI_ASCII", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    if encoding and "utf" not in encoding:
        return True
    return False


# Mutable on purpose: tests flip it, and every render path reads it per call.
ascii_mode = _detect_ascii_mode()

_GLYPHS_UNICODE = {
    "sep": "\u25aa", "dot": "\u25cf", "middot": "\u00b7", "smalldot": "\u2022",
    "ring": "\u2218", "tiny": "\u2219", "ok": "\u2714", "fail": "\u2718",
    "cancel": "\u2298", "ellipsis": "\u2026", "dash": "\u2014",
    "bar_full": "\u2588", "bar_empty": "\u2591", "bar_none": "\u254c",
    "corner": "\u25e2\u25e4",
}
_GLYPHS_ASCII = {
    "sep": "|", "dot": "O", "middot": "-", "smalldot": ".",
    "ring": "o", "tiny": ".", "ok": "[+]", "fail": "[x]",
    "cancel": "[-]", "ellipsis": "...", "dash": "-",
    "bar_full": "#", "bar_empty": "-", "bar_none": "-",
    "corner": "><",
}


def glyph(name: str) -> str:
    """The terminal-safe version of a decorative character."""
    return (_GLYPHS_ASCII if ascii_mode else _GLYPHS_UNICODE)[name]


_ASCII_CSS_OVERRIDES = (
    "\n    .hud, #core { border: ascii #1c6fa8; }"
    "\n    #conversation, #tool-log { border: ascii #1c4f86; }"
    "\n    #topbar { border-bottom: ascii #1c6fa8; }"
    "\n    #input-bar { border-top: ascii #1c6fa8; }"
    "\n    Input, Input:focus { border: ascii #1c6fa8; }"
    "\n    .user-msg { border-left: ascii #38e8a0; }"
    "\n    .risk-high { border-left: ascii #ff5c6c; }"
    "\n    .risk-medium { border-left: ascii #ffc35a; }"
    "\n    .risk-low { border-left: ascii #36d6ff; }"
    "\n    .risk-safe { border-left: ascii #38e8a0; }"
    "\n    #confirm-box { border: ascii #ff9f43; }\n"
)


def _detect_voice_first() -> bool:
    """Voice-first start: JARVIS begins listening as soon as it is ready.

    Default on. Set JARVIS_TUI_VOICE_FIRST=0 (or press STOP) for typed-first.
    The microphone runs as one-utterance captures chained after each reply -
    never hidden always-on recording.
    """
    return os.getenv("JARVIS_TUI_VOICE_FIRST", "1").strip().lower() not in {"0", "false", "no", "off"}


# ---------------------------------------------------------------------------
# Confirmation dialog
# ---------------------------------------------------------------------------
class ConfirmModal(ModalScreen[bool]):
    """Ask the user before a risky tool runs."""

    CSS = """
    ConfirmModal { align: center middle; }
    #confirm-box {
        width: 76; height: auto; max-height: 90%;
        background: #101820; border: thick #ff9f43;
        padding: 1 2;
    }
    #confirm-title { color: #ff9f43; text-style: bold; width: 100%; }
    #confirm-tool { color: #7ed6df; text-style: bold; }
    #confirm-args { color: #c8d6e5; margin: 1 0; }
    #confirm-risk { color: #ff6b6b; }
    .confirm-row { height: 3; margin-top: 1; }
    #confirm-approve { background: #2ecc71; color: #000; width: 1fr; }
    #confirm-reject { background: #e74c3c; color: #fff; width: 1fr; }
    #confirm-always { background: #34495e; color: #fff; width: 1fr; }
    """ + (_ASCII_CSS_OVERRIDES if ascii_mode else "")

    BINDINGS = [
        Binding("escape", "reject", "Reject", show=False),
        Binding("y", "approve", "Approve", show=False),
        Binding("n", "reject", "Reject", show=False),
    ]

    def __init__(self, tool: Tool, args: dict[str, Any], on_always: Any | None = None) -> None:
        super().__init__()
        self.tool = tool
        self.args = args
        self.on_always = on_always

    def compose(self) -> ComposeResult:
        pretty = json.dumps(self.args, indent=2, ensure_ascii=False) if self.args else "(no arguments)"
        with Vertical(id="confirm-box"):
            yield Static("!  CONFIRMATION REQUIRED", id="confirm-title")
            yield Static(f"tool: {self.tool.name}", id="confirm-tool")
            yield Static(f"risk: {self.tool.risk.name}   {glyph('middot')}   {self.tool.description}", id="confirm-risk")
            yield Static(pretty, id="confirm-args")
            with Horizontal(classes="confirm-row"):
                yield Button("APPROVE  (y)", id="confirm-approve", variant="success")
                yield Button("REJECT  (n)", id="confirm-reject", variant="error")
            if self.tool.risk.name != "HIGH" and self.tool.allow_always:
                yield Button("ALWAYS ALLOW THIS SESSION", id="confirm-always", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "confirm-approve":
            self.dismiss(True)
        elif button_id == "confirm-always":
            if self.on_always:
                self.on_always(self.tool.name)
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_reject(self) -> None:
        self.dismiss(False)


# ---------------------------------------------------------------------------
# Sidebar widgets
# ---------------------------------------------------------------------------
class ToolEntry(Static):
    """One tool invocation shown in the sidebar."""

    def __init__(self, tool: str, risk: str, args: dict[str, Any]) -> None:
        label = tool
        if args:
            brief = ", ".join(f"{k}={_brief(v)}" for k, v in list(args.items())[:2])
            label = f"{tool}({brief})"
        super().__init__(f"{glyph('ellipsis')} {label}", classes=f"tool-entry risk-{risk.lower()}")
        self.tool_name = tool

    def mark_ok(self, summary: str, elapsed: float) -> None:
        self.update(Text.from_markup(f"[green]{glyph('ok')}[/green] {self.tool_name} [dim]{elapsed:.1f}s[/dim]\n[dim]{_brief(summary, 60)}[/dim]"))
        self.add_class("done")

    def mark_fail(self, error: str) -> None:
        self.update(Text.from_markup(f"[red]{glyph('fail')}[/red] {self.tool_name}\n[dim red]{_brief(error, 60)}[/dim red]"))
        self.add_class("failed")

    def mark_cancelled(self) -> None:
        self.update(Text.from_markup(f"[yellow]{glyph('cancel')}[/yellow] {self.tool_name} [dim]cancelled[/dim]"))
        self.add_class("cancelled")


class StatusBar(Static):
    """Live header strip: model, machine health, phone status."""

    def render(self) -> Any:
        data = getattr(self, "data", None) or {}
        laptop = data.get("laptop") or {}
        volume = data.get("volume") or {}
        android = data.get("android") or {}

        parts = [Text.assemble(("JARVIS", "bold cyan"), (f" {glyph('sep')} ", "dim"))]
        state = data.get("state", "STARTING")
        colour = {"READY": "green", "THINKING": "yellow", "ERROR": "red"}.get(state, "cyan")
        parts.append(Text.assemble((glyph("dot") + " ", colour), (state, f"bold {colour}"), ("  ", "")))

        parts.append(Text.assemble((f"{data.get('model', '-')}", "magenta"), ("  ", "")))
        parts.append(Text.assemble((f"tools:{data.get('tools', 0)}", "dim"), ("  ", "")))

        if laptop.get("success"):
            cpu = laptop.get("cpu_percent", 0)
            ram = laptop.get("memory_percent", 0)
            bat = laptop.get("battery_percent")
            parts.append(Text.assemble(
                ("CPU ", "dim"), (f"{cpu:.0f}%", _heat(cpu)),
                ("  RAM ", "dim"), (f"{ram:.0f}%", _heat(ram)),
                ("  BAT ", "dim"), (f"{bat}%", "green" if laptop.get("battery_plugged") else "cyan"),
                ("  ", ""),
            ))
        if volume.get("success"):
            label = "MUTED" if volume.get("muted") else "VOL"
            parts.append(Text.assemble((f"{label} {volume.get('volume')}%", "dim"), ("  ", "")))

        if android.get("connected"):
            count = len(android.get("devices", []))
            bat = (android.get("battery") or {})
            bat_txt = f"{bat.get('percent')}%" if bat.get("success") else "n/a"
            parts.append(Text.assemble(("PHONE ", "dim"), (f"{count} device {bat_txt}", "green")))
        else:
            parts.append(Text.assemble(("", ""), ("no phone", "dim red")))

        parts.append(Text.assemble(("  ", ""), (datetime.now().strftime("%H:%M:%S"), "dim")))
        return self._join(parts)

    @staticmethod
    def _join(parts: list[Text]) -> Text:
        out = Text()
        for part in parts:
            out.append(part)
        return out


def _heat(value: float) -> str:
    if value >= 90:
        return "bold red"
    if value >= 75:
        return "yellow"
    return "green"


def _brief(value: Any, limit: int = 40) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + glyph("ellipsis")



# ---------------------------------------------------------------------------
# Cinematic widgets
# ---------------------------------------------------------------------------
CORE_W, CORE_H = 33, 13
STATE_STYLE = {
    "READY": "#38e8a0", "THINKING": "#ffc35a", "LISTENING": "#36d6ff", "TRANSCRIBING": "#36d6ff",
    "AWAITING": "#ff9f43", "ERROR": "#ff5c6c", "STARTING": "#7aa7ff",
}


def _bar(percent: float | None, width: int = 14, invert: bool = False) -> Text:
    """Unicode gauge. None means 'not measured' and is drawn as dashes, never as a value."""
    if percent is None:
        return Text(glyph("bar_none") * width + "  --", style="dim")
    pct = max(0.0, min(100.0, float(percent)))
    filled = int(round(pct / 100 * width))
    hot = (100 - pct) if invert else pct
    colour = "#ff5c6c" if hot >= 90 else "#ffc35a" if hot >= 75 else "#38e8a0"
    return Text.assemble((glyph("bar_full") * filled, colour), (glyph("bar_empty") * (width - filled), "#1c4f86"), (f" {pct:3.0f}%", colour))


def core_lines(frame: int, state: str, simple: bool = False) -> list[Text]:
    """Draw the AI core: a ring with a moving highlight around a JARVIS label.

    Pure function of (frame, state) so it can be tested and screenshotted.
    """
    colour = STATE_STYLE.get(state, "#36d6ff")
    if simple:
        return [Text(f"[ JARVIS {glyph('middot')} {state} ]", style=f"bold {colour}")]
    cx, cy = (CORE_W - 1) / 2, (CORE_H - 1) / 2
    rx, ry = 15.0, 5.6
    grid = [[" "] * CORE_W for _ in range(CORE_H)]
    style = [[""] * CORE_W for _ in range(CORE_H)]
    points = 64
    active = state in {"THINKING", "LISTENING", "TRANSCRIBING", "AWAITING"}
    head = (frame * (3 if active else 1)) % points
    for i in range(points):
        a = 2 * math.pi * i / points
        x = int(round(cx + rx * math.cos(a)))
        y = int(round(cy + ry * math.sin(a)))
        dist = (head - i) % points
        if dist < 10:
            ch, st = (glyph("dot") if dist == 0 else glyph("smalldot")), colour
        elif i % 2 == 0:
            ch, st = glyph("middot"), "#1c6fa8"
        else:
            continue
        if 0 <= x < CORE_W and 0 <= y < CORE_H:
            grid[y][x], style[y][x] = ch, st
    # inner ring
    rx2, ry2 = 9.0, 3.0
    for i in range(48):
        a = 2 * math.pi * i / 48 + (frame * 0.12 if active else 0)
        x = int(round(cx + rx2 * math.cos(a)))
        y = int(round(cy + ry2 * math.sin(a)))
        if 0 <= x < CORE_W and 0 <= y < CORE_H and grid[y][x] == " ":
            grid[y][x], style[y][x] = (glyph("tiny") if i % 3 else glyph("ring")), "#2f8fd6"
    label = "J A R V I S"
    ly = int(cy)
    lx = int(cx - len(label) / 2)
    for k, ch in enumerate(label):
        grid[ly][lx + k], style[ly][lx + k] = ch, "bold #e4f3ff"
    sub = state
    sx = int(cx - len(sub) / 2)
    for k, ch in enumerate(sub):
        grid[ly + 1][sx + k], style[ly + 1][sx + k] = ch, f"bold {colour}"
    lines: list[Text] = []
    for r in range(CORE_H):
        t = Text()
        for c in range(CORE_W):
            t.append(grid[r][c], style=style[r][c] or None)
        lines.append(t)
    return lines


class CoreWidget(Static):
    """Animated AI core. Animation only reflects the app's real state."""

    def __init__(self, simple: bool = False, **kw: Any) -> None:
        super().__init__("", **kw)
        self.state = "STARTING"
        self.frame = 0
        self.simple = simple

    def tick(self) -> None:
        self.frame += 1
        self.refresh()

    def render(self) -> Any:
        out = Text(justify="center")
        for i, line in enumerate(core_lines(self.frame, self.state, self.simple)):
            if i:
                out.append("\n")
            out.append(line)
        return out


def _tool_present(name: str) -> bool:
    return shutil.which(name) is not None


DEVOPS_PROMPTS = {
    "/tf": "Review this Terraform for security and reliability risks:\n",
    "/docker": "Review this Dockerfile:\n",
    "/cicd": "Review this CI/CD pipeline config:\n",
    "/iam": "Review this IAM policy for least privilege:\n",
    "/runbook": "Give me a troubleshooting runbook for ",
}

# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
class JarvisTUI(App):
    """Realtime JARVIS terminal UI."""

    TITLE = f"JARVIS {glyph('middot')} Personal AI"
    SUB_TITLE = "laptop + android control"

    CSS = """
    Screen { background: #02060f; color: #e4f3ff; }
    #head { height: 5; dock: top; }
    #topbar { height: 3; background: #04122a; border-bottom: heavy #1c6fa8; padding: 0 2; content-align: left middle; }
    #status-bar { height: 1; background: #03102a; padding: 0 2; }
    #foot { height: 8; dock: bottom; }
    #main { height: 1fr; }
    #left { width: 36; min-width: 34; }
    #center { width: 1fr; min-width: 40; }
    #sidebar { width: 40; min-width: 32; }
    .hud { border: round #1c6fa8; background: #04122ad9; padding: 0 1; margin: 0 0 0 0; border-title-color: #36d6ff; border-title-style: bold; height: auto; }
    #core { height: 15; width: 100%; content-align: center middle; border: round #1c6fa8; background: #03102a; border-title-color: #36d6ff; border-title-style: bold; }
    #conversation { height: 1fr; padding: 0 1; scrollbar-gutter: stable; background: #02060f; border: round #1c4f86; border-title-color: #36d6ff; border-title-style: bold; }
    #tool-log { height: 1fr; min-height: 6; scrollbar-gutter: stable; border: round #1c4f86; background: #03102a; border-title-color: #36d6ff; border-title-style: bold; }
    #sys-panel { height: auto; }
    #services { height: auto; }
    #needs { height: auto; min-height: 3; }
    #devops { height: auto; }
    .user-msg { background: #062a22; color: #c8ffe6; padding: 0 1; margin: 1 0; width: 100%; border-left: thick #38e8a0; }
    .jarvis-msg { margin: 1 0; width: 100%; }
    .sys-msg { color: #86a7c8; padding: 0 1; margin: 1 0; width: 100%; }
    .tool-entry { width: 100%; height: auto; padding: 0 1; background: #04122a; color: #c8d6e5; }
    .risk-high { border-left: thick #ff5c6c; }
    .risk-medium { border-left: thick #ffc35a; }
    .risk-low { border-left: thick #36d6ff; }
    .risk-safe { border-left: thick #38e8a0; }
    #input-bar { height: 6; background: #04122a; padding: 1 1; border-top: heavy #1c6fa8; }
    Input { background: #030d20; border: tall #1c6fa8; width: 1fr; }
    Input:focus { border: tall #36d6ff; }
    #send-btn { width: 14; background: #0b7bb8; color: #fff; }
    #stop-btn { width: 10; background: #7a0f1d; color: #fff; }
    #mic-btn { width: 10; background: #0d6b4f; color: #fff; }
    #hint { height: 1; color: #5b7a99; padding: 0 2; background: #02060f; }
    .compact #left, .compact #sidebar { display: none; }
    .short #core { display: none; }
    .simple #core { display: none; }
    .voice-first #cmd, .voice-first #send-btn { display: none; }
    #type-btn { width: 10; }
    """ + (_ASCII_CSS_OVERRIDES if ascii_mode else "")

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+c", "copy_last", "Copy last", show=False),
        Binding("f1", "help", "Help"),
        Binding("ctrl+space", "focus_input", "Focus", show=False),
        Binding("ctrl+t", "toggle_sidebar", "Sidebar", show=False),
        Binding("f2", "focus_input", "Input", show=False),
        Binding("f3", "toggle_sidebar", "Panels"),
        Binding("f4", "stop_turn", "Stop"),
    ]

    def __init__(self, brain: JarvisBrain | None = None, simple: bool | None = None) -> None:
        # Textual removes NO_COLOR from the environment when it starts, so read it first.
        wants_plain = "NO_COLOR" in os.environ or os.getenv("TERM", "") == "dumb" or \
            os.getenv("JARVIS_TUI_SIMPLE", "") == "1"
        super().__init__()
        # Plain mode: no animation and no colour (greyscale only).
        if simple is None:
            simple = wants_plain
        self.simple = simple
        if simple:
            from textual.filter import Monochrome

            if not any(isinstance(f, Monochrome) for f in self._filters):
                self._filters.append(Monochrome())
        self.pending_tool: str | None = None
        self.brain = brain
        self.history_widgets: list[Any] = []
        self.live_markdown: Markdown | None = None
        self.live_buffer: str = ""
        self.live_last_render = 0.0
        self.busy = False
        self.stop_requested = False
        self.auto_allow: set[str] = set()
        self.last_reply = ""
        self.turn_started = 0.0
        self.mic_worker = None
        self.voice_mode = _detect_voice_first()
        self._voice_loop = self.voice_mode

    # ------------------------------------------------------------- lifecycle
    def compose(self) -> ComposeResult:
        with Vertical(id="head"):
            yield Static("", id="topbar")
            yield StatusBar(id="status-bar")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield CoreWidget(simple=self.simple, id="core")
                yield Static("", id="sys-panel", classes="hud")
                yield Static("", id="services", classes="hud")
            yield VerticalScroll(id="conversation")
            with Vertical(id="sidebar"):
                yield Static("", id="needs", classes="hud")
                yield Static("", id="devops", classes="hud")
                yield VerticalScroll(id="tool-log")
        with Vertical(id="foot"):
            with Horizontal(id="input-bar"):
                yield Input(placeholder=f"Ask JARVIS{glyph('ellipsis')}   /help for commands", id="cmd", suggester=None)
                yield Button("MIC", id="mic-btn", variant="success")
                yield Button("STOP", id="stop-btn", variant="error")
                yield Button("SEND", id="send-btn", variant="primary")
                yield Button("TYPE", id="type-btn", variant="default")
            yield Static(f"Enter send {glyph('middot')} F1 help {glyph('middot')} F2 input {glyph('middot')} F3 panels {glyph('middot')} F4 stop {glyph('middot')} Ctrl+L clear {glyph('middot')} Ctrl+Q quit", id="hint")

    async def on_mount(self) -> None:
        if self.brain is None:
            self.brain = JarvisBrain()
        self.query_one("#stop-btn", Button).disabled = True
        self.query_one("#mic-btn", Button).disabled = False
        if self.voice_mode:
            self.set_class(True, "voice-first")
        else:
            self.query_one("#cmd", Input).focus()
        self.set_interval(2.0, self.refresh_status)
        self.set_interval(0.12 if not self.simple else 1.0, self._tick)
        self.query_one("#conversation").border_title = "CONVERSATION"
        self.query_one("#tool-log").border_title = "TOOL ACTIVITY"
        self.query_one("#core").border_title = "CORE"
        self.query_one("#sys-panel").border_title = "SYSTEM"
        self.query_one("#services").border_title = "SERVICES"
        self.query_one("#needs").border_title = "NEEDS YOU"
        self.query_one("#devops").border_title = "AWS DEVOPS"
        self._apply_layout(self.size.width, self.size.height)
        self._render_static_panels()
        self.refresh_status()

        self._sys(f"JARVIS online {glyph('dash')} direct AI tool loop (Gemini/OpenRouter/Groq), no server required.")
        if not self.brain.configured:
            self._sys("[red]No AI provider key.[/red] Set GEMINI_API_KEY, OPENROUTER_API_KEY, or "
                      "GROQ_API_KEY in .env (see .env.example), then restart.")
        else:
            providers = ", ".join(self.brain.provider_candidates())
            self._sys(f"providers [magenta]{providers}[/magenta] {glyph('middot')} model [magenta]{self.brain.active_model}[/magenta] {glyph('middot')} "
                      f"[cyan]{len(self.brain.registry)} tools[/cyan] {glyph('middot')} type /tools to inspect")
        self._sys("Ask anything, or try: 'set volume to 20', 'open chrome and screenshot', 'battery status'.")
        if self.voice_mode:
            self._sys(f"[cyan]Voice mode:[/cyan] JARVIS listens one utterance at a time, answers, then listens "
                      f"again. Press STOP to pause voice; TYPE or F2 reveals the input box. Speech uses the "
                      f"SpeechRecognition online service {glyph('dash')} no offline wake word yet.")
            self.call_later(self._start_mic_capture)

    # ---------------------------------------------------------- layout/panels
    def on_resize(self, event: Any) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def _apply_layout(self, width: int, height: int) -> None:
        self.set_class(width < 110, "compact")
        self.set_class(height < 32, "short")
        self.set_class(self.simple, "simple")
        self.query_one("#hint", Static).update(
            f"Enter send {glyph('middot')} F1 help {glyph('middot')} F3 panels {glyph('middot')} F4 stop {glyph('middot')} Ctrl+Q quit" if width < 90 else
            f"Enter send {glyph('middot')} F1 help {glyph('middot')} F2 input {glyph('middot')} F3 panels {glyph('middot')} F4 stop {glyph('middot')} Ctrl+L clear {glyph('middot')} Ctrl+Q quit")

    def _tick(self) -> None:
        try:
            core = self.query_one("#core", CoreWidget)
            top = self.query_one("#topbar", Static)
        except Exception:  # pragma: no cover - during teardown
            return
        if not self.simple:
            core.tick()
        top.update(self._topbar_text())

    def _topbar_text(self) -> Text:
        state = getattr(self.query_one("#core", CoreWidget), "state", "STARTING")
        colour = STATE_STYLE.get(state, "#36d6ff")
        return Text.assemble(
            (glyph("corner") + " ", "#36d6ff"), ("JARVIS", "bold #e4f3ff"), (f" {glyph('middot')} COMMAND CENTRE", "#36d6ff"),
            ("    " + glyph("dot") + " ", colour), (state, f"bold {colour}"),
            ("    " + datetime.now().strftime("%a %d %b  %H:%M:%S"), "#86a7c8"),
        )

    def _render_static_panels(self) -> None:
        """AWS DevOps panel: what is installed locally. No credential or network access."""
        rows = Text()
        for name in ("aws", "terraform", "kubectl", "docker"):
            ok = _tool_present(name)
            rows.append((glyph("ok") if ok else glyph("fail")) + " ", style="#38e8a0" if ok else "#5b7a99")
            rows.append(f"{name:<10}", style="#e4f3ff" if ok else "#5b7a99")
            rows.append("on PATH\n" if ok else "not found\n", style="dim")
        rows.append("AWS access: read-only tools,\nchanges always ask. Not\nchecked from this panel.\n", style="dim")
        rows.append("/tf /docker /cicd /iam /runbook", style="#36d6ff")
        self.query_one("#devops", Static).update(rows)
        self._render_needs()

    def _render_needs(self) -> None:
        text = Text()
        if self.pending_tool:
            text.append("! Approval waiting\n", style="bold #ff9f43")
            text.append(f"{self.pending_tool}\n", style="#e4f3ff")
            text.append(f"y approve {glyph('middot')} n reject", style="dim")
        else:
            text.append("Nothing waiting for you.", style="dim")
        self.query_one("#needs", Static).update(text)

    # --------------------------------------------------------------- status
    def refresh_status(self) -> None:
        if self.brain is None:
            return
        bar = self.query_one("#status-bar", StatusBar)
        data: dict[str, Any] = dict(getattr(bar, "data", {}) or {})
        data["model"] = self.brain.active_model
        data["providers"] = ", ".join(self.brain.provider_candidates())
        data["tools"] = len(self.brain.registry)
        data["state"] = "THINKING" if self.busy else ("READY" if self.brain.configured else "ERROR")
        core = self.query_one("#core", CoreWidget)
        if core.state == "STARTING":
            core.state = data["state"]
        if self.turn_started:
            data.setdefault("elapsed", round(time.time() - self.turn_started, 1))
        # Snapshot off the UI thread so slow I/O never stalls the interface.
        self._status_worker(data, bar)

    @work(exclusive=True, group="status")
    async def _status_worker(self, data: dict[str, Any], bar: StatusBar) -> None:
        try:
            snap = await asyncio.to_thread(self.brain.snapshot)
        except Exception as exc:  # pragma: no cover - defensive
            snap = {"laptop": {"success": False, "error": str(exc)}}
        merged = {**data, **{k: snap.get(k) for k in ("laptop", "volume", "android", "model", "tools")}}
        merged["state"] = data.get("state", "READY")
        bar.data = merged
        bar.refresh()
        self._render_sys_panel(merged)

    def _render_sys_panel(self, snap: dict[str, Any]) -> None:
        laptop = snap.get("laptop") or {}
        android = snap.get("android") or {}
        t = Text()
        if laptop.get("success"):
            t.append("CPU  ", style="dim")
            t.append(_bar(laptop.get("cpu_percent")))
            t.append("\n")
            t.append("RAM  ", style="dim")
            t.append(_bar(laptop.get("memory_percent")))
            t.append("\n")
            bat = laptop.get("battery_percent")
            t.append("BAT  ", style="dim")
            t.append(_bar(bat, invert=True))
            if bat is not None:
                t.append("  AC" if laptop.get("battery_plugged") else "  batt", style="dim")
            t.append("\n")
            t.append(f"disk free {laptop.get('disk_free_gb')} GB", style="dim")
        else:
            t.append(f"unavailable: {_brief(laptop.get('error', 'no data'), 40)}", style="#ff5c6c")
        self.query_one("#sys-panel", Static).update(t)

        v = Text()
        configured = bool(getattr(self.brain, "configured", False))
        providers = ", ".join(self.brain.provider_candidates()) if configured else ""
        v.append("AI provider  ", style="dim")
        v.append((providers or "none") if configured else "no key set", style="#38e8a0" if configured else "#ff5c6c")
        v.append("\nmodel        ", style="dim")
        v.append(_brief(str(self.brain.active_model), 20), style="#c792ff")
        v.append("\ntools        ", style="dim")
        v.append(str(len(self.brain.registry)), style="#36d6ff")
        v.append("\nphone        ", style="dim")
        v.append("connected" if android.get("connected") else "not connected",
                 style="#38e8a0" if android.get("connected") else "#5b7a99")
        v.append("\nvoice        ", style="dim")
        v.append("listening loop (online speech)" if self.voice_mode else "MIC button (online speech)", style="#86a7c8")
        v.append("\nhistory      ", style="dim")
        v.append(f"{len(self.brain.history)} msgs", style="#86a7c8")
        self.query_one("#services", Static).update(v)

    # ---------------------------------------------------------------- input
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            await self._submit()
        elif event.button.id == "mic-btn":
            self._start_mic_capture()
        elif event.button.id == "type-btn":
            self.action_focus_input()
        elif event.button.id == "stop-btn":
            if self.voice_mode:
                self.voice_mode = False
                self._voice_loop = False
                self._sys("[cyan]Voice mode paused. Press MIC to talk again, or /voice to resume the loop.[/cyan]")
            self.stop_requested = True
            self._sys(f"[yellow]stopping after current step{glyph('ellipsis')}[/yellow]")

    def _start_mic_capture(self, quiet: bool = False) -> None:
        """Capture one user-requested utterance without blocking the Textual UI."""
        if self.busy or (self.mic_worker is not None and self.mic_worker.is_running):
            if not quiet:
                self._sys("[yellow]JARVIS is busy or the microphone is already active.[/yellow]")
            return
        self.query_one("#mic-btn", Button).disabled = True
        self._set_status("LISTENING")
        self._sys(f"[cyan]MIC active {glyph('dash')} speak after the prompt. One utterance only; click MIC again for another.[/cyan]")
        self.mic_worker = self._capture_and_transcribe()

    @work(thread=True, exclusive=True, group="mic")
    def _capture_and_transcribe(self) -> None:
        """SpeechRecognition's Google endpoint transcribes the explicitly captured clip."""
        try:
            import speech_recognition as sr
        except ImportError:
            self.call_from_thread(
                self._mic_unavailable,
                "Microphone support is not installed. Run: pip install 'SpeechRecognition[audio]'",
            )
            return
        try:
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.call_from_thread(self._sys, f"[cyan]Listening now{glyph('ellipsis')}[/cyan]")
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)
            self.call_from_thread(self._set_status, "TRANSCRIBING")
            transcript = recognizer.recognize_google(audio, language="en-IN")
            self.call_from_thread(self._mic_finished, transcript, None)
        except sr.WaitTimeoutError:
            self.call_from_thread(self._mic_finished, None, "No speech detected within 8 seconds.")
        except sr.UnknownValueError:
            self.call_from_thread(self._mic_finished, None, "Speech was not clear enough to transcribe.")
        except sr.RequestError as exc:
            self.call_from_thread(self._mic_finished, None, f"Speech service unavailable: {_brief(str(exc), 120)}")
        except Exception as exc:
            self.call_from_thread(self._mic_finished, None, f"Microphone error: {_brief(str(exc), 120)}")

    def _mic_unavailable(self, error: str) -> None:
        """Mic stack missing: drop out of voice mode instead of looping errors."""
        self.voice_mode = False
        self._voice_loop = False
        self.query_one("#mic-btn", Button).disabled = False
        self._set_status("READY")
        self._sys(f"[red]MIC:[/red] {error}")
        self._sys("Voice mode off. Type below, or install microphone support and press MIC.")

    def _mic_finished(self, transcript: str | None, error: str | None) -> None:
        self.query_one("#mic-btn", Button).disabled = False
        self._set_status("READY")
        if error:
            # In the listening loop, silence or unclear audio just listens again.
            if self.voice_mode and ("No speech detected" in error or "not clear enough" in error):
                self.call_later(self._start_mic_capture, True)
                return
            self._sys(f"[red]MIC:[/red] {error}")
            if self.voice_mode:
                self.call_later(self._start_mic_capture, True)
            return
        if transcript:
            self._sys(f"[dim]heard: {_brief(transcript, 180)}[/dim]")
            widget = self.query_one("#cmd", Input)
            widget.value = transcript
            self._user(f"[voice] {transcript}")
            self._run_turn(transcript)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cmd":
            await self._submit()

    async def _submit(self) -> None:
        widget = self.query_one("#cmd", Input)
        message = widget.value.strip()
        if not message or self.busy:
            return
        widget.value = ""
        if message.startswith("/"):
            await self._handle_command(message)
            return
        self._user(message)
        self._run_turn(message)  # @work decorated; starts a background worker

    # ------------------------------------------------------------ commands
    async def _handle_command(self, message: str) -> None:
        parts = message.split()
        cmd = parts[0].lower()
        arg = " ".join(parts[1:])

        if cmd in {"/quit", "/exit", "/q"}:
            self.exit()
        elif cmd == "/clear" or cmd == "/reset":
            self._clear()
        elif cmd == "/help" or cmd == "/?":
            self._help()
        elif cmd == "/status":
            self.refresh_status()
            self._sys("status refreshed (see sidebar)")
        elif cmd == "/tools":
            self._show_tools(arg)
        elif cmd == "/model":
            if arg:
                self.brain.model = arg
                self._sys(f"model set to [magenta]{arg}[/magenta] for this session")
            else:
                self._sys(f"current model: [magenta]{self.brain.model}[/magenta]")
        elif cmd == "/history":
            self._sys(f"{len(self.brain.history)} history messages; /clear resets them")
        elif cmd == "/run":
            if not arg:
                self._sys("usage: /run <command>")
                return
            await self._run_turn(f"Run this shell command and report the output: {arg}")
        elif cmd == "/voice":
            if arg.lower() in {"off", "0", "stop"}:
                self.voice_mode = False
                self._voice_loop = False
                self._sys("voice loop off; press MIC for a single utterance or /voice to resume")
            else:
                self.voice_mode = True
                self._voice_loop = True
                self._sys("voice loop on; JARVIS listens again after every reply")
                self._start_mic_capture(quiet=True)
        elif cmd == "/allow":
            if arg:
                self.auto_allow.add(arg)
                self._sys(f"auto-allowed [cyan]{arg}[/cyan] for this session")
            else:
                self._sys("auto-allow: " + (", ".join(sorted(self.auto_allow)) or "none"))
        else:
            self._sys(f"unknown command {cmd} {glyph('dash')} try /help")

    def _help(self) -> None:
        self._sys(
            "[bold]Commands[/bold]  /help /clear /status /tools /model <name> /history /run <cmd> /voice [on|off] "
            "/allow <tool> /quit\n"
            f"[bold]Shortcuts[/bold]  Enter send {glyph('middot')} /voice on|off {glyph('middot')} F2 type {glyph('middot')} Ctrl+L clear {glyph('middot')} Ctrl+T sidebar {glyph('middot')} F1 help {glyph('middot')} Ctrl+Q quit\n"
            "[bold]Risky actions[/bold]  always ask first; /allow <tool> pre-approves one tool."
        )

    def _show_tools(self, category: str) -> None:
        registry = self.brain.registry
        if category:
            names = registry.names(category)
            self._sys(f"[cyan]{category}[/cyan]: {', '.join(names) or 'none'}")
            return
        for cat, names in sorted(registry.categories().items()):
            self._sys(f"[bold cyan]{cat}[/bold cyan] ({len(names)}): {', '.join(sorted(names))}")

    # ------------------------------------------------------------ streaming
    @work(exclusive=True, group="turn", thread=False)
    async def _run_turn(self, message: str) -> None:
        self.busy = True
        self.stop_requested = False
        self.turn_started = time.time()
        self.query_one("#send-btn", Button).disabled = True
        self.query_one("#stop-btn", Button).disabled = False
        self._set_status("THINKING")

        confirm = self._make_confirm()
        error: str | None = None
        try:
            async for event in self.brain.ask(message, confirm=confirm):
                if event["type"] == "status":
                    if event["message"] != "thinking":
                        self._sys(f"[dim]{event['message']}[/dim]")
                elif event["type"] == "text_delta":
                    self._stream_text(event["text"])
                elif event["type"] == "tool_start":
                    self._tool_start(event)
                elif event["type"] == "tool_end":
                    self._tool_end(event, ok=True)
                elif event["type"] == "tool_error":
                    self._tool_end(event, ok=False)
                elif event["type"] == "tool_cancelled":
                    self._tool_end(event, ok=None)
                elif event["type"] == "done":
                    self._finish_stream(event)
                    self.last_reply = event.get("text", "")
                    if event.get("tools_used"):
                        self._sys(f"[dim]used {len(event['tools_used'])} tool(s) {glyph('middot')} "
                                  f"{event.get('elapsed', 0)}s[/dim]")
                elif event["type"] == "error":
                    error = event["error"]
                    self._abort_stream()
                    self._sys(f"[red]error:[/red] {error}")
                if self.stop_requested and event["type"] == "tool_start":
                    self._sys(f"[yellow]stop requested {glyph('dash')} no further tools will run this turn[/yellow]")
        except Exception as exc:  # pragma: no cover - defensive
            self._abort_stream()
            self._sys(f"[red]crash:[/red] {_brief(str(exc), 160)}")
        finally:
            self.busy = False
            self.turn_started = 0.0
            self.query_one("#send-btn", Button).disabled = False
            self.query_one("#stop-btn", Button).disabled = True
            self._set_status("READY" if not error else "ERROR")
            if self.voice_mode:
                self.call_later(self._start_mic_capture, True)
            else:
                self.query_one("#cmd", Input).focus()

    def _make_confirm(self):
        async def confirm(tool: Tool, args: dict[str, Any]) -> bool:
            if tool.allow_always and tool.name in self.auto_allow:
                return True
            if self.stop_requested:
                return False
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            self.call_later(self._show_confirm, tool, args, future)
            return await future

        return confirm

    def _show_confirm(self, tool: Tool, args: dict[str, Any], future: asyncio.Future[bool]) -> None:
        self.pending_tool = tool.name
        self._render_needs()

        def done(approved: bool | None) -> None:
            self.pending_tool = None
            self._render_needs()
            if future.done():
                return
            future.set_result(bool(approved))
            self._set_status("THINKING" if self.busy else "READY")

        self._set_status("AWAITING")
        self.push_screen(ConfirmModal(tool, args, on_always=self.auto_allow.add), done)

    # ---------------------------------------------------------- chat widgets
    def _conversation(self) -> VerticalScroll:
        return self.query_one("#conversation", VerticalScroll)

    def _append(self, widget: Any) -> None:
        container = self._conversation()
        container.mount(widget)
        self.history_widgets.append(widget)
        if len(self.history_widgets) > MAX_CONVERSATION_WIDGETS:
            old = self.history_widgets.pop(0)
            old.remove()
        self.call_later(container.scroll_end, animate=False)

    def _user(self, text: str) -> None:
        self._append(Static(text, classes="user-msg"))

    def _sys(self, text: str) -> None:
        self._append(Static(text, classes="sys-msg"))

    def _stream_text(self, delta: str) -> None:
        if self.live_markdown is None:
            self.live_markdown = Markdown("", classes="jarvis-msg", id="live-reply")
            self._append(self.live_markdown)
            self.live_buffer = ""
        self.live_buffer += delta
        now = time.monotonic()
        if now - self.live_last_render >= STREAM_THROTTLE:
            self.live_last_render = now
            self.live_markdown.update(self.live_buffer)

    def _finish_stream(self, event: dict[str, Any]) -> None:
        text = event.get("text") or self.live_buffer
        if self.live_markdown is not None:
            self.live_markdown.update(text or "_(empty reply)_")
        elif text:
            self._append(Markdown(text, classes="jarvis-msg"))
        self.live_markdown = None
        self.live_buffer = ""
        if text:
            self._append(Static(_timestamp(), classes="sys-msg meta"))

    def _abort_stream(self) -> None:
        if self.live_markdown is not None:
            if self.live_buffer:
                self.live_markdown.update(self.live_buffer + "\n\n> _[stopped]_")
            else:
                self.live_markdown.remove()
        self.live_markdown = None
        self.live_buffer = ""

    # --------------------------------------------------------- tool widgets
    def _tool_start(self, event: dict[str, Any]) -> None:
        entry = ToolEntry(event["tool"], event.get("risk", "LOW"), event.get("args") or {})
        log = self.query_one("#tool-log", VerticalScroll)
        log.mount(entry)
        log.scroll_end(animate=False)
        if self.stop_requested:
            self._sys(f"[yellow]stopping{glyph('ellipsis')}[/yellow]")

    def _tool_end(self, event: dict[str, Any], ok: bool | None) -> None:
        log = self.query_one("#tool-log", VerticalScroll)
        entries = list(log.query(ToolEntry))
        target = next((e for e in reversed(entries) if e.tool_name == event["tool"]), None)
        if target is None:
            return
        if ok is None:
            target.mark_cancelled()
        elif ok:
            target.mark_ok(str(event.get("summary", "")), float(event.get("elapsed", 0.0)))
        else:
            target.mark_fail(str(event.get("error") or event.get("summary") or "failed"))
        log.scroll_end(animate=False)

    # --------------------------------------------------------------- misc
    def _set_status(self, state: str) -> None:
        self.query_one("#core", CoreWidget).state = state
        bar = self.query_one("#status-bar", StatusBar)
        data = dict(getattr(bar, "data", {}) or {})
        data["state"] = state
        bar.data = data
        bar.refresh()

    def _clear(self) -> None:
        for widget in self.history_widgets:
            widget.remove()
        self.history_widgets.clear()
        self.live_markdown = None
        self.live_buffer = ""
        log = self.query_one("#tool-log", VerticalScroll)
        for child in list(log.children):
            child.remove()
        if self.brain:
            self.brain.reset()
        self._sys("conversation and tool log cleared")

    def action_clear(self) -> None:
        self._clear()

    def action_help(self) -> None:
        self._help()

    def action_focus_input(self) -> None:
        self.set_class(False, "voice-first")
        self.query_one("#cmd", Input).focus()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def action_stop_turn(self) -> None:
        if self.busy:
            self.stop_requested = True
            self._sys(f"[yellow]stopping after current step{glyph('ellipsis')}[/yellow]")

    def action_copy_last(self) -> None:
        if self.last_reply:
            try:
                import pyperclip

                pyperclip.copy(self.last_reply)
                self._sys("last reply copied to clipboard")
            except Exception:
                self._sys("[red]clipboard unavailable[/red]")


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M")


def main() -> None:
    if "--no-voice" in sys.argv or "--type" in sys.argv:
        os.environ["JARVIS_TUI_VOICE_FIRST"] = "0"
    JarvisTUI().run()


if __name__ == "__main__":
    main()
