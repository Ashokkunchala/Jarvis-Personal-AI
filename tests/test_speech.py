"""Tests for the speech backend interface (local-first, sanitized errors)."""

from __future__ import annotations

import threading
import time

import pytest

from jarvis.core.voice.speech import (
    ElevenLabsBackend,
    LocalTTSBackend,
    SpeechEngine,
    SpeechError,
    SynthesisResult,
    TTSBackend,
)


class FakeBackend(TTSBackend):
    def __init__(self, name="fake", reason="", fails_with=None, audio=b"AUDIO"):
        self.name = name
        self.reason = reason
        self.fails_with = fails_with
        self.audio = audio
        self.calls = []

    def available(self):
        return self.reason

    def synthesize(self, text, *, cancel=None):
        self.calls.append(text)
        if self.fails_with:
            raise SpeechError(self.fails_with)
        return SynthesisResult(audio=self.audio, format="wav", backend=self.name, chars=len(text))


class FakePyttsx:
    def __init__(self, delay=0.0):
        self.delay = delay
        self.saved = []

    def setProperty(self, *args):  # noqa: N802 - mirrors the pyttsx3 API
        pass

    def save_to_file(self, text, path):
        self.saved.append((text, path))

    def runAndWait(self):  # noqa: N802 - mirrors the pyttsx3 API
        if self.delay:
            time.sleep(self.delay)
        with open(self.saved[-1][1], "wb") as fh:
            fh.write(b"RIFF-local-wav")

    def stop(self):
        pass


# ------------------------------------------------------------------ local
def test_local_backend_reports_missing_pyttsx3():
    backend = LocalTTSBackend()
    reason = backend.available()
    # In the test venv pyttsx3 is not installed, so it must explain, not crash.
    assert "pyttsx3" in reason
    with pytest.raises(SpeechError, match="unavailable"):
        backend.synthesize("hello")


def test_local_backend_synthesizes_with_engine_factory(tmp_path):
    backend = LocalTTSBackend(engine_factory=FakePyttsx)
    result = backend.synthesize("hello jarvis")
    assert result.backend == "local"
    assert result.format == "wav"
    assert result.audio.startswith(b"RIFF")
    assert result.chars == len("hello jarvis")


def test_local_backend_timeout():
    backend = LocalTTSBackend(timeout_seconds=0.2, engine_factory=lambda: FakePyttsx(delay=2.0))
    with pytest.raises(SpeechError, match="timed out"):
        backend.synthesize("slow speech")


def test_local_backend_cancelled_before_start():
    cancel = threading.Event()
    cancel.set()
    backend = LocalTTSBackend(engine_factory=FakePyttsx)
    with pytest.raises(SpeechError, match="cancelled"):
        backend.synthesize("hello", cancel=cancel)


# ------------------------------------------------------------- elevenlabs
def test_elevenlabs_missing_key_and_voice_are_explained():
    env = {"ELEVENLABS_API_KEY": "", "ELEVENLABS_VOICE_ID": ""}
    backend = ElevenLabsBackend(env=env)
    assert "ELEVENLABS_API_KEY" in backend.available()
    with pytest.raises(SpeechError, match="ELEVENLABS_API_KEY"):
        backend.synthesize("hello")
    env["ELEVENLABS_API_KEY"] = "secret-key-123"
    backend = ElevenLabsBackend(env=env)
    assert "ELEVENLABS_VOICE_ID" in backend.available()


def test_elevenlabs_success_uses_header_and_returns_mp3():
    seen = {}

    def opener(url, headers, body, timeout):
        seen.update({"url": url, "headers": headers, "body": body, "timeout": timeout})
        return b"mp3-bytes"

    env = {"ELEVENLABS_API_KEY": "secret-key-123", "ELEVENLABS_VOICE_ID": "voice-9"}
    backend = ElevenLabsBackend(env=env, opener=opener)
    result = backend.synthesize("hello there")
    assert result.audio == b"mp3-bytes" and result.format == "mp3"
    assert seen["headers"]["xi-api-key"] == "secret-key-123"
    assert "voice-9" in seen["url"]
    assert b"hello there" in seen["body"]


def test_elevenlabs_error_never_leaks_the_key():
    def opener(url, headers, body, timeout):
        raise RuntimeError("HTTP 401 for key secret-key-123: unauthorized")

    env = {"ELEVENLABS_API_KEY": "secret-key-123", "ELEVENLABS_VOICE_ID": "voice-9"}
    backend = ElevenLabsBackend(env=env, opener=opener)
    with pytest.raises(SpeechError) as excinfo:
        backend.synthesize("hello")
    message = str(excinfo.value)
    assert "secret-key-123" not in message
    assert "<redacted>" in message


def test_elevenlabs_timeout_is_passed_to_transport():
    seen = {}

    def opener(url, headers, body, timeout):
        seen["timeout"] = timeout
        return b"x"

    env = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}
    backend = ElevenLabsBackend(env=env, opener=opener, timeout_seconds=7)
    backend.synthesize("hello")
    assert seen["timeout"] == 7.0


def test_elevenlabs_key_never_appears_in_status():
    env = {"ELEVENLABS_API_KEY": "secret-key-123", "ELEVENLABS_VOICE_ID": "voice-9"}
    engine = SpeechEngine.from_env({**env, "JARVIS_TTS_BACKEND": "elevenlabs"})
    rendered = str(engine.status())
    assert "secret-key-123" not in rendered
    assert all(entry["available"] for entry in engine.status())


# ----------------------------------------------------------------- engine
def test_engine_defaults_to_local_first():
    engine = SpeechEngine.from_env({})
    assert [b.name for b in engine.backends] == ["local"]


def test_engine_order_follows_env():
    engine = SpeechEngine.from_env({"JARVIS_TTS_BACKEND": "elevenlabs,local"})
    assert [b.name for b in engine.backends] == ["elevenlabs", "local"]
    with pytest.raises(ValueError, match="Unknown TTS backend"):
        SpeechEngine.from_env({"JARVIS_TTS_BACKEND": "bogus"})


def test_engine_falls_back_to_next_backend():
    first = FakeBackend(name="first", reason="not configured")
    second = FakeBackend(name="second")
    engine = SpeechEngine([first, second])
    result = engine.synthesize("fallback works")
    assert result.backend == "second"
    assert first.calls == [] and second.calls == ["fallback works"]


def test_engine_falls_back_after_failure_and_reports_all_reasons():
    first = FakeBackend(name="first", fails_with="boom")
    second = FakeBackend(name="second")
    engine = SpeechEngine([first, second])
    assert engine.synthesize("hi").backend == "second"

    broken = SpeechEngine([FakeBackend(name="a", reason="missing"), FakeBackend(name="b", fails_with="down")])
    with pytest.raises(SpeechError) as excinfo:
        broken.synthesize("hi")
    assert "a: missing" in str(excinfo.value) and "b: down" in str(excinfo.value)


def test_engine_rejects_empty_text():
    engine = SpeechEngine([FakeBackend()])
    with pytest.raises(SpeechError, match="empty"):
        engine.synthesize("   ")
    with pytest.raises(ValueError):
        SpeechEngine([])
