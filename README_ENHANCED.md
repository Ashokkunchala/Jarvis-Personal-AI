# JARVIS Personal AI - Enhanced Edition

A production-grade, Gemini-powered personal assistant with advanced security, intelligence, and features.

## ?? What's New in v0.4.0

### Security & Authentication
- **Per-device token management** - Issue, revoke, and track multiple devices
- **Token hashing** - Secure storage with SHA-256
- **Centralized auth** - Unified dependency injection
- **Rate limiting** - Protect against abuse with SlowAPI
- **Security headers** - XSS, clickjacking, and content-type protection
- **Audit logging** - Track all authentication events

### Architecture & Reliability
- **Enhanced configuration** - Pydantic validation with type safety
- **Gemini service layer** - Retry logic, fallbacks, timeouts
- **Structured logging** - Better observability
- **Docker support** - Containerized deployment
- **Database migrations** - Alembic for schema management
- **Health checks** - Detailed system status

### Features
- **Snooze reminders** - Postpone reminders on demand
- **Tags for memories** - Better organization
- **Research caching** - Faster repeated searches
- **Enhanced API docs** - Swagger UI at /docs
- **Metrics ready** - Prometheus integration prepared

## Quick Start

### Using Docker (Recommended)
`ash
# Copy environment file
cp .env.example .env

# Edit .env with your Gemini API key and tokens
nano .env

# Start with docker-compose
docker-compose up -d

# Open http://localhost:8000
`

### Using Python directly
`ash
# Setup
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your keys

# Run enhanced server
python run_enhanced.py
# or
uvicorn app.main_enhanced:app --reload
`

## API Endpoints

### Authentication
- POST /api/devices/issue - Issue new device token (master token required)
- GET /api/devices - List devices
- DELETE /api/devices/{device_id} - Revoke device

### Chat
- POST /api/chat - Standard chat
- POST /api/chat/stream - Streaming chat (SSE)

### Personal Data
- GET/POST/PUT/DELETE /api/memories - Manage memories with tags
- GET/POST /api/reminders - Manage reminders
- POST /api/reminders/{id}/complete - Complete reminder
- POST /api/reminders/{id}/snooze - Snooze reminder
- GET/POST /api/workouts - Track workouts
- GET /api/export - Export all data

### Health
- GET /health - Basic health check
- GET /api/health/detailed - Detailed system status (auth required)

## Development

`ash
# Install dev dependencies
make dev

# Run tests
make test

# Linting
make lint

# Format code
make format

# Database migrations
make migrate msg="description"
make upgrade
`

## Security Notes
- Always use strong random tokens (32+ characters)
- Keep server bound to localhost in development
- Use HTTPS in production
- Rotate tokens regularly
- Review audit logs

## License
See LICENSE file for details.
