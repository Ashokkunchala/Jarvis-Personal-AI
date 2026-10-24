# Development Guide

## Prerequisites
- Python 3.11+
- Gemini API key from Google AI Studio (optional for tests; required for live chat)

## Local setup
PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Edit .env and add your own GEMINI_API_KEY
uvicorn app.main:app --reload
```

Use `http://127.0.0.1:8000/docs` to explore the API. Never share a live API key in chat, screenshots, commits, or issue reports.

## Test
```powershell
pytest -q
```

The initial tests do not call Gemini. Add mocked SDK tests before expanding the API.

## Change checklist
1. Describe the intended behavior and threat model.
2. Implement the smallest useful change.
3. Add tests for success, validation failures, and provider failures.
4. Run tests and lint/type checks.
5. Update README, roadmap, and changelog.
6. Review secret handling, privacy, permissions, and API cost.
7. Verify behavior manually before claiming a feature is complete.
