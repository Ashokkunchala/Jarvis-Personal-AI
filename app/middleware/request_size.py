"""Bound HTTP request bodies for API routes before framework parsing."""

from __future__ import annotations

from starlette.responses import JSONResponse

DEFAULT_API_BODY_LIMIT = 1_048_576


class RequestBodyLimitMiddleware:
    """Reject API bodies above a fixed limit, including chunked requests."""

    def __init__(self, app, max_bytes: int = DEFAULT_API_BODY_LIMIT):
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                if int(raw_length) > self.max_bytes:
                    await self._too_large(scope, receive, send)
                    return
            except ValueError:
                pass  # The ASGI server or body reader will reject malformed framing.

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                await self._too_large(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _too_large(self, scope, receive, send):
        response = JSONResponse(
            {"detail": f"Request body exceeds the {self.max_bytes}-byte API limit."},
            status_code=413,
        )
        await response(scope, receive, send)
