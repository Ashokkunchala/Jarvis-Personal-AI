# JARVIS Abilities Blueprint

Source: the shared planning conversation (2026-11-13) where the full ability
set for Jarvis-Personal-AI was defined. Jarvis is one unified intelligence with
four identities - Personal Assistant, Friend, Mentor, and DevOps Professional -
across the Windows laptop and the Android phone.

## 1. Personal assistant - daily life management
- Daily planning and task prioritisation
- Reminders: meetings, bills, deadlines, activities
- Calendar: create, edit and cancel events with permission
- To-do manager: add, complete, postpone, track
- Notes: voice notes, meeting notes, personal notes
- Email: read, summarise, draft and send approved emails
- WhatsApp: draft messages through supported integrations
- Contacts search; travel research; shopping comparison
- Document manager: search, organise, summarise, create
- Expense tracker with monthly reports
- Personal dashboard: today's priorities, tasks, reminders
- Notifications to laptop and mobile

## 2. Friend - natural companionship
- Natural casual conversation; emotional awareness
- Jokes (including Telugu comedy), storytelling
- Music recommendations and control of supported apps
- English + Indian English + Telugu with natural code-switching
- Conversation memory; resume interrupted conversations
- Daily greetings, motivation, celebration of milestones
- Conversation modes: friendly, funny, professional, calm, motivational
- Natural voice with adjustable speed and tone

## 3. Mentor - personal technology trainer
- Subjects: Python/JS/TS, FastAPI/PostgreSQL, React/HTML/CSS,
  CI/CD (Jenkins, GitHub Actions, GitLab), AWS/Azure/GCP,
  Terraform/CloudFormation, Docker/Kubernetes/EKS/ECS, Linux/shell,
  ELK/Grafana/Prometheus, LLMs/RAG/agents/MCP, distributed systems,
  IAM/secrets/vulnerability management
- Teaching: explain beginner-to-advanced, daily learning schedules,
  hands-on labs, terminal-guided exercises, quizzes and coding tests,
  answer evaluation, weak-area detection, interview questions,
  mock interviews, progress tracking, practice projects, code review,
  certification study plans

## 4. DevOps professional
- Laptop automation: approved PowerShell/CMD/Bash, Linux administration,
  file management, git operations, code generation/review/debug,
  Python automation, Docker, Kubernetes, Terraform, Jenkins,
  GitHub Actions diagnostics, networking checks, system monitoring,
  security scans, backups
- AWS: EC2, EBS cleanup, S3 inventory and access analysis, IAM analysis,
  VPC/subnets/security groups, ECS/EKS, RDS, Lambda, CloudWatch,
  Cost Explorer, CloudFormation, AWS Backup, Secrets Manager,
  Security Hub and GuardDuty
- Kubernetes: cluster health, CrashLoopBackOff diagnosis, deploy/scale,
  services, ingress, Helm, storage, logs, RBAC audits, upgrades
- CI/CD: generate Jenkinsfiles and GitHub Actions workflows, build images,
  run tests, security scans, publish artifacts, deploy/validate/monitor,
  roll back after approval
- Incident/SRE: failure detection, abnormal resource usage, log analysis,
  metric/trace correlation, outage detection, root-cause analysis,
  incident reports, remediation, MTTR, SLO/SLA monitoring, postmortems

## 5. Android mobile assistant
- Voice assistant and wake word where Android permits
- Notifications, calls and SMS with permission, contacts
- Camera/gallery analysis, files, calendar, location reminders
- App launching, clipboard, battery/storage/network status
- Laptop connection: voice notes to laptop, remote approved commands,
  laptop health on phone, GitHub Actions failure and AWS cost alerts

## 6. Windows laptop control centre
- System monitoring: CPU, RAM, GPU, disk, battery, processes
- Application management: VS Code, PowerShell, browser, Docker Desktop
- Development: projects, code editing, tests, logs, docs, commits, PRs
- Remote control from Android with approvals

## 7. Smart memory
- Typed memory: personal, conversational, projects, technical, learning,
  tasks, work, context
- Long-term and short-term memory, semantic search, summarisation,
  conflict detection, correction, export, review and deletion,
  retention controls; secrets never stored in memory

## 8. Proactive Jarvis
- Morning briefing; low battery, high CPU and disk-full alerts
- Failed GitHub workflow notification with analysis
- AWS cost-spike investigation; vulnerability alerts
- Missed learning-session rescheduling; interview preparation
- Important-email summaries; deadline reminders; crash diagnostics
- User-defined schedules, thresholds and triggers

