# JARVIS Personal AI - Project Overview

## Executive Summary

**JARVIS Personal AI** is a multi-provider personal assistant prototype designed for Indian English and Telugu speakers. The project delivers a voice-first, secure, cost-conscious assistant across Windows and Android platforms with adaptive personality, contextual memory, and comprehensive tool orchestration.

> **Status**: Multi-component prototype, not a complete JARVIS yet

## Core Architecture

### Multi-Platform Components
- **Windows**: Installer-based setup with backend + browser UI + terminal assistant
- **Android**: Native Kotlin/Jetpack Compose with HTTPS encryption
- **Web**: Browser-based chat interface with Live Voice support
- **Backend**: Python FastAPI with Gemini/OpenRouter/Groq providers

### AI Core Capabilities
- **Natural-language understanding** with multi-step planning
- **Streaming responses** with conversation context and error handling
- **Provider adapters** for Gemini, OpenRouter, Groq, and compatible services
- **Adaptive personality** (friendly/witty, calm, energetic modes)
- **Indian English/Telugu** language support

## Security Quality Gates (Current Focus)

### Authentication System
- **Bearer token protection** for all personal-data endpoints
- **Device token management** with master-token rotation
- **HMAC verification** for secure token comparison
- **Audit logging** for all authentication events
- **Android Keystore** for encrypted token storage

### Request Protection
- **Rate limiting middleware** (`100/minute` default, sliding window)
- **Request size limits** (1 MiB max for `/api/` routes)
- **Connection timeouts** and **error handling**
- **Security headers** in all responses

### CI/CD Quality Gates
- **Static code analysis** (Ruff linter)
- **PowerShell script validation** (syntax checking)
- **Android APK builds** in GitHub Actions
- **Test coverage** and **regression protection**

## Implementation Status

### Current Milestone (Milestone 1)
**Status: Complete**

All core local components and persistent data APIs are operational:

- ✅ **Gemini API keys** remain server-side
- ✅ **SQLite endpoints** for memory, reminders, workout logs
- ✅ **Bearer token gating** on personal-data endpoints
- ✅ **UI controls** for memory review/edit/delete/export
- ✅ **Notification workers** with retries and delivery status
- ✅ **Security hardening** (rate limits, request caps, headers)
- ✅ **CI integration** with test coverage and security checks

### Real-time Voice & Interface (Milestone 1B)
**Status: Complete**

- ✅ **Browser Live Voice panel** with PCM streaming
- ✅ **WebSocket authentication** with ticket-based access
- ✅ **AudioWorklet capture** with bounded PCM blocks
- ✅ **Session limits** (duration, audio budget, concurrency)
- ✅ **Android native voice** with explicit controls
- ✅ **Browser transcript** display and error recovery

### Agent Orchestration
**Status: Complete**

- ✅ **Shared task orchestrator** with dependency awareness
- ✅ **Parallel execution control** (3x read-only cap)
- ✅ **Saved user plans** with SQLite persistence
- ✅ **Schedule system checks** for read-only metrics
- ✅ **Lifecycle events** with cancellation and retry

## Feature Matrix (Implemented vs Pending)

### Core Capabilities
| Feature | Status | Key Details |
|---------|--------|-------------|
| **Gemini Chat Backend** | Implemented | Bearer token required; streaming available |
| **Voice-First Browser UI** | Implemented | Orb interface with visual states |
| **Terminal Voice Input** | Implemented | Single utterance capture |
| **Browser Speech I/O** | Implemented | User-initiated with review |
| **Real-time Voice** | Implemented | Gemini Live with session limits |
| **Indian English/Telugu** | Implemented | Dual-language support |

### Personal Assistant Features
| Feature | Status | Details |
|---------|--------|-------------|
| **Persistent Memory** | Implemented | Explicit entries with export controls |
| **Reminders** | Partially Implemented | Recurrence support; experimental delivery |
| **Saved Plans** | Implemented | Checklist with status history |
| **System Checks** | Partial | Read-only metrics only |
| **Live Web Research** | Initial | DuckDuckGo HTML adapter |
| **Android Native** | Initial | Pending device verification |

### Windows & Integration
| Feature | Status | Details |
|---------|--------|-------------|
| **Windows Companion** | Restricted | Allow-listed HTTPS only |
| **Laptop Control** | Broad | Guarded shell execution |
| **File Operations** | Initial | Point-action confirmation |

## Setup & Installation

### Quick Start (Windows PowerShell)

