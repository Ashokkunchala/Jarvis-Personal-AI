# JARVIS Personal AI

A multi-provider personal assistant prototype for Indian English and Telugu, supporting Gemini, OpenRouter, and Groq for text chat. The intended personality is adaptive: friendly and witty for everyday chat, calm for serious topics, and energetic for coaching.

> **Status: multi-component prototype, not a complete JARVIS yet.** This repository contains a local Gemini chat UI, authenticated SQLite APIs for explicit memories/reminders/workout logs, a first live web-search adapter, a restricted Windows helper, and a native Android starter screen. An earlier Android revision built successfully in GitHub Actions; the latest voice/language changes are awaiting their CI build and a physical-device end-to-end test. Public cloud deployment is not safe yet.

## One-file Windows installer

Download [INSTALL-JARVIS.ps1](INSTALL-JARVIS.ps1) from this branch, open PowerShell in its download folder, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\INSTALL-JARVIS.ps1
```

The installer downloads this branch, installs Python (using winget if needed), installs dependencies, asks for your Gemini key (OpenRouter/Groq are optional), creates local secrets, and registers a Windows sign-in task. After sign-in it starts the local backend, opens the browser UI, and opens the terminal assistant. It does not run as administrator or expose the server beyond localhost.

In the browser, enter your generated `JARVIS_API_TOKEN` from the installed `.env` file once. If you choose **Remember device token on this browser**, it is stored in browser local storage for convenience; this is less secure than session-only entry. Then click **Start Live Voice** and grant microphone permission. Voice is not silently activated on boot; the explicit start control is intentional.

**Android is a separate APK**, not installable by the Windows script. Get the debug APK from the successful [Android build artifact](https://github.com/Ashokkunchala/Jarvis-Personal-AI/actions). Install it on Android and configure your private HTTPS backend. Android 14 restricts starting microphone foreground services from boot, so the phone app cannot safely promise automatic always-listening voice after reboot; launch the app and start voice explicitly.

## Start here

### Terminal clients

There are two independent terminal clients. The default one needs **only** `GEMINI_API_KEY` — it drives the same local tool-calling brain the browser uses, with no backend process.

```powershell
# Realtime full-screen UI: streaming text, live tool log, confirmation dialogs.
.\.venv\Scripts\python.exe jarvis_cli.py tui

# One-shot or interactive chat in the current pane (streams as it thinks).
.\.venv\Scripts\python.exe jarvis_cli.py ask "what's my battery level?"

# Direct device control, no model required.
.\.venv\Scripts\python.exe jarvis_cli.py laptop status
.\.venv\Scripts\python.exe jarvis_cli.py android devices

