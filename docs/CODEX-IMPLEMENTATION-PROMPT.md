# JARVIS Codex Implementation Brief

> Source of truth for the target vision and execution rules. This is a roadmap and engineering contract, not a claim that every listed capability already exists.

## Repository rules

- Repository: https://github.com/Ashokkunchala/Jarvis-Personal-AI
- Work only on `improve/security-quality-gates`.
- Never modify or merge into `main`.
- Inspect the working tree, current branch, recent commits, CI, architecture, and existing feature matrix before changing code.
- Preserve user data and local changes. Never use destructive Git commands such as `git reset --hard`.
- Reuse and improve existing components; avoid duplicate implementations.
- Commit and push reviewed changes to the working branch when authorized GitHub access is available. If push is unavailable, provide exact commands.
- Do not claim a feature or test passed without evidence. Mark hardware-dependent tests as pending if no device is available.
- Check the current stable Python and dependency compatibility before changing runtime versions; avoid unnecessary hardcoded minor versions.

## Product vision

Build one secure, cost-conscious, voice-first JARVIS assistant for Windows and Android. It should understand, plan, remember user-approved context, perform authorized work, verify outcomes, and visualize actual activity in a holographic command center.

## Required UI

Use the supplied holographic JARVIS references as the primary design: dark navy/black, neon cyan and turquoise accents, central reactor with layered HUD rings, compact system status, live intelligence feed, voice controls, agent cards, tool execution timeline, performance charts, memory and provider panels, and touch-friendly mobile layout.

Visualizations must reflect actual events:
- Voice: mic state, measured audio level, speech and playback state.
- AI: current request, model/provider reported by backend, streaming state and latency.
- Tools: name, status, duration, result and error.
- Research: sources and progress.
- Coding: repository, changed files, tests and Git state.
- DevOps: service/resource health, incidents and cost data.
- Agents: task assignments, dependencies, progress and failures.
- Devices: CPU, RAM, disk, battery, network and sync state where available.

Never use random or fabricated metrics, pretend-connected providers, fake agent activity, or misleading progress animations. Clearly mark unavailable and stale data.

## Capability scope

### AI core and providers
1. Natural-language understanding and multi-step planning.
2. Streaming responses, conversation context, error handling and bounded retries.
3. Provider adapters for configured Gemini, OpenRouter, Groq, and other compatible providers.
4. Model routing based on task, cost, latency, capability and privacy constraints.
5. Provider health, quota, latency and usage display only when measured or reported.

### Voice
6. Explicit microphone enable/disable, speech-to-text, text-to-speech, interruption and follow-up conversation.
7. Optional “Hey JARVIS” wake word, with explicit consent, visible listening state and immediate mute/stop.
8. Prefer local wake-word detection where practical; disclose all external audio processing.
9. Do not promise global or background listening where OS/browser restrictions prevent it.
10. Android microphone and foreground-service behavior must comply with platform policies.

### Memory and productivity
11. Short-term context and user-approved long-term memory.
12. Search, edit, export, delete, retention controls and backups.
13. Reminders, recurring routines, tasks, daily briefings and notifications.
14. Calendar, email and task-manager integrations only through authorized APIs/connectors.

### Windows and Android
15. Windows app/file/browser launching, approved shell commands, process and device monitoring, screenshots and safe system controls.
16. Native Android chat/voice, notifications, device pairing, permitted telemetry and secure synchronization.
17. Reuse the current Android application and backend; do not create a disconnected second product.
18. Respect OS permissions and background-execution limitations.

### Agents and automation
19. Shared task orchestrator and typed tool registry.
20. Specialized coding, research, browser, DevOps, security and productivity agents.
21. Task dependencies, bounded parallelism, status events, cancellation, retries and verified summaries.
22. Schedules and event triggers with audit trail, disable controls and persistent state.
23. Never claim an action completed unless the tool result confirms it.

### Coding, web and DevOps
24. Repository inspection, code edits, tests, documentation and Git workflows.
25. Browser/web research with source links and clear provenance.
26. AWS, Azure, GCP, Docker, Kubernetes, EKS/ECS, Terraform, CI/CD and observability integrations when configured.
27. Incident investigation, runbooks, security checks, resource inventory and cost optimization.
28. Read-only inspection first; explicit approval for destructive actions, production deploys, IAM changes, resource deletion or costly provisioning.

### Personal and career support
29. Resume and interview support, technical learning plans and progress tracking.
30. Workout, nutrition and wellness organization using user-provided or authorized data; do not present it as a substitute for professional care.
31. Budget, expense, shopping, travel and personal goal organization with approval before consequential transactions.

### Browser, search and research
37. Search the public web for user questions and return concise answers with source URLs, publication dates where available, and uncertainty notes.
38. Search YouTube for videos/channels and open the selected result visibly in the user's browser; distinguish searching results from actually playing a video.
39. Use browser automation only through a controlled, observable browser session. Show the current domain and actions; handle login/2FA by asking the user to take over rather than bypassing access controls.
40. Never state a page was opened, a video played, or a search completed unless the browser/tool result confirms it.

