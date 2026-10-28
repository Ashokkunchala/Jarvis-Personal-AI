"""JARVIS terminal UI — realtime streaming chat with live tool execution.

Talks straight to the local multi-provider tool loop (no server required), renders
replies as they stream, shows every tool call as it happens, and asks for
confirmation before anything risky runs.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Markdown, Static

from jarvis.core.brain import JarvisBrain
from jarvis.tools.registry import Tool

MAX_CONVERSATION_WIDGETS = 120
STREAM_THROTTLE = 0.05  # seconds between markdown re-renders while streaming


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
    """

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
            yield Static("⚠  CONFIRMATION REQUIRED", id="confirm-title")
            yield Static(f"tool: {self.tool.name}", id="confirm-tool")
            yield Static(f"risk: {self.tool.risk.name}   ·   {self.tool.description}", id="confirm-risk")
            yield Static(pretty, id="confirm-args")
            with Horizontal(classes="confirm-row"):
                yield Button("APPROVE  (y)", id="confirm-approve", variant="success")
                yield Button("REJECT  (n)", id="confirm-reject", variant="error")
            if self.tool.risk.name != "HIGH":
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
        super().__init__(f"… {label}", classes=f"tool-entry risk-{risk.lower()}")
        self.tool_name = tool

    def mark_ok(self, summary: str, elapsed: float) -> None:
        self.update(Text.from_markup(f"[green]✔[/green] {self.tool_name} [dim]{elapsed:.1f}s[/dim]\n[dim]{_brief(summary, 60)}[/dim]"))
        self.add_class("done")

    def mark_fail(self, error: str) -> None:
        self.update(Text.from_markup(f"[red]✘[/red] {self.tool_name}\n[dim red]{_brief(error, 60)}[/dim red]"))
        self.add_class("failed")

    def mark_cancelled(self) -> None:
        self.update(Text.from_markup(f"[yellow]⊘[/yellow] {self.tool_name} [dim]cancelled[/dim]"))
        self.add_class("cancelled")


