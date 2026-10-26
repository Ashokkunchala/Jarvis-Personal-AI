"""OpenAI-compatible chat providers for OpenRouter and Groq.

Secrets are loaded from server environment settings and are never returned to clients.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import httpx

from app.config import Settings

logger = logging.getLogger("jarvis.providers")

_PROVIDER_DETAILS = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openrouter_api_key", "openrouter_model"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "groq_api_key", "groq_model"),
}


def configured_provider_order(settings: Settings) -> list[str]:
    """Return configured providers, honoring a preferred provider while retaining fallbacks."""
    available = []
    if settings.gemini_api_key and settings.gemini_api_key != "replace_me":
        available.append("gemini")
    for name, (_, key_field, _) in _PROVIDER_DETAILS.items():
        key = getattr(settings, key_field, "")
        if key and not key.startswith("replace_"):
            available.append(name)
    preferred = settings.jarvis_ai_provider.strip().lower()
    if preferred in {"gemini", "openrouter", "groq"} and preferred in available:
        return [preferred] + [name for name in available if name != preferred]
    return available


def provider_model(settings: Settings, provider: str) -> str:
    if provider == "gemini":
        return settings.gemini_model
    if provider in _PROVIDER_DETAILS:
        return getattr(settings, _PROVIDER_DETAILS[provider][2])
    raise ValueError("Unsupported AI provider")


def _request_payload(messages: list[dict], temperature: float) -> dict:
    return {"messages": messages, "temperature": temperature, "stream": False}


def openai_compatible_chat(settings: Settings, provider: str, messages: list[dict], temperature: float = 0.8) -> tuple[str, str]:
    """Call OpenRouter or Groq and return (model, response text)."""
    if provider not in _PROVIDER_DETAILS:
        raise ValueError("Unsupported OpenAI-compatible provider")
    endpoint, key_field, model_field = _PROVIDER_DETAILS[provider]
    api_key = getattr(settings, key_field)
    model = getattr(settings, model_field)
    payload = _request_payload(messages, temperature)
    payload["model"] = model
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/Ashokkunchala/Jarvis-Personal-AI"
        headers["X-Title"] = "JARVIS Personal AI"
    response = httpx.post(endpoint, headers=headers, json=payload, timeout=httpx.Timeout(45.0, connect=10.0))
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    text = choices[0].get("message", {}).get("content") if choices else None
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("AI provider returned an empty response")
    return model, text.strip()


def openai_compatible_stream(settings: Settings, provider: str, messages: list[dict], temperature: float = 0.8) -> Iterator[str]:
    """Yield content deltas from an OpenAI-compatible SSE endpoint."""
    if provider not in _PROVIDER_DETAILS:
        raise ValueError("Unsupported OpenAI-compatible provider")
    endpoint, key_field, model_field = _PROVIDER_DETAILS[provider]
    api_key = getattr(settings, key_field)
    payload = {"model": getattr(settings, model_field), "messages": messages, "temperature": temperature, "stream": True}
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/Ashokkunchala/Jarvis-Personal-AI"
        headers["X-Title"] = "JARVIS Personal AI"
    with httpx.stream("POST", endpoint, headers=headers, json=payload, timeout=httpx.Timeout(90.0, connect=10.0)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                logger.debug("Skipping malformed provider SSE event")
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta", {}).get("content")
            if isinstance(delta, str) and delta:
                yield delta
