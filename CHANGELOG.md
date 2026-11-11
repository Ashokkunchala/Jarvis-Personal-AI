# Changelog

## Unreleased
- On screens 860 px wide or less, the voice approval prompt is pinned to the bottom of the viewport so it is visible wherever you scroll. It shows a countdown to the automatic denial, has Approve, Deny and Stop voice buttons, does not trap keyboard focus, and the page keeps bottom padding while it is open. Checked in headless Chrome at 390 px (scrolled to top, middle and bottom; Tab order; timeout removal; no reminder created on timeout). "Gemini Live model" now reads "Session opened (audio not verified)" so an open session is not mistaken for proof the real model works.
- New cinematic command-centre UI: animated AI core with listening/thinking/speaking states and waveform, system overview, connected services, upcoming reminders, approvals panel ("Needs you"), AWS DevOps starters, quick actions and a stop-voice-and-replies button; chat, memory, reminders, workouts, research, coach, nutrition and settings stay available in folded panels. Responsive for desktop, tablet and phone. Every panel shows real state (health check, device token, voice session, live reminders) or says it is not connected; there are no demo metrics, and the readiness gauge counts four real checks only. Checked in headless Chrome at 1600, 1024 and 390 px wide. Real microphone, model and AWS behaviour are untested.
- After pressing Interrupt, audio of the old reply that is still in flight is now dropped until that turn ends (turn_complete or interrupted, or 5 s). Before, late chunks restarted playback and the UI said "speaking" next to "interrupted". Checked in headless Chrome with a fake session; real-model timing is untested.
- Fixed the page script, found by running it in a real headless Chrome: `index.html` called `$("voiceStop").addEventListener`, but no element had that id, so the inline script threw during load and the live voice Stop/Interrupt controls never worked. Added the missing button and a test that every id the scripts look up exists in the page.
- Fixed `/static/live_voice.js` returning 404 (nothing served it), so the live voice client never loaded. Both `app.main` and `app.main_enhanced` now serve it. `app.main_enhanced` (used by the Dockerfile and `run_enhanced.py`) did not include the live voice router at all; it does now.
- Removed a stray literal `\n` shown on the page. The approval prompt now sits under the live voice status line.
- Live voice can ask to create a reminder (`create_reminder`). The server holds the call and sends an `approval_request`; the browser shows Approve/Deny. Only an exact `approve: true` for the matching request id runs it. Deny, a wrong id, a 60 s timeout (`JARVIS_LIVE_APPROVAL_TIMEOUT_SECONDS`), a disconnect, or bad arguments all leave data unchanged. One approval can wait at a time. Tested with a fake session and the client source; not run against the real Live API or a real browser.
- Browser playback queue is capped at 20 s ahead so audio cannot build up lag on a slow device.
- Live voice can now call three read-only tools (current time, open reminders, saved memories). Calls are run server-side, restricted to an allow-list, and anything else is refused. Voice cannot add or change reminders, memories, files or devices. The tool-call wiring was written against the installed google-genai types and tested with a fake session; it has not been run against the real Live API.
- Live voice session guardrails: maximum session length (default 900 s), idle timeout (120 s, pings do not count), per-minute audio volume cap (1.5x real time) and a concurrent-session cap (2). Override with `JARVIS_LIVE_MAX_SESSION_SECONDS`, `JARVIS_LIVE_IDLE_TIMEOUT_SECONDS`, `JARVIS_LIVE_MAX_AUDIO_BYTES_PER_MINUTE`, `JARVIS_LIVE_MAX_CONCURRENT_SESSIONS`.
- Added WebSocket flow tests for live voice against a fake Gemini client (ticket rejection, event forwarding, bad frames, rate limit, idle timeout, session cap). These do not prove behaviour with the real Live API or a microphone.
- Fixed `jarvis_daemon.py` and `run_enhanced.py`, which had escaped triple quotes and failed with SyntaxError.
- Tools that need approval now fail closed: with no confirmation callback they do not run. CLI chat now asks on the terminal before running them.
- Shell classifier no longer treats chained, piped, redirected or substituted commands as safe.
- CI now compiles every Python file and lints for syntax errors and undefined names. (The earlier lint-job claim in this file was not backed by the workflow.)
- Raised dependency floors to versions with no known advisories at the time of the audit: cryptography>=50.0, pillow>=13.0, pyopenssl>=26.4, pytest>=9.0.3, pytest-asyncio>=1.3.
- Added AWS DevOps tools: offline reviewers for Terraform, Dockerfiles, GitHub Actions/Jenkinsfiles and IAM policies, troubleshooting runbooks (ECS, EKS, Terraform locks, Jenkins, ALB, IAM), `aws_read` (read-only AWS CLI) and `aws_change` (always asks first). Not tested against a real AWS account.
- Reworked the browser dashboard into a voice-first JARVIS command centre with a responsive layout, animated assistant orb, visible listening/thinking/speaking/ready states, and explicit voice controls.
- Added transcript-first capture: speech recognition displays interim/final text for review and does not automatically submit a dictated phrase.
- Added voice cancellation and stop-speaking controls, plus reduced-motion accessibility support.
- Added real-time voice integration plan and physical-device acceptance checklist; the new interface does not claim full-duplex audio until the Live API session path is implemented and verified.
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
Full-duplex low-latency voice across browser and Android, production per-device authentication and revocation, reliable cross-device/recurring notifications, and secure public deployment remain unfinished. Use the feature status and milestone documentation for exact current boundaries.
