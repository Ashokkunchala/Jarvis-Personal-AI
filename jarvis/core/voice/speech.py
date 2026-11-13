"""Speech output backends: one shared interface for the TUI, robot and server.

Four things that are often tangled together stay separate here:

* STT engine  - how speech becomes text (``jarvis.config.settings.stt_engine``)
* TTS backend - how text becomes audio (this module)
* chat model  - which LLM produced the reply (not this module's concern)
* voice id    - which voice a backend uses (a different value from any model id)

Local on-device synthesis (pyttsx3) is the default and costs nothing.
ElevenLabs is used only when explicitly selected through ``JARVIS_TTS_BACKEND``
and configured with ``ELEVENLABS_API_KEY`` plus ``ELEVENLABS_VOICE_ID``.
Backend errors are sanitized: API keys never appear in exceptions, logs or
status output, and a missing key is reported as missing, not as a crash.

The backend-separation idea is adapted from OpenJarvis (Apache-2.0,
https://github.com/open-jarvis/OpenJarvis); this is an independent
implementation for Jarvis-Personal-AI. Playback stays with the caller (the
terminal robot and the HTTP server already own their audio paths), so the
same engine serves the voice-first TUI and the Android client's server side
without a second application.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "SpeechError",
    "SynthesisResult",
    "TTSBackend",
    "LocalTTSBackend",
    "ElevenLabsBackend",
    "SpeechEngine",
]

DEFAULT_ELEVENLABS_MODEL = "eleven_multilingual_v2"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TEXT_CHARS = 5000


class SpeechError(Exception):
    """A sanitized speech failure. Messages never contain credentials."""


@dataclass(frozen=True)
class SynthesisResult:
    """Audio produced by a backend. Playback is the caller's job."""

    audio: bytes
    format: str  # "wav" or "mp3"
    backend: str
    chars: int


def _redact(text: str, secrets: Sequence[str]) -> str:
    """Remove every known secret value from text destined for logs/errors."""
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "<redacted>")
    return cleaned


def _check_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise SpeechError("Nothing to say - text is empty.")
    if len(text) > MAX_TEXT_CHARS:
        raise SpeechError(f"Text is too long ({len(text)} chars, max {MAX_TEXT_CHARS}).")
    return text


class TTSBackend:
    """Interface every speech backend implements."""

    name = "base"

    def available(self) -> str:
        """Return "" when usable, otherwise a short user-facing reason."""
        raise NotImplementedError

    def synthesize(
        self,
        text: str,
        *,
        cancel: threading.Event | None = None,
    ) -> SynthesisResult:
        """Turn text into audio bytes. Raises SpeechError on failure."""
        raise NotImplementedError


