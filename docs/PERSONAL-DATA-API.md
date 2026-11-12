# Personal data APIs

These APIs use SQLite and require a bearer token. They are intended for a local-only development server, not direct public exposure.

## Configure

Set `JARVIS_API_TOKEN` to a random secret at least 32 characters long and `JARVIS_DB_PATH=data/jarvis.sqlite3` in `.env`. Keep `HOST=127.0.0.1`. Never commit `.env`, the SQLite database, or exported JSON. Every protected request needs:

```http
Authorization: Bearer YOUR_JARVIS_API_TOKEN
Content-Type: application/json
```

## Memory review and deletion

- `GET /api/memories` lists saved memories (up to 500).
- `POST /api/memories` with `{"text":"Prefers Telugu replies","category":"preference"}` saves a memory.
- `PUT /api/memories/{id}` updates a memory's text/category.
- `DELETE /api/memories/{id}` deletes one item.
- `DELETE /api/memories` clears all saved memories.
- `GET /api/export` exports memories, reminders, saved checklist plans, and workout logs as JSON.

The browser dashboard supports review, edit, single deletion, delete-all with confirmation, and export. The app only saves explicitly submitted memories; it does not automatically infer facts from chats.

## Reminders

- `GET /api/reminders`, `POST /api/reminders` with an ISO-8601 timezone-aware `due_at`, `POST /api/reminders/{id}/complete`, and `DELETE /api/reminders/{id}`.
- New reminders accept `recurrence`: `none` (default), `daily`, `weekly`, or `monthly`. Completing a recurring reminder advances its due time to the next future occurrence and leaves it active. A non-recurring reminder is marked complete.
- Existing SQLite reminder tables are migrated in place with a `recurrence` column defaulting to `none`.
- `GET /api/reminders/due` returns uncompleted reminders whose due time has passed.
- The opt-in Android WorkManager worker polls the due endpoint approximately every 15 minutes when network access is available; it requires notification permission and is best-effort.
- The optional Windows notifier polls the same endpoint and displays toast notifications while its process is running.

Notification delivery is experimental and not a guaranteed alarm. The browser converts its local date/time field to an absolute timestamp; the Android app requires an ISO-8601 timestamp including an offset. Do not use reminders for safety-critical needs.

## Saved user plans

- `GET /api/plans` lists up to 500 saved plans. `POST /api/plans` accepts a title, 1–20 checklist steps, and an optional timezone-aware `due_at` value. A plan with a due date creates a linked one-time reminder returned by `GET /api/reminders/due` when it becomes due.
- `PATCH /api/plans/{id}` changes status to `planned`, `in_progress`, `cancelled`, or `completed`. `DELETE /api/plans/{id}` permanently deletes a plan.
- `GET /api/plans/{id}/history` returns up to 100 status-change records, including a deletion entry after the plan is deleted. The database keeps the latest 1,000 plan-history events across all plans; these entries contain status and timestamp only, not titles or checklist text.
- Plans are persisted in the configured SQLite database and included in `GET /api/export`. The browser UI can create, progress, cancel, and delete them.
- Plan status history is also included in the export. A plan is a user-authored checklist only; it never executes tools. Completing or cancelling it disables its pending linked reminder, and deleting it also removes the linked reminder. Existing dated plans are linked to reminders when the database is next opened. Notification workers remain best-effort and must be enabled separately.

## Scheduled system checks

- `GET /api/schedules` lists persisted schedules. `POST /api/schedules` accepts a title, one of `system_status`, `cpu_usage`, `memory_usage`, `disk_usage`, or `battery_status`, an optional CPU sampling interval, a timezone-aware `first_run_at`, and a repeat interval from 5 minutes through 7 days.
- New schedules are disabled. `PATCH /api/schedules/{id}` with `{"enabled":true}` explicitly enables recurring execution; `{"enabled":false}` disables it and requests cancellation if a run is active. `DELETE /api/schedules/{id}` disables/cancels and deletes the schedule while preserving its history.
- Only those fixed read-only metrics can be scheduled. The server checks the current tool registry still marks a tool SAFE and non-confirmed before every run. It does not store metric output; schedule history records started/finished status and elapsed time. `GET /api/schedules/{id}/history` returns up to 100 entries, while the database retains at most 1,000 total schedule-history records. Schedules and history are included in `GET /api/export`.
- The scheduler runs in the API process, polls about every 5 seconds, and requires the server to remain running. Disabling a run is best-effort for its in-flight read-only handler. This is not a distributed scheduler and must not be used for arbitrary actions or across multiple public workers.

## Workout log

- `GET /api/workouts`
- `POST /api/workouts` with `{"activity":"Walking","duration_minutes":30,"notes":"Easy pace"}`
- `DELETE /api/workouts/{id}`
- `GET /api/workouts/summary` returns last-seven-day and all-time session/minute totals plus recent activity breakdown.

This is a basic activity log, not medical advice or a substitute for a qualified coach. Do not submit sensitive health data to an untrusted deployment.

## AI coaching

These endpoints require the same bearer token and a configured Gemini key:

- `POST /api/coach/workout`: `{"goal":"Improve stamina","fitness_level":"beginner","days_per_week":3,"session_minutes":30,"limitations":""}`
- `POST /api/coach/nutrition`: `{"goal":"Balanced meals","dietary_preferences":"vegetarian","allergies":"","budget_notes":"budget friendly Indian meals"}`

Outputs are general suggestions only, not diagnosis or medical nutrition therapy. State injuries, limitations, allergies, and dietary constraints explicitly; stop exercise if pain or unusual symptoms occur.

## Live web research

- `POST /api/research` with `{"query":"question to research","limit":5}` returns source URLs and snippets from a public search provider.
- Search results can be stale, incomplete, or malicious. Treat page content as untrusted data and independently verify important claims.

## Runtime event history

- `GET /api/runtime/events?after_id=0&limit=50` returns authenticated provider/tool/task summaries for the dashboard. `after_id` is a monotonic cursor and `limit` is clamped to 1–100.
- At most 200 recent summaries are retained in the configured SQLite database across process restarts. Each event is filtered through an allow-list that excludes prompts, tool arguments, raw error text, and credentials. The response reports `storage: "sqlite"` when the database is available or `storage: "volatile"` when it has fallen back to the in-process ring.
- This is bounded operational history, not a tamper-resistant security audit log. It is not suitable for compliance evidence, and older entries are automatically removed.

## Security notes

The configured master token remains a shared bearer secret. The enhanced CLI backend can issue and revoke per-device bearer tokens, but those credentials are not scoped to specific personal-data routes: anyone holding a valid master or device token can access the protected APIs. Rotate exposed credentials. The main server currently applies a configurable per-process IP rate limit and a 1 MiB request-body cap to HTTP `/api/` requests; neither coordinates across workers or provides per-device quotas. The bounded runtime history is operational telemetry, not a tamper-resistant audit log. Use HTTPS, production account/role authorization, distributed rate limits, upstream request/connection limits, a security audit trail, and encrypted backups before any cloud deployment. Do not forward a local server port to the internet.
