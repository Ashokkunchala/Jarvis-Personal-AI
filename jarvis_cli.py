#!/usr/bin/env python3
"""JARVIS command line interface.

Three tiers of entry:

* ``jarvis tui``   - realtime streaming terminal UI against the local tool loop
* ``jarvis ask``   - one-shot / interactive streamed replies (no server needed)
* ``jarvis laptop``/``jarvis android`` - direct device control with rich output
* ``jarvis serve`` - the HTTP/WebSocket backend for browser and remote clients
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))

app = typer.Typer(
    name="jarvis",
    help="JARVIS Personal AI — streaming assistant, laptop control, Android control.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
android_app = typer.Typer(help="Control a connected Android phone over ADB.", no_args_is_help=True)
laptop_app = typer.Typer(help="Control this Windows laptop.", no_args_is_help=True)
app.add_typer(android_app, name="android")
app.add_typer(laptop_app, name="laptop")

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ok(result: Any) -> bool:
    return bool(isinstance(result, dict) and result.get("success"))


def _fail(result: Any) -> None:
    if isinstance(result, dict):
        err_console.print(f"[red]failed:[/red] {_brief(result.get('error') or result)}")
    else:
        err_console.print(f"[red]failed:[/red] {_brief(result)}")


def _brief(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _emit(result: Any, success: str, extra: str = "") -> None:
    if _ok(result):
        tail = f" [dim]{_brief(extra, 90)}[/dim]" if extra else ""
        console.print(f"[green]✔[/green] {success}{tail}")
        return
    _fail(result)


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("items", "entries", "rows", "apps", "processes", "windows", "devices", "files"):
            if isinstance(payload.get(key), list):
                return _rows(payload[key])
    return []


def _lazy_laptop():
    from jarvis.control.laptop import LaptopController

    return LaptopController()


def _lazy_android():
    from jarvis.android_bridge.android import AndroidController

    return AndroidController()


def _table(title: str, columns: list[str], rows: list[list[str]]) -> Table:
    table = Table(title=title, header_style="bold cyan")
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*[("" if cell is None else str(cell)) for cell in row])
    return table


def _api_base() -> str:
    base = os.getenv("JARVIS_API_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise typer.BadParameter("JARVIS_API_URL must use HTTPS or point to localhost")
    return base


def _ensure_server_secret() -> None:
    """The backend refuses to boot without a 32+ char secret; mint a local one."""
    changed = False
    if not os.getenv("SECRET_KEY", "").strip():
        os.environ["SECRET_KEY"] = secrets.token_urlsafe(32)
        changed = True
    if not os.getenv("JARVIS_API_TOKEN", "").strip():
        os.environ["JARVIS_API_TOKEN"] = secrets.token_urlsafe(24)
        err_console.print(
            "[yellow]JARVIS_API_TOKEN was not set — generated a random one for this process only.[/yellow]\n"
            "[dim]Put it in .env so the browser UI and CLI chat stay authenticated.[/dim]"
        )
    if changed:
        err_console.print("[dim]SECRET_KEY was not set — generated an ephemeral one for this process.[/dim]")


# ---------------------------------------------------------------------------
# brain-backed commands
# ---------------------------------------------------------------------------
@app.command()
def ask(
    message: str = typer.Argument("", help="Question or instruction; omit for interactive mode."),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the Gemini model."),
    history: bool = typer.Option(True, "--history/--no-history", help="Keep multi-turn context in interactive mode."),
):
    """Ask JARVIS directly (local tool loop, streams as it thinks)."""
    from jarvis.core.brain import JarvisBrain

    brain = JarvisBrain()
    if model:
        brain.model = model
    if not brain.configured:
        err_console.print("[red]GEMINI_API_KEY missing[/red] — set GEMINI_API_KEY in .env")
        raise typer.Exit(code=1)

    interactive = not message
    console.print(
        Panel.fit(
            f"[bold cyan]JARVIS[/bold cyan] · model [magenta]{brain.model}[/magenta] · "
            f"[cyan]{len(brain.registry)}[/cyan] tools",
            border_style="cyan",
        )
    )

    while True:
        prompt = message or console.input("[bold green]You › [/]")
        message = None
        prompt = prompt.strip()
        if not prompt:
            continue
        if prompt.lower() in {"/quit", "/exit", "/q"}:
            break
        if prompt.lower() == "/clear":
            if hasattr(brain, "reset"):
                brain.reset()
            console.print("[dim]history cleared[/dim]")
            continue
        if prompt.lower() == "/help":
            console.print("[dim]/help /clear /quit · Ctrl+C aborts a turn.[/dim]")
            continue

        buffer: list[str] = []
        if not history:
            brain.reset()
        console.print("[bold cyan]JARVIS[/bold cyan]")
        try:
            asyncio.run(_stream_reply(brain, prompt, buffer))
        except KeyboardInterrupt:
            console.print("\n[yellow]stopped[/yellow]")
            continue
        answer = "".join(buffer)
        if answer and history:
            _persist_history(brain, prompt, answer)
        if not interactive:
            break


async def _stream_reply(brain, prompt: str, buffer: list[str]) -> None:
    async for event in brain.ask(prompt):
        kind = event["type"]
        if kind == "text_delta":
            text = event["text"]
            buffer.append(text)
            console.print(text, end="", markup=False, soft_wrap=True)
        elif kind == "status":
            if event["message"] != "thinking":
                console.print(f"[dim]{event['message']}[/dim]")
        elif kind == "tool_start":
            args = _brief(event.get("args") or {}, 60)
            console.print(f"  [cyan]→ {event['tool']}[/cyan] [dim]{args}[/dim]")
        elif kind == "tool_end":
            mark = "green" if event.get("ok") else "red"
            console.print(f"  [{mark}]✔ {event['tool']}[/{mark}] [dim]{_brief(event.get('summary', ''), 70)}[/dim]")
        elif kind == "tool_cancelled":
            console.print(f"  [yellow]⊘ {event['tool']}[/yellow] [dim]cancelled[/dim]")
        elif kind == "error":
            console.print(f"\n[red]error:[/red] {event['error']}")
    console.print()


def _persist_history(brain, prompt: str, answer: str) -> None:
    brain.history.append({"role": "user", "parts": [{"text": prompt}]})
    brain.history.append({"role": "model", "parts": [{"text": answer}]})
    brain.history = brain.history[-40:]


@app.command()
def tui():
    """Launch the realtime streaming terminal UI (local brain, no server)."""
    from jarvis.terminal.jarvis_tui import JarvisTUI

    console.print("[cyan]Launching JARVIS terminal UI…[/cyan]")
    JarvisTUI().run()


@app.command()
def tools(
    category: str | None = typer.Argument(None, help="Category filter, e.g. 'audio', 'android'."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema for one tool."),
):
    """List every tool the assistant can call."""
    from jarvis.tools.builtin_tools import build_registry

    registry = build_registry()
    if schema:
        if not category:
            err_console.print("[red]usage:[/red] jarvis tools <tool_name> --schema")
            raise typer.Exit(code=2)
        tool = registry.get(category)
        if tool is None:
            err_console.print(f"[red]unknown tool:[/red] {category}")
            raise typer.Exit(code=2)
        console.print_json(json.dumps(tool.schema(), ensure_ascii=False))
        return

    if category:
        names = registry.names(category)
        console.print(f"[bold cyan]{category}[/bold cyan] ({len(names)})")
        for name in sorted(names):
            tool = registry.get(name)
            console.print(f"  {name:<34} [{tool.risk.name}] {tool.description}")
        return

    total = len(registry)
    console.print(Panel.fit(f"[bold cyan]{total}[/bold cyan] tools registered", border_style="cyan"))
    for cat, names in sorted(registry.categories().items()):
        console.print(f"  [bold]{cat:<14}[/bold] {len(names):>3}  [dim]{', '.join(sorted(names)[:4])}…[/dim]")


@app.command()
def status():
    """Show brain, laptop, phone and backend status in one view."""
    from jarvis.core.brain import JarvisBrain

    brain = JarvisBrain()
    table = Table(title="JARVIS status", header_style="bold cyan")
    table.add_column("Component")
    table.add_column("State")
    table.add_column("Detail")

    table.add_row(
        "Gemini brain",
        "[green]ready[/green]" if brain.configured else "[red]no key[/red]",
        f"{brain.model} · {len(brain.registry)} tools",
    )

    from jarvis.tools.builtin_tools import get_android, get_laptop

    laptop = get_laptop().status()
    if _ok(laptop):
        table.add_row(
            "Laptop",
            "[green]online[/green]",
            f"CPU {laptop.get('cpu_percent', 0):.0f}% · RAM {laptop.get('memory_percent', 0):.0f}% · "
            f"disk free {laptop.get('disk_free_gb')} GB",
        )
        if laptop.get("battery_percent") is not None:
            plug = "charging" if laptop.get("battery_plugged") else "discharging"
            table.add_row("Battery", "[green]ok[/green]", f"{laptop.get('battery_percent')}% ({plug})")
    else:
        table.add_row("Laptop", "[red]error[/red]", _brief(laptop.get("error", "unavailable"), 80))

    overview = get_android().overview()
    devices = _rows(overview)
    if devices:
        for dev in devices:
            table.add_row("Android", "[green]connected[/green]", _brief(dev, 80))
    else:
        table.add_row("Android", "[yellow]no device[/yellow]", "USB debugging off, or no phone attached")

    try:
        import httpx

        base = os.getenv("JARVIS_API_URL", "http://127.0.0.1:8000").rstrip("/")
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"{base}/health")
            table.add_row("HTTP backend", "[green]up[/green]", f"{base} ({response.status_code})")
    except Exception:
        table.add_row("HTTP backend", "[dim]down[/dim]", "run 'jarvis serve' to start it")

    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8000, help="Port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
):
    """Start the HTTP + WebSocket backend (browser UI, remote clients)."""
    _ensure_server_secret()
    import uvicorn

    console.print(Panel.fit(
        f"[bold cyan]JARVIS[/bold cyan] backend on [green]http://{host}:{port}[/green]\n"
        f"UI: http://{host}:{port}/ · WS: ws://{host}:{port}/ws",
        border_style="cyan",
    ))
    uvicorn.run("app.main_enhanced:app", host=host, port=port, reload=reload, log_level="info")


@app.command()
def chat(message: str = typer.Argument(None, help="Optional first message; omit for interactive chat")):
    """Chat against the HTTP backend (requires 'jarvis serve' and JARVIS_API_TOKEN)."""
    import httpx

    token = os.getenv("JARVIS_API_TOKEN", "").strip()
    if not token:
        raise typer.BadParameter("Set JARVIS_API_TOKEN in .env before starting terminal chat")
    try:
        base = _api_base()
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    history: list[dict[str, str]] = []
    interactive = message is None
    console.print(Panel.fit("[bold cyan]JARVIS[/bold cyan] · Backend chat", border_style="cyan"))
    console.print(f"[dim]Backend: {base} · /help for commands · /quit to exit[/dim]")
    with httpx.Client(timeout=httpx.Timeout(120, connect=10)) as client:
        while True:
            prompt = message if message is not None else console.input("[bold green]You › [/]")
            message = None
            prompt = prompt.strip()
            if not prompt:
                continue
            if prompt.lower() in {"/quit", "/exit"}:
                break
            if prompt.lower() == "/clear":
                history.clear()
                console.clear()
                console.print("[dim]Backend conversation cleared.[/dim]")
                continue
            if prompt.lower() == "/help":
                console.print("[dim]/help  /clear  /quit · History lives in this process only.[/dim]")
                continue
            try:
                with client.stream(
                    "POST",
                    f"{base}/api/chat/stream",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"message": prompt, "history": history[-20:]},
                ) as response:
                    if response.status_code >= 400:
                        try:
                            detail = response.json().get("detail", "Request failed")
                        except (ValueError, AttributeError):
                            detail = response.read().decode("utf-8", errors="replace")
                        raise RuntimeError(f"HTTP {response.status_code}: {detail}")
                    chunks: list[str] = []
                    console.print("[bold cyan]JARVIS[/bold cyan] ", end="")
                    for line in response.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        if event.get("error"):
                            raise RuntimeError(event["error"])
                        if event.get("text"):
                            chunks.append(event["text"])
                            console.print(event["text"], end="", markup=False, soft_wrap=True)
                        if event.get("done"):
                            break
                    console.print()
                answer = "".join(chunks)
                if answer:
                    history.extend([{"role": "user", "content": prompt}, {"role": "model", "content": answer}])
                    history = history[-40:]
                if not interactive:
                    break
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                console.print(f"[red]Chat failed:[/red] {exc}")
                if interactive:
                    continue
                raise typer.Exit(code=1) from exc


@app.command()
def start():
    """Start JARVIS in real-time voice mode."""

    console.print(Panel.fit("[bold cyan]JARVIS[/bold cyan] Starting Real-Time Mode...", border_style="cyan"))
    asyncio.run(start_realtime())


async def start_realtime():
    from jarvis.core.jarvis_unified import JarvisUnified

    jarvis = JarvisUnified()
    await jarvis.initialize()
    console.print("[green]✔[/green] All systems online")
    console.print("[yellow]Say 'Hey JARVIS' to activate[/yellow]")
    try:
        await jarvis.start_realtime()
    except KeyboardInterrupt:
        await jarvis.stop()
        console.print("\n[red]JARVIS shut down[/red]")


# ---------------------------------------------------------------------------
# laptop group
# ---------------------------------------------------------------------------
@laptop_app.command("status")
def laptop_status():
    """CPU, memory, disk, battery, GPU and OS summary."""
    result = _lazy_laptop().status()
    if not _ok(result):
        return _fail(result)
    table = _table(
        "Laptop",
        ["Metric", "Value"],
        [[k.replace("_", " ").title(), str(v)] for k, v in result.items() if k != "success"],
    )
    console.print(table)


@laptop_app.command("open")
def laptop_open(app_name: str):
    """Launch an application by name."""
    _emit(_lazy_laptop().open_app(app_name), f"launched {app_name}")


@laptop_app.command("apps")
def laptop_apps(query: str = typer.Argument("", help="Search filter; empty lists everything.")):
    """Search installed applications."""
    result = _lazy_laptop().search_apps(query) if query else _lazy_laptop().list_running_apps()
    rows = _rows(result)
    if not rows and not _ok(result):
        return _fail(result)
    console.print(_table(f"Apps {query!r}".strip(), ["Name", "Path"], [[r.get("name"), r.get("path")] for r in rows]))


@laptop_app.command("volume")
def laptop_volume(level: int | None = typer.Argument(None, help="0-100; omit to print current.")):
    """Get or set the system volume."""
    ctrl = _lazy_laptop()
    if level is None:
        result = ctrl.get_volume()
        if not _ok(result):
            return _fail(result)
        console.print(f"[cyan]volume[/cyan] {result.get('volume')}%  muted={result.get('muted')}")
        return
    _emit(ctrl.set_volume(level), f"volume set to {level}%")


@laptop_app.command("mute")
def laptop_mute(on: bool = typer.Option(True, help="--no-mute to unmute.")):
    """Mute or unmute the system audio."""
    _emit(_lazy_laptop().set_mute(on), "muted" if on else "unmuted")


@laptop_app.command("windows")
def laptop_windows():
    """List top-level windows."""
    rows = _rows(_lazy_laptop().list_windows())
    console.print(_table("Windows", ["Handle", "Title"], [[r.get("handle"), r.get("title")] for r in rows]))


@laptop_app.command("focus")
def laptop_focus(title: str):
    """Focus a window whose title contains this text."""
    _emit(_lazy_laptop().focus_window(title), f"focused {title}")


@laptop_app.command("screenshot")
def laptop_screenshot(path: str | None = typer.Argument(None)):
    """Capture the screen to a PNG."""
    result = _lazy_laptop().screenshot(path)
    if _ok(result):
        console.print(f"[green]✔[/green] screenshot saved: {result.get('file')}")
    else:
        _fail(result)


@laptop_app.command("processes")
def laptop_processes(query: str = typer.Argument("", help="Filter by name.")):
    """List running processes."""
    rows = _rows(_lazy_laptop().list_processes(query) if query else _lazy_laptop().list_processes())
    console.print(_table("Processes", ["PID", "Name", "CPU%", "MEM MB"],
                         [[r.get("pid"), r.get("name"), r.get("cpu_percent"), r.get("memory_mb")] for r in rows[:60]]))


@laptop_app.command("kill")
def laptop_kill(name: str, force: bool = typer.Option(False, "--force", help="Also try a hard kill.")):
    """Terminate processes matching this name (critical processes are refused)."""
    _emit(_lazy_laptop().kill_process(name, force=force), f"killed {name}")


@laptop_app.command("shell")
def laptop_shell(command: str, yes: bool = typer.Option(False, "--yes", help="Skip confirmation.")):
    """Run a shell command with JARVIS's safe/confirm/blocked guardrails."""
    ctrl = _lazy_laptop()
    level = ctrl.classify_shell(command)
    if level == "blocked":
        err_console.print(f"[red]blocked:[/red] {command!r} matches a refused pattern")
        raise typer.Exit(code=1)
    if level == "confirm" and not yes:
        if not typer.confirm(f"Run {command!r}?", default=False):
            console.print("[yellow]cancelled[/yellow]")
            raise typer.Exit()
    _emit(ctrl.run_shell(command), "command ran")


