# JARVIS real-time voice and interface

## What is implemented on the feature branch

- Browser dashboard with responsive JARVIS orb, ready/listening/thinking/speaking states, text chat, transcript view, and explicit live voice start/stop/interruption controls.
- Browser Live Voice client that requests microphone access after a user click, down-samples audio to 16 kHz PCM16, streams frames to the backend, and plays returned 24 kHz PCM audio.
- Default Live Voice profile uses Gemini's `Charon` prebuilt voice for a composed, lower-register assistant style. Override with `GEMINI_LIVE_VOICE` in `.env` if your enabled model supports another prebuilt voice. This is an original JARVIS-inspired voice profile, not a copy of a film actor's exact voice.
- FastAPI WebSocket route at `/api/live-voice`. It authenticates the configured bearer token, checks browser Origin against configured CORS origins, keeps the Gemini API key on the server, validates payload sizes, opens a Gemini Live session, forwards audio/text/transcripts, and closes the session on disconnect.
- The server caps each audio frame at 64 KiB, cumulative input per session at 16 MiB, and each session at 10 minutes.
- The backend permits at most two simultaneous Live Voice provider sessions per client IP in a single process; excess sessions are rejected with a clear limit status. This is a local guardrail, not a distributed or provider-account usage quota.
- Typed chat remains available as a fallback. Voice-session model tool calls are not permitted to execute device actions.

## Not yet proven / not production-ready

- The configured model `gemini-3.8-live` is listed as a stable Gemini Live model. The owner's API account still needs a real handshake test; model listing alone does not prove account access ([official model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live)).
- The browser exchanges its bearer token for a single-use, 60-second WebSocket ticket because browser WebSocket APIs cannot attach an Authorization header. The in-memory ticket store is process-local; keep the server private and logs free of query strings.
- The audio client and server protocol are served through the backend's `/static` route and have bounded per-frame and per-session input budgets. They still require a live API-key smoke test and browser microphone/playback tests; they have not been confirmed on a physical Android phone.
- Browser capture uses an AudioWorklet to resample into bounded 40 ms PCM blocks; the Android client sends 40 ms blocks. The browser and Android clients cap their outbound audio queues, and the server caps total session audio. Google recommends 20–40 ms Live API audio chunks; current browser/device quality, backpressure under sustained congestion, and audio focus still need hands-on verification ([Live API best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices)).
- Browser input/output transcripts are shown in the Live Voice transcript panel. Unexpected transport/server disconnects (1006/1011/1012) trigger at most two delayed reconnect attempts with fresh one-time tickets; authentication, origin, normal stop, and provider-configuration failures do not auto-retry. The visible Stop control cancels a pending retry. This recovery path still needs browser/device testing.
- User speech may interrupt model playback only after the backend/model reports interruption or the user taps **Interrupt JARVIS**. The current stop control sends an interrupt instruction; confirm actual barge-in behavior with the Live API session.
- Live audio responses and transcripts are streamed to the page. The raw audio is not explicitly saved by the client, but audio is sent to the configured Gemini API as part of the Live session.
- The Android client now has an explicit start/stop/interrupt Live Voice controller using a one-time ticket, `AudioRecord` 16 kHz PCM input, and `AudioTrack` 24 kHz output. It runs only while the visible activity is active; its build, permission flows, and audio behavior still need device verification.

## Security expectations

- Never expose the Gemini key in browser JS or Android resources.
- Do not expose this shared-token prototype through a public tunnel.
- Before a remote deployment, implement per-device pairing/revocation, rate/time/token budgets, request quotas, session limits, safe error responses, audit logs with token redaction, TLS, allowed origins, and backup/restore.
- No hidden microphone or automatic background recording. Show when audio is being captured and provide an obvious stop button.
- The live audio route deliberately does not execute model tool calls. Device actions require the separate JARVIS confirmation workflow.

## Acceptance checklist

- [ ] Python unit/API suite passes in the latest PR workflow.
- [ ] Android debug APK build passes in the latest PR workflow.
- [ ] Browser: microphone denied / allowed / unavailable paths tested.
- [ ] Live API: current model is available, setup handshake succeeds, and a real voice turn completes.
- [ ] Browser: PCM input and output sound correct on current Chrome and Edge.
- [ ] Browser: stop releases the microphone and stops queued audio; interruption behavior is verified.
- [x] WebSocket: invalid token is rejected and provider timeout is returned as a client error event (automated regression tests in `tests/test_ws.py`).
- [x] Rejected-origin and invalid-ticket WebSocket paths plus malformed/oversized audio-frame validation have regression tests.
- [ ] Physical Android 14 device: HTTPS, token storage/clear, TTS, permission denial, and typed fallback tested.
- [x] Native Android full-duplex audio transport implemented with visible microphone controls and session-ticket authentication.
- [x] Browser transcript display and bounded transient reconnect retries with a visible cancel/stop path are implemented; live browser behavior remains unverified.
- [ ] Build and test native Android audio on an Android 14 device, including permission denial, interruption, disconnect, and stop releasing microphone/speaker resources.
- [x] Short-lived one-time session tickets replace bearer tokens in WebSocket query parameters (local regression coverage; not a distributed ticket store).
- [ ] Device-action broker integrated only with visible confirmation and cancellation.
- [ ] Production deployment threat model and review complete.

## Run the existing app

Windows PowerShell from the repository root:

```powershell
# Check Python 3.11+, configure Charon, prompt for a Gemini key if needed,
# generate missing local secrets, and validate local settings.
.\\scripts\\setup-live-voice.ps1

# Create .venv and install/upgrade requirements-dev.txt (runtime + test dependencies).
.\\scripts\\setup-live-voice.ps1 -InstallDependencies

# Install dependencies, then start the backend.
.\\scripts\\setup-live-voice.ps1 -InstallDependencies -StartAfterSetup
```

The script checks Python 3.11+ and warns if Git is missing. With `-InstallDependencies`, it creates `.venv`, upgrades pip, and installs `requirements-dev.txt`. It edits only your local `.env`, which is ignored by Git. It cannot verify the Gemini model is enabled for your account or prove that microphone capture and audio playback work; test those in the browser after the backend starts.

If you prefer manual setup, use `.\\scripts\\setup-windows.ps1`, set `GEMINI_API_KEY`, `GEMINI_LIVE_MODEL`, `GEMINI_LIVE_VOICE=Charon`, and a random `JARVIS_API_TOKEN` in `.env`, then run `.\\scripts\\start-windows.ps1`.

Keep the backend local/private. Do not use a public tunnel until the security acceptance checklist is complete.
