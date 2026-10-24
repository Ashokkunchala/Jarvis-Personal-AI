# JARVIS Personal AI

A Gemini-powered personal assistant prototype for Indian English and Telugu. The intended personality is adaptive: friendly and witty for everyday chat, calm for serious topics, and energetic for coaching.

> **Status: multi-component prototype, not a complete JARVIS yet.** This repository contains a local Gemini chat UI, authenticated SQLite APIs for explicit memories/reminders/workout logs, a first live web-search adapter, a restricted Windows helper, and a native Android starter screen. The Android app now has an initial HTTPS chat client, but needs a successful Android build and end-to-end device test. Public cloud deployment is not safe yet.

## Start here

- [Windows setup](docs/SETUP-WINDOWS.md)
- [Features and known limitations](docs/FEATURES.md)
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

- FastAPI + Gemini chat backend and responsive browser interface.
- Adaptive personality instructions and English/Telugu response preference.
- Browser speech input (only when manually activated and supported) and browser text-to-speech.
- Optional browser-local conversation history and local checklist.
- SQLite-backed, token-protected APIs to create/list/delete explicit memories, create/list/complete reminders, and log/delete workouts.
- Token-protected AI workout and general nutrition suggestion endpoints.
- Token-protected user-triggered web search with source links.
- Experimental Windows agent: system status and user-confirmed HTTPS URL opening for allow-listed domains.
- Optional Windows toast reminder worker that polls the local backend while its process is running.
- Native Kotlin/Jetpack Compose Android starter screen; it checks an HTTPS health endpoint and stores the device token encrypted with an Android Keystore key, but it is not yet connected to authenticated chat or personal-data APIs.
- Python API tests and GitHub Actions test/build workflows.

## Major gaps

- The Android app can send authenticated chat requests over HTTPS and encrypts the token with Android Keystore. It is not yet integrated with the personal-data APIs or per-device pairing/revocation.
- The Windows helper does not execute arbitrary commands or control files/apps/settings. This is intentionally restricted.
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

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The automated tests use mocks and do not prove your real Gemini key works. After local startup, send a simple chat request from the UI to verify your key, model access, network, and quota. Never paste your key into chat or GitHub.

## API overview

- `GET /health` — health check.
- `GET /` — browser chat UI.
- `POST /api/chat` — Gemini chat; currently **not authenticated**, so only run the backend locally.
- Token-protected APIs: `/api/memories`, `/api/reminders`, `/api/workouts`, `/api/research`, `/api/coach/workout`, and `/api/coach/nutrition`.
- `GET /docs` — local API reference.

## Security rules

- Never expose this server directly to the public internet. Do not bind to `0.0.0.0`, port-forward it, or use a public tunnel.
- Keep real API keys and tokens in `.env`, never in source control, Android resources, screenshots, or logs.
- The protected APIs reject missing/invalid bearer tokens; a shared token is not production device pairing.
- Sensitive OS or browser actions need user confirmation and explicit allow-lists. Model-generated arbitrary shell execution is out of scope.
- Fitness and nutrition outputs are general information, not medical advice.
- Check Google model availability, quotas, and pricing for your account; do not assume every request is free.

See [docs/NEXT-MILESTONES.md](docs/NEXT-MILESTONES.md) for the staged acceptance criteria.