@laptop_app.command("lock")
def laptop_lock():
    """Lock the workstation immediately."""
    _emit(_lazy_laptop().lock(), "locked")


@laptop_app.command("shutdown")
def laptop_shutdown(delay: int = typer.Option(10, help="Seconds until shutdown.")):
    """Schedule Windows shutdown (asks first, cancellable)."""
    if not typer.confirm(f"Schedule Windows shutdown in {delay} seconds?", default=False):
        raise typer.Exit()
    _emit(_lazy_laptop().shutdown(delay), f"shutting down in {delay}s")


@laptop_app.command("restart")
def laptop_restart(delay: int = typer.Option(10, help="Seconds until restart.")):
    """Schedule Windows restart (asks first, cancellable)."""
    if not typer.confirm(f"Schedule Windows restart in {delay} seconds?", default=False):
        raise typer.Exit()
    _emit(_lazy_laptop().restart(delay), f"restarting in {delay}s")


@laptop_app.command("clipboard")
def laptop_clipboard(text: str | None = typer.Argument(None, help="Text to copy; omit to read.")):
    """Read or write the Windows clipboard."""
    ctrl = _lazy_laptop()
    if text is None:
        result = ctrl.get_clipboard()
        if _ok(result):
            console.print(result.get("text", ""))
        else:
            _fail(result)
    else:
        _emit(ctrl.set_clipboard(text), "copied to clipboard")


