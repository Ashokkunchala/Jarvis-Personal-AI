# Personal data APIs (first implementation)

These APIs use SQLite and require a bearer token. They are intended for a local-only development server, not direct public exposure.

## Configure

Set `JARVIS_API_TOKEN` to a random secret at least 32 characters long and `JARVIS_DB_PATH=data/jarvis.sqlite3` in `.env`. Keep `HOST=127.0.0.1`. Never commit `.env` or the SQLite database. Every request below needs:

```http
Authorization: Bearer YOUR_JARVIS_API_TOKEN
Content-Type: application/json
```

## Memory review and deletion

- `GET /api/memories` lists saved memories (up to 500).
- `POST /api/memories` with `{"text":"Prefers Telugu replies","category":"preference"}` saves a memory.
- `DELETE /api/memories/{id}` deletes one item.
- `DELETE /api/memories` clears all saved memories.

This first version saves only explicit API submissions. It does not automatically infer or save facts from chat. Add consent and review UI before enabling automatic memory extraction.

## Reminders

- `GET /api/reminders`, `POST /api/reminders` with an ISO-8601 timezone-aware `due_at`, `POST /api/reminders/{id}/complete`, and `DELETE /api/reminders/{id}`.
- `GET /api/reminders/due` returns uncompleted reminders whose due time has passed.

Important: the API stores reminders and exposes due items; it does **not yet send OS/mobile notifications**. A trusted Windows/mobile notification worker must poll the due endpoint and mark reminders complete after user confirmation. Do not treat this as a reliable alarm service yet.

## Workout log

- `GET /api/workouts`
- `POST /api/workouts` with `{"activity":"Walking","duration_minutes":30,"notes":"Easy pace"}`
- `DELETE /api/workouts/{id}`

This is a basic activity log, not medical advice or a substitute for a qualified coach. Do not submit sensitive health data to an untrusted deployment.

## Security notes

The token is a shared bearer secret, not full device pairing. Anyone who obtains it can access these endpoints. Rotate it if exposed. Use HTTPS, per-device credentials, revocation, rate limits, audit logs, and encrypted backups before any cloud deployment. Do not forward a local server port to the internet.


## AI coaching endpoints

These endpoints require the same bearer token and a configured Gemini key:

- `POST /api/coach/workout`: `{"goal":"Improve stamina","fitness_level":"beginner","days_per_week":3,"session_minutes":30,"limitations":""}`
- `POST /api/coach/nutrition`: `{"goal":"Balanced meals","dietary_preferences":"vegetarian","allergies":"","budget_notes":"budget friendly Indian meals"}`

The outputs are general suggestions only. They are not diagnosis, medical nutrition therapy, or a substitute for a qualified professional. State injuries, limitations, allergies, and dietary constraints explicitly; stop exercise if pain or unusual symptoms occur.
