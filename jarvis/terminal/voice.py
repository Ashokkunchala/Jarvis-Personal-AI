"""Background voice-call controller for the floating robot.

The robot animation itself is standard-library only. This module is imported
lazily when the user presses the call key and it keeps every heavy dependency
(``sounddevice``, ``webrtcvad``, ``openwakeword``, Gemini Live) inside a worker
thread, so the animation never blocks and the module can be imported safely on
machines without the audio stack.

The worker runs :class:`jarvis.core.agent.jarvis_agent.JarvisAgent` in call
mode: no wake word, microphone streaming from the first frame, and no idle
sleep. Transcripts and tool activity are mirrored into a thread-safe snapshot
that the renderer can read every frame.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import logging
import os
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

__all__ = ["VoiceCall", "VoiceView", "missing_voice_packages", "has_api_key"]

# Packages the realtime loop needs. google.genai is checked separately because
# it is a submodule of a namespace package.
_REQUIRED_PACKAGES = ("sounddevice", "webrtcvad", "openwakeword", "numpy", "scipy")
_GEMINI_PACKAGE = "google.genai"

# Audio is a device-level API; only one call can own the microphone at a time.
_AMBIENT = ("off", "error")


@dataclass(frozen=True)
class VoiceView:
    """Thread-safe snapshot of the call, read by the frame renderer."""

    state: str = "off"  # off | connecting | live | error
    detail: str = ""
    user: str = ""
    reply: str = ""
    tool: str = ""

    @property
    def active(self) -> bool:
        return self.state not in _AMBIENT


def _module_missing(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is None
    except (ImportError, ModuleNotFoundError, ValueError):
        return True


def missing_voice_packages() -> list[str]:
    """Return the realtime packages that are not importable in this venv."""
    missing = [name for name in _REQUIRED_PACKAGES if _module_missing(name)]
    if _module_missing(_GEMINI_PACKAGE):
        missing.append(_GEMINI_PACKAGE)
    return missing


def has_api_key() -> bool:
    """True when ``GEMINI_API_KEY`` is configured (``.env`` is loaded by config)."""
    try:
        from jarvis.config.settings import config

        if config.gemini_api_key.strip():
            return True
    except Exception:  # noqa: BLE001 - fall back to the raw environment
        pass
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


class VoiceCall:
    """Own a JarvisAgent voice call from a background thread.

    ``start()`` is non-blocking and returns ``""`` on success or a short,
    user-facing reason when the call cannot be dialled. ``stop()`` hangs up and
    joins the worker. ``view()`` returns the latest snapshot at any time.
    """

    def __init__(
        self,
        agent_factory: Callable[[], Any] | None = None,
        *,
        preflight: bool = True,
        join_timeout: float = 6.0,
    ) -> None:
        self._factory = agent_factory
        self._preflight = preflight
        self._join_timeout = join_timeout

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()
        self._view = VoiceView()
        self._events: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=200)

    # -- public API -----------------------------------------------------
    def is_active(self) -> bool:
        """True while the worker thread is alive (connecting or live)."""
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> str:
        """Dial the call in the background. Returns ``""`` on success."""
        if self.is_active():
            return ""
        if self._preflight:
            missing = missing_voice_packages()
            if missing:
                return self._fail("voice stack missing: " + ", ".join(missing))
            if not has_api_key():
                return self._fail("GEMINI_API_KEY is not set in .env")

        self._stop_flag.clear()
        self._events = queue.Queue(maxsize=200)
        with self._lock:
            self._view = VoiceView(state="connecting", detail="dialing")
        self._thread = threading.Thread(
            target=self._run,
            name="jarvis-voice-call",
            daemon=True,
        )
        self._thread.start()
        return ""

    def stop(self, timeout: float | None = None) -> None:
        """Hang up the call and wait for the worker thread to finish."""
        self._stop_flag.set()
        loop, stop_event = self._loop, self._stop_event
        if loop is not None and stop_event is not None:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(stop_event.set)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(self._join_timeout if timeout is None else timeout)
        if thread is not None and thread.is_alive():
            # Never let a second call grab the microphone while the first is
            # still shutting down; leave the thread visible and retry later.
            return
        self._thread = None
        self._loop = None
        self._stop_event = None
        with self._lock:
            self._view = VoiceView()

    def view(self) -> VoiceView:
        """Return a copy of the latest call state."""
        with self._lock:
            return replace(self._view)

    def drain_events(self) -> list[tuple[str, dict[str, Any]]]:
        """Return and clear any pending agent events (useful for logging)."""
        items: list[tuple[str, dict[str, Any]]] = []
        while True:
            try:
                items.append(self._events.get_nowait())
            except queue.Empty:
                return items

    # -- worker ---------------------------------------------------------
    def _fail(self, message: str) -> str:
        with self._lock:
            self._view = VoiceView(state="error", detail=message)
        return message

    def _run(self) -> None:
        # The robot owns the terminal: library logs would corrupt frames.
        # Call state, errors and tool activity reach the UI through _on_event.
        if self._preflight:
            library_log = logging.getLogger("jarvis")
            library_log.addHandler(logging.NullHandler())
            library_log.propagate = False
            library_log.setLevel(logging.CRITICAL + 1)
        try:
            asyncio.run(self._main())
        except Exception as exc:  # noqa: BLE001 - surfaced to the robot
            self._publish("error", {"message": str(exc)})
            self._fail(str(exc)[:120])
        finally:
            with self._lock:
                if self._view.state not in ("error",):
                    self._view = VoiceView()

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        if self._stop_flag.is_set():
            self._stop_event.set()

        agent = self._make_agent()
        try:
            await agent.initialize()
            run_task = asyncio.create_task(agent.start(call_mode=True))
            stop_waiter = asyncio.create_task(self._stop_event.wait())
            try:
                done, _ = await asyncio.wait(
                    {run_task, stop_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if run_task in done and not run_task.cancelled():
                    # The agent ended by itself (usually an error); surface it.
                    exc = run_task.exception()
                    if exc is not None:
                        raise exc
                else:
                    run_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await run_task
            finally:
                stop_waiter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stop_waiter
        finally:
            # JarvisAgent.start() already calls stop() on cancellation; this
            # second call only matters when initialize() itself failed.
            with contextlib.suppress(Exception):
                await agent.stop()

    def _make_agent(self) -> Any:
        if self._factory is not None:
            return self._factory()
        from jarvis.control.laptop import LaptopController
        from jarvis.core.agent.jarvis_agent import JarvisAgent

        return JarvisAgent(machine=LaptopController(), on_event=self._on_event)

    # -- event mirroring ------------------------------------------------
    def _on_event(self, kind: str, payload: dict[str, Any]) -> None:
        self._publish(kind, payload)
        with self._lock:
            view = self._view
            if kind == "ready":
                view = replace(view, state="live", detail="microphone online")
            elif kind == "live_ready":
                view = replace(view, state="live", detail="live session open")
            elif kind == "wake":
                view = replace(
                    view,
                    state="live",
                    detail="call live" if payload.get("mode") == "call" else "awake",
                )
            elif kind == "transcript":
                text = str(payload.get("text", ""))[:160]
                if payload.get("source") == "user":
                    view = replace(view, user=text, reply="")
                else:
                    view = replace(view, reply=text)
            elif kind == "text":
                view = replace(view, reply=str(payload.get("text", ""))[:160])
            elif kind == "tool":
                view = replace(view, tool=str(payload.get("name", ""))[:60])
            elif kind == "interrupted":
                view = replace(view, reply="")
            elif kind == "error":
                view = replace(
                    view,
                    state="error",
                    detail=str(payload.get("message", "voice error"))[:120],
                )
            self._view = view

    def _publish(self, kind: str, payload: dict[str, Any]) -> None:
        try:
            self._events.put_nowait((kind, payload))
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self._events.get_nowait()
            with contextlib.suppress(queue.Full):
                self._events.put_nowait((kind, payload))
