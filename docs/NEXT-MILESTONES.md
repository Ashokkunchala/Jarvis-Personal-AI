# JARVIS delivery plan

## Milestone 1 — local core and persistent data (in progress)
- [x] Gemini API key stays server-side.
- [x] SQLite endpoints for explicit memory entries, reminders, and workout logs.
- [x] Bearer-token gate on personal-data endpoints; refuses to run these APIs without a configured token.
- [x] Add UI for reviewing/editing/deleting memories, exporting personal data, and tracking reminders/workouts.
- [x] Add a notification worker with retries, deduplication, and visible delivery status (local toast call status; keep it running for delivery).
- [x] Align CI test installation with the repository's pytest coverage configuration.
- [x] Add regression coverage for required security response headers.
- [ ] Re-run Python tests, lint, and Android build after the CI update; retain the workflow URL as evidence.
- [ ] Verify clean setup and local end-to-end behavior on Windows with the owner's API key.

## Milestone 2 — Windows companion agent
- Localhost-only agent, explicit allow-listed actions, bearer authentication, user confirmation for consequential actions, audit log, and a stop switch.
- No arbitrary shell execution, password access, stealth, or background surveillance.
- Require a paired-device design before remote calls are enabled.

## Milestone 3 — Android application
- Native Kotlin + Jetpack Compose client; API token stored using Android Keystore-backed encrypted storage.
- Request microphone, notification, and other permissions only when a user activates the relevant feature.
- Use Android WorkManager for deferrable background sync. Android restricts always-on microphone and background activity; no promise of unrestricted continuous listening.
- Build and sign an APK on a machine with Android SDK/Gradle. CI source checks do not prove a device build.
- [ ] Install the latest APK on a physical Android 14 device and test login/token persistence, HTTPS chat, speech input/output, disconnects, and error states.
- [ ] Integrate explicit memories and reminders in the native app with review/delete controls.

## Milestone 4 — live research and browser automation
- Research adapter with source URLs, timestamps, timeouts, domain allowlists, and clear separation between webpage content and trusted instructions.
- Browser automation runs in a separate, least-privilege worker. Require confirmation before form submissions, purchases, account changes, or destructive actions.

## Milestone 5 — secure cloud and device connectivity
- Authentication with per-device pairing/revocation rather than a shared secret; HTTPS, rate limiting, audit trail, encrypted secrets, backups and restore tests.
- Apply rate limits consistently across chat, research, reminders and coaching APIs.
- Restrict CORS to the actual production origin, add log redaction and budget limits, and test token rotation.
- Deploy only after threat modeling and security tests. Never expose the current local backend directly to the internet.

## Milestone 6 — personal coaching and routines
- Reminder delivery across Android and Windows, daily check-in, opt-in routines, workout history and trends.
- Fitness advice should be general and conservative; ask about injuries/limitations before recommending strenuous routines. Nutrition suggestions are general information, not medical treatment.

## Acceptance criteria
Every milestone includes reproducible setup instructions, unit/API tests, security checks, manual test steps, known limitations, and a versioned release note. Never claim a feature is working until the relevant test/build or device test has actually passed. See [VERIFICATION-CHECKLIST.md](VERIFICATION-CHECKLIST.md) for current evidence and release gates.
