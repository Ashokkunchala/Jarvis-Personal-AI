# Terminal UI on Windows

JARVIS detects when your terminal cannot draw its Unicode box art and falls
back to plain ASCII automatically, so the default Windows console works out
of the box - no tofu squares.

## Voice-first controls

JARVIS starts in voice mode: it listens for one utterance, answers, then
listens again.

| Key / button | Action |
| --- | --- |
| MIC | capture one utterance (when the loop is paused) |
| STOP | pause the voice loop and stop the current action |
| TYPE or F2 | reveal the input box and type instead |
| `/voice` / `/voice off` | resume / pause the listening loop |

Set `JARVIS_TUI_VOICE_FIRST=0` (or run with `--no-voice`) to start
typed-first. Set `JARVIS_TUI_ASCII=1` or `=0` to force a rendering mode.

Speech recognition uses the SpeechRecognition package's online service; it
is not an offline wake word. The microphone only records when the status bar
shows LISTENING.

## Optional polish: full cinematic glyphs

For the full box art (rounded borders, block bars) use
[Windows Terminal](https://aka.ms/terminal) with a
[Nerd Font](https://www.nerdfonts.com/) such as CaskaydiaCove NF, selected in
Settings -> Profiles -> Appearance -> Font. JARVIS detects the UTF-8 code
page and switches to Unicode automatically. This is cosmetic only.
