# JARVIS Personal AI

A private, extensible personal AI companion powered by the Gemini API, designed for Indian English with Telugu support. Its personality adapts: friendly and witty for everyday conversation, calm and thoughtful when needed, and energetic and motivational for coaching.

> **Current release: early local MVP.** The Gemini chat backend and browser interface are implemented in code. A successful live Gemini call, browser voice behavior, and the full automated test run still need to be verified on your computer. Android control, Windows system automation, cloud memory, web search, and real scheduled reminders are not implemented yet.

## Start here

- **Windows installation:** [docs/SETUP-WINDOWS.md](docs/SETUP-WINDOWS.md)
- Feature status: [docs/FEATURES.md](docs/FEATURES.md)
- Architecture and roadmap: [docs/ROADMAP.md](docs/ROADMAP.md)
- Security: [docs/SECURITY.md](docs/SECURITY.md)
- Deployment strategy: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- Continuous improvement: [docs/CONTINUOUS-IMPROVEMENT.md](docs/CONTINUOUS-IMPROVEMENT.md)
- Developer guide: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

## What works in this codebase

- FastAPI backend with a Gemini API integration.
- Responsive web chat interface served at `http://127.0.0.1:8000`.
- Adaptive personality instructions and English/Telugu response preference.
- Bounded conversation context for the active chat; the server does not persist conversations.
- Browser speech input when supported and user-authorized.
- Browser text-to-speech using installed voices (not Gemini-generated audio).
- Optional browser-local chat history and a local checklist, both stored only on the current browser/device.
- Health endpoint, initial API tests, and a GitHub Actions test workflow.

## Not implemented yet

- Native Android app or background always-on assistant.
- Windows agent that controls applications, files, or system settings.
- Live web search or autonomous browser agent.
- Cloud-synced memory, real notifications, or recurring reminders.
- Workout sensor integration or personalised medical/nutrition services.
- Public cloud deployment. The current API has no authentication and must not be exposed to the internet.

## Quick setup (Windows PowerShell)

Requirements: Python 3.11+ and a Gemini API key from [Google AI Studio](https://aistudio.google.com/).

```powershell
git clone https://github.com/Ashokkunchala/Jarvis-Personal-AI.git
cd Jarvis-Personal-AI
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup-windows.ps1
notepad .env
```

Put your key in the local `.env` file, save it, then start the server:

```powershell
.\scripts\start-windows.ps1
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Keep the terminal open while using the app; Ctrl+C stops the server.

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

For all prerequisites, key setup, troubleshooting, and voice limitations, follow the [full setup guide](docs/SETUP-WINDOWS.md).

## API endpoints

- `GET /health` — basic health status, no secrets exposed.
- `GET /` — JARVIS browser interface.
- `POST /api/chat` — body example: `{"message":"Hi JARVIS","language":"auto","history":[]}`.
- `GET /docs` — local OpenAPI documentation.

## Architecture

- **AI backend:** Python + FastAPI + Google GenAI SDK.
- **Model:** configurable through `GEMINI_MODEL`; confirm the selected model is currently available to your account.
- **Secrets:** local `.env`; never put API keys in the UI, mobile app, logs, or Git.
- **Future clients:** Android (Kotlin/Jetpack Compose) and a Windows local agent, added separately.
- **Memory:** opt-in and user-manageable if implemented; not currently stored server-side.

## Security and cost

- Keep the server bound to `127.0.0.1`. Do not use a public tunnel, port-forwarding, or `0.0.0.0` binding with this unauthenticated starter.
- The Gemini API may incur charges depending on model, quota, and account terms. Check provider pricing and usage controls.
- Never commit a real `.env`; `.gitignore` excludes it.
- Sensitive device actions must require confirmation; arbitrary model-generated shell execution is prohibited by design.
- Wellness guidance is general information, not diagnosis or medical treatment.

## Continuous improvement

Every feature should include acceptance criteria, tests, a security and cost review, updated documentation, and a changelog entry. See [docs/CONTINUOUS-IMPROVEMENT.md](docs/CONTINUOUS-IMPROVEMENT.md). Automatic code changes must be tested and reviewed before deployment.
