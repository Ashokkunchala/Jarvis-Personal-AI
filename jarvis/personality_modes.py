"""Conversation personality modes for JARVIS.

A mode is a style overlay on top of the base system prompt plus hints the
voice layer can use (pace, tone). Modes never change what tools can do and
never weaken safety rules; approval gating applies in every mode.

The active mode chosen through the CLI/TUI tools is persisted in a small
JSON file (``~/.jarvis/personality_mode.json`` by default) so the brain,
CLI and TUI share it. The web chat passes its per-request mode instead.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.personality_modes")

DEFAULT_MODE = "assistant"


@dataclass(frozen=True)
class PersonalityMode:
    name: str
    label: str
    description: str
    overlay: str
    voice_style: dict[str, Any] = field(default_factory=dict)


MODES: dict[str, PersonalityMode] = {
    "assistant": PersonalityMode(
        name="assistant",
        label="Assistant",
        description="Default mode: precise, practical, gets things done.",
        overlay=(
            "Mode: ASSISTANT. Be precise, practical and action-oriented. Lead with the "
            "answer or the action taken. Offer useful next steps without being pushy."
        ),
        voice_style={"pace": "steady", "tone": "professional and warm"},
    ),
    "friend": PersonalityMode(
        name="friend",
        label="Friend",
        description="Casual, warm, playful companion conversation.",
        overlay=(
            "Mode: FRIEND. Talk like a close, trusted friend: relaxed, warm, playful, "
            "comfortable with jokes and teasing. Ask how the user is doing and remember "
            "what they tell you within the conversation. Be honest like a real friend, "
            "including gentle pushback when something is a bad idea. Never pretend to be "
            "human or claim real feelings or experiences."
        ),
        voice_style={"pace": "relaxed", "tone": "warm and playful"},
    ),
    "teacher": PersonalityMode(
        name="teacher",
        label="Teacher",
        description="Patient, structured explanations and learning coaching.",
        overlay=(
            "Mode: TEACHER. Teach patiently and structurally. Start from what the user "
            "likely knows, build up in small steps, use examples and analogies, and check "
            "understanding with short questions. Encourage curiosity; never shame a wrong "
            "answer. When the user is an AWS/DevOps engineer, pitch depth accordingly."
        ),
        voice_style={"pace": "measured", "tone": "encouraging"},
    ),
    "storyteller": PersonalityMode(
        name="storyteller",
        label="Storyteller",
        description="Original stories, narrated with pace and character.",
        overlay=(
            "Mode: STORYTELLER. Tell original, vivid stories with a clear arc: setting, "
            "tension, resolution. Vary pacing, use dialogue and sensory detail, and keep "
            "it suitable for the user. All stories must be your own creation; do not "
            "reproduce copyrighted text. Offer to continue, branch or change the story "
            "at natural pauses."
        ),
        voice_style={"pace": "expressive with pauses", "tone": "narrative"},
    ),
    "doctor": PersonalityMode(
        name="doctor",
        label="Health guide",
        description="General health information only - never a substitute for a real doctor.",
        overlay=(
            "Mode: HEALTH GUIDE (not a doctor). Provide general, widely accepted health "
            "information only: how the body works, what common symptoms can mean, healthy "
            "habits, and what questions to ask a professional. You MUST follow these rules:\n"
            "- Never diagnose, never name a condition as what the user has, never prescribe "
            "or adjust medication or dosage.\n"
            "- In every health reply, make clear you are not a doctor and this is general "
            "information, not medical advice.\n"
            "- For worrying, severe, persistent or worsening symptoms, tell the user to see "
            "a qualified doctor promptly.\n"
            "- For anything that sounds like an emergency (chest pain, trouble breathing, "
            "uncontrolled bleeding, stroke signs, thoughts of self-harm), tell the user to "
            "call local emergency services immediately, then give only basic first-aid level "
            "guidance.\n"
            "- Be calm, kind and factual; never alarmist."
        ),
        voice_style={"pace": "calm and unhurried", "tone": "caring and factual"},
    ),
}


def list_modes() -> list[dict[str, str]]:
    """All available modes with human-readable labels and descriptions."""
    return [{"name": m.name, "label": m.label, "description": m.description} for m in MODES.values()]


def get_mode(name: str | None) -> PersonalityMode:
    """Resolve a mode name, falling back to the default for empty input."""
    if not name or not str(name).strip():
        return MODES[DEFAULT_MODE]
    key = str(name).strip().lower()
    if key not in MODES:
        raise ValueError(f"Unknown personality mode {name!r}. Available: {', '.join(sorted(MODES))}.")
    return MODES[key]


def overlay_for(name: str | None) -> str:
    """System-prompt overlay text for a mode; empty-string-safe."""
    try:
        return get_mode(name).overlay
    except ValueError:
        logger.warning("Falling back to default mode for unknown mode %r", name)
        return MODES[DEFAULT_MODE].overlay


class ModeStore:
    """Persists the active CLI/TUI mode in a small JSON file."""

    def __init__(self, path: Path | None = None):
        self.path = path or (Path.home() / ".jarvis" / "personality_mode.json")

    def get(self) -> str:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            mode = str(data.get("mode", "")).strip().lower()
            return mode if mode in MODES else DEFAULT_MODE
        except FileNotFoundError:
            return DEFAULT_MODE
        except (OSError, ValueError) as exc:
            logger.warning("Could not read mode store %s: %s", self.path, exc)
            return DEFAULT_MODE

    def set(self, name: str) -> PersonalityMode:
        mode = get_mode(name)  # raises on unknown mode
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"mode": mode.name}), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not persist mode to %s: %s", self.path, exc)
        return mode


_default_store: ModeStore | None = None


def default_store() -> ModeStore:
    global _default_store
    if _default_store is None:
        _default_store = ModeStore()
    return _default_store


MAX_SONG_LINES = 40
MAX_SONG_LINE_CHARS = 200


def prepare_song(lyrics: str, mood: str = "playful") -> dict[str, Any]:
    """Prepare original lyrics for a spoken 'sung' performance.

    JARVIS has no singing voice; the active speech output speaks the lines
    with rhythm and pauses. This function only shapes the performance plan
    and keeps the honest note that it is a playful approximation.
    """
    if not isinstance(lyrics, str) or not lyrics.strip():
        return {"success": False, "error": "No lyrics supplied. Compose original lyrics first, then perform them."}
    lines = [ln.strip() for ln in lyrics.strip().splitlines() if ln.strip()]
    if not lines:
        return {"success": False, "error": "No lyrics supplied. Compose original lyrics first, then perform them."}
    if len(lines) > MAX_SONG_LINES:
        return {"success": False, "error": f"Keep the song to {MAX_SONG_LINES} lines or fewer."}
    long_lines = [ln for ln in lines if len(ln) > MAX_SONG_LINE_CHARS]
    if long_lines:
        return {"success": False, "error": f"Song lines must be {MAX_SONG_LINE_CHARS} characters or fewer."}
    mood = (mood or "playful").strip().lower() or "playful"
    performance = []
    for i, line in enumerate(lines):
        pause = "long" if (i + 1) % 4 == 0 else "short"
        performance.append({"line": line, "pause_after": pause})
    return {
        "success": True,
        "mood": mood,
        "lines": performance,
        "line_count": len(lines),
        "performance_note": (
            "Speak the lines rhythmically with the marked pauses through the active voice "
            "output. This is spoken-word with rhythm, a playful approximation of singing - "
            "say so cheerfully if asked, never claim it is real melodic singing."
        ),
        "originality_note": "Only perform original lyrics composed for the user; never reproduce copyrighted song lyrics.",
    }