### Local computer operator
41. Open, focus, minimize, maximize and close supported Windows applications; launch URLs in a visible default browser window.
42. Search, read, create, edit, copy, move, rename, organize and delete user-authorized local files and folders. Preview source/destination and estimate affected items before bulk operations.
43. Type user-requested content directly into the focused app/editor when keyboard automation is available. Preserve line breaks and verify success where possible; do not default to telling the user to copy/paste.
44. For deletion, overwriting, bulk file changes, app uninstall, registry/system changes, or other destructive operations: show exact targets and obtain explicit confirmation. Prefer recycle-bin/trash over permanent deletion.
45. Install, update and uninstall applications using official package managers/installers where practical. Show package/source, scope and impact first; require approval for installs/uninstalls, administrator elevation and license/cost implications. Never silently disable security controls.
46. Provide visible notifications/warnings for failures, permission issues, security risks, battery/resource thresholds and task completion; support dismiss, snooze and notification preferences.
47. Check actual foreground-window focus and automation availability before typing. Never claim text was typed if the target window or keyboard action failed.

### Connected accounts and communications
48. Support Gmail, Google Calendar, Drive, Docs, Sheets, YouTube and other Google services through official OAuth/API scopes or user-authorized connectors. Request least-privilege scopes and show which account is connected.
49. For Gmail: search/list/read with granted scopes, draft replies, and compose messages. Sending, forwarding, deleting, sharing files, changing permissions or modifying calendar events requires a clear user request and confirmation at the point of impact.
50. For WhatsApp and other messaging apps: open the desktop/web app and prepare a draft in the intended conversation where supported. Sending a message, sharing an attachment or contacting a person requires explicit user authorization; never bypass login, QR pairing or platform protections.
51. Keep account tokens encrypted and out of logs; provide disconnect/revoke controls, account selection, and an audit history. If an official API does not support an action, explain the limitation instead of pretending it worked.

### Media and conversation
52. Find and play a requested song/video through a user-selected or authorized service, using visible controls and the service's own playback. Report when playback is blocked by login, subscription, region or autoplay settings.
53. Support original singing, humming or generated music when the configured model/service supports it; do not reproduce non-user-provided copyrighted song lyrics or imitate a living artist's voice. For existing songs, open/play through a legitimate service rather than copying protected audio.
54. Hold natural conversations, brainstorm ideas, compare options, offer constructive opinions and reflect on user-shared experiences. Clearly distinguish personal-assistant reasoning from actual lived experience or verified facts; JARVIS must not invent real personal memories or experiences.
55. Learn preferences only through transparent, user-controlled memory: explain what may be saved, allow review/edit/export/delete, and never covertly collect sensitive information.

### Self-development and debugging
56. Diagnose JARVIS and user-approved projects by inspecting logs, reproducing errors, identifying likely causes, writing fixes and adding regression tests.
57. For code changes, show a plan and diff, run relevant tests, summarize results, and work on a non-production branch. Ask before pushing changes, merging, releasing, deploying or modifying production systems.
58. Self-improvement means measured evaluation, proposing changes, testing in isolation and asking for approval—not uncontrolled self-modification, disabling safeguards, or silently changing permissions.
59. Offer proactive ideas and improvement opportunities grounded in observed evidence; label hypotheses, estimated savings and uncertain recommendations clearly.

### Security, observability and reliability
32. Authentication, least privilege, secure secret handling, encrypted communication and input validation.
33. Approval gates, audit logs, timeouts, cancellation, emergency stop and safe failure behavior.
34. Real CPU/RAM/disk/battery/network and process telemetry, AI latency, tool duration, task state and errors.
35. Keep telemetry retention bounded and never log credentials or sensitive audio.
36. Keep local development endpoints bound to localhost by default; do not deploy publicly without a security review.

## Implementation phases

Phase 1 — Audit and stabilize current repository, install, dependencies, CI and security.
Phase 2 — Stabilize AI providers, streaming, tool calls, permissions, errors and logs.
Phase 3 — Complete voice pipeline and optional wake-word feature.
Phase 4 — Connect the holographic dashboard to actual telemetry and runtime events.
Phase 5 — Complete persistent memory, reminders and routines.
Phase 6 — Integrate agent orchestration, browser research, coding and DevOps tools.
Phase 7 — Stabilize desktop app/file/typing automation with verified focus and approval-gated destructive actions.
Phase 8 — Add OAuth-based Google integrations and supported messaging workflows with least-privilege scopes and send/share confirmations.
Phase 9 — Add media search/playback, notifications, and transparent memory-based personal assistance.
Phase 10 — Complete Android experience, secure pairing, permitted sync, hardening and acceptance testing.

Adjust the order if dependency inspection justifies it. Maintain a working app after each phase.

## Required engineering workflow

1. Audit before editing; report current branch, dirty files, latest CI and relevant feature status.
2. Create a small, dependency-aware checklist.
3. Implement a coherent, testable slice rather than one giant rewrite.
4. Add/update unit, integration, UI, security and install tests appropriate to the change.
5. Run linting, type checks, tests, Android build and CI where available.
6. Diagnose and fix failures caused by the change.
7. Inspect the diff for secrets, unsafe defaults, regressions and misleading UI.
8. Update docs and the feature matrix.
9. Commit to `improve/security-quality-gates`; push only when access permits.
10. Report commit SHA, test commands/results, CI link/status, files changed, remaining blockers and exact manual verification steps.

## Feature status rules

Maintain `docs/FEATURES.md` with one of: `Implemented`, `Partially Implemented`, `Not Started`, `Blocked`, or `Tested`. Code existing is not the same as device-tested or production-ready. Document provider, hardware, account and credentials needed for tests.

## Final delivery criteria

Deliver working code, updated documentation, installation and recovery instructions, tests, and a prioritized list of remaining gaps. Never stop at a proposal when code changes are requested. If an integration or credential is unavailable, implement safe independent work and record the blocker without faking success.

**Final objective:** a reliable personal JARVIS that can listen, understand, remember, plan, act within permissions, verify its work, and show the truth about its state across Windows and Android.
