"""Best-effort per-process request throttling for local API routes."""

from __future__ import annotations

import math
import re
import threading
import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse

_RATE_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(second|minute|hour)s?\s*$", re.IGNORECASE)
_MAX_CLIENT_KEYS = 4096


class ApiRateLimitMiddleware:
    """Apply a configurable sliding-window limit to HTTP paths under ``/api/``."""

    def __init__(self, app, rate_limit: str = "100/minute", enabled: bool = True):
        self.app = app
        self.enabled = enabled
        match = _RATE_PATTERN.match(rate_limit)
        if not match:
            raise ValueError("rate_limit_default must look like '100/minute'.")
        self.maximum = int(match.group(1))
        if self.maximum < 1:
            raise ValueError("rate_limit_default must allow at least one request.")
        unit = match.group(2).lower()
        self.window_seconds = {"second": 1, "minute": 60, "hour": 3600}[unit]
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _consume(self, client_key: str) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            if client_key not in self._events and len(self._events) >= _MAX_CLIENT_KEYS:
                for key in list(self._events):
                    events = self._events[key]
                    while events and events[0] <= cutoff:
                        events.popleft()
                    if not events:
                        self._events.pop(key, None)
                if len(self._events) >= _MAX_CLIENT_KEYS:
                    return False, self.window_seconds

            events = self._events[client_key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.maximum:
                return False, max(1, math.ceil(events[0] + self.window_seconds - now))
            events.append(now)
            return True, 0

    async def __call__(self, scope, receive, send):
        if not self.enabled or scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_key = str(client[0]) if client else "unknown"
        allowed, retry_after = self._consume(client_key)
        if not allowed:
            response = JSONResponse(
                {"detail": "Too many API requests. Please wait before trying again."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
