# Floating robot on Windows

JARVIS detects when your terminal cannot draw its Unicode box art and falls
back to plain ASCII automatically, so the default Windows console works out of
the box - no tofu squares.

## Start

`jarvis` with no arguments launches the floating robot (the default command):

```powershell
.\.venv\Scripts\python.exe jarvis_cli.py
```

`jarvis robot` is the explicit form and `jarvis tui` remains an alias. Both
`robot` and `tui` accept `--call` and `--no-laptop`; `robot` also accepts
`--frames`, `--fps`, `--ascii`, `--unicode`, `--no-color` and `--dump`.

To open the robot automatically when you sign in:

```powershell
.\scripts\install-jarvis-startup.ps1          # robot only; microphone closed
.\scripts\install-jarvis-startup.ps1 -Call    # dial a call at sign-in
.\scripts\install-jarvis-startup.ps1 -Remove  # uninstall
```

The shortcut is `JARVIS.lnk` in your per-user Startup folder and runs
`scripts\start-jarvis-terminal.ps1`; no backend or browser is started.

## Keys

| Key | Action |
| --- | --- |
| `q`, `Esc`, `Ctrl+C` | quit |
| `space` | pause / resume the float |
| `v` | start / end a live voice call |
| `a` | toggle ASCII art |
| `h` | toggle the footer hints |
| `+` / `-` (or `=` / `_`) | faster / slower |

## Laptop gauge

The robot draws a cached CPU / RAM / battery / free-disk line using `psutil`.
Hide it with `--no-laptop`; if `psutil` is not installed the line is simply
omitted. Gauges refresh at most every two seconds and never block a frame.

## Voice call

Press `v` in the robot, or run:

```powershell
.\.venv\Scripts\python.exe jarvis_cli.py call
```

This is a normal two-way Gemini Live call: speak immediately, no "Hey JARVIS"
wake word, barge-in and laptop tools work the same as `jarvis start`. The call
runs in a background thread so the robot keeps animating, and the speech line
shows `You:` / `JARVIS:` transcripts.

It needs `GEMINI_API_KEY` and the realtime audio stack
(`sounddevice`, `webrtcvad`, `openwakeword`, `numpy`, `scipy`,
`google-genai`). If a key or package is missing the robot shows `VOICE ERR`
with the reason and does not open the microphone. The animation and gauge
themselves are local-only and never call a model or the network.

## Rendering

For the full box art (rounded borders) use
[Windows Terminal](https://aka.ms/terminal) with a
[Nerd Font](https://www.nerdfonts.com/) such as CaskaydiaCove NF, selected in
Settings -> Profiles -> Appearance -> Font. JARVIS detects the UTF-8 code
page and switches to Unicode automatically.

- `--ascii` / `--unicode` force a rendering mode (`JARVIS_ROBOT_ASCII=1`
  also forces ASCII).
- `--no-color`, `JARVIS_ROBOT_NO_COLOR=1` or `NO_COLOR` disable colour.
- `--frames N --dump` prints frames without redrawing, for logs and
  screenshots.