class LocalTTSBackend(TTSBackend):
    """Free on-device synthesis through pyttsx3 (SAPI5 on Windows).

    pyttsx3 is an optional dependency: when it is not installed the backend
    simply reports itself unavailable and the engine falls back or explains
    what to install. Synthesis runs on a worker thread with a timeout so a
    stuck driver can never hang the caller.
    """

    name = "local"

    def __init__(
        self,
        *,
        voice_id: str = "",
        rate: int | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        engine_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.voice_id = voice_id
        self.rate = rate
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        # Test hook; production builds a pyttsx3 engine.
        self._engine_factory = engine_factory

    def available(self) -> str:
        if self._engine_factory is not None:
            return ""
        try:
            import importlib.util

            if importlib.util.find_spec("pyttsx3") is None:
                return "pyttsx3 is not installed (pip install pyttsx3)"
        except (ImportError, ValueError):
            return "pyttsx3 is not installed (pip install pyttsx3)"
        return ""

    def _build_engine(self) -> Any:
        if self._engine_factory is not None:
            return self._engine_factory()
        import pyttsx3  # noqa: PLC0415 - optional dependency, imported lazily

        engine = pyttsx3.init()
        if self.voice_id:
            try:
                engine.setProperty("voice", self.voice_id)
            except Exception:  # noqa: BLE001 - unknown voice ids just fall back
                pass
        if self.rate:
            engine.setProperty("rate", int(self.rate))
        return engine

    def synthesize(
        self,
        text: str,
        *,
        cancel: threading.Event | None = None,
    ) -> SynthesisResult:
        text = _check_text(text)
        reason = self.available()
        if reason:
            raise SpeechError(f"Local speech is unavailable: {reason}")
        if cancel is not None and cancel.is_set():
            raise SpeechError("Speech cancelled before it started.")

        result: dict[str, Any] = {}
        tmp = tempfile.NamedTemporaryFile(prefix="jarvis-tts-", suffix=".wav", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()

        def work() -> None:
            try:
                engine = self._build_engine()
                engine.save_to_file(text, str(tmp_path))
                engine.runAndWait()
                with contextlib.suppress(Exception):
                    engine.stop()
                result["audio"] = tmp_path.read_bytes()
            except Exception as exc:  # noqa: BLE001 - sanitized below
                result["error"] = str(exc)[:200]

        thread = threading.Thread(target=work, name="jarvis-tts-local", daemon=True)
        thread.start()
        thread.join(self.timeout_seconds)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        if thread.is_alive():
            raise SpeechError("Local speech timed out; the audio driver did not answer.")
        if cancel is not None and cancel.is_set():
            raise SpeechError("Speech cancelled.")
        if "error" in result:
            raise SpeechError(f"Local speech failed: {_redact(result['error'], [])}")
        audio = result.get("audio") or b""
        if not audio:
            raise SpeechError("Local speech produced no audio.")
        return SynthesisResult(audio=audio, format="wav", backend=self.name, chars=len(text))


class ElevenLabsBackend(TTSBackend):
    """Cloud synthesis through the ElevenLabs API - opt-in only.

    ``ELEVENLABS_API_KEY`` and ``ELEVENLABS_VOICE_ID`` are two different
    values and both are required. The key is read from the environment (or
    passed explicitly in tests), used only in the request header, and never
    written to logs, exceptions or status output.
    """

    name = "elevenlabs"
    API_BASE = "https://api.elevenlabs.io/v1"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        env: Mapping[str, str] | None = None,
        opener: Callable[..., bytes] | None = None,
    ) -> None:
        env = os.environ if env is None else env
        self._api_key = api_key if api_key is not None else env.get("ELEVENLABS_API_KEY", "")
        self.voice_id = voice_id if voice_id is not None else env.get("ELEVENLABS_VOICE_ID", "")
        self.model_id = model_id or env.get("ELEVENLABS_MODEL", DEFAULT_ELEVENLABS_MODEL)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        # Test hook: replaces the network call. Signature (url, headers, body, timeout) -> bytes.
        self._opener = opener

    @property
    def configured(self) -> bool:
        return bool(self._api_key.strip() and self.voice_id.strip())

    def available(self) -> str:
        if not self._api_key.strip():
            return "ELEVENLABS_API_KEY is not set"
        if not self.voice_id.strip():
            return "ELEVENLABS_VOICE_ID is not set"
        return ""

    def _post(self, url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        if self._opener is not None:
            return self._opener(url, headers, body, timeout)
        import urllib.request

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed API host
            return resp.read()

    def synthesize(
        self,
        text: str,
        *,
        cancel: threading.Event | None = None,
    ) -> SynthesisResult:
        import json

        text = _check_text(text)
        reason = self.available()
        if reason:
            raise SpeechError(f"ElevenLabs is not configured: {reason}")
        if cancel is not None and cancel.is_set():
            raise SpeechError("Speech cancelled before it started.")

        url = f"{self.API_BASE}/text-to-speech/{self.voice_id.strip()}"
        headers = {
            "xi-api-key": self._api_key.strip(),
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        body = json.dumps({"text": text, "model_id": self.model_id}).encode("utf-8")
        secrets = [self._api_key.strip()]
        try:
            audio = self._post(url, headers, body, self.timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - sanitized before it leaves here
            message = _redact(str(exc), secrets)[:200]
            raise SpeechError(f"ElevenLabs request failed: {message}") from None
        if cancel is not None and cancel.is_set():
            raise SpeechError("Speech cancelled.")
        if not audio:
            raise SpeechError("ElevenLabs returned no audio.")
        return SynthesisResult(audio=audio, format="mp3", backend=self.name, chars=len(text))


class SpeechEngine:
    """Ordered backend chain with local-first defaults.

    ``JARVIS_TTS_BACKEND`` selects the order: ``local`` (default),
    ``elevenlabs`` (cloud first, local as safety net when the key is missing
    is NOT automatic - an explicit cloud choice stays explicit, so the chain
    is exactly what was asked for), or a comma list such as
    ``elevenlabs,local``.
    """

    def __init__(self, backends: Sequence[TTSBackend]) -> None:
        if not backends:
            raise ValueError("SpeechEngine needs at least one backend.")
        self._backends = list(backends)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SpeechEngine:
        env = os.environ if env is None else env
        spec = env.get("JARVIS_TTS_BACKEND", "local").strip().lower() or "local"
        backends: list[TTSBackend] = []
        for name in [part.strip() for part in spec.split(",") if part.strip()]:
            if name == "local":
                backends.append(LocalTTSBackend())
            elif name == "elevenlabs":
                backends.append(ElevenLabsBackend(env=env))
            else:
                raise ValueError(
                    f"Unknown TTS backend '{name}' in JARVIS_TTS_BACKEND "
                    "(expected local and/or elevenlabs)."
                )
        if not backends:
            backends.append(LocalTTSBackend())
        return cls(backends)

    @property
    def backends(self) -> list[TTSBackend]:
        return list(self._backends)

    def status(self) -> list[dict[str, Any]]:
        """Per-backend availability for `jarvis doctor` - never includes keys."""
        return [
            {"backend": b.name, "available": not b.available(), "reason": b.available()}
            for b in self._backends
        ]

    def synthesize(
        self,
        text: str,
        *,
        cancel: threading.Event | None = None,
    ) -> SynthesisResult:
        """Try each backend in order; return the first successful synthesis."""
        text = _check_text(text)
        reasons: list[str] = []
        for backend in self._backends:
            unavailable = backend.available()
            if unavailable:
                reasons.append(f"{backend.name}: {unavailable}")
                continue
            try:
                return backend.synthesize(text, cancel=cancel)
            except SpeechError as exc:
                reasons.append(f"{backend.name}: {exc}")
        raise SpeechError("No speech backend could speak. " + "; ".join(reasons))