class StatusBar(Static):
    """Live header strip: model, machine health, phone status."""

    def render(self) -> Any:
        data = getattr(self, "data", None) or {}
        laptop = data.get("laptop") or {}
        volume = data.get("volume") or {}
        android = data.get("android") or {}

        parts = [Text.assemble(("JARVIS", "bold cyan"), (" ▪ ", "dim"))]
        state = data.get("state", "STARTING")
        colour = {"READY": "green", "THINKING": "yellow", "ERROR": "red"}.get(state, "cyan")
        parts.append(Text.assemble(("● ", colour), (state, f"bold {colour}"), ("  ", "")))

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
            icon = "🔇" if volume.get("muted") else "🔊"
            parts.append(Text.assemble((f"{icon}{volume.get('volume')}%", "dim"), ("  ", "")))

        if android.get("connected"):
            count = len(android.get("devices", []))
            bat = (android.get("battery") or {})
            bat_txt = f"{bat.get('percent')}%" if bat.get("success") else "n/a"
            parts.append(Text.assemble(("📱 ", ""), (f"{count} device {bat_txt}", "green")))
        else:
            parts.append(Text.assemble(("📱 ", ""), ("no phone", "dim red")))

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
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
class JarvisTUI(App):
    """Realtime JARVIS terminal UI."""

    TITLE = "JARVIS · Personal AI"
    SUB_TITLE = "laptop + android control"

    CSS = """
    Screen { background: #070b10; }
    Header { background: #0b3954; color: #ffffff; }
    #status-bar { height: 3; dock: top; background: #0d1520; padding: 0 1; }
    #main { height: 1fr; }
    #conversation {
        width: 1fr; padding: 0 1; scrollbar-gutter: stable;
        background: #070b10;
    }
    #sidebar {
        width: 44; min-width: 34; background: #0a1119;
        border-left: tall #14425c; padding: 0 1;
    }
    #side-title { color: #7ed6df; text-style: bold; height: 1; margin-top: 1; }
    #tool-log { height: 1fr; scrollbar-gutter: stable; }
    #sys-panel { height: auto; max-height: 12; border-top: tall #14425c; padding-top: 1; }
    .user-msg {
        background: #0f2a1c; color: #d1f7c4; padding: 1 1; margin: 1 0;
        width: 100%; border-left: tall #2ecc71;
    }
    .jarvis-msg { margin: 1 0; width: 100%; }
    .sys-msg { color: #7f8fa6; padding: 0 1; margin: 1 0; width: 100%; }
    .tool-entry {
        width: 100%; height: auto; padding: 0 1; margin: 0 0;
        background: #0d1520; color: #c8d6e5;
    }
    .risk-high { border-left: tall #e74c3c; }
    .risk-medium { border-left: tall #f39c12; }
    .risk-low { border-left: tall #3498db; }
    .risk-safe { border-left: tall #27ae60; }
    #input-bar {
        height: 5; dock: bottom; background: #0d1520;
        padding: 1 1; border-top: tall #14425c;
    }
    Input { background: #111a24; border: tall #1f6f8b; width: 1fr; }
    #send-btn { width: 14; background: #1f6f8b; color: #fff; }
    #stop-btn { width: 10; background: #6c1f1f; color: #fff; }\n    #mic-btn { width: 10; background: #145a32; color: #fff; }
    #hint { height: 1; color: #4a6274; padding: 0 1; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+c", "copy_last", "Copy last", show=False),
        Binding("f1", "help", "Help"),
        Binding("ctrl+space", "focus_input", "Focus", show=False),
        Binding("ctrl+t", "toggle_sidebar", "Sidebar", show=False),
    ]

    def __init__(self, brain: JarvisBrain | None = None) -> None:
        super().__init__()
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

    # ------------------------------------------------------------- lifecycle
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StatusBar(id="status-bar")
        with Horizontal(id="main"):
            yield VerticalScroll(id="conversation")
            with Vertical(id="sidebar"):
                yield Static("TOOL ACTIVITY", id="side-title")
                yield VerticalScroll(id="tool-log")
                yield Static("", id="sys-panel")
        with Horizontal(id="input-bar"):
            yield Input(placeholder="Ask JARVIS…   /help for commands", id="cmd", suggester=None)
            yield Button("MIC", id="mic-btn", variant="success")
            yield Button("STOP", id="stop-btn", variant="error")
            yield Button("SEND", id="send-btn", variant="primary")
        yield Static("Enter sends · MIC records one utterance · F1 help · Ctrl+L clear · Ctrl+Q quit", id="hint")
        yield Footer()

    async def on_mount(self) -> None:
        if self.brain is None:
            self.brain = JarvisBrain()
        self.query_one("#stop-btn", Button).disabled = True
        self.query_one("#mic-btn", Button).disabled = False
        self.query_one("#cmd", Input).focus()
        self.set_interval(2.0, self.refresh_status)
        self.refresh_status()

        self._sys("JARVIS online — direct AI tool loop (Gemini/OpenRouter/Groq), no server required.")
        if not self.brain.configured:
            self._sys("[red]No AI provider key.[/red] Set GEMINI_API_KEY, OPENROUTER_API_KEY, or "
                      "GROQ_API_KEY in .env (see .env.example), then restart.")
        else:
            providers = ", ".join(self.brain.provider_candidates())
            self._sys(f"providers [magenta]{providers}[/magenta] · model [magenta]{self.brain.active_model}[/magenta] · "
                      f"[cyan]{len(self.brain.registry)} tools[/cyan] · type /tools to inspect")
        self._sys("Ask anything, or try: “set volume to 20”, “open chrome and screenshot”, “battery status”.")

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
        lines: list[str] = ["[dim]SYSTEM[/dim]"]
        if laptop.get("success"):
            lines.append(f"CPU {laptop.get('cpu_percent', 0):.0f}% · RAM {laptop.get('memory_percent', 0):.0f}%")
            lines.append(f"disk free {laptop.get('disk_free_gb')} GB")
            bat = laptop.get("battery_percent")
            if bat is not None:
                plug = "charging" if laptop.get("battery_plugged") else "on battery"
                lines.append(f"battery {bat}% ({plug})")
        else:
            lines.append(f"[red]{_brief(laptop.get('error', 'unavailable'), 40)}[/red]")
        if android.get("connected"):
            info = android.get("battery") or {}
            lines.append("[green]phone connected[/green]" +
                         (f" · {info.get('percent')}%" if info.get("success") else ""))
        else:
            lines.append("[dim]phone: not connected[/dim]")
        lines.append(f"[dim]history {len(self.brain.history)} messages[/dim]")
        panel = self.query_one("#sys-panel", Static)
        panel.update("\n".join(lines))

    # ---------------------------------------------------------------- input
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            await self._submit()
        elif event.button.id == "mic-btn":
            self._start_mic_capture()
        elif event.button.id == "stop-btn":
            self.stop_requested = True
            self._sys("[yellow]stopping after current step…[/yellow]")

    def _start_mic_capture(self) -> None:
        """Capture one user-requested utterance without blocking the Textual UI."""
        if self.busy or (self.mic_worker is not None and self.mic_worker.is_running):
            self._sys("[yellow]JARVIS is busy or the microphone is already active.[/yellow]")
            return
        self.query_one("#mic-btn", Button).disabled = True
        self._set_status("LISTENING")
        self._sys("[cyan]MIC active — speak after the prompt. One utterance only; click MIC again for another.[/cyan]")
        self.mic_worker = self._capture_and_transcribe()

    @work(thread=True, exclusive=True, group="mic")
    def _capture_and_transcribe(self) -> None:
        """SpeechRecognition's Google endpoint transcribes the explicitly captured clip."""
        try:
            import speech_recognition as sr
        except ImportError:
            self.call_from_thread(
                self._mic_finished,
                None,
                "Microphone support is not installed. Run: pip install 'SpeechRecognition[audio]'",
            )
            return
        try:
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.call_from_thread(self._sys, "[cyan]Listening now…[/cyan]")
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

    def _mic_finished(self, transcript: str | None, error: str | None) -> None:
        self.query_one("#mic-btn", Button).disabled = False
        self._set_status("READY")
        if error:
            self._sys(f"[red]MIC:[/red] {error}")
            return
        if transcript:
            self._sys(f"[dim]heard: {_brief(transcript, 180)}[/dim]")
            widget = self.query_one("#cmd", Input)
            widget.value = transcript
            self._user(f"🎙 {transcript}")
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
        elif cmd == "/allow":
            if arg:
                self.auto_allow.add(arg)
                self._sys(f"auto-allowed [cyan]{arg}[/cyan] for this session")
            else:
                self._sys("auto-allow: " + (", ".join(sorted(self.auto_allow)) or "none"))
        else:
            self._sys(f"unknown command {cmd} — try /help")

    def _help(self) -> None:
        self._sys(
            "[bold]Commands[/bold]  /help /clear /status /tools /model <name> /history /run <cmd> "
            "/allow <tool> /quit\n"
            "[bold]Shortcuts[/bold]  Enter send · MIC one-shot speech input · Ctrl+L clear · Ctrl+T sidebar · F1 help · Ctrl+Q quit\n"
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
                        self._sys(f"[dim]used {len(event['tools_used'])} tool(s) · "
                                  f"{event.get('elapsed', 0)}s[/dim]")
                elif event["type"] == "error":
                    error = event["error"]
                    self._abort_stream()
                    self._sys(f"[red]error:[/red] {error}")
                if self.stop_requested and event["type"] == "tool_start":
                    self._sys("[yellow]stop requested — no further tools will run this turn[/yellow]")
        except Exception as exc:  # pragma: no cover - defensive
            self._abort_stream()
            self._sys(f"[red]crash:[/red] {_brief(str(exc), 160)}")
        finally:
            self.busy = False
            self.turn_started = 0.0
            self.query_one("#send-btn", Button).disabled = False
            self.query_one("#stop-btn", Button).disabled = True
            self._set_status("READY" if not error else "ERROR")
            self.query_one("#cmd", Input).focus()

    def _make_confirm(self):
        async def confirm(tool: Tool, args: dict[str, Any]) -> bool:
            if tool.name in self.auto_allow:
                return True
            if self.stop_requested:
                return False
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            self.call_later(self._show_confirm, tool, args, future)
            return await future

        return confirm

    def _show_confirm(self, tool: Tool, args: dict[str, Any], future: asyncio.Future[bool]) -> None:
        def done(approved: bool | None) -> None:
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
            self._sys("[yellow]stopping…[/yellow]")

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
        self.query_one("#cmd", Input).focus()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

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
    JarvisTUI().run()


if __name__ == "__main__":
    main()
