# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Stage 1: build Python deps. PyAudio (via SpeechRecognition[audio]) needs a
# C compiler and the PortAudio headers, which python:3.11-slim does not ship.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# libc6-dev must be explicit: on current Debian slim images gcc no longer
# drags in the C standard headers, so Python.h compile fails with
# "fatal error: stdlib.h: No such file or directory".
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
        portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: runtime image. Only the PortAudio shared library is required here.
# ---------------------------------------------------------------------------
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Venv comes from the builder, so console scripts (uvicorn, alembic) keep
# working and the interpreter path /opt/venv/bin/python exists here too.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY . .

RUN mkdir -p /app/data /app/data/cache

RUN useradd --create-home --uid 10001 jarvis \
    && chown -R jarvis:jarvis /app/data
USER jarvis

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main_enhanced:app", "--host", "0.0.0.0", "--port", "8000"]
