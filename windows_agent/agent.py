"""Opt-in Windows helper: status and allow-listed URL opening only.

Run locally only. This agent intentionally exposes no shell/PowerShell endpoint.
"""
import hmac
import os
import platform
import webbrowser
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="JARVIS Windows Companion Agent", version="0.1.0")


def authorize(authorization: str | None = Header(default=None)):
    expected = os.getenv("JARVIS_AGENT_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="Configure JARVIS_AGENT_TOKEN (32+ characters).")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid agent token.")


class OpenUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    confirmed: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "agent": "jarvis-windows"}


@app.get("/v1/status")
def status(_=__import__("fastapi").Depends(authorize)):
    return {"platform": platform.platform(), "python": platform.python_version(), "actions": ["open-approved-url"]}


@app.post("/v1/open-url")
def open_url(request: OpenUrlRequest, _=__import__("fastapi").Depends(authorize)):
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="User confirmation is required before opening a URL.")
    parsed = urlparse(request.url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Only credential-free HTTPS URLs are allowed.")
    allowed = {x.strip().lower() for x in os.getenv("JARVIS_ALLOWED_URL_HOSTS", "google.com;github.com;youtube.com").replace(",", ";").split(";") if x.strip()}
    host = parsed.hostname.lower()
    if not any(host == domain or host.endswith("." + domain) for domain in allowed):
        raise HTTPException(status_code=403, detail="This domain is not in JARVIS_ALLOWED_URL_HOSTS.")
    # This opens a normal browser tab. No downloaded content or command is executed.
    opened = webbrowser.open(request.url, new=2)
    if not opened:
        raise HTTPException(status_code=502, detail="The operating system could not open the URL.")
    return {"opened": True, "host": host}
