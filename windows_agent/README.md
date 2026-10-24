# JARVIS Windows companion agent (experimental)

This is a deliberately narrow first version. It can report basic platform information and open a user-confirmed HTTPS URL on an allow-listed domain. It cannot execute arbitrary commands, inspect files, control other applications, or run invisibly.

## Run on Windows

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:JARVIS_AGENT_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:JARVIS_ALLOWED_URL_HOSTS = "google.com;github.com;youtube.com"
python -m uvicorn windows_agent.agent:app --host 127.0.0.1 --port 8765
```

Keep it bound to `127.0.0.1`. Do not expose the port or configure router forwarding. Use the same token only for local development; use distinct per-device credentials in a future pairing system.

## Endpoints

- `GET /health` — health check, no sensitive information.
- `GET /v1/status` — requires `Authorization: Bearer <token>`.
- `POST /v1/open-url` — requires token and JSON `{"url":"https://github.com","confirmed":true}`. The domain must match the explicit allow-list.

The calling UI must ask the user before sending `confirmed: true`. The server also rejects unapproved domains and non-HTTPS URLs. Treat this as a foundation, not a complete remote-control agent. Add a consent UI, audit log, rate limits, tests, and device pairing before use from another device.
