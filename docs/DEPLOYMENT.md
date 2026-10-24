# Deployment Strategy

## Current recommendation
Run the first version locally on Windows. It is the simplest, cheapest way to validate the Gemini integration and voice interface while keeping the API key on your own machine.

## Why not public hosting yet?
The current API has no authentication or per-user authorization. If exposed publicly, other people could use your endpoint and cause API usage or cost. Do not deploy this version to a public URL or expose it through a tunnel.

## Before cloud deployment
1. Add authentication and per-user authorization.
2. Add request throttling, token/request limits, timeouts, and usage monitoring.
3. Add a managed secret store and HTTPS.
4. Restrict CORS to the exact production frontend origin.
5. Add log redaction, retention rules, monitoring, and a process for key rotation.
6. Add tests for auth failures, rate limits, and abuse cases.
7. Review the selected host's current Python/runtime support and pricing.

## Cloudflare options
- Cloudflare Pages is suitable for a static frontend, but it does not automatically host this Python FastAPI server.
- A Cloudflare Worker/Pages Function requires a compatible implementation/runtime; do not assume the standard Python Gemini SDK will run unchanged in a JavaScript Worker.
- A supported Python application host can run FastAPI; Cloudflare can then provide DNS/proxying in a properly secured deployment.
- A Cloudflare Tunnel to a personal computer is not a substitute for authentication and should not be used to expose this unauthenticated starter.

## Environment variables
Set secrets through the hosting provider's secret manager or environment configuration. Never commit a real `.env` file. Use a least-privilege service identity where available.

## Cost control
- Start with a model available to your account that fits the response quality and price you want.
- Set usage limits/alerts where the provider supports them.
- Limit message size and conversation history.
- Track requests, failures, and latency without logging personal prompts by default.
- Add explicit daily usage budgets before enabling proactive tasks or tool loops.
