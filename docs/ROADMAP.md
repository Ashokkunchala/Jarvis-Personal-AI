# Product Roadmap

Status labels describe code in the repository, not a claim that a feature has been tested on every device.

## Phase 1 — Local Gemini companion (implemented in code; verify locally)
- [x] FastAPI starter and health endpoint
- [x] Gemini API integration using a server-side environment variable
- [x] Adaptive personality and English/Telugu instructions
- [x] Request validation and bounded conversation context
- [x] Responsive browser chat UI
- [x] Browser speech input/output where supported
- [x] Opt-in local chat history and a local task checklist
- [x] Windows setup/start scripts and troubleshooting guide
- [x] GitHub Actions test workflow and initial test suite
- [ ] Verify clean installation and automated tests on a real Windows machine
- [ ] Verify live Gemini API call with the user's own key
- [x] Add streamed browser responses and a stop control; live-key/device verification remains pending

## Phase 2 — Voice and personal memory
- Voice activity states, stop-speaking button, and improved language selection.
- Optional long-term memory with review, edit, export, and delete controls.
- Retention policy and per-item consent.
- Do not store secrets or sensitive personal details by default.

## Phase 3 — Daily life
- Real reminders and scheduled notifications.
- Tasks, routines, habits, and daily/weekly reviews.
- Time-zone-aware scheduling and user-configurable quiet hours.
- Calendar integration only after explicit account connection and permissions.

## Phase 4 — Secure multi-device access
- Add authentication, user sessions, rate limits, and per-user authorization before remote access.
- Android client (Kotlin/Jetpack Compose), Android 14-compatible permissions.
- Windows local agent with a narrow allowlist and explicit pairing.
- Secure device-to-service communication and revocation.
- Sensitive actions require a preview and explicit approval.
- No unrestricted shell, arbitrary file access, or hidden recording.

## Phase 5 — Skills
- Web search and browsing with citations and source provenance.
- Workout timer, progress journal, learning plans, and general meal ideas.
- Coding and DevOps skills, read-only first; write actions gated by approval.
- User-approved plugins and integrations.

## Phase 6 — Production readiness
- Automated unit/integration tests and CI.
- Authentication, rate limits, quotas, usage tracking, timeouts, and retry policy.
- HTTPS, secret management, structured redacted logs, and monitoring.
- Deployment guide, threat model, backup/restore, and security review.

## Continuous improvement
Every change should include: a clear issue/goal, acceptance criteria, implementation, tests, documentation update, security/cost impact review, and changelog entry. Use opt-in feedback; do not silently train on private conversations. Model updates should be configurable and tested before release.
