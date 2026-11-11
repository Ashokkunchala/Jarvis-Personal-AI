# JARVIS delivery plan

## Milestone 1 — local core and persistent data (in progress)
- [x] Gemini API key stays server-side.
- [x] SQLite endpoints for explicit memory entries, reminders, and workout logs.
- [x] Bearer-token gate on personal-data endpoints; refuses to run these APIs without a configured token.
- [x] Add UI for reviewing/editing/deleting memories, exporting personal data, and tracking reminders/workouts.
- [x] Add a notification worker with retries, deduplication, and visible delivery status (local toast call status; keep it running for delivery).
- [x] Align CI test installation with the repository's pytest coverage configuration.
- [x] Add regression coverage for required security response headers.
- [x] Enforce a 1 MiB `/api/` request-body cap in both HTTP apps, including chunked requests, with authenticated-route independent 413 handling and security-header tests.
- [x] Re-run the local Python tests, lint, and compile checks after the CI update.
- [ ] Confirm the Android build in CI for the latest changes; retain the workflow URL as evidence.
- [ ] Verify clean setup and local end-to-end behavior on Windows with the owner's API key.

## Milestone 1B — real-time voice and interface (in progress)
- [x] Add a browser Live Voice panel and PCM audio streaming client.
- [x] Add an authenticated server-side WebSocket bridge; keep provider API credentials on the backend.
- [x] Add same-origin and allow-listed-origin checks with regression tests.
- [x] Make the Live API model and voice configurable (`GEMINI_LIVE_MODEL`, `GEMINI_LIVE_VOICE`).
- [x] Exchange the long-lived bearer token for a single-use, 60-second WebSocket ticket before opening live voice.
- [x] Bound live voice sessions by duration and cumulative inbound audio, in addition to per-frame limits.
- [x] Limit concurrent Live Voice provider sessions to two per client IP; the limit is process-local and provider account quota/usage budgets remain pending.
- [ ] Confirm the configured model is available to the owner's API project; exercise a real microphone-to-model-to-speaker session and interruption on Chrome/Android Chrome.
- [x] Replace ScriptProcessor capture with AudioWorklet and bound the client send queue.
- [ ] Add provider account usage budgets and verify audio focus/backpressure on supported browsers; browser transcript captions are streamed and transient socket reconnects now retry twice with a visible cancel control.
- [x] Add native Android real-time bidirectional audio with one-time ticket authentication and explicit start, interrupt, and stop controls.
- [ ] Build and verify Android Live Voice audio, microphone permission handling, and stop/disconnect cleanup on a physical Android device.

## Milestone 2 — Windows companion agent
- Localhost-only agent, explicit allow-listed actions, bearer authentication, user confirmation for consequential actions, audit log, and a stop switch.
- No arbitrary shell execution, password access, stealth, or background surveillance.
- Require a paired-device design before remote calls are enabled.

## Milestone 3 — Android application
- Native Kotlin + Jetpack Compose client; API token stored using Android Keystore-backed encrypted storage.
- Request microphone, notification, and other permissions only when a user activates the relevant feature.
- Use Android WorkManager for deferrable background sync. Android restricts always-on microphone and background activity; no promise of unrestricted continuous listening.
- Build and sign an APK on a machine with Android SDK/Gradle. CI source checks do not prove a device build.
- [ ] Install the latest APK on a physical Android 14 device and test master-token pairing/revocation, encrypted token persistence, HTTPS chat, speech input/output, disconnects, and error states.
- [x] Add native Android quick links to device/Wi-Fi/Bluetooth settings and JARVIS app permissions; Android keeps protected changes in system UI.
- [x] Add authenticated reminder creation and list refresh in the native app.
- [x] Integrate explicit memories with review/delete controls in the Android app and add daily/weekly/monthly reminder recurrence.
- [x] Add opt-in Android WorkManager reminder polling with user-controlled notification permission; recurrence is handled by the backend after completion.
- [x] Add Android device pairing and confirmed revoke controls backed by master-token-only issue/revoke endpoints; physical-device verification remains pending.
- [ ] Verify Android notification permission, due delivery, disable/forget-token behavior, and recurring reminders on a physical Android device.

## Agent orchestration (in progress)
- [x] Route model-issued tool batches through the shared dependency-aware orchestrator; cap read-only parallel calls at three and run state-changing actions serially.
- [x] Emit task lifecycle, skip, retry, and cancellation events; only allow explicit retries for transient failures on read-only tools.
- [x] Add user-authored saved checklist plans with SQLite persistence, optional linked due reminders, status-change history, cancel/delete controls, and personal-data export. Saved plans do not execute tools.
- [x] Add persistent interval schedules for a fixed allowlist of read-only system metrics, default-disabled enrollment, status history, and browser enable/disable/cancel/delete controls.
- [ ] Add user-authored executable multi-step plans, resumable task state, arbitrary event-triggered actions, and UI cancellation for those plan runs. The schedule runner is a single-process local service; the bounded SQLite lifecycle feed is not a durable execution journal or security audit log.

## Milestone 4 — live research and browser automation
- Research adapter with source URLs, timestamps, timeouts, domain allowlists, and clear separation between webpage content and trusted instructions.
- Browser automation runs in a separate, least-privilege worker. Require confirmation before form submissions, purchases, account changes, or destructive actions.

## Milestone 5 — secure cloud and device connectivity
- Verify Android pairing and device revocation on hardware; add token rotation, HTTPS, distributed rate limiting, audit trail, encrypted secrets, backups and restore tests.
- Apply rate limits consistently across chat, research, reminders and coaching APIs.
- Restrict CORS to the actual production origin, add log redaction and budget limits, and test token rotation.
- Deploy only after threat modeling and security tests. Never expose the current local backend directly to the internet.

## Milestone 6 — personal coaching and routines
- Reminder delivery across Android and Windows, daily check-in, opt-in routines, workout history and trends.
- Fitness advice should be general and conservative; ask about injuries/limitations before recommending strenuous routines. Nutrition suggestions are general information, not medical treatment.

## Acceptance criteria
Every milestone includes reproducible setup instructions, unit/API tests, security checks, manual test steps, known limitations, and a versioned release note. Never claim a feature is working until the relevant test/build or device test has actually passed. See [VERIFICATION-CHECKLIST.md](VERIFICATION-CHECKLIST.md) for current evidence and release gates.
