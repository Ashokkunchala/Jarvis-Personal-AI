FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user; only /app/data needs to be writable.
RUN useradd --create-home --uid 10001 jarvis \
    && mkdir -p /app/data \
    && chown -R jarvis:jarvis /app

USER jarvis

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Inside the container the app must listen on all interfaces so a published
# port works. Never publish it beyond 127.0.0.1 on the host (see compose).
CMD ["uvicorn", "app.main_enhanced:app", "--host", "0.0.0.0", "--port", "8000"]
