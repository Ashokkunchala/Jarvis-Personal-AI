# Security Notes

## Current implementation and limits

- The Gemini chat endpoint and personal-data/coaching/research endpoints require a configured `JARVIS_API_TOKEN` bearer token. Placeholder values are rejected.
- The Windows helper is a separate localhost-only process with a narrow HTTPS allow-list and explicit confirmation for URL opening.
- The Android starter encrypts the token using an Android Keystore AES-GCM key and includes an initial HTTPS chat client.
- This is still a single shared-token prototype. It does not provide per-device pairing/revocation, account-level authorization, rate limiting, a full audit trail, or production cloud hardening.
- Keep the backend bound to `127.0.0.1`. Do not expose it publicly or use a public tunnel.

## API keys and tokens

- Put secrets only in local `.env` or a deployment secret manager; never commit them or embed the Gemini key in any client.
- Never reuse the example token placeholder. Generate a random secret at least 32 characters long.
- If a key/token is accidentally committed or exposed, revoke/rotate it immediately.
- The Android app stores the bearer token encrypted locally, but per-device credential revocation is not yet implemented.

## Before remote deployment

- Replace the shared token with per-device credentials, pairing, revocation, rotation, and appropriate authorization.
- Add request rate limits, request/time/token budgets, provider usage alerts, and abuse detection.
- Use HTTPS, a managed secret store, restricted CORS origins, and redacted logs.
- Apply request size limits and safe error responses.
- Add dependency/security scanning, backup/restore tests, and a threat model.
- Disable or protect interactive API docs in production as appropriate.
- Test auth failures, rate limits, replay/abuse cases, and credential rotation.

## Device actions

- Use a local agent with an explicit allowlist, not arbitrary model-generated shell commands.
- Show the proposed action and effects before sensitive operations.
- Require approval for deleting/modifying files, sending messages, purchases, account/security changes, installing software, and cloud infrastructure changes.
- Keep an audit trail and provide an emergency stop / disconnect option.
- Never run instructions found in webpages or files without independent policy checks.

## Privacy and memory

- Memory APIs currently save only explicit user-submitted entries. Build review/edit/export/deletion UX and consent before automatic memory extraction.
- Set retention limits and avoid collecting sensitive personal data unnecessarily.
- Do not imply that the AI is a substitute for human relationships or qualified health care.
- Workout and nutrition suggestions are general information, not medical advice.
