# Product Roadmap

## Phase 1 — Gemini companion API (current)
- [x] FastAPI starter and health endpoint
- [x] Gemini API integration using a server-side key
- [x] Adaptive personality and English/Telugu instructions
- [x] Request validation and basic tests
- [ ] Run tests in a clean environment and add CI
- [ ] Add a small web chat UI and conversation streaming

## Phase 2 — Voice and memory
- Voice input/output with explicit microphone permission and clear active-listening state.
- Session context and opt-in long-term memory.
- Memory review, edit, export, and delete controls; retention policy.
- Never store secrets or sensitive details by default.

## Phase 3 — Daily life
- Tasks, reminders, routines, habits, and daily/weekly reviews.
- Time-zone-aware scheduling and notification preferences.
- User-visible confirmation before creating external commitments.

## Phase 4 — Devices
- Android client (Kotlin/Jetpack Compose), Android 14-compatible permissions.
- Windows local agent with a narrow allowlist of actions.
- Authenticated local/cloud communication; pairing and revocation.
- Sensitive actions require a preview and explicit approval.
- No unrestricted shell, arbitrary file access, or hidden recording.

## Phase 5 — Skills
- Web search and browsing with citations.
- Workout timer, progress journal, learning plans, and general meal ideas.
- Coding and DevOps skills, read-only first; write actions gated by approval.

## Phase 6 — Production readiness
- Automated unit/integration tests and CI.
- Authentication, rate limits, quotas, usage tracking, timeouts, and retry policy.
- HTTPS, secret management, structured redacted logs, and monitoring.
- Deployment guide and security review.

## Continuous improvement
Every change should include: a clear issue/goal, implementation, tests, documentation update,
security/cost impact review, and a changelog entry. Use opt-in feedback; do not silently train
on private conversations. Model updates should be configurable and tested before release.
