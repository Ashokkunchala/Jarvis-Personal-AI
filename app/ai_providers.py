"""Multi-provider chat: Gemini plus OpenAI-compatible OpenRouter and Groq.

Secrets are loaded from server environment settings and are never returned to
clients. Every helper here is synchronous so FastAPI can run it in the
threadpool from plain ``def`` endpoints.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger("jarvis.providers")

PROVIDERS = ("gemini", "openrouter", "groq")

_PROVIDER_DETAILS = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openrouter_api_key", "openrouter_model"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "groq_api_key", "groq_model"),
}


def _is_configured_key(key: str) -> bool:
    cleaned = (key or "").strip()
    return bool(cleaned) and not cleaned.lower().startswith("replace")


def configured_provider_order(settings: Settings) -> list[str]:
    """Return configured providers, honoring a preferred provider while retaining fallbacks."""
    available = []
    if _is_configured_key(settings.gemini_api_key):
        available.append("gemini")
    for name, (_, key_field, _) in _PROVIDER_DETAILS.items():
        if _is_configured_key(getattr(settings, key_field, "")):
            available.append(name)
    preferred = settings.jarvis_ai_provider.strip().lower()
    if preferred in PROVIDERS and preferred in available:
        return [preferred] + [name for name in available if name != preferred]
    return available


def provider_model(settings: Settings, provider: str) -> str:
    if provider == "gemini":
        return settings.gemini_model
    if provider in _PROVIDER_DETAILS:
        return getattr(settings, _PROVIDER_DETAILS[provider][2])
    raise ValueError("Unsupported AI provider")


def normalize_role(role: str) -> str:
    """Map Gemini-style roles onto OpenAI chat roles."""
    return "assistant" if role in {"model", "assistant"} else role


def build_openai_messages(
    system_instruction: str,
    history: Sequence[Any],
    message: str,
    limit: int = 20,
) -> list[dict[str, str]]:
    """Build an OpenAI-style chat list from a system prompt, history and a user message.

    ``history`` items may be dicts or pydantic models with ``role``/``content``
    (Gemini roles ``model`` become OpenAI ``assistant``).
    """
    messages: list[dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    for item in list(history)[-limit:]:
        if isinstance(item, dict):
            role, content = item.get("role", ""), item.get("content", "")
        else:
            role, content = getattr(item, "role", ""), getattr(item, "content", "")
        if not content:
            continue
        messages.append({"role": normalize_role(str(role)), "content": str(content)})
    messages.append({"role": "user", "content": message})
    return messages


def openai_to_gemini_contents(messages: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Convert OpenAI-style messages into Gemini ``contents`` (system is dropped)."""
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        if role == "system":
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": [{"text": message.get("content", "")}]})
    return contents


def _system_of(messages: Sequence[dict[str, str]]) -> str:
    for message in messages:
        if message.get("role") == "system":
            return message.get("content", "")
    return ""


def complete_chat(
    settings: Settings,
    provider_order: Sequence[str],
    messages: list[dict[str, str]],
    temperature: float = 0.8,
    gemini_client: Any = None,
) -> tuple[str, str]:
    """Run a non-streaming chat across providers with automatic fallback.

    Returns ``(provider/model, reply_text)``. Raises ``RuntimeError`` when every
    configured provider fails.
    """
    if not provider_order:
        raise RuntimeError(NO_PROVIDER_DETAIL)
    system_instruction = _system_of(messages)
    contents = openai_to_gemini_contents(messages)
    failures: list[str] = []
    for provider in provider_order:
        try:
            if provider == "gemini":
                if gemini_client is None:
                    raise RuntimeError("Gemini client is unavailable")
                response = gemini_client.models.generate_content(
                    model=settings.gemini_model,
                    contents=contents,
                    config={"system_instruction": system_instruction, "temperature": temperature},
                )
                reply = (response.text or "").strip()
                model = settings.gemini_model
            else:
                model, reply = openai_compatible_chat(settings, provider, messages, temperature)
            if not reply:
                raise RuntimeError("The AI returned an empty response")
            if provider != provider_order[0]:
                logger.warning("AI provider fallback succeeded: %s", provider)
            return f"{provider}/{model}", reply
        except Exception as error:
            logger.warning(
                "AI provider %s failed; trying next configured provider: %s",
                provider,
                type(error).__name__,
            )
            failures.append(provider)
    raise RuntimeError(
        "All configured AI providers failed (" + ", ".join(failures) + "). "
        "Check server-side provider configuration and logs."
    )