```powershell
git clone https://github.com/Ashokkunchala/Jarvis-Personal-AI.git
cd Jarvis-Personal-AI
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup-windows.ps1
notepad .env
```

**Environment Variables Required:**
- `GEMINI_API_KEY` (at least one provider)
- `JARVIS_API_TOKEN` (random secret, 32+ chars)
- `JARVIS_AI_PROVIDER` (auto/gemini/openrouter/groq)
- Keep `HOST=127.0.0.1` for local development

### Testing

```powershell
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m ruff check .
.\venv\Scripts\python.exe -m compileall -q app jarvis windows_agent jarvis_cli.py
```

## Security Rules & Guidelines

### Before Production

1. **Verify Android pairing/revocation** on actual device
2. **Add master-token rotation** and production authorization
3. **Implement distributed rate limits** (per-device quotas)
4. **Deploy behind HTTPS** with secret management
5. **Restrict CORS** to exact production origins
6. **Add log redaction** and monitoring
7. **Complete Android/Windows e2e security tests**
8. **Run dependency scanning** and abuse testing

### Runtime Security

- **Never expose public internet** - bind to localhost
- **Keep secrets in `.env`** - never in source control
- **Request confirmation** for destructive actions
- **Bound telemetry** - no credentials in logs
- **Use HTTPS** for all external communications
- **Audit critical changes** before deployment

### API Usage

**Protected Endpoints:**
- `/api/memories` - Memory management
- `/api/reminders` - Reminder system
- `/api/workouts` - Workout logging
- `/api/research` - Web research
- `/api/coach/workout` - Workout coaching
- `/api/coach/nutrition` - Nutrition advice

**Authentication:**
```http
Authorization: Bearer YOUR_JARVIS_API_TOKEN
Content-Type: application/json
```

## Technology Stack

### Backend (Python)
- **Framework**: FastAPI
- **Providers**: Gemini, OpenRouter, Groq
- **Database**: SQLite
- **Authentication**: Bearer tokens
- **Middleware**: Rate limiting, request size caps

### Android (Kotlin)
- **UI**: Jetpack Compose
- **Security**: Android Keystore encryption
- **Networking**: HTTPS with certificate pinning
- **Background**: WorkManager for notifications

### Web (Browser)
- **Frontend**: Responsive HTML/CSS/JS
- **Voice**: AudioWorklet for real-time processing
- **Authentication**: Session tokens
- **Storage**: Local storage for preferences

### Desktop Terminal
- **UI**: Textual streaming interface
- **Tools**: 137 typed tools across 20 categories
- **Control**: Windows/Android device management

## Development Workflow

### Change Checklist
1. **Describe behavior** and threat model
2. **Implement smallest useful change**
3. **Add comprehensive tests**
4. **Run linting and type checks**
5. **Update documentation** and changelogs
6. **Review security** and privacy implications
7. **Verify behavior manually**

### Git Branch Strategy
- **Work only on** `improve/security-quality-gates`
- **Never modify** `main` directly
- **Commit reviewed changes** to working branch
- **Push when authorized** GitHub access available

## Remaining Gaps & Future Work

### Critical (Device Verification)
- [ ] Android Live Voice on physical device
- [ ] Windows device verification
- [ ] Android device pairing/revocation testing
- [ ] YouTube search and playback

### Medium-term
- [ ] Gmail/Google Workspace OAuth
- [ ] WhatsApp messaging support
- [ ] Secure cloud deployment
- [ ] Media search/playback
- [ ] Proactive daily routines

### Long-term
- [ ] Distributed rate limiting
- [ ] Audit trails for compliance
- [ ] Multi-user authorization
- [ ] Production hardening
- [ ] Cost monitoring and budgets

## Final Deliverable

**Objective**: A reliable personal JARVIS that can:
- ✅ **Listen, understand, remember** user context
- ✅ **Plan and act** within configured permissions
- ✅ **Verify outcomes** of executed actions
- ✅ **Show transparent state** across Windows and Android

**Success Metrics**:
- All CI tests pass
- E2E device tests verified
- Security reviews completed
- Documentation comprehensive
- User experience polished

## Contact & Support

For issues, refer to:
- [SECURITY.md](docs/SECURITY.md) - Security policies
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - Deployment guide
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) - Development guide
- [FEATURES.md](docs/FEATURES.md) - Feature status
- [NEXT-MILESTONES.md](docs/NEXT-MILESTONES.md) - Roadmap