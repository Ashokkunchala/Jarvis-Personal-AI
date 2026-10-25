# Feature Status Matrix

Status meanings: **implemented** means code exists; **CI verified** means automated checks passed for a repository revision; **device verification pending** means it still needs a real local/device test. No item should be treated as production-ready solely because code exists.

| Capability | Status | Details |
|---|---|---|
| Gemini chat backend | Implemented; live-key test pending | API key remains server-side; chat requires configured bearer token |
| Adaptive assistant personality | Implemented | Friendly, witty, calm, motivational and technical modes in system instructions |
| Indian English / Telugu | Implemented; quality test pending | Auto, English, Telugu choices; actual speech voice depends on browser/OS |
| Conversation context | Implemented | Up to 20 previous messages per request; not stored server-side |
| Browser chat UI | Implemented | Includes session-only token entry, memory/reminder/workout forms, research and coaching panels |
| Browser speech input | Implemented where supported; device test pending | User-initiated only; browser permission required |
| Browser text-to-speech | Implemented where supported; device test pending | Uses OS/browser voices, not Gemini-generated audio |
| Explicit persistent memory | Implemented | SQLite API plus browser review/edit/delete/export controls; no automatic extraction |
| Reminders | Partially implemented | SQLite create/list/complete/delete and due polling; experimental Windows toast worker; no recurrence or Android notifications |
| Live web research | Initial implementation | Authenticated DuckDuckGo HTML adapter returns source links/snippets; not full browser automation |
| Native Android app | Initial implementation; CI build available | Kotlin/Compose, HTTPS health check, Android Keystore encrypted token, initial authenticated chat client; physical device test pending |
| Windows companion agent | Restricted initial implementation | Authenticated status endpoint and user-confirmed allow-listed HTTPS URL opening; no arbitrary shell/app/file control |
| Workout tracking | Implemented | SQLite activity log with list/delete |
| Workout/nutrition coaching | Implemented; live-key test pending | Authenticated Gemini endpoints with general-information safeguards |
| Secure cloud deployment | Not ready | Shared token only; per-device pairing/revocation, rate limiting, audit/monitoring and production hardening remain |
| Proactive daily routines | Partial | Reminder polling exists; recurring routines and cross-device delivery remain |
| Continuous improvement loop | Designed, not autonomous | Roadmap defines feedback, tests, review and release; no self-modifying code/deployment is enabled |

See [NEXT-MILESTONES.md](NEXT-MILESTONES.md) for remaining acceptance criteria.
