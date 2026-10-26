# JARVIS real-time voice and interface plan

## Goal

Make JARVIS a voice-first personal assistant with an assistant-style interface across desktop and Android. The interface should clearly show microphone state, connection state, transcription, response playback, tool activity, and confirmation requests.

## Current baseline (code exists; not all behavior has been device-verified)

- Browser dashboard: streaming text responses; optional browser speech-recognition input; optional OS/browser text-to-speech output; English/Telugu language selection.
- Android: native Compose screen; tap-to-speak through Android speech-recognition intent; text-to-speech replies; token stored with Android Keystore.
- Desktop terminal: realtime Textual UI with streaming text and a tool activity log.
- Experimental Python Gemini Live client exists at `jarvis/core/voice/gemini_live_client.py`; its protocol, audio format, authentication, current model support, reconnect behavior, cancellation, and real-device audio path require verification before product use.
- The browser and Android production paths are not yet a unified, full-duplex low-latency voice session. Do not describe the prototype as having continuous live voice until integration and acceptance testing are complete.

## Target interaction design

1. **Idle / ready:** JARVIS orb, connection indicator, language preference and clear microphone button.
2. **Listening:** obvious visual indicator, elapsed/active status, user-visible transcript, and a one-tap stop/cancel control.
3. **Thinking:** stream text as it arrives and show safe status/tool activity without exposing secrets.
4. **Speaking:** show response text and playback state; allow interruption.
5. **Action approval:** display the exact action, target and effect. Require explicit approval for messages, purchases, file changes, settings, installs, shell commands, and infrastructure mutations.
6. **Offline / error:** show a useful explanation and a retry route; never silently pretend the audio request succeeded.

## Required engineering stages

### A. Web voice UI
- Keep current browser-compatible speech input as a fallback and make its limitations visible.
- Improve compact/mobile layout and provide an explicit voice mode, listening/speaking states, transcript review, cancel, and stop-speaking controls.
- Never access microphone without a user gesture and browser permission.
- Browser recognition and OS voices are a compatibility path, not proof of natural full-duplex audio.

### B. Real-time audio transport
- Choose and verify a currently supported Gemini Live model and SDK/protocol using official documentation before implementation; do not hardcode a guessed or preview model ID.
- Keep the provider API key server-side. Do not ship Gemini credentials in Android resources or browser JavaScript.
- Build a server-side session broker with short-lived per-session credentials, authentication, origin checks, session expiry, rate/time limits and safe disconnect.
- Stream audio frames with bounded buffering, interruption handling, reconnect/backoff, input/output format checks and cancellation.
- Avoid logging raw audio/transcripts by default. Explicitly disclose whether a provider receives audio and apply the user's consent choice.

### C. Android voice-first UI
- Retain user-initiated microphone permission and HTTPS-only backend traffic.
- Replace the current one-message screen with a conversation timeline, animated but accessible listening/speaking indicator, language picker, transcript review, stop/interruption control and connection state.
- Handle lifecycle changes, rotation, screen lock, offline state, audio focus, TTS shutdown and permission denial.
- Use WorkManager for deferrable routines only; do not promise unrestricted microphone access in the background.

### D. Personal-assistant skills
- Add a consent-based action router for reminders, memory, research, coaching, laptop status and Android status.
- Prefer read-only tools first. Require the user's confirmation for consequential actions.
- Make results visible in the conversation, including success/failure and a record of what action was attempted.
- Add recurring reminders and cross-device notifications only after durable scheduling, timezone, retry and duplicate-delivery tests.

## Acceptance checklist

- [ ] Browser: microphone denied / allowed / unavailable paths.
- [ ] Browser: transcript can be reviewed and cancelled before submission.
- [ ] Browser: stream appears incrementally, stop cancels cleanly, and retry works.
- [ ] Browser: voice output can be interrupted and does not start unless opted in.
- [ ] Android 14: permission request occurs on demand; permission denial leaves typed chat usable.
- [ ] Android: HTTPS, device token storage/clear, lifecycle changes, reconnect and TTS interruption tested on a physical phone.
- [ ] Live audio: only official supported protocol/model; no provider key embedded in client; session expiration and quota limits verified.
- [ ] Device action: all high-impact actions request confirmation; rejected/cancelled actions do not execute.
- [ ] Privacy: microphone state is visible; no hidden recording; raw audio retention is explicitly documented.
- [ ] CI: Python tests, lint and Android debug build pass.
- [ ] Manual test report and known limitations are recorded in `docs/VERIFICATION-CHECKLIST.md`.

## Run today's baseline

Windows PowerShell from the repository root:

```powershell
.\scripts\setup-windows.ps1
# Set GEMINI_API_KEY and a random JARVIS_API_TOKEN in the local .env
.\scripts\start-windows.ps1
```

Open `http://127.0.0.1:8000`. In the dashboard, choose the reply language, enter the configured token, and select **Save settings**. Tap **Speak** to capture one utterance; review its transcript and press Send. Enable spoken replies if desired. This is the current browser voice baseline, not continuous full-duplex voice.

Keep the backend local/private. Do not expose the current shared-token prototype through a public tunnel.