## 9. Research, browsing and automation
- Web search, documentation comparison, repository reading
- Product research; job search, JD analysis, resume matching
- Application preparation, LinkedIn drafts, YouTube summaries
- PDF extraction, technical reports, website monitoring
- Approved browser automation; confirmation before any submission

## 10. Health, fitness and lifestyle coach
- Workout planning, activity and sleep tracking, meal planning
- Hydration and meditation reminders, habit tracking
- Fitness progress reports and weekly wellness summaries
- General wellness support only - not medical advice

## 11. Security and privacy manager
- Secure API-key storage; encrypted phone-laptop channel
- Authenticated remote commands; role-based permissions
- Command allowlists, audit logs, file access restrictions
- Dependency scanning, login alerts, session management
- Device registration and revocation; emergency stop
- Permission levels: Read, Suggest, Execute, Critical

## 12. Operating modes
Personal, Friend, Mentor, DevOps, Developer, Research, System Admin,
Security, Fitness, Emergency.

## 13. Cinematic dashboard
Unified cinematic interface: greeting, system overview (Windows, Android,
cloud, AI intelligence) and quick actions. Navigation: Home, Voice,
Personal life, Friend, Learning, DevOps, Developer tools, AWS cloud,
Laptop control, Mobile control, Automation, Memory, Security, Settings.

## Architecture proposals (deployment still needs approval)
- Deployment: hybrid - local agents + cloud AI
- Autonomy: automatic safe tasks; approval for sensitive actions
- Voice: Indian English + Telugu
- Scope: complete Jarvis platform on branch `jarvis-cinematic-local-voice`
- Milestones: P0 stabilise -> P1 security/approval -> P2 orchestrator ->
  P3 personal + friend -> P4 mentor -> P5 DevOps agent ->
  P6 Windows + Android integration -> P7 hybrid hardening


## Implemented foundation

See [Local execution safety](EXECUTION-SAFETY.md) for invocation-bound one-time
approvals, the persistent emergency stop and redacted audit controls in the
existing tool registry. Remote actor/device authorization is not implemented.

## Offline mentor starter engine

The existing brain/CLI/TUI tool registry includes six mentor tools:
`mentor_catalog`, `mentor_lesson`, `mentor_quiz`, `mentor_submit`,
`mentor_plan` and `mentor_progress`. Ask Jarvis to list mentor lessons, then
choose the lesson IDs and a local YYYY-MM-DD start date for a study plan.

Each of the twelve domains has one introductory lesson, a manual practice
exercise and an objective multiple-choice checkpoint with feedback. Plans
save one topic per day for a chosen 10-120 minute study period. Progress
survives restart, tracks the latest checkpoint result and attempt count,
and lists weak areas and overdue unpassed sessions. Replanning updates the
selected topics without deleting other sessions.

Data stays in `~/.jarvis/mentor.db` (override with `JARVIS_MENTOR_DB`). No lab
commands are executed, no calendar event is created, and no notification is
sent. These are starter checkpoints, not complete courses, coding evaluation,
certification preparation or evidence of mastery. Advanced lessons, coding
sandboxes and proactive learning reminders remain to build. Mock-interview
practice has since been added as described below.

## Offline cloud evidence reviews

Three additional DevOps tools run without AWS credentials or network calls:

- `review_security_groups(path)`: reviews a local `describe-security-groups`
  JSON export for explicit world (`/0`) inbound rules, including IPv6,
  all-protocol ingress, SSH/RDP and broad port ranges. It does not evaluate
  combined CIDRs, prefix lists, referenced groups, routing or actual reachability.
- `review_terraform_plan(path)`: summarizes a local Terraform plan JSON export
  (format 1.x), counts delete/replacement/state-removal actions and warns about
  unknown action types or errored/incomplete plans. Attribute values, variables,
  outputs and imports are not returned. This is not approval to apply.
- `analyze_daily_costs(daily, currency, complete_days, increase_percent=50,
  minimum_increase=5)`: compares the latest supplied complete daily total with
  up to seven prior daily totals. Supply at least four consecutive days in a
  single currency, with explicit zero-cost days. Values use decimal arithmetic.
  This is a simple threshold check, not AWS's ML anomaly detection or a final bill.

Example requests: "Review my exported security-groups.json for public ingress",
"Summarize deletions in my local plan.json without exposing values", or
"Compare these complete daily USD costs and flag increases over 50% and $5".

