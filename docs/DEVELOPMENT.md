# Development Guide

## Prerequisites
- Python 3.11+
- At least one AI provider key for live chat: Gemini, OpenRouter, or Groq (mocked provider tests do not call external APIs)

## Local setup
PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Add one or more server-side keys: GEMINI_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY
# Set JARVIS_AI_PROVIDER=auto, gemini, openrouter, or groq
uvicorn app.main_enhanced:app --reload
```

`app.main_enhanced` is the canonical backend used by `jarvis serve`, the Windows
scripts and the Docker image (WebSocket brain bridge, device pairing and health
detail). `app.main` is a smaller compatibility app retained for tests; it does
not include `/ws` or the device-management endpoints.

Use `http://127.0.0.1:8000/docs` to explore the API. Never share a live API key in chat, screenshots, commits, or issue reports.

## Test
```powershell
python -m pytest -q
python -m ruff check .
python -m compileall -q app jarvis windows_agent jarvis_cli.py jarvis_daemon.py run_enhanced.py
```

`ruff` is the merge gate. `python -m mypy app/ --ignore-missing-imports` is
available for local type checks but has a pre-existing error baseline, so it is
not a pass/fail gate yet.

The SQLite schema is hand-written, so Alembic autogenerate is unsupported.
Create a revision with `alembic revision -m "..."` and write the DDL by hand.

Tests should not call live providers. Chat and streaming select the configured provider and can fall back to other configured providers if a request fails before streaming output begins. Live voice remains Gemini Live API based.

## Change checklist
1. Describe the intended behavior and threat model.
2. Implement the smallest useful change.
3. Add tests for success, validation failures, and provider failures.
4. Run tests and lint/type checks.
5. Update README, roadmap, and changelog.
6. Review secret handling, privacy, permissions, and API cost.
7. Verify behavior manually before claiming a feature is complete.
