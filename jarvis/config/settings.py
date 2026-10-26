import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class JarvisConfig:
    # API
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    use_gemini_live: bool = os.getenv("USE_GEMINI_LIVE", "true").lower() == "true"
    
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
    allowed_apps: List[str] = field(default_factory=lambda: [
        "chrome.exe", "msedge.exe", "firefox.exe", "notepad.exe", 
        "code.exe", "devenv.exe", "explorer.exe", "calc.exe"
    ])
    allowed_domains: List[str] = field(default_factory=lambda: [
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
