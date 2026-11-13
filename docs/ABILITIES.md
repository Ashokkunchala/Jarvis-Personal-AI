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
sandboxes, mock interviews and proactive learning reminders remain to build.

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