def stream_chat(
    settings: Settings,
    provider_order: Sequence[str],
    messages: list[dict[str, str]],
    temperature: float = 0.8,
    gemini_client: Any = None,
) -> Iterator[dict[str, Any]]:
    """Yield SSE-ready chat events: ``{"text": ...}`` deltas, then a terminal
    ``{"done": True, "model": ...}`` or ``{"error": ...}`` event.

    A provider is abandoned before any text has been emitted so the next
    configured provider can take over invisibly.
    """
    if not provider_order:
        yield {"error": NO_PROVIDER_DETAIL}
        return
    system_instruction = _system_of(messages)
    contents = openai_to_gemini_contents(messages)
    for provider in provider_order:
        emitted = False
        model = ""
        stream = None
        try:
            if provider == "gemini":
                if gemini_client is None:
                    raise RuntimeError("Gemini client is unavailable")
                model = settings.gemini_model
                stream = gemini_client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config={"system_instruction": system_instruction, "temperature": temperature},
                )
                for chunk in stream:
                    delta = getattr(chunk, "text", None)
                    if delta:
                        emitted = True
                        yield {"text": delta}
            else:
                model = provider_model(settings, provider)
                for delta in openai_compatible_stream(settings, provider, messages, temperature):
                    emitted = True
                    yield {"text": delta}
            yield {"done": True, "model": f"{provider}/{model}"}
            return
        except Exception:
            logger.exception("AI streaming provider %s failed", provider)
            if emitted:
                yield {"error": "The AI stream failed after output began; retry the request."}
                return
        finally:
            close = getattr(stream, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    logger.debug("Provider stream cleanup failed", exc_info=True)
    yield {"error": "All configured AI providers failed. Check server logs and configuration."}


NO_PROVIDER_DETAIL = (
    "No AI provider configured. Set GEMINI_API_KEY, OPENROUTER_API_KEY, or GROQ_API_KEY on the server."
)


def _request_payload(messages: list[dict], temperature: float) -> dict:
    return {"messages": messages, "temperature": temperature, "stream": False}


def _headers(settings: Settings, provider: str) -> dict[str, str]:
    endpoint, key_field, _ = _PROVIDER_DETAILS[provider]
    headers = {"Authorization": "Bearer " + getattr(settings, key_field), "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/Ashokkunchala/Jarvis-Personal-AI"
        headers["X-Title"] = "JARVIS Personal AI"
    return headers


def openai_compatible_chat(settings: Settings, provider: str, messages: list[dict], temperature: float = 0.8) -> tuple[str, str]:
    """Call OpenRouter or Groq and return (model, response text)."""
    if provider not in _PROVIDER_DETAILS:
        raise ValueError("Unsupported OpenAI-compatible provider")
    endpoint, _, model_field = _PROVIDER_DETAILS[provider]
    model = getattr(settings, model_field)
    payload = _request_payload(messages, temperature)
    payload["model"] = model
    response = httpx.post(
        endpoint,
        headers=_headers(settings, provider),
        json=payload,
        timeout=httpx.Timeout(45.0, connect=10.0),
    )
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
    endpoint, _, model_field = _PROVIDER_DETAILS[provider]
    payload = {"model": getattr(settings, model_field), "messages": messages, "temperature": temperature, "stream": True}
    with httpx.stream(
        "POST",
        endpoint,
        headers=_headers(settings, provider),
        json=payload,
        timeout=httpx.Timeout(90.0, connect=10.0),
    ) as response:
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
