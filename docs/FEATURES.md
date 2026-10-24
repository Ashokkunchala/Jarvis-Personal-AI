# Feature Status Matrix

Status meanings: Implemented means code exists in this repository; needs verification means it has not yet been confirmed on your device; planned means it is not implemented yet.

| Capability | Status | Details |
|---|---|---|
| Gemini chat backend | Implemented; needs live-key test | API key stays server-side; model configurable |
| Adaptive assistant personality | Implemented | Friendly, witty, calm, motivational and technical modes described in system instructions |
| Indian English / Telugu instructions | Implemented; needs language-quality testing | Auto, English, Telugu choices; code-switching requested in prompt |
| Conversation context | Implemented | Up to 20 previous messages sent with each request; not saved server-side |
| Responsive chat UI | Implemented | Served by FastAPI at `/` |
| Browser speech input | Implemented where supported; needs device test | User-initiated only, browser permission required |
| Browser text-to-speech | Implemented where supported; needs device test | Uses OS/browser voices, not Gemini audio |
| Optional local chat history | Implemented | Browser local storage only, opt-in |
| Local task checklist | Implemented | Browser local storage; no sync or notifications |
| Persistent cloud memory | Planned | Must include review/edit/delete and opt-in |
| Scheduled reminders and notifications | Planned | Current task checklist does not notify |
| Live web search / browser agent | Planned | No browsing tool connected yet |
| Android dedicated app | Planned | Not built or installed yet |
| Windows device-control agent | Planned | No shell or system-control endpoints exposed |
| Workout / nutrition journal | Planned | General coaching to be added with appropriate safeguards |
| Cloud deployment | Not ready | Authentication, rate limiting, and security review required |
| Automatic improvement loop | Partially designed | Roadmap exists; no self-modifying code agent is enabled |

Do not interpret a UI label or roadmap item as proof that a feature is production-ready.