# List the 135 registered tools by category.
.\.venv\Scripts\python.exe jarvis_cli.py tools
```

`jarvis_cli.py chat` is the **backend** client: it requires `JARVIS_API_TOKEN` and a running `jarvis_cli.py serve`, and streams from the authenticated HTTP API. Use it when you want the browser's memory/reminder/coaching context in the terminal. Both clients read `JARVIS_API_URL` if set and only send a token to HTTPS endpoints or localhost.

- [Windows setup](docs/SETUP-WINDOWS.md)
- [Installation and live terminal microphone guide](docs/INSTALLATION-AND-LIVE-TERMINAL.md)
- [Features and known limitations](docs/FEATURES.md)
- [JARVIS Command Center dashboard](app/static/dashboard.html) — responsive live performance dashboard
- [Milestone plan](docs/NEXT-MILESTONES.md)
- [Personal data APIs and AI coaching](docs/PERSONAL-DATA-API.md)
- [Live web research](docs/WEB-RESEARCH.md)
- [Windows reminder notifications](docs/REMINDER-NOTIFICATIONS.md)
- [Android starter](android/README.md)
- [Windows companion agent](windows_agent/README.md)
- [Security](docs/SECURITY.md)
- [Deployment plan](docs/DEPLOYMENT.md)
- [Development guide](docs/DEVELOPMENT.md)

## Implemented in code

### Personal-assistant core (`jarvis/`)

- **Local Gemini tool-calling brain** (`jarvis/core/brain.py`): streams replies, dispatches to registered tools, retries with a model fallback chain, and enforces per-tool confirmation. Shared by the TUI and the WebSocket endpoint.
- **Tool registry** (`jarvis/tools/`): 135 typed tools across 20 categories (system, apps, audio, window, power, screen, input, files, process, clipboard, network, shell, notify, and six `android_*` groups) with JSON schemas for Gemini function-calling and schema validation.
- **Laptop control** (`jarvis/control/`): apps, audio, windows, power, screen capture, input, files, processes, clipboard, network, guarded shell, notifications, hardware info.
- **Android control over ADB** (`jarvis/android_bridge/`): device state, apps, input, screen, files, SMS/calls/contacts, notifications, settings, location, wireless debugging, plus automatic ADB provisioning (`jarvis android setup`).
- **Realtime terminal UI** (`jarvis/terminal/jarvis_tui.py`): streaming text, live tool log, status bar, confirmation dialogs, slash commands.
- **Realtime HTTP/WebSocket API** (`app/ws.py`): JSON protocol carrying the same streamed events plus interactive tool confirmation.

### Backend and clients

- FastAPI chat backend with Gemini, OpenRouter, and Groq text providers; choose a preferred provider or use automatic fallback. Provider keys stay on the server. Real-time audio remains on Gemini Live.
- Live authenticated terminal chat (`python jarvis_cli.py chat`) against the HTTP backend, plus a realtime full-screen Textual UI (`python jarvis_cli.py tui`) that talks to the local brain directly. Session context is held in process memory.
- Adaptive personality instructions and English/Telugu response preference.
- Browser speech input (only when manually activated and supported) and browser text-to-speech.
- Optional browser-local conversation history and local checklist.
- SQLite-backed, token-protected APIs to create/list/edit/delete explicit memories, export personal data, create/list/complete reminders, and log/delete workouts.
- Token-protected AI workout and general nutrition suggestion endpoints.
- Token-protected user-triggered web search with source links.
- Experimental Windows agent integrated with the local dashboard: authenticated status and user-confirmed HTTPS URL opening for allow-listed domains.
- Optional Windows toast reminder worker that polls the local backend while its process is running.
- Native Kotlin/Jetpack Compose Android client with HTTPS health check, Android Keystore token storage, authenticated chat, tap-to-speak voice input, spoken replies, and English/Telugu/adaptive language selection. Personal-data screens and device pairing/revocation remain pending.
- Python API tests and GitHub Actions test/build workflows.

## Major gaps

- The Android app can send authenticated chat requests over HTTPS, supports tap-to-speak/spoken replies, and encrypts the token with Android Keystore. It is not yet integrated with the personal-data APIs or per-device pairing/revocation.
- The Windows companion agent (`windows_agent/`) remains restricted to allow-listed HTTPS URL opening. The Python laptop-control suite (`jarvis/control/`) is broader by design and guards destructive paths, critical processes, and blocked shell patterns.
- Android control requires a physical device with USB debugging (or wireless debugging); ADB is provisioned on demand, and most actions have only been exercised in degraded "no device connected" mode here.
- Shell execution is allow/confirm/deny classified, not sandboxed; the model cannot run blocked patterns, but a confirmed command runs with your full user rights.
- Reminder notification delivery is an experimental Windows polling worker, not a reliable alarm service. There is no Android push notification or recurrence yet.
- Memories are explicitly entered via API; there is no consent-driven extraction or review UI.
- Web research is a small HTML search adapter, not full browser automation or authenticated website workflows.
- Workout/nutrition endpoints give general AI suggestions; no wearable integration, progress charts, or medical service exists.
- No secure cloud deployment, TLS termination, per-device credentials/revocation, or complete authentication for every route.

## Quick start — Windows PowerShell

Requirements: Python 3.11+ and a Gemini API key from [Google AI Studio](https://aistudio.google.com/).

```powershell
git clone https://github.com/Ashokkunchala/Jarvis-Personal-AI.git
cd Jarvis-Personal-AI
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup-windows.ps1
notepad .env
```

In the local `.env`, set `GEMINI_API_KEY` to your real key and replace the example `JARVIS_API_TOKEN` with a random secret generated using:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Keep `HOST=127.0.0.1`. Save `.env`, then start:

```powershell
.\scripts\start-windows.ps1
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Open the responsive [JARVIS Command Center dashboard](http://127.0.0.1:8000/dashboard) for live authenticated CPU/RAM/disk/battery telemetry and charts (enter your local device token). API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

The local assistant (TUI, `ask`, laptop/android control) works without starting the backend — only `GEMINI_API_KEY` is required:

```powershell
.\.venv\Scripts\python.exe jarvis_cli.py tui      # realtime streaming terminal UI
.\.venv\Scripts\python.exe jarvis_cli.py ask "set volume to 30"
.\.venv\Scripts\python.exe jarvis_cli.py laptop status
```

`jarvis_cli.py serve` boots the HTTP + WebSocket backend (`/`, `/ws`, personal-data APIs).

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## API overview

- `GET /health` — health check.
- `GET /` — browser chat UI.
- `POST /api/chat` — Gemini chat returning JSON; requires the configured bearer token.
- `POST /api/chat/stream` — Gemini chat streamed as server-sent events for the browser; uses the same bearer token. Keep the service local until production security is completed.
- `WS /ws?token=…` — realtime brain: streamed text, tool lifecycle events, and interactive tool confirmation over JSON frames (see `app/ws.py` for the protocol).
- Token-protected APIs: `/api/memories`, `/api/reminders`, `/api/workouts`, `/api/research`, `/api/coach/workout`, and `/api/coach/nutrition`.
- `GET /docs` — local API reference.

## Security rules

- Never expose this server directly to the public internet. Do not bind to `0.0.0.0`, port-forward it, or use a public tunnel.
- Keep real API keys and tokens in `.env`, never in source control, Android resources, screenshots, or logs.
- The protected APIs reject missing/invalid bearer tokens; a shared token is not production device pairing.
- Sensitive OS or browser actions need user confirmation and explicit allow-lists. Model-generated shell commands are classified (`safe` / `confirm` / `blocked`); blocked patterns never run, and every risky tool prompts before executing. Nothing runs on the model's say-so alone.
- Fitness and nutrition outputs are general information, not medical advice.
- Check Google model availability, quotas, and pricing for your account; do not assume every request is free.

See [docs/NEXT-MILESTONES.md](docs/NEXT-MILESTONES.md) for the staged acceptance criteria.
