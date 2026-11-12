# JARVIS Personal AI - Enhanced Backend

This document describes the enhanced FastAPI backend (`app.main_enhanced:app`),
which is the entry point used by `jarvis serve`, the Windows start scripts and
the Docker image.

> **Status: local prototype, not production-ready.** Bind the server to
> `127.0.0.1` and keep it on a trusted machine. There is no public deployment
> hardening, no distributed quota, and no reliable cross-device delivery
> guarantee. See `docs/FEATURES.md` and `docs/NEXT-MILESTONES.md` for exact
> boundaries.

## What this backend adds over `app.main`

- WebSocket brain bridge at `/ws`
- Master-token device pairing, listing and revocation
- Detailed authenticated health and performance endpoints
- Live Voice ticket issuing and bounded concurrent sessions
- Personal data API: memories, reminders, plans, schedules, workouts, export
- Research cache endpoint
- Workout and nutrition coaching endpoints with disclaimers
- Global per-IP `/api/` rate limiting, a 1 MiB API body cap and security headers

`app.main` remains a smaller compatibility app used by the API tests. It does
not include `/ws` or device management.

## Quick start

### Docker Compose

```bash
cp .env.example .env
# Edit .env: set JARVIS_API_TOKEN (32+ random characters) and one provider key
docker compose up -d
# The published port is 127.0.0.1:8000 only.
```

The image runs as an unprivileged user, drops Linux capabilities and mounts only
`./data`. If `./data` does not exist, create it first so the container user can
write the SQLite database.

### Python

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Add keys, then:
uvicorn app.main_enhanced:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` for the browser UI, `/dashboard` for the
operational dashboard, and `/docs` for the API schema.

## Authentication

Send `Authorization: Bearer <token>`.

- `JARVIS_API_TOKEN` acts as the master/legacy token.
- `/api/devices/*` requires the master token.
- Issued device tokens authenticate normal data and chat routes but cannot
  administer other devices.
- If `JARVIS_API_TOKEN` is unset, shorter than 32 characters, or still starts
  with `replace_`, authenticated routes fail closed with `503`.

## Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | none | Liveness check |
| GET | `/api/health/detailed` | token | Database and provider status |
| GET | `/api/performance` | token | Process and host metrics |
| GET | `/api/runtime/events` | token | Bounded operational event feed |
| POST | `/api/chat` | token | Chat completion |
| POST | `/api/chat/stream` | token | SSE chat stream |
| POST | `/api/coach/workout` | token | Workout plan plus disclaimer |
| POST | `/api/coach/nutrition` | token | Nutrition suggestions plus disclaimer |
| POST | `/api/devices/issue` | master | Issue a device token |
| GET | `/api/devices` | master | List devices |
| DELETE | `/api/devices/{device_id}` | master | Revoke a device |
| POST | `/api/live-voice-ticket` | token | Short-lived Live Voice ticket |
| GET/POST | `/api/memories` | token | List or create memories |
| PUT/DELETE | `/api/memories/{memory_id}` | token | Update or delete a memory |
| GET/POST | `/api/reminders` | token | List or create reminders |
| GET | `/api/reminders/due` | token | Due reminders |
| POST | `/api/reminders/{reminder_id}/complete` | token | Complete a reminder |
| DELETE | `/api/reminders/{reminder_id}` | token | Delete a reminder |
| GET/POST | `/api/plans` | token | List or create plans |
| PATCH/DELETE | `/api/plans/{plan_id}` | token | Update or delete a plan |
| GET | `/api/plans/{plan_id}/history` | token | Plan status history |
| GET/POST | `/api/schedules` | token | List or create interval schedules |
| PATCH/DELETE | `/api/schedules/{schedule_id}` | token | Update or delete a schedule |
| GET | `/api/schedules/{schedule_id}/history` | token | Schedule status history |
| GET/POST | `/api/workouts` | token | List or record workouts |
| GET | `/api/workouts/summary` | token | Aggregate workout summary |
| DELETE | `/api/workouts/{workout_id}` | token | Delete a workout |
| GET | `/api/export` | token | Export personal data |
| POST | `/api/research` | token | Cached research query |
| WS | `/ws` | ticket/token | Realtime brain bridge |

There is no reminder snooze endpoint in this backend. `app/personal_data_enhanced.py`
is unused legacy code and is not part of the running application.

## Development

```powershell
python -m pytest -q
python -m ruff check .
python -m compileall -q app jarvis windows_agent jarvis_cli.py jarvis_daemon.py run_enhanced.py
```

`ruff` is the merge gate. mypy has a pre-existing error baseline and is
informational only. The `Makefile` targets are optional and require GNU make;
run the underlying commands directly on Windows if make is unavailable.

The SQLite schema is created with hand-written DDL, so Alembic autogenerate is
unsupported. Create a revision with `alembic revision -m "description"`, write
the DDL, then run `alembic upgrade head`.

## Security notes

- Keep `127.0.0.1` binding; do not publish the container port on `0.0.0.0`.
- Use a random `JARVIS_API_TOKEN` of at least 32 characters.
- Revoke unused device tokens and review `/api/devices`.
- Provider keys stay server-side in `.env`; never commit or print them.
- Rate limiting, body caps and security headers reduce abuse but are not a
  substitute for a reverse proxy, TLS and authentication when exposed.
