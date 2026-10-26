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
uvicorn app.main:app --reload
```

Use `http://127.0.0.1:8000/docs` to explore the API. Never share a live API key in chat, screenshots, commits, or issue reports.

## Test
```powershell
pytest -q
```

Tests should not call live providers. Chat and streaming select the configured provider and can fall back to other configured providers if a request fails before streaming output begins. Live voice remains Gemini Live API based.

## Change checklist
1. Describe the intended behavior and threat model.
2. Implement the smallest useful change.
3. Add tests for success, validation failures, and provider failures.
4. Run tests and lint/type checks.
5. Update README, roadmap, and changelog.
6. Review secret handling, privacy, permissions, and API cost.
7. Verify behavior manually before claiming a feature is complete.