The two file reviews accept existing UTF-8 `.json` files up to 2 MB. Raw plan
attributes stay local rather than entering the tool's event arguments. No AWS
calls, Terraform commands, changes, alerts or deployments are performed. Findings
are review aids based on supplied evidence, not a complete security audit.

Reference formats checked against provider documentation:
- https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API%5FIpPermission.html
- https://developer.hashicorp.com/terraform/internals/json-format
- https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html

## Opt-in proactive local checks

`proactive_configure(metric, threshold, enabled=false)` saves a resource rule.
Metrics are `cpu`, `memory`, `disk` (system volume) and `battery`. New rules
are disabled. To opt in, ask Jarvis to enable the chosen rule. Enabled rules
are checked roughly once a minute while the backend is running. Battery
alerts fire below the chosen percentage when unplugged; other metrics fire
at or above the threshold. Unknown or unavailable samples are ignored.

`proactive_rules` lists settings. `proactive_alerts` reads the local inbox,
and `proactive_acknowledge(alert_id)` marks an alert reviewed. Events appear
on threshold crossings and recovery, not on every poll. Two percentage points
of hysteresis reduce boundary noise. State persists across backend restarts;
history keeps the newest 500 events, with the newest 100 shown per read.
Set `JARVIS_PROACTIVE_DB` to override `~/.jarvis/proactive.db`.

The existing backend scheduler now also checks saved daily briefing jobs
roughly once a minute. This closes the gap between saving a briefing schedule
and actually generating it automatically while the backend runs. No briefing
job is created automatically; the existing briefing schedule/status/cancel
controls still apply. Generated briefings stay in the personal database.

These checks do not send desktop notifications, phone pushes, messages or
email; the inbox must be reviewed through Jarvis. They do not stop processes,
clean disks, change system settings, or continue when the backend is stopped.
Briefing catch-up follows each saved job's existing policy. Terminal-only
sessions still need the backend or the manual `jarvis briefing run-due` command.

## Task correction, priority and postponement

`edit_commitment(commitment_id, text?, due_at?, clear_due?, priority?)` extends
the existing commitment tracker rather than creating another to-do database.
It corrects an open task, postpones its due time, removes its due time, or sets
priority from 1 (highest) to 5 (lowest). Existing tasks default to priority 3.
Lists prioritize open work, then due times. Completed tasks cannot be silently
reopened by this operation. Recording or editing a task never marks work done.

New due dates require an explicit timezone and are normalized to UTC. Overdue
comparisons now use actual instants rather than comparing timezone-offset strings.
Existing ambiguous dates stay visible with a warning and are not treated as
reliable follow-ups until corrected. No external calendar, notification or
message is created by editing a commitment.

## Saved-memory search and retention controls

`memory_search_saved(query?, category?, include_expired=false)` searches the
existing backend personal-memory store using literal text and exact category.
It is separate from the existing `memory_search` document-index tool, which
keeps its citations and folder controls. This is not vector/semantic search.

`memory_set_expiry(memory_id, expires_at?)` sets a timezone-qualified expiry;
omitting the expiry removes it. Expired rows are excluded from future backend
chat context and normal saved-memory search. Existing memories have no expiry
until the user sets one. Editing text through the API preserves expiry unless
an explicit new expiry or null is supplied.

`memory_retention_status` shows expired IDs/counts. `memory_purge_expired`
requires explicit confirmation and deletes only expired rows. Expiration alone
does not erase storage: review APIs and exports still contain expired rows
until purged. Purging is not secure disk erasure and does not change backups,
exports, previous messages or document indexes. Already-sent model context
cannot be recalled. No expiry or purge is scheduled automatically.

The authenticated existing memory API accepts `expires_at` on creation/update
and literal `query`, `category`, and `include_expired` filters on listing.
The web review list still includes expired rows by default so users can correct
or delete them. These controls cover the backend personal-memory store, not
a separate CLI conversation-history store.

## Resumable mock-interview practice

`mentor_interview_start(lesson_ids)` creates a local practice session of 1-12
chosen topics. `mentor_interview_resume(session_id)` shows the current question.
`mentor_interview_answer(session_id, position, answer)` records the user's answer
and returns reference concepts, a manual practice task and a source link for
conversational feedback. `mentor_interview_history` reviews saved answers.
Sessions survive restart. Stale/replayed/out-of-order answers are rejected,
including concurrent submissions to the same question.

