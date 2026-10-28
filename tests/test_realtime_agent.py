"""Realtime voice agent state machine tests (offline, no devices, no API).

The audio stack (sounddevice/webrtcvad/openwakeword) is optional at test time:
when those packages are missing (e.g. Linux CI) we install empty stand-ins so
the module imports, then replace every collaborator with a fake.
"""

from __future__ import annotations

import asyncio
import sys
import time
import types as stdlib_types

import pytest

for _name in ("sounddevice", "webrtcvad"):
    if _name not in sys.modules:
        try:
            __import__(_name)
        except ImportError:
            stub = stdlib_types.ModuleType(_name)
            if _name == "webrtcvad":
                stub.Vad = lambda *args, **kwargs: None  # type: ignore[attr-defined]
            sys.modules[_name] = stub

np = pytest.importorskip("numpy")

from jarvis.config.settings import config  # noqa: E402
from jarvis.core.agent import jarvis_agent as agent_mod  # noqa: E402
from jarvis.core.agent.jarvis_agent import AWAKE, SLEEPING, JarvisAgent  # noqa: E402
from jarvis.core.agent.voice_tools import TOOL_DECLARATIONS  # noqa: E402


class FakeAudio:
    def __init__(self, **kwargs):
        self.enqueued: list[bytes] = []
        self.chimes = 0
        self.cleared = 0
        self.input_started = False
        self.input_stopped = False
        self.output_started = False
        self._pending = False

    def start_output(self, sample_rate=24000):
        self.output_started = True

    def start_input(self, callback=None):
        self.input_started = True
        self.callback = callback

    def stop_input(self):
        self.input_stopped = True

    def stop_output(self):
        pass

    def enqueue(self, pcm16: bytes, sample_rate=None):
        self.enqueued.append(pcm16)
        self._pending = True

    def clear_output(self):
        self.cleared += 1
        self.enqueued.clear()
        self._pending = False

    def output_pending(self) -> bool:
        return self._pending

    def play_chime(self, **kwargs):
        self.chimes += 1


class FakeWake:
    def __init__(self, threshold=0.5, **kwargs):
        self.threshold = threshold
        self.armed = True
        self.resets = 0

    def detect(self, frame):
        if self.armed:
            self.armed = False
            return True, 0.91
        return False, 0.0

    def reset(self):
        self.resets += 1


class FakeVAD:
    def __init__(self, **kwargs):
        self.speech = False

    def reset(self):
        pass

    def is_speech(self, frame) -> bool:
        return self.speech


class FakeLive:
    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        self.kwargs = kwargs
        self.connected = False
        self.sent_audio: list[bytes] = []
        self.sent_text: list[str] = []
        self.on_ready = None
        self.on_audio = None
        self.on_text = None
        self.on_transcript = None
        self.on_turn_complete = None
        self.on_interrupted = None
        self.on_tool_call = None
        self.on_error = None

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def disconnect(self):
        self.connected = False

    async def send_audio(self, data):
        if self.connected:
            self.sent_audio.append(data if isinstance(data, bytes) else bytes(data))

    async def send_text(self, text: str):
        self.sent_text.append(text)


class FakeMachine:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def _record(self, name, args=None, **extra):
        self.calls.append((name, args or {}))
        return {"success": True, **extra}

    def status(self):
        return self._record("status", cpu_percent=12.0, memory_percent=40.0, disk_free_gb=100)

    def open_app(self, name):
        return self._record("open_app", {"name": name})

    def set_volume(self, level):
        return self._record("set_volume", {"level": level}, volume=level)

    def set_mute(self, muted):
        return self._record("set_mute", {"muted": muted})

    def screenshot(self, path=None):
        return self._record("screenshot", file="shot.png")

    def focus_window(self, title):
        return self._record("focus_window", {"title": title})

    def lock(self):
        return self._record("lock")


