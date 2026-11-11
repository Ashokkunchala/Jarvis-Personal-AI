# Changelog

## Unreleased
- Verified a clean-room build from `requirements-dev.txt` on Python 3.13: full test suite passes (135 tests) and `pip check` reports no broken requirements.
- Fixed Ruff failures in `jarvis/core/agent/voice_tools.py` (two unused `result` assignments and import ordering); `ruff check .` is clean again.
- Added `ruff` and `mypy` to `requirements-dev.txt` so the documented lint commands work in a fresh development environment.
- Hardened containers: added `.dockerignore`, run the image as an unprivileged user, publish the Compose port on `127.0.0.1` only, drop Linux capabilities, and mount only `data/` instead of the whole `app/` tree.
- Canonicalised the backend entry point on `app.main_enhanced:app` in the development docs; `app.main` remains a documented minimal compatibility app used by tests.
- Applied the shared `/api/` sliding-window rate limiter to the canonical enhanced backend, which previously only had per-route slowapi limits, and ordered middleware so security headers wrap 413/429 responses.
- Restored coaching response parity in the enhanced backend: workout and nutrition now return the conservative prompts, `disclaimer` text, and the `suggestions` key the browser UI reads.
- Added an idempotent Alembic baseline migration (`0001_initial`) covering all SQLite tables so `alembic upgrade head` works for fresh and existing local databases.
- Updated the registered tool count in the docs to 137.
- Fixed `scripts/setup-and-validate.ps1` failing to parse in Windows PowerShell 5.1: a UTF-8 em dash in a BOM-less file was decoded as a smart quote and terminated a string early. The script is now ASCII-only, so it parses and runs under stock Windows PowerShell.
- Rewrote `README_ENHANCED.md`, which contained control characters, deprecated `docker-compose` commands and claims for features that do not exist (snooze, memory tags, "production-grade"). It now lists only implemented endpoints and repeats the local-prototype status.
- Added `types-python-dateutil` for mypy, documented the pre-existing mypy baseline, and split `make lint` (Ruff, gating) from `make typecheck` (informational). `make migrate` now creates a manual revision because the hand-written SQLite schema has no SQLAlchemy metadata to autogenerate from.
- Added opt-in dashboard CPU/RAM/disk threshold crossing alerts with locally saved thresholds; desktop notifications require a separate user permission click, and checks run only while the dashboard is open.
- Added a 1 MiB `/api/` request-body limit to both HTTP apps, including bodies sent without `Content-Length`; oversized requests receive a secure 413 response.
- Added default-disabled SQLite interval schedules for five read-only system metrics, with explicit enable/disable/delete controls, best-effort cancellation, bounded status history, and browser management. Scheduled outputs are discarded; arbitrary tools cannot be scheduled.
- Added authenticated SQLite-backed user plans with checklist steps, optional linked due reminders through the existing notification workers, progress/cancellation/deletion controls, bounded status history, browser UI, and personal-data export. Cancelling/completing disables a pending reminder; deleting a plan removes it. Plans do not execute tools; notification delivery remains best-effort.
- Added an authenticated `/api/runtime/events` feed and dashboard timeline for provider request/turn durations and tool lifecycle status. Up to 200 allow-listed summaries persist in SQLite; if persistence is unavailable, the feed falls back to its in-memory ring. This bounded operational history is not a security audit log.
- Added aggregate network byte counters to the authenticated performance API and live dashboard send/receive rates computed from adjacent samples; unavailable OS counters are shown as unavailable.
- Added a shared dependency-aware tool task orchestrator with bounded parallel execution for read-only AI tool batches, serialized state-changing actions, lifecycle events, cancellation, and opt-in transient retries limited to read-only tasks. User-authored plans, durable task state, schedules, and event triggers remain pending; persisted lifecycle history is operational telemetry, not a security audit log.
- Capped Live Voice at two concurrent provider sessions per client IP per process; excess connections are rejected with a specific client status. Provider-account usage budgets and distributed limits remain outstanding.
- Added at most two delayed browser Live Voice reconnect attempts for transient transport/server disconnects, using fresh one-time tickets and a visible Stop-to-cancel path; authentication and provider configuration failures remain explicit errors.
- Added a foreground process and keyboard-automation availability check before desktop text entry; unverified focus now fails without typing.
- Added browser and native Android full-duplex Live Voice code with user-visible start/interrupt/stop controls, bounded audio buffers, short-lived single-use tickets, and server-side session/audio limits. Real provider and device verification remain pending.
- Added Android master-token pairing and confirmed device revocation. The app encrypts the issued device token, backend URL, and device ID with Android Keystore, and does not persist the master token. Device-management endpoints now require the master token; device tokens cannot administer other devices.
- Added recurring daily/weekly/monthly reminders, explicit Android memory controls, and opt-in Android WorkManager reminder notifications. Android delivery remains best-effort and device verification is pending.
- Added configurable per-process IP rate limiting for HTTP API routes and expanded CI to lint Python, parse Windows setup scripts, and build the Android debug APK.
- Required point-of-action confirmation with bounded item/byte and destination previews for file mutations; file changes cannot use session-wide or global auto-approval. Delete fails closed when Recycle Bin support is unavailable, and directory transfers into themselves are rejected.
- Added regression tests for API rate limiting, live-voice bounds and ticket checks, WebSocket auth/provider-timeout handling, recurring reminders, per-device token issue/authentication/revocation, and file-mutation confirmation/preview/fail-safe behavior.
- Updated setup, security, feature, deployment, and verification documentation to distinguish implemented code from unverified CI, provider, and device requirements.
- Reworked the browser dashboard into a voice-first JARVIS command centre with a responsive layout, animated assistant orb, visible listening/thinking/speaking/ready states, and explicit voice controls.
- Added transcript-first capture: speech recognition displays interim/final text for review and does not automatically submit a dictated phrase.
- Added voice cancellation and stop-speaking controls, plus reduced-motion accessibility support.
- Added the real-time voice acceptance checklist. Live Voice paths now exist in code, but actual provider access, browser hardware behavior, Android build, and physical-device tests remain pending.
- Fixed CI dependency mismatch: install the project with development extras so pytest-cov is available for the configured coverage flags.
- Added a Python lint job and regression test coverage for API security headers.
- Added an evidence-based release verification checklist.

