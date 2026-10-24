# JARVIS Personal AI

A private, extensible personal AI companion powered by the Gemini API, designed for Indian English with Telugu support. The personality is adaptive: friendly and witty for everyday conversation, calm and thoughtful when needed, and energetic and motivational for coaching.

> **Status:** Phase 1 starter backend. This repository is not yet a full device-controlling assistant. Android, Windows automation, persistent memory, reminders, and voice sessions will be added in staged, tested phases.

## Goals

- Friendly conversation, jokes, brainstorming, and original song-writing.
- Indian English and Telugu-aware responses; follow the language the user uses and support natural code-switching.
- Daily planning, tasks, reminders, habits, learning, workouts, and general nutrition guidance.
- Web research and tool use through explicit, permissioned integrations.
- Android and Windows control through separately installed local clients, with confirmation for sensitive actions.
- Continuous improvement through documented issues, regression tests, security reviews, and opt-in user feedback.

## Architecture

- **AI backend:** Python + FastAPI + Google GenAI SDK.
- **Model:** configurable through `GEMINI_MODEL`; verify model availability for your API project.
- **Secrets:** `.env` locally; never put API keys in source code, client apps, logs, or Git.
- **Future clients:** Android (Kotlin/Jetpack Compose) and Windows local agent. The cloud model alone cannot control device hardware or applications.
- **Memory:** will be opt-in, inspectable, and deletable. Do not send sensitive personal details unless you choose to.

## Quick start (Windows PowerShell)

1. Install Python 3.11 or newer.
2. Copy `.env.example` to `.env` and set your Gemini API key.
3. In this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

4. Open `http://127.0.0.1:8000/docs` and try `POST /api/chat`.

Keep the service bound to localhost while developing. Do not expose it publicly without authentication, rate limits, HTTPS, and a deliberate deployment review.

## Configuration

See `.env.example`. Keep `GEMINI_API_KEY` on the backend only. Set usage limits in Google AI Studio / your Google Cloud project as available, and monitor usage and billing. API availability and pricing depend on the selected model and account.

## API

- `GET /health` — basic health status (does not expose secrets).
- `POST /api/chat` — request JSON: `{"message":"Hi JARVIS","language":"auto"}`.
- `language` accepts `auto`, `en`, or `te`.

The initial API is stateless: it does not persist conversations. This is intentional until memory controls and retention rules are implemented.

## Safety boundaries

- This backend only generates responses; it does not execute shell commands or control devices.
- Never add arbitrary shell execution as an LLM tool.
- Require explicit approval for file deletion, sending messages, purchases, account changes, infrastructure changes, or other consequential actions.
- Use least-privilege permissions and audit tool actions.
- Wellness suggestions are general information, not diagnosis or medical treatment. Stop exercise if you experience concerning symptoms and seek qualified help.
- Use original lyrics/songwriting rather than reproducing copyrighted song lyrics on request.

## Development and tests

```powershell
python -m pip install -r requirements-dev.txt
pytest -q
```

See [docs/ROADMAP.md](docs/ROADMAP.md), [docs/SECURITY.md](docs/SECURITY.md), and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Roadmap

1. Gemini chat backend, adaptive personality, English/Telugu support, tests.
2. Voice interface and opt-in personal memory.
3. Tasks, reminders, routines, and daily summaries.
4. Android client and secure local Windows agent.
5. Browser research and approved tool integrations.
6. Workout and learning coaching, then proactive routines.
7. Deployment, observability, cost limits, and end-to-end security tests.
