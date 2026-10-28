# Feature Status Matrix

Status meanings: **implemented** means code exists; **CI verified** means automated checks passed for a repository revision; **device verification pending** means it still needs a real local/device test. No item should be treated as production-ready solely because code exists.

| Capability | Status | Details |
|---|---|---|
| Gemini chat backend | Implemented with browser streaming and stop control; live-key test pending | API key remains server-side; JSON and SSE chat endpoints require configured bearer token |
| Voice-first browser interface | Initial implementation | Assistant orb, visible ready/listening/thinking/speaking states, responsive layout, transcript-first capture, stop listening and stop speaking controls |
| Terminal microphone input | Implemented as explicit one-utterance capture; device test pending | Click MIC to capture a single utterance, transcribe it with Google Speech Recognition (`en-IN`), and submit it to the Gemini tool loop. Audio is sent to the speech service; this is not offline transcription or an always-on wake-word listener. Install `SpeechRecognition[audio]` and a working microphone/PyAudio device. |\n| Browser speech input | Implemented where supported; device test pending | User-initiated only; browser permission required; transcript is displayed for review before sending |
| Browser text-to-speech | Implemented where supported; device test pending | Uses OS/browser voices, not Gemini-generated audio; playback can be interrupted |
| Full-duplex real-time voice | Not yet integrated end-to-end | Experimental Gemini Live client exists, but server-side session/authentication, current supported model/protocol, browser streaming, interruption, quotas and physical-device acceptance tests remain |
| Adaptive assistant personality | Implemented | Friendly, witty, calm, motivational and technical modes in system instructions |
| Indian English / Telugu | Implemented; quality test pending | Auto, English, Telugu choices; actual speech voice depends on browser/OS |
| Conversation context | Implemented | Up to 20 previous messages per request; not stored server-side |
| Responsive Command Center dashboard | Initial implementation; host/device test pending | `/dashboard` displays authenticated live CPU, RAM, disk, battery and process memory telemetry with auto-updating trend charts and alternate visualization types. Works in desktop and mobile browsers; it is not yet a native Android dashboard. AI provider connection status and agent/task activity are not reported as connected unless verified backend events are available. |
| Browser chat UI | Implemented | Includes session-only token entry, memory/reminder/workout forms, research and coaching panels |
| Explicit persistent memory | Implemented | SQLite API plus browser review/edit/delete/export controls; explicitly saved memories are bounded and included in chat context as untrusted profile data |
| Reminders | Partially implemented | SQLite create/list/complete/delete and due polling; experimental Windows toast worker; no recurrence or Android notifications |
| Live web research | Initial implementation | Authenticated DuckDuckGo HTML adapter returns source links/snippets; not full browser automation |
| Native Android app | Initial implementation; CI debug build has passed on earlier revision | Kotlin/Compose, HTTPS health check, Android Keystore token, authenticated chat, tap-to-speak and spoken replies, English/Telugu choice; physical-device test pending |
| Windows companion agent | Restricted initial implementation | Integrated with the local dashboard for authenticated status and user-confirmed allow-listed HTTPS URL opening; no arbitrary shell/app/file control |
| Laptop/Android tool core | Broad implementation, safety/device tests still needed | Typed risk-graded tool registry; risky actions must remain confirmation-gated |
| Workout tracking | Implemented | SQLite activity log with list/delete |
| Workout/nutrition coaching | Implemented; live-key test pending | Authenticated Gemini endpoints with general-information safeguards |
| Secure cloud deployment | Not ready | Shared-token prototype; per-device pairing/revocation, consistent rate limiting, audit/monitoring and production hardening remain |
| Proactive daily routines | Partial | Reminder polling exists; recurring routines and cross-device delivery remain |
| Continuous improvement loop | Designed, not autonomous | Roadmap defines feedback, tests, review and release; no self-modifying code/deployment is enabled |

See [NEXT-MILESTONES.md](NEXT-MILESTONES.md), [REALTIME-VOICE-AND-INTERFACE.md](REALTIME-VOICE-AND-INTERFACE.md) and [VERIFICATION-CHECKLIST.md](VERIFICATION-CHECKLIST.md) for remaining acceptance criteria.