Every starter lesson, quiz and interview topic now carries a checked technical
reference link. Interview prompts go beyond the multiple-choice checkpoints
by asking for reasoning, tradeoffs, verification and safe operational boundaries.
There is one scenario per domain. This is practice, not a hiring assessment or
certification exam. Free-text answers are not automatically graded: the tool
returns reference concepts for honest discussion rather than inventing a score.
Answers stay in the local mentor database; do not include credentials. No answer
text or practice command is executed. No recording or microphone capture is added.

## Operating modes in the shared brain and web chat

The requested ten modes are available: Personal, Friend, Mentor, DevOps,
Developer, Research, System admin, Security, Fitness and Emergency. Existing
Assistant, Teacher, Storyteller and Health guide styles remain available too.
The web Style selector exposes all fourteen choices. CLI/TUI mode-selection
tools persist them through the existing mode store; the backend chat uses the
same overlay definitions. Mode changes specialize the conversation workflow,
not tool access, account permissions or autonomous execution rights.

Emergency mode is calm triage and guidance, not an emergency dispatch service
or automatic remediation. It does not activate a technical emergency stop by
itself. Fitness remains general wellness, not diagnosis or treatment. New modes
are not yet added to the native Android app's separate fixed selector; the
responsive web interface exposes them on mobile browsers. No live audio or
real-device testing is claimed by this change.


## Offline Kubernetes pod triage

`review_kubernetes_pods(path, restart_threshold=3)` reads a local core-v1 Pod,
PodList or Pod-only List JSON export (2 MB, at most 500 Pods). It reports Pod
phases and explicit readiness conditions, current and previous container
states, cumulative restart counts, known crash-loop/image-pull/OOM signals,
nonzero exits, unschedulable signals and deletion timestamps. Init and
ephemeral container statuses are reviewed separately from app containers.

The output distinguishes phase from readiness: a Running Pod is not assumed
to be ready, missing conditions stay unreported, completed workloads are not
flagged merely for being unready, and a deletion timestamp is not treated as
a failure by itself. Pagination tokens trigger a partial-list warning.
Cumulative restarts are not a restart rate, CrashLoopBackOff is not a root
cause, and exit code 137 alone is not labelled OOMKilled. Suggested next checks
are review guidance, never executed commands or automatic remediation.

Raw logs, free-form messages, environment, annotations, images and other spec
values are omitted. Supply the export path rather than pasting raw values
into the conversation. Pod/container identifiers remain in the result. The
snapshot's freshness and completeness are unknown; this is not live cluster
health, node/service/controller analysis, or a security audit. No credentials,
cluster connection, deploy, scale, restart or other mutation is performed.

Reference checked: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/

## Weekly wellness record review

`weekly_wellness_review(start_day, timezone)` reviews seven calendar days from
an explicit YYYY-MM-DD date in an IANA timezone (for example Asia/Kolkata).
It reads existing local habit logs and backend workout records, without
creating another tracker. Habit results show logged dates and unlogged dates;
workout results show session/minute totals by activity and day. A partial
current week is clipped at now. Future workout times, malformed records and
naive workout timestamps are excluded with counts. Timestamped workouts use
the requested timezone, including DST transitions. Habits keep their original
logged calendar dates rather than pretending to have timestamp precision.

Unlogged is not missed, and no record is not evidence of inactivity. No goal
frequency, fitness score, diagnosis, medical advice, wearable/sleep/nutrition
data, notification or automatic plan is inferred. Workout notes and individual
timestamps are not returned. Habit names and activity labels are user-provided
data. Source reads are separate rather than an atomic cross-store snapshot.
At most 10000 recent rows per source and 100 groups per breakdown are reviewed;
truncation is flagged. Missing stores/tables are flagged and not created or
migrated. Package installation now includes tzdata, matching requirements.txt,
so IANA timezone data is available on Windows too. No real-device test claimed.


## Review and reschedule overdue learning sessions

`mentor_reschedule_preview(start_date)` proposes new one-topic-per-day dates
for overdue sessions whose latest starter checkpoint is not passed, skipping
other occupied plan dates. Previewing never changes a saved date.
`mentor_reschedule_session(lesson_id, expected_date, new_date)` applies one
chosen proposal, preserving its duration and all answers/other sessions. It
rejects changed plans, replayed proposals, newly passed checkpoints, occupied
dates and past destinations. Concurrent moves cannot claim the same target
date through this operation.

Dates use the computer's local calendar, matching the existing study plan.
Overdue means an unpassed scheduled checkpoint, not evidence that the user
did no studying. Neither operation creates external calendar events, sends
notifications, changes interview progress or enables automatic rescheduling.
Re-check the preview when the plan or checkpoint results change.
