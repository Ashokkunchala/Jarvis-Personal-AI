"""`jarvis doctor` - one health check for the whole local stack.

Answers "will JARVIS actually work on this machine right now?" in a single
pass: Python version, model configuration, realtime voice packages,
microphone/speaker, the speech backends (local and optional ElevenLabs),
Android bridge, local storage, document memory and the briefing scheduler.

Every check is safe to run anywhere: no network calls, no audio is played or
recorded, and secrets are only ever reported as present/absent - values are
never printed. Critical failures make the command exit non-zero so scripts
and installers can gate on it.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Check", "DoctorReport", "run_checks"]

MIN_PYTHON = (3, 11)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    critical: bool = False  # critical failures make the overall report fail


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.critical)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "critical": c.critical}
                for c in self.checks
            ],
        }


def _module_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _check_python() -> Check:
    version = sys.version_info
    ok = version >= MIN_PYTHON
    detail = f"Python {version.major}.{version.minor}.{version.micro}"
    if not ok:
        detail += f" (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)"
    return Check("python", ok, detail, critical=True)


def _check_config() -> list[Check]:
    checks: list[Check] = []
    try:
        from jarvis.config.settings import config

        key = (config.gemini_api_key or "").strip()
        checks.append(Check(
            "model-key",
            bool(key),
            "GEMINI_API_KEY is set" if key else "GEMINI_API_KEY is not set - add it to .env",
            critical=True,
        ))
        checks.append(Check(
            "model",
            True,
            f"chat model {config.gemini_model}; live model {config.gemini_live_model}"
            if config.use_gemini_live else f"chat model {config.gemini_model}; Gemini Live off",
        ))
    except Exception as exc:  # noqa: BLE001 - config must never crash doctor
        checks.append(Check("model-key", False, f"config failed to load: {exc}", critical=True))
    return checks


def _check_voice_packages() -> Check:
    try:
        from jarvis.terminal.voice import missing_voice_packages

        missing = missing_voice_packages()
    except Exception as exc:  # noqa: BLE001
        return Check("voice-packages", False, f"could not inspect voice stack: {exc}")
    if missing:
        return Check(
            "voice-packages",
            False,
            "missing for realtime voice: " + ", ".join(missing),
        )
    return Check("voice-packages", True, "realtime voice packages installed")


def _check_audio_devices() -> Check:
    if not _module_present("sounddevice"):
        return Check("audio-devices", False, "sounddevice not installed - mic/speaker unchecked")
    try:
        import sounddevice as sd  # noqa: PLC0415

        devices = sd.query_devices()
        inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
        outputs = [d for d in devices if d.get("max_output_channels", 0) > 0]
        if not inputs:
            return Check("audio-devices", False, "no microphone found")
        if not outputs:
            return Check("audio-devices", False, "no speaker/output device found")
        return Check(
            "audio-devices",
            True,
            f"{len(inputs)} input(s), {len(outputs)} output(s)",
        )
    except Exception as exc:  # noqa: BLE001 - audio hosts fail in odd ways
        return Check("audio-devices", False, f"audio query failed: {exc}")


def _check_speech() -> list[Check]:
    checks: list[Check] = []
    try:
        from jarvis.core.voice.speech import ElevenLabsBackend, SpeechEngine

        engine = SpeechEngine.from_env()
        for status in engine.status():
            name = f"speech-{status['backend']}"
            if status["available"]:
                checks.append(Check(name, True, f"{status['backend']} backend ready"))
            else:
                # The local backend is the default, so its absence is critical;
                # a missing optional cloud key is only a warning.
                critical = status["backend"] == "local"
                checks.append(Check(name, not critical, status["reason"], critical=critical))
        eleven = ElevenLabsBackend()
        checks.append(Check(
            "elevenlabs-key",
            True,
            "ELEVENLABS_API_KEY set (value hidden)" if eleven.configured
            else "ELEVENLABS_API_KEY/VOICE_ID not set - cloud voice off (local voice still works)",
        ))
    except Exception as exc:  # noqa: BLE001
        checks.append(Check("speech", False, f"speech engine check failed: {exc}", critical=True))
    return checks


def _check_android() -> Check:
    adb = shutil.which("adb")
    if not adb:
        return Check("android", True, "adb not on PATH - Android control off (laptop features unaffected)")
    try:
        proc = subprocess.run(
            [adb, "devices"], capture_output=True, text=True, timeout=5, check=False,
        )
        lines = [ln for ln in proc.stdout.splitlines()[1:] if ln.strip()]
        devices = [ln for ln in lines if "\tdevice" in ln]
        if devices:
            return Check("android", True, f"{len(devices)} device(s) connected")
        return Check("android", True, "adb present, no device connected right now")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("android", True, f"adb present but query failed: {exc}")


def _check_storage() -> list[Check]:
    checks: list[Check] = []
    home = Path.home() / ".jarvis"
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = tempfile.NamedTemporaryFile(dir=home, prefix=".doctor-", delete=True)
        probe.close()
        checks.append(Check("storage", True, f"{home} is writable", critical=True))
    except OSError as exc:
        checks.append(Check("storage", False, f"{home} is not writable: {exc}", critical=True))

    try:
        from jarvis.personal import PersonalStore

        store = PersonalStore()
        checks.append(Check("personal-db", True, f"notes/expenses/habits database ok ({store.path})"))
    except Exception as exc:  # noqa: BLE001
        checks.append(Check("personal-db", False, f"personal store failed: {exc}", critical=True))
    return checks


def _check_doc_memory() -> Check:
    try:
        from jarvis.memory.doc_memory import DocMemory

        memory = DocMemory()
        status = memory.status()
        return Check(
            "doc-memory",
            True,
            f"ready - {status['roots']} folder(s) indexed, {status['indexed_docs']} docs",
        )
    except RuntimeError as exc:  # FTS5 missing
        return Check("doc-memory", False, str(exc))
    except Exception as exc:  # noqa: BLE001
        return Check("doc-memory", False, f"document memory failed: {exc}")


def _check_scheduler() -> Check:
    try:
        from jarvis.briefing_schedule import BriefingScheduler

        scheduler = BriefingScheduler()
        status = scheduler.status()
        if not status["jobs"]:
            return Check("scheduler", True, "no briefing schedule set - run: jarvis briefing schedule")
        next_runs = "; ".join(status["next"]) if status["next"] else "all schedules disabled"
        return Check("scheduler", True, f"{len(status['jobs'])} schedule(s); {next_runs}")
    except Exception as exc:  # noqa: BLE001
        return Check("scheduler", False, f"briefing scheduler failed: {exc}")


def run_checks() -> DoctorReport:
    """Run every health check. Never raises; failures are reported as checks."""
    report = DoctorReport()
    report.checks.append(_check_python())
    report.checks.extend(_check_config())
    report.checks.append(_check_voice_packages())
    report.checks.append(_check_audio_devices())
    report.checks.extend(_check_speech())
    report.checks.append(_check_android())
    report.checks.extend(_check_storage())
    report.checks.append(_check_doc_memory())
    report.checks.append(_check_scheduler())
    return report


def _redact_environment(text: str) -> str:
    """Defense in depth: strip any known secret value from rendered output."""
    for var in ("ELEVENLABS_API_KEY", "GEMINI_API_KEY"):
        value = os.environ.get(var, "").strip()
        if value:
            text = text.replace(value, "<redacted>")
    return text
