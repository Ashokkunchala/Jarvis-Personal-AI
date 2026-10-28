import os
from dataclasses import dataclass, field
from pathlib import Path

# Load the repo .env before reading environment-backed fields below.
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parents[2] / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:  # pragma: no cover - dotenv is optional for library use
    pass


@dataclass
class JarvisConfig:
    # API
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    use_gemini_live: bool = os.getenv("USE_GEMINI_LIVE", "true").lower() == "true"

    # Realtime voice (Gemini Live)
    gemini_live_model: str = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    gemini_live_voice: str = os.getenv("GEMINI_LIVE_VOICE", "Aoede")
    live_output_sample_rate: int = int(os.getenv("GEMINI_LIVE_OUTPUT_RATE", "24000"))
    # Seconds of silence after the last exchange before JARVIS returns to sleep.
    awake_timeout_seconds: float = float(os.getenv("JARVIS_AWAKE_TIMEOUT", "20"))
    # Local voice tools (open apps, volume, screenshot, ...) exposed to the model.
    voice_tools_enabled: bool = os.getenv("JARVIS_VOICE_TOOLS", "true").lower() == "true"


    # Wake word
    wakeword_enabled: bool = True
    wakeword_model: str = "jarvis"  # or path to custom model
    wakeword_threshold: float = 0.5
    wakeword_models_dir: Path = Path("jarvis/models/wakeword")

    # VAD
    vad_enabled: bool = True
    vad_aggressiveness: int = 2  # 0-3
    vad_frame_duration_ms: int = 30
    vad_padding_duration_ms: int = 300

    # Audio
    audio_input_device: int = None
    audio_output_device: int = None
    sample_rate: int = 16000
    channels: int = 1
    # 30 ms at 16 kHz is 480 samples, which WebRTC VAD accepts.
    chunk_size: int = 480

    # TTS
    tts_engine: str = "browser"  # browser, piper, gtts
    tts_voice: str = "en-US-AriaNeural"

    # STT
    stt_engine: str = "gemini"  # gemini, whisper, vosk

    # System control
    system_control_enabled: bool = True
    require_confirmation: bool = True
    allowed_apps: list[str] = field(default_factory=lambda: [
        "chrome.exe", "msedge.exe", "firefox.exe", "notepad.exe",
        "code.exe", "devenv.exe", "explorer.exe", "calc.exe"
    ])
    allowed_domains: list[str] = field(default_factory=lambda: [
        "google.com", "github.com", "stackoverflow.com", "youtube.com"
    ])

    # Memory
    memory_enabled: bool = True
    memory_path: Path = Path("data/memory/chroma")
    embedding_model: str = "all-MiniLM-L6-v2"

    # Proactivity
    proactivity_enabled: bool = True
    context_monitoring: bool = True
    proactive_suggestions: bool = True

    # UI
    overlay_enabled: bool = True
    overlay_always_on_top: bool = True
    hotkey_summon: str = "win+shift+j"

    # Privacy
    local_only: bool = False  # if True, avoid cloud where possible
    log_audio: bool = False


config = JarvisConfig()
