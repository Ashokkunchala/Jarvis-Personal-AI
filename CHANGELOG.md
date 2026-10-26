# Changelog

# Unreleased
- Added authenticated server-sent-event streaming for browser chat and a stop control; retained the JSON endpoint for native clients.
- Updated the dashboard capability descriptions and API documentation to match shipped features.
- Added persistent reminder notification deduplication, capped exponential retries, and terminal delivery status for the optional Windows worker.
- Documented worker state-file behavior and its delivery-status limits.

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
Native Android app, Windows system-control agent, live web search, cloud memory, real notifications, production authentication, and public deployment remain future work.
