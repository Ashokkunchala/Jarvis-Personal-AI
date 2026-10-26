# Changelog

## Unreleased
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