@laptop_app.command("network")
def laptop_network():
    """Local IP, public IP, Wi-Fi and listening ports."""
    ctrl = _lazy_laptop()
    payload = {
        "local_ip": ctrl.local_ip(),
        "public_ip": ctrl.public_ip(),
        "wifi": ctrl.current_wifi(),
        "listening": ctrl.listening_ports(),
    }
    console.print_json(json.dumps(payload, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# android group
# ---------------------------------------------------------------------------
@android_app.command("devices")
def android_devices():
    """List attached devices."""
    ctrl = _lazy_android()
    devices = ctrl.refresh_devices()
    if not devices:
        console.print("[yellow]No Android devices connected.[/yellow]")
        console.print("[dim]Enable USB debugging, plug the phone in, then: jarvis android setup[/dim]")
        raise typer.Exit()
    console.print(_table("Android devices", ["Serial", "State"], [[d, "connected"] for d in devices]))


@android_app.command("setup")
def android_setup():
    """One-shot provisioning: find/install ADB, grant permissions, verify the device."""
    console.print("[cyan]Provisioning Android bridge…[/cyan]")
    result = asyncio.run(_lazy_android().setup())
    if _ok(result):
        console.print(f"[green]✔[/green] {result.get('summary', 'setup complete')}")
        for step in result.get("steps", []):
            console.print(f"  [dim]{step}[/dim]")
    else:
        _fail(result)


@android_app.command("battery")
def android_battery():
    """Battery level, status, temperature of the phone."""
    ctrl = _lazy_android()
    console.print_json(json.dumps(ctrl.battery(), ensure_ascii=False, default=str))


@android_app.command("apps")
def android_apps(query: str = typer.Argument("", help="Package/name filter.")):
    """List or search installed phone apps."""
    ctrl = _lazy_android()
    rows = _rows(ctrl.search_apps(query) if query else ctrl.list_apps())
    console.print(_table(f"Phone apps {query!r}".strip(), ["Package", "Label"],
                         [[r.get("package") or r.get("name"), r.get("label") or r.get("name")] for r in rows[:80]]))


@android_app.command("launch")
def android_launch(package: str):
    """Launch an app by package name."""
    _emit(_lazy_android().launch_app(package), f"launched {package}")


@android_app.command("screenshot")
def android_screenshot(path: str = typer.Argument("android.png")):
    """Capture the phone screen."""
    result = _lazy_android().screenshot(path)
    if _ok(result):
        console.print(f"[green]✔[/green] saved {result.get('file', path)}")
    else:
        _fail(result)


@android_app.command("tap")
def android_tap(x: int, y: int):
    """Tap screen coordinates."""
    _emit(_lazy_android().tap(x, y), f"tapped ({x},{y})")


@android_app.command("swipe")
def android_swipe(
    x1: int, y1: int, x2: int, y2: int, duration: int = typer.Option(300, help="Swipe duration in ms.")
):
    """Swipe between two screen coordinates."""
    _emit(_lazy_android().swipe(x1, y1, x2, y2, duration), f"swiped ({x1},{y1}) → ({x2},{y2})")


@android_app.command("type")
def android_type(text: str):
    """Type text into the focused field."""
    _emit(_lazy_android().type_text(text), "typed")


@android_app.command("key")
def android_key(key: str):
    """Press a key alias (home, back, volume_up, power, enter …)."""
    _emit(_lazy_android().press_key(key), f"pressed {key}")


@android_app.command("sms")
def android_sms(number: str, body: str):
    """Send an SMS (requires the messaging permission granted during setup)."""
    if not typer.confirm(f"Send SMS to {number}?", default=False):
        raise typer.Exit()
    result = _lazy_android().send_sms(number, message=body)
    if _ok(result):
        console.print("[green]✔[/green] sms handed to the messaging app")
        if result.get("note"):
            console.print(f"[dim]{result['note']}[/dim]")
    else:
        _fail(result)


@android_app.command("notifications")
def android_notifications(panel: bool = typer.Option(False, "--panel", help="Open the shade instead of listing.")):
    """Read the notification shade, or open it on the phone."""
    ctrl = _lazy_android()
    result = ctrl.open_notifications() if panel else ctrl.recent_notifications()
    if _ok(result):
        if panel:
            console.print("[green]✔[/green] notification shade opened")
        else:
            notes = result.get("notifications") or result.get("items") or []
            if not notes:
                console.print("[dim]no notifications[/dim]")
            else:
                console.print(_table("Notifications", ["App", "Text"],
                                     [[n.get("package") or n.get("app"), n.get("text") or n.get("title")] for n in notes]))
    else:
        _fail(result)


@android_app.command("install")
def android_install(apk_path: str):
    """Install an APK file from this computer."""
    _emit(_lazy_android().install_app(apk_path), f"installed {apk_path}")


@android_app.command("pull")
def android_pull(remote: str, local: str):
    """Copy a file off the phone."""
    _emit(_lazy_android().pull_file(remote, local), f"pulled {remote} → {local}")


@android_app.command("push")
def android_push(local: str, remote: str):
    """Copy a file onto the phone."""
    _emit(_lazy_android().push_file(local, remote), f"pushed {local} → {remote}")


if __name__ == "__main__":
    app()
