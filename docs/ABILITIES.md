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

## Architecture decisions (approved)
- Deployment: hybrid - local agents + cloud AI
- Autonomy: automatic safe tasks; approval for sensitive actions
- Voice: Indian English + Telugu
- Scope: complete Jarvis platform on branch `jarvis-cinematic-local-voice`
- Milestones: P0 stabilise -> P1 security/approval -> P2 orchestrator ->
  P3 personal + friend -> P4 mentor -> P5 DevOps agent ->
  P6 Windows + Android integration -> P7 hybrid hardening