## 0.2.0 — Browser MVP and setup improvements
- Added a responsive JARVIS chat UI served by FastAPI.
- Added browser speech recognition where supported and browser text-to-speech for responses.
- Added selectable auto/English/Telugu response instructions.
- Added bounded conversation context; server-side conversation persistence remains disabled.
- Added opt-in browser-local chat history and a local checklist.
- Added Windows setup and start scripts, full setup/troubleshooting documentation, deployment guidance, feature status matrix, and continuous-improvement process.
- Expanded API tests for the interface, input validation, missing-key handling, and a mocked Gemini response.
- Added dotenv dependency for loading local environment configuration.
- Added/retained GitHub Actions test workflow.

## 0.1.0 — Initial starter
- Added FastAPI health and chat endpoints.
- Added Gemini SDK integration using a server-side environment variable.
- Added adaptive JARVIS personality and English/Telugu language instructions.
- Added input validation, safe API error messages, basic tests, and GitHub Actions test workflow.
- Documented architecture, setup, safety boundaries, and phased roadmap.

## Not yet implemented
Production-grade account authorization, master-token rotation, distributed quotas and session limits, comprehensive audit/monitoring, reliable real-time/cross-device notifications, and secure public deployment remain unfinished. Per-device issue/revoke endpoints and Android pairing controls exist, but the Android flow still needs build and device verification. Use the feature status and milestone documentation for exact current boundaries.
