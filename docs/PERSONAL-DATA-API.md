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
- `GET /api/export` exports memories, reminders, and workout logs as JSON.

The browser dashboard supports review, edit, single deletion, delete-all with confirmation, and export. The app only saves explicitly submitted memories; it does not automatically infer facts from chats.

## Reminders

- `GET /api/reminders`, `POST /api/reminders` with an ISO-8601 timezone-aware `due_at`, `POST /api/reminders/{id}/complete`, and `DELETE /api/reminders/{id}`.
- `GET /api/reminders/due` returns uncompleted reminders whose due time has passed.
- The optional Windows notifier polls the due endpoint and displays toast notifications while its process is running.

The notifier is experimental: delivery is deduplicated only in process memory, so restarting it can show a due reminder again. It is not a guaranteed alarm and does not yet support recurrence or Android notifications. The UI converts the local date/time field to an absolute timestamp. Do not use it for safety-critical reminders.

## Workout log

- `GET /api/workouts`
- `POST /api/workouts` with `{"activity":"Walking","duration_minutes":30,"notes":"Easy pace"}`
- `DELETE /api/workouts/{id}`

This is a basic activity log, not medical advice or a substitute for a qualified coach. Do not submit sensitive health data to an untrusted deployment.

## AI coaching

These endpoints require the same bearer token and a configured Gemini key:

- `POST /api/coach/workout`: `{"goal":"Improve stamina","fitness_level":"beginner","days_per_week":3,"session_minutes":30,"limitations":""}`
- `POST /api/coach/nutrition`: `{"goal":"Balanced meals","dietary_preferences":"vegetarian","allergies":"","budget_notes":"budget friendly Indian meals"}`

Outputs are general suggestions only, not diagnosis or medical nutrition therapy. State injuries, limitations, allergies, and dietary constraints explicitly; stop exercise if pain or unusual symptoms occur.

## Live web research

- `POST /api/research` with `{"query":"question to research","limit":5}` returns source URLs and snippets from a public search provider.
- Search results can be stale, incomplete, or malicious. Treat page content as untrusted data and independently verify important claims.

## Security notes

The token is a shared bearer secret, not full device pairing. Anyone who obtains it can access these endpoints. Rotate it if exposed. Use HTTPS, per-device credentials, revocation, rate limits, audit logs, and encrypted backups before any cloud deployment. Do not forward a local server port to the internet.