class FakeCall:
    def __init__(self, name, args=None, id="call-1"):
        self.name = name
        self.args = args or {}
        self.id = id


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(agent_mod, "AudioIO", FakeAudio)
    monkeypatch.setattr(agent_mod, "WakeWordDetector", FakeWake)
    monkeypatch.setattr(agent_mod, "VADProcessor", FakeVAD)
    monkeypatch.setattr(agent_mod, "GeminiLiveClient", FakeLive)
    monkeypatch.setattr(config, "use_gemini_live", True)
    monkeypatch.setattr(config, "gemini_api_key", "test-key")
    monkeypatch.setattr(config, "wakeword_enabled", True)
    monkeypatch.setattr(config, "voice_tools_enabled", True)
    monkeypatch.setattr(config, "awake_timeout_seconds", 5.0)


async def _settle(rounds: int = 5):
    for _ in range(rounds):
        await asyncio.sleep(0.02)


async def test_wake_stream_tool_sleep_cycle(patched):
    machine = FakeMachine()
    events: list[tuple[str, dict]] = []
    agent = JarvisAgent(machine=machine, on_event=lambda kind, payload: events.append((kind, payload)))

    await agent.initialize()
    assert agent.live_client is not None and agent.live_client.connected
    assert agent.live_client.kwargs.get("tools"), "voice tools must be advertised to the model"
    assert agent.audio.output_started

    agent._loop = asyncio.get_running_loop()
    agent.is_listening = True
    agent.wakeword.armed = False  # deaf until we choose to hear the wake word

    # 1. Silence while sleeping: nothing happens.
    agent.on_audio_frame(np.zeros(480, dtype=np.float32))
    await _settle()
    assert agent.state == SLEEPING
    assert agent.live_client.sent_audio == []

    # 2. Wake word fires -> chime, state awake.
    agent.wakeword.armed = True
    agent.on_audio_frame(np.zeros(480, dtype=np.float32))
    await _settle()
    assert agent.state == AWAKE
    assert agent.audio.chimes == 1
    assert events and events[0][0] == "wake"

    # 3. While awake, mic frames stream to the live session.
    frame = (np.ones(480, dtype=np.float32) * 0.1)
    agent.on_audio_frame(frame)
    await _settle()
    assert len(agent.live_client.sent_audio) == 1
    assert len(agent.live_client.sent_audio[0]) == 960  # 480 int16 samples

    # 4. Server events: transcript, reply audio, tool call.
    await agent._on_transcript("user", "open chrome")
    await agent._on_audio(b"\x01\x00" * 100, 24000)
    await agent._on_turn_complete()
    assert agent.audio.enqueued, "model audio must reach the speaker queue"

    result = await agent._on_tool_call(FakeCall("open_app", {"name": "chrome"}))
    assert result["success"] is True
    assert machine.calls == [("open_app", {"name": "chrome"})]
    assert any(kind == "tool" for kind, _ in events)

    # 5. Idle timeout returns JARVIS to sleep and clears playback.
    agent.audio._pending = False
    agent._last_activity = time.monotonic() - (config.awake_timeout_seconds + 1)
    await agent._check_idle()
    assert agent.state == SLEEPING
    assert ("sleep",) == (events[-1][0],)

    await agent.stop()
    assert agent.audio.input_stopped
    assert not agent.live_client.connected


async def test_interrupt_clears_playback(patched):
    machine = FakeMachine()
    agent = JarvisAgent(machine=machine)
    await agent.initialize()
    agent._loop = asyncio.get_running_loop()
    agent.is_listening = True

    await agent._on_audio(b"\x02\x00" * 50, 24000)
    assert agent.audio.enqueued
    await agent._on_interrupted()
    assert agent.audio.enqueued == []

    await agent.stop()


async def test_tool_failure_is_reported_to_model(patched):
    class ExplodingMachine(FakeMachine):
        def open_app(self, name):
            raise RuntimeError("boom")

    agent = JarvisAgent(machine=ExplodingMachine())
    await agent.initialize()
    result = await agent._on_tool_call(FakeCall("open_app", {"name": "chrome"}))
    assert result["success"] is False
    assert "boom" in result["error"]
    await agent.stop()


def test_tool_declarations_match_handlers():
    from jarvis.core.agent.voice_tools import _HANDLERS

    names = {tool["name"] for tool in TOOL_DECLARATIONS}
    assert names == set(_HANDLERS)
