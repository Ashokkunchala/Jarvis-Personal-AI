# JARVIS - Iron Man Style AI Assistant

The ultimate real-time AI assistant with full system control, terminal UI, voice interaction, and Android device management.

## Features

### ??? Real-Time Voice
- **Always-on listening** with wake word "Hey JARVIS"
- **Voice Activity Detection** (VAD) for natural conversations
- **Gemini Live API** for bidirectional audio streaming
- **Low-latency responses** with barge-in support
- **Natural conversation flow**

### ?? Terminal & UI
- **Beautiful TUI** built with Textual
- **CLI interface** with Rich formatting
- **System tray support** (coming soon)
- **HUD Overlay** - Iron Man style circular indicator
- **Multi-mode**: Voice, Text, Hybrid

### ??? Full System Control
- **Application control** - Open/close any app
- **Window management** - Focus, minimize, maximize, close
- **Volume control** - Set, mute, unmute
- **Mouse & Keyboard** - Automate anything
- **Screenshots** - Capture screen on demand
- **Power control** - Shutdown, restart, lock
- **Process management** - View and kill processes

### ?? Android Control
- **ADB Integration** - Full control via ADB
- **App management** - Install, launch, uninstall
- **Touch control** - Tap, swipe, type
- **Navigation** - Home, back, recent
- **Screenshots & Recording** - Capture Android screen
- **File transfer** - Push/pull files
- **Shell access** - Run commands

### ?? Intelligence
- **Vector memory** - Long-term recall with ChromaDB
- **Context awareness** - Remembers everything
- **Tool use** - Can execute actions autonomously
- **Proactive** - Suggests and helps
- **Natural language** - Just speak naturally

## Quick Start

### Installation
`ash
# Run installer
INSTALL_JARVIS.bat
`

### Usage

#### CLI Commands
`ash
# Start real-time voice mode
python jarvis_cli.py start

# Launch Terminal UI
python jarvis_cli.py tui

# System control
python jarvis_cli.py open chrome
python jarvis_cli.py volume 50
python jarvis_cli.py screenshot
python jarvis_cli.py lock

# Android control
python jarvis_cli.py android
python jarvis_cli.py android-screenshot

# Status
python jarvis_cli.py status
`

#### Voice Commands (Examples)
- "Hey JARVIS, open Chrome"
- "Hey JARVIS, set volume to 70"
- "Hey JARVIS, take a screenshot"
- "Hey JARVIS, what's the time?"
- "Hey JARVIS, lock the computer"
- "Hey JARVIS, show Android screenshot"

## Configuration

Edit .env file:
`env
GEMINI_API_KEY=your_key_here
USE_GEMINI_LIVE=true
WAKEWORD_ENABLED=true
SYSTEM_CONTROL_ENABLED=true
ANDROID_BRIDGE_ENABLED=true
`

## Architecture

`
JARVIS
+-- Voice Layer (Wakeword + VAD + Gemini Live)
+-- Terminal UI (Textual)
+-- System Controller (Full Windows Control)
+-- Android Bridge (ADB)
+-- Tool Registry (Extensible)
+-- Vector Memory (ChromaDB)
+-- Agent Core (Reasoning + Planning)
`

## Requirements

- Windows 10/11
- Python 3.11+
- Microphone
- Speakers
- Gemini API key with Live access
- Android device with USB debugging (optional)

## Tips

- Use in a quiet environment for better wake word detection
- For Android, enable USB debugging in Developer Options
- Grant necessary permissions for system control
- Run as administrator for some advanced features

**Built for the Iron Man experience. Just say "Hey JARVIS" and you're in control.**
