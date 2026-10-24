# Deployment Strategy

## Current recommendation

Run the prototype locally on Windows while validating Gemini integration, browser voice, SQLite data, and the native Android chat client. Keep `HOST=127.0.0.1`.

## Why not public hosting yet?

Chat and personal-data endpoints now require a configured bearer token, but this is still a shared-token prototype. It lacks per-device pairing/revocation, rate limiting, account-level authorization, production audit/monitoring, and complete security hardening. The Android client has not yet passed an end-to-end device test. Do not deploy to a public URL or expose it through a tunnel yet.

## Required before cloud deployment

1. Replace the shared token with per-device credentials, pairing, revocation, rotation, and authorization.
2. Add request throttling, payload limits, timeouts, usage budgets, and abuse monitoring.
3. Put the service behind HTTPS with a managed secret store.
4. Restrict CORS to the exact production frontend origin and protect/disable interactive API docs as appropriate.
5. Add log redaction, retention rules, monitoring, and key-rotation procedures.
6. Add database encryption/backup policy and tested restore procedures for personal data.
7. Run dependency/security scanning and tests for auth failures, rate limits, token rotation, and abuse cases.
8. Complete Android and Windows end-to-end security tests.
9. Review the selected host's current Python/runtime support and pricing.

## Cloudflare options

- Cloudflare Pages is suitable for a static frontend, but it does not automatically host this Python FastAPI server.
- A Cloudflare Worker/Pages Function requires a compatible implementation/runtime; do not assume the standard Python Gemini SDK will run unchanged in a JavaScript Worker.
- A supported Python application host can run FastAPI; Cloudflare can then provide DNS/proxying in a properly secured deployment.
- A Cloudflare Tunnel to a personal computer is not a substitute for production authentication. Do not use it to expose this prototype.

## Environment variables

Set secrets through the hosting provider's secret manager or environment configuration. Never commit a real `.env` file. Use a least-privilege service identity where available.

## Cost control

- Start with a model available to your account that fits the response quality and price you want.
- Set usage limits/alerts where the provider supports them.
- Limit message size and conversation history.
- Track requests, failures, and latency without logging personal prompts by default.
- Add explicit daily usage budgets before enabling proactive tasks or tool loops.
