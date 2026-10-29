# JARVIS real-time voice and interface

## What is implemented on the feature branch

- Browser dashboard with responsive JARVIS orb, ready/listening/thinking/speaking states, text chat, transcript view, and explicit live voice start/stop/interruption controls.
- Browser Live Voice client that requests microphone access after a user click, down-samples audio to 16 kHz PCM16, streams frames to the backend, and plays returned 24 kHz PCM audio.
- Default Live Voice profile uses Gemini's `Charon` prebuilt voice for a composed, lower-register assistant style. Override with `GEMINI_LIVE_VOICE` in `.env` if your enabled model supports another prebuilt voice. This is an original JARVIS-inspired voice profile, not a copy of a film actor's exact voice.
- FastAPI WebSocket route at `/api/live-voice`. It authenticates the configured bearer token, checks browser Origin against configured CORS origins, keeps the Gemini API key on the server, validates payload sizes, opens a Gemini Live session, forwards audio/text/transcripts, and closes the session on disconnect.
- Typed chat remains available as a fallback. Voice-session model tool calls are not permitted to execute device actions.

## Not yet proven / not production-ready

- The Live API model configured in `app/live_voice.py` is a preview model ID. Confirm current availability and API account access using official Gemini Live documentation before relying on it; do not assume all API accounts have access.
- The WebSocket query currently carries the configured bearer token because browser WebSocket APIs cannot attach an Authorization header. Treat URLs as sensitive, keep server logs from recording query strings, and replace this compatibility path with short-lived one-time session tickets before public use.
- The audio client and server protocol have been committed but still require a live API-key smoke test and browser microphone/playback tests. They have not been confirmed on a physical Android phone.
- The browser uses Web Audio `ScriptProcessorNode` for a starter implementation. A production client should move capture to AudioWorklet, add bounded queues/backpressure, better resampling, and explicit audio focus/cancel handling.
- User speech may interrupt model playback only after the backend/model reports interruption or the user taps **Interrupt JARVIS**. The current stop control sends an interrupt instruction; confirm actual barge-in behavior with the Live API session.
- Live audio responses and transcripts are streamed to the page. The raw audio is not explicitly saved by the client, but audio is sent to the configured Gemini API as part of the Live session.
- Android remains tap-to-speak via system speech recognition + system TTS; native continuous Live audio is not yet connected to the WebSocket.

## Security expectations

- Never expose the Gemini key in browser JS or Android resources.
- Do not expose this shared-token prototype through a public tunnel.
- Before a remote deployment, implement per-device pairing/revocation, one-time live session tickets, rate/time/token budgets, request quotas, session limits, safe error responses, audit logs with token redaction, TLS, allowed origins, and backup/restore.
- No hidden microphone or automatic background recording. Show when audio is being captured and provide an obvious stop button.
- The live audio route deliberately does not execute model tool calls. Device actions require the separate JARVIS confirmation workflow.

## Acceptance checklist

- [ ] Python unit/API suite passes in the latest PR workflow.
- [ ] Android debug APK build passes in the latest PR workflow.
- [ ] Browser: microphone denied / allowed / unavailable paths tested.
- [ ] Live API: current model is available, setup handshake succeeds, and a real voice turn completes.
- [ ] Browser: PCM input and output sound correct on current Chrome and Edge.
- [ ] Browser: stop releases the microphone and stops queued audio; interruption behavior is verified.
- [ ] WebSocket: invalid token, disallowed origin, oversized audio, malformed base64, and provider timeout paths tested.
- [ ] Physical Android 14 device: HTTPS, token storage/clear, TTS, permission denial, and typed fallback tested.
- [ ] Native Android full-duplex audio transport implemented and tested.
- [ ] Short-lived session tickets replace tokens in WebSocket query parameters.
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
