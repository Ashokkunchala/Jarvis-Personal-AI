"""JARVIS brain — a streaming multi-provider tool-calling agent.

The brain is the single decision loop shared by the CLI, the TUI and the
WebSocket bridge. It streams text as it is generated, emits structured tool
events while actions run, and honours a confirmation callback before anything
risky executes.

Text providers (in fallback order, ``JARVIS_AI_PROVIDER=auto`` by default):

* ``gemini``     — Google Gemini via ``GEMINI_API_KEY`` (full model chain)
* ``openrouter`` — OpenAI-compatible via ``OPENROUTER_API_KEY``
* ``groq``       — OpenAI-compatible via ``GROQ_API_KEY``

Events yielded by :meth:`JarvisBrain.ask`:

    {"type": "status",     "message": str}
    {"type": "text_delta", "text": str}
    {"type": "tool_start", "tool": str, "args": dict, "risk": str, "category": str}
    {"type": "tool_end",   "tool": str, "ok": bool, "summary": str, "elapsed": float}
    {"type": "tool_error", "tool": str, "error": str}
    {"type": "tool_cancelled", "tool": str}
    {"type": "done",       "text": str, "turns": int, "tools_used": [str]}
    {"type": "error",      "error": str}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis.tools.builtin_tools import build_registry
from jarvis.tools.registry import Tool, ToolRegistry, ToolResult

logger = logging.getLogger("jarvis.brain")

ConfirmFn = Callable[[Tool, dict[str, Any]], Awaitable[bool]]


def load_env() -> None:
    """Best-effort load of the local ``.env`` (never overrides real env vars)."""
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=False)
    except ImportError:
        pass

DEFAULT_SYSTEM = """You are JARVIS, a precise, capable personal assistant running on the user's Windows laptop \
with a connected Android phone.

Style:
- Be concise and direct. Lead with the answer or the action taken.
- Use short paragraphs and bullet lists only when they genuinely help.
- Speak like a competent operator: "Done.", "Volume is now 35%.", "No device connected."
- If a tool fails, say what failed and what the user should check — never invent success.
- Match the user's language. Support Telugu and Indian English when asked.

Tool rules:
- Use tools for any real-world action (opening apps, volume, files, phone control) instead of guessing.
- Prefer the narrowest tool that does the job; chain small tools rather than one big guess.
- Read-only tools need no permission. Tools marked risky will ask the user first — that is normal.
- Never call a destructive tool (delete, kill, shutdown, reboot, uninstall) without the user asking for it.
- Before acting on the phone, check android_status first if you do not know whether a device is connected.
- After a tool runs, report the actual result in one short sentence.

You have full access to this laptop and the paired phone. Use it."""
MAX_HISTORY_MESSAGES = 40
MAX_TURNS = 8

# Tried in order when the primary model is busy, missing or over quota.
DEFAULT_FALLBACKS = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]

# A model that times out or 5xxs goes into cooldown so the next request skips
# it immediately instead of burning the first-token timeout again.
MODEL_COOLDOWN_SECONDS = float(os.getenv("JARVIS_MODEL_COOLDOWN", "300") or 300)
_model_cooldown: dict[str, float] = {}

_TRANSIENT_MARKERS = (
    "overloaded", "high demand", "unavailable", "resource_exhausted", "resource exhausted",
    "rate limit", "quota", "429", "503", "500", "502", "504", "deadline",
    "model not found", "not found for api key", "no longer available", "has been retired",
    "not enabled", "permission denied on model",
)


class ModelBusyError(Exception):
    """Raised when the current model cannot serve the request right now."""

    def __init__(self, model: str, reason: str):
        super().__init__(reason)
        self.model = model
        self.reason = reason


def _is_transient(exc: Exception) -> bool:
    """True when it is worth switching to a different model."""
    text = str(exc).lower()
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status in {429, 500, 502, 503, 504}:
        return True
    # A 404 naming a model means that model is unavailable to this key/account.
    if (status == 404 or "404" in text) and "model" in text:
        return True
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _mark_bad(model: str) -> None:
    _model_cooldown[model] = time.time()


def _mark_good(model: str) -> None:
    _model_cooldown.pop(model, None)


def _is_cooling(model: str) -> bool:
    ts = _model_cooldown.get(model)
    if ts is None:
        return False
    if time.time() - ts > MODEL_COOLDOWN_SECONDS:
        _model_cooldown.pop(model, None)
        return False
    return True


@dataclass
class TurnStats:
    text_chars: int = 0
    tools: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    model_turns: int = 0


class JarvisBrain:
    """Streaming multi-provider agent bound to the tool registry."""

    _OPENAI_PROVIDERS = {
        "openrouter": (
            "https://openrouter.ai/api/v1/chat/completions",
            "OPENROUTER_API_KEY",
            "OPENROUTER_MODEL",
            "openai/gpt-4o-mini",
        ),
        "groq": (
            "https://api.groq.com/openai/v1/chat/completions",
            "GROQ_API_KEY",
            "GROQ_MODEL",
            "llama-3.3-70b-versatile",
        ),
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        registry: ToolRegistry | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        history: list[dict[str, Any]] | None = None,
        provider: str | None = None,
    ) -> None:
        load_env()
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = (model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()
        self.provider_preference = (
            provider or os.getenv("JARVIS_AI_PROVIDER", "auto") or "auto"
        ).strip().lower()
        self.registry = registry or build_registry()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM
        self.temperature = temperature
        self.history: list[dict[str, Any]] = list(history or [])
        self.first_token_timeout = float(os.getenv("JARVIS_FIRST_TOKEN_TIMEOUT", "10") or 10)
        self.chunk_timeout = float(os.getenv("JARVIS_CHUNK_TIMEOUT", "90") or 90)
        self._client = None

    # ------------------------------------------------------------------ init
    @staticmethod
    def _configured_key(name: str) -> str:
        """Read a provider key from the environment; blanks out placeholders."""
        value = (os.getenv(name, "") or "").strip()
        if not value or value.lower().startswith("replace"):
            return ""
        return value

    def provider_candidates(self) -> list[str]:
        """Configured providers in try-order; a valid preference goes first."""
        available: list[str] = []
        if self._configured_key("GEMINI_API_KEY") or (
            self.api_key and not self.api_key.lower().startswith("replace")
        ):
            available.append("gemini")
        if self._configured_key("OPENROUTER_API_KEY"):
            available.append("openrouter")
        if self._configured_key("GROQ_API_KEY"):
            available.append("groq")
        if self.provider_preference in available:
            return [self.provider_preference] + [p for p in available if p != self.provider_preference]
        return available

    @property
    def configured(self) -> bool:
        return bool(self.provider_candidates())

    @property
    def active_model(self) -> str:
        """Model the primary configured provider will use."""
        candidates = self.provider_candidates()
        if not candidates:
            return self.model
        primary = candidates[0]
        if primary == "gemini":
            return self.model
        _, _, model_field, default = self._OPENAI_PROVIDERS[primary]
        return (os.getenv(model_field, "") or default).strip()

    def _client_or_raise(self):
        if not self.api_key or self.api_key.lower().startswith("replace"):
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key from "
                "https://aistudio.google.com/apikey (or set OPENROUTER_API_KEY / GROQ_API_KEY)."
            )
        if self._client is None:
            from google import genai
            from google.genai import types

            # Fail fast on busy models so the fallback chain can take over
            # instead of blocking the user behind long SDK backoffs.
            http_options = types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=2, initial_delay=0.5, max_delay=2.0, exp_base=2.0, jitter=0.2
                )
            )
            self._client = genai.Client(api_key=self.api_key, http_options=http_options)
        return self._client

    def model_candidates(self) -> list[str]:
        """Primary model first, then configured and built-in fallbacks."""
        raw = os.getenv("GEMINI_MODEL_FALLBACK", "")
        configured = [m.strip() for m in raw.replace(";", ",").split(",") if m.strip()]
        ordered: list[str] = []
        for candidate in [self.model, *configured, *DEFAULT_FALLBACKS]:
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        return ordered

    async def model_candidates_async(self) -> list[str]:
        """Like :meth:`model_candidates` but intersected with models this key can use.

        Discovery runs once per process off the event loop; on any failure the
        static chain is used unchanged.
        """
        base = self.model_candidates()
        try:
            discovered: list[str] = await asyncio.to_thread(self._discover_models)
        except Exception:
            logger.debug("Model discovery failed; using static fallback chain", exc_info=True)
            return base
        if not discovered:
            return base
        available = set(discovered)
        ordered = [m for m in base if m in available]
        if self.model not in ordered:
            ordered.insert(0, self.model)
        # Extra belt-and-braces: any other flash-class model the key can call.
        for name in discovered:
            if name in ordered:
                continue
            if "flash" in name and "image" not in name and "tts" not in name:
                ordered.append(name)
        return ordered[:10]

    _discovered_cache: list[str] | None = None

    def _discover_models(self) -> list[str]:
        if JarvisBrain._discovered_cache is not None:
            return list(JarvisBrain._discovered_cache)
        client = self._client_or_raise()
        names: list[str] = []
        for model in client.models.list():
            name = getattr(model, "name", "") or ""
            name = name.replace("models/", "")
            actions = getattr(model, "supported_actions", None) or getattr(
                model, "supported_generation_methods", None
            )
            if name and (not actions or "generateContent" in actions or "generate_content" in actions):
                names.append(name)
        if names:
            JarvisBrain._discovered_cache = names
        return names

    # ------------------------------------------------------------- streaming
    async def _guarded_stream(
        self,
        client: Any,
        models: list[str],
        state: dict[str, int],
        contents: list[dict[str, Any]],
        config: Any,
    ):
        """Yield ``("event", dict)`` or ``("chunk", chunk)`` with failover.

        A model that has not produced its first token within
        ``first_token_timeout`` seconds is abandoned in favour of the next one
        in the chain — before any text has been shown to the user, so the
        switch is invisible.
        """
        idx = state.get("idx", 0)
        skipped_cooling = 0
        while idx < len(models):
            candidate = models[idx]
            if _is_cooling(candidate):
                skipped_cooling += 1
                idx += 1
                state["idx"] = idx
                continue

            stream = None
            try:
                stream = await client.aio.models.generate_content_stream(
                    model=candidate, contents=contents, config=config
                )
            except Exception as exc:
                if _is_transient(exc):
                    _mark_bad(candidate)
                    if idx + 1 < len(models):
                        idx += 1
                        state["idx"] = idx
                        reason = " ".join(str(exc).split())[:200]
                        logger.warning("%s rejected (%s); switching to %s", candidate, reason, models[idx])
                        yield ("event", {"type": "status", "message": f"{candidate} unavailable — using {models[idx]}"})
                        continue
                    raise
                raise

            iterator = stream.__aiter__()
            first = None
            try:
                first = await asyncio.wait_for(iterator.__anext__(), timeout=self.first_token_timeout)
            except StopAsyncIteration:
                first = None
            except TimeoutError:
                await _safe_close(stream)
                _mark_bad(candidate)
                if idx + 1 < len(models):
                    idx += 1
                    state["idx"] = idx
                    logger.warning("%s produced no first token in %.0fs; switching to %s",
                                   candidate, self.first_token_timeout, models[idx])
                    yield ("event", {"type": "status", "message": f"{candidate} is too slow — using {models[idx]}"})
                    continue
                raise TimeoutError(
                    f"{candidate} produced no response in {self.first_token_timeout:.0f}s "
                    "and no fallback model is available."
                )
            except Exception as exc:
                await _safe_close(stream)
                if _is_transient(exc):
                    _mark_bad(candidate)
                    if idx + 1 < len(models):
                        idx += 1
                        state["idx"] = idx
                        yield ("event", {"type": "status", "message": f"{candidate} failed — using {models[idx]}"})
                        continue
                raise

            _mark_good(candidate)

            if first is not None:
                yield ("chunk", first)

            while True:
                try:
                    nxt = await asyncio.wait_for(iterator.__anext__(), timeout=self.chunk_timeout)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    raise TimeoutError(
                        f"{candidate} stalled mid-response for {self.chunk_timeout:.0f}s"
                    ) from None
                yield ("chunk", nxt)
            return

        if skipped_cooling:
            raise RuntimeError(
                f"{skipped_cooling} model(s) are cooling down after recent failures — "
                "retry in a few minutes."
            )
        raise RuntimeError(
            "Every Gemini model is temporarily unavailable (rate limited or overloaded). "
            "Retry shortly, or set GEMINI_MODEL to a model your key can use."
        )

    def reset(self) -> None:
        self.history.clear()

    # --------------------------------------------------------------- context
    def build_system_instruction(self, extra: str | None = None) -> str:
        parts = [self.system_prompt, self.live_context()]
        if extra:
            parts.append(extra)
        return "\n\n".join(p for p in parts if p)

    def live_context(self) -> str:
        """Live machine + phone context injected each turn."""
        lines: list[str] = []
        try:
            from jarvis.control.laptop import LaptopController

            lc = LaptopController()
            status = lc.status()
            if status.get("success"):
                lines.append(
                    f"LAPTOP: {status.get('os')} on {status.get('hostname')}; "
                    f"CPU {status.get('cpu_percent')}%, RAM {status.get('memory_percent')}% "
                    f"({status.get('memory_used_gb')}/{status.get('memory_total_gb')} GB), "
                    f"battery {status.get('battery_percent')}%"
                    f"{' (plugged in)' if status.get('battery_plugged') else ''}, "
                    f"{status.get('disk_free_gb')} GB free on C:."
                )
            import datetime

            lines.append(f"TIME: {datetime.datetime.now().strftime('%A, %d %B %Y %H:%M:%S')}")
        except Exception:
            logger.debug("Could not build laptop context", exc_info=True)

        try:
            from jarvis.android_bridge import adb

            devices = adb.list_devices(refresh=False)
            if devices:
                lines.append(f"ANDROID: {len(devices)} device(s) connected: {', '.join(devices)}.")
            else:
                lines.append("ANDROID: no device connected (adb devices is empty).")
        except Exception:
            lines.append("ANDROID: unavailable (adb not installed).")
        return "\n".join(lines)

    def snapshot(self) -> dict[str, Any]:
        """Everything the UIs need for a status panel."""
        from jarvis.tools.builtin_tools import get_android, get_laptop

        try:
            status = get_laptop().status()
        except Exception as exc:
            status = {"success": False, "error": str(exc)}
        try:
            volume = get_laptop().get_volume()
        except Exception as exc:
            volume = {"success": False, "error": str(exc)}
        try:
            az = get_android()
            android = {"devices": az.devices, "connected": bool(az.devices), "adb": az.adb_path}
            if az.devices:
                android["battery"] = az.battery()
        except Exception as exc:
            android = {"devices": [], "connected": False, "error": str(exc)}
        return {
            "model": self.active_model,
            "providers": self.provider_candidates(),
            "configured": self.configured,
            "tools": len(self.registry),
            "history_turns": len(self.history),
            "laptop": status,
            "volume": volume,
            "android": android,
        }

    # ------------------------------------------------------------------- ask
    async def ask(
        self,
        message: str,
        confirm: ConfirmFn | None = None,
        auto_approve: bool = False,
        extra_system: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a full turn across configured providers: text, tools, done."""
        providers = self.provider_candidates()
        if not providers:
            yield {
                "type": "error",
                "error": "No AI provider configured — set GEMINI_API_KEY, OPENROUTER_API_KEY, "
                         "or GROQ_API_KEY in .env.",
            }
            return

        yield {"type": "status", "message": "thinking"}
        system_instruction = self.build_system_instruction(extra_system)
        # Once any of these leaves the process, the turn is no longer replayable
        # on another provider — only pre-output failures may fail over.
        committed = {"text_delta", "tool_start", "tool_end", "tool_error", "tool_cancelled", "done"}

        for index, provider in enumerate(providers):
            stats = TurnStats()
            emitted = False
            try:
                if provider == "gemini":
                    runner = self._ask_gemini(message, confirm, auto_approve, system_instruction, stats)
                else:
                    runner = self._ask_openai(provider, message, confirm, auto_approve, system_instruction, stats)
                async for event in runner:
                    if event.get("type") in committed:
                        emitted = True
                    yield event
                return
            except Exception as exc:
                logger.warning("AI provider %s failed during ask: %s", provider, exc)
                if emitted:
                    yield {"type": "error", "error": _friendly_error(exc, provider)}
                    return
                if index + 1 < len(providers):
                    yield {
                        "type": "status",
                        "message": f"{provider} failed — using {providers[index + 1]}",
                    }
                    continue
                yield {"type": "error", "error": _friendly_error(exc, provider)}
                return

    def _persist_turn(self, message: str, final_text: str) -> None:
        self.history.append({"role": "user", "parts": [{"text": message}]})
        if final_text:
            self.history.append({"role": "model", "parts": [{"text": final_text}]})
        self.history = self.history[-MAX_HISTORY_MESSAGES:]

    @staticmethod
    def _done_event(stats: TurnStats, final_text: str) -> dict[str, Any]:
        return {
            "type": "done",
            "text": final_text,
            "turns": stats.model_turns,
            "tools_used": stats.tools,
            "elapsed": round(time.time() - stats.started, 2),
        }

    async def _execute_calls(
        self,
        calls: list[dict[str, Any]],
        confirm: ConfirmFn | None,
        auto_approve: bool,
        stats: TurnStats,
        results: list[tuple[str, dict[str, Any]]],
    ) -> AsyncIterator[dict[str, Any]]:
        """Run tool calls, yielding lifecycle events; append (name, payload) to results."""
        for call in calls:
            name = call["name"]
            args = call.get("args") or {}
            tool = self.registry.get(name)
            yield {
                "type": "tool_start",
                "tool": name,
                "args": args,
                "risk": tool.risk.name if tool else "UNKNOWN",
                "category": tool.category if tool else "general",
            }
            if tool is None:
                payload: dict[str, Any] = {"success": False, "error": f"Unknown tool {name}"}
            else:
                result: ToolResult = await self.registry.execute(
                    name,
                    args,
                    confirm=confirm,
                    auto_approve=auto_approve,
                    on_event=self._forward_lifecycle(stats),
                )
                stats.tools.append(name)
                payload = json.loads(result.for_model())
                yield {
                    "type": "tool_end" if result.ok and not result.cancelled else
                           ("tool_cancelled" if result.cancelled else "tool_error"),
                    "tool": name,
                    "ok": result.ok and not result.cancelled,
                    "summary": result.error if not result.ok else _short(result.data),
                    "elapsed": round(result.elapsed, 3),
                }
            results.append((name, payload if isinstance(payload, dict) else {"result": payload}))

    async def _ask_gemini(
        self,
        message: str,
        confirm: ConfirmFn | None,
        auto_approve: bool,
        system_instruction: str,
        stats: TurnStats,
    ) -> AsyncIterator[dict[str, Any]]:
        """Gemini runner: model chain + function declarations. Raises on failure."""
        contents: list[dict[str, Any]] = [
            {"role": item["role"], "parts": item["parts"]} for item in self.history
        ]
        contents.append({"role": "user", "parts": [{"text": message}]})
        declarations = self.registry.get_tool_schemas()

        client = self._client_or_raise()
        final_text = ""
        models = await self.model_candidates_async()
        state = {"idx": 0}
        logger.debug("Model chain: %s", models[:5])

        for _ in range(MAX_TURNS):
            stats.model_turns += 1
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=self.temperature,
                tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            )

            function_calls: list[Any] = []
            raw_parts: list[Any] = []

            async for kind, payload in self._guarded_stream(
                client, models, state, contents, config
            ):
                if kind == "event":
                    yield payload
                    continue
                chunk = payload
                if not chunk.candidates:
                    continue
                content = chunk.candidates[0].content
                if not content or not content.parts:
                    continue
                for part in content.parts:
                    # Echo parts back verbatim so thought signatures survive.
                    raw_parts.append(part)
                    if getattr(part, "function_call", None):
                        function_calls.append(part.function_call)
                    if getattr(part, "text", None) and not getattr(part, "thought", False):
                        stats.text_chars += len(part.text)
                        final_text += part.text
                        yield {"type": "text_delta", "text": part.text}

            if not function_calls:
                break

            # Replay the model turn exactly as it arrived (thought signatures
            # are required by the API on functionCall parts), then answer it.
            if raw_parts:
                contents.append({"role": "model", "parts": raw_parts})

            calls = [{"name": fc.name, "args": dict(fc.args or {})} for fc in function_calls]
            results: list[tuple[str, dict[str, Any]]] = []
            async for event in self._execute_calls(calls, confirm, auto_approve, stats, results):
                yield event
            response_parts = [
                {"function_response": {"name": name, "response": payload}}
                for name, payload in results
            ]
            contents.append({"role": "user", "parts": response_parts})
            yield {"type": "status", "message": "thinking"}
        else:
            yield {"type": "status", "message": "turn limit reached"}

        self._persist_turn(message, final_text)
        yield self._done_event(stats, final_text)

    def _openai_history(self, system_instruction: str, message: str) -> list[dict[str, Any]]:
        """Convert the brain's Gemini-style history into OpenAI chat messages."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        for item in self.history:
            role = "assistant" if item.get("role") == "model" else item.get("role", "user")
            parts = item.get("parts") or []
            text = "".join(
                p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)
            )
            if text:
                messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": message})
        return messages

    def _openai_endpoint(self, provider: str) -> tuple[str, str, str]:
        endpoint, key_field, model_field, default_model = self._OPENAI_PROVIDERS[provider]
        key = self._configured_key(key_field)
        if not key:
            raise RuntimeError(f"{key_field} is not set in .env.")
        model = (os.getenv(model_field, "") or default_model).strip()
        return endpoint, key, model

    async def _ask_openai(
        self,
        provider: str,
        message: str,
        confirm: ConfirmFn | None,
        auto_approve: bool,
        system_instruction: str,
        stats: TurnStats,
    ) -> AsyncIterator[dict[str, Any]]:
        """OpenRouter/Groq runner over the OpenAI chat-completions tool protocol."""
        import httpx

        endpoint, key, model = self._openai_endpoint(provider)
        cooldown_key = f"{provider}:{model}"
        if _is_cooling(cooldown_key):
            raise RuntimeError(f"{provider}/{model} is cooling down after a recent failure.")

        declarations = self.registry.get_tool_schemas()
        tools = [{"type": "function", "function": d} for d in declarations]
        messages = self._openai_history(system_instruction, message)
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/Ashokkunchala/Jarvis-Personal-AI"
            headers["X-Title"] = "JARVIS Personal AI"

        final_text = ""
        timeout = httpx.Timeout(self.chunk_timeout, connect=min(self.first_token_timeout, 30.0))

        for _ in range(MAX_TURNS):
            stats.model_turns += 1
            turn_text: list[str] = []
            acc: dict[int, dict[str, str]] = {}

            async with httpx.AsyncClient(timeout=timeout) as http:
                payload: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "stream": True,
                    "tools": tools,
                }
                async with http.stream("POST", endpoint, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:300]
                        _mark_bad(cooldown_key)
                        raise RuntimeError(f"{provider} returned HTTP {response.status_code}: {body}")
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            stats.text_chars += len(content)
                            final_text += content
                            turn_text.append(content)
                            yield {"type": "text_delta", "text": content}
                        for tc in delta.get("tool_calls") or []:
                            index = tc.get("index") or 0
                            slot = acc.setdefault(index, {"id": "", "name": "", "arguments": ""})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                slot["name"] = fn["name"]
                            if fn.get("arguments"):
                                slot["arguments"] += fn["arguments"]
            _mark_good(cooldown_key)

            tool_calls = [acc[i] for i in sorted(acc)]
            if not tool_calls:
                break

            assistant_tool_calls = []
            for i, tc in enumerate(tool_calls):
                assistant_tool_calls.append({
                    "id": tc["id"] or f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"] or "{}",
                    },
                })
            messages.append({
                "role": "assistant",
                "content": "".join(turn_text) or None,
                "tool_calls": assistant_tool_calls,
            })

            calls: list[dict[str, Any]] = []
            call_ids: list[str] = []
            for tool_call in assistant_tool_calls:
                raw_args = tool_call["function"]["arguments"]
                try:
                    args = json.loads(raw_args or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": raw_args}
                if not isinstance(args, dict):
                    args = {"value": args}
                calls.append({"name": tool_call["function"]["name"], "args": args})
                call_ids.append(tool_call["id"])

            results: list[tuple[str, dict[str, Any]]] = []
            async for event in self._execute_calls(calls, confirm, auto_approve, stats, results):
                yield event
            for tool_call_id, (_, payload) in zip(call_ids, results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(payload, ensure_ascii=False, default=str),
                })
            yield {"type": "status", "message": "thinking"}
        else:
            yield {"type": "status", "message": "turn limit reached"}

        self._persist_turn(message, final_text)
        yield self._done_event(stats, final_text)

    def _forward_lifecycle(self, stats: TurnStats) -> Callable[[dict[str, Any]], None]:
        """Bridge registry lifecycle events into the stream.

        The registry emits ``tool_start``/``tool_end`` itself; here we only
        swallow duplicates because ``ask`` already yields them around the call.
        """
        def handler(event: dict[str, Any]) -> None:
            logger.debug("tool lifecycle: %s", event)
        return handler


async def _safe_close(stream: Any) -> None:
    close = getattr(stream, "aclose", None) or getattr(stream, "close", None)
    if close is None:
        return
    try:
        result = close()
        if hasattr(result, "__await__"):
            await result
    except Exception:
        logger.debug("Stream close failed", exc_info=True)


def _short(data: Any, limit: int = 200) -> str:
    try:
        if isinstance(data, dict):
            for key in ("message", "action", "path", "name", "launched", "volume", "percent", "count", "success"):
                if key in data:
                    return f"{key}={data[key]}"
            text = json.dumps(data, ensure_ascii=False, default=str)
        elif isinstance(data, list):
            text = f"{len(data)} item(s)"
        else:
            text = str(data)
        return text[:limit]
    except Exception:
        return "ok"


def _friendly_error(exc: Exception, provider: str = "gemini") -> str:
    text = str(exc)
    lowered = text.lower()
    label = {"gemini": "Gemini", "openrouter": "OpenRouter", "groq": "Groq"}.get(provider, provider)
    if "api key" in lowered or "401" in text or "unauthorized" in lowered or "permission" in lowered:
        return f"{label} rejected the API key — check the {provider.upper()}_API_KEY entry in .env."
    if "429" in text or "quota" in lowered or "rate limit" in lowered or "resource_exhausted" in lowered:
        return f"{label} rate limit or quota exceeded — wait a moment and retry."
    if "503" in text or "unavailable" in lowered or "overloaded" in lowered:
        return f"{label} service temporarily unavailable — retry shortly."
    if "connection" in lowered or "timed out" in lowered or "timeout" in lowered:
        return f"Network problem reaching {label} — check your connection."
    if "not found" in lowered and "model" in lowered:
        if provider == "gemini":
            return "Model not available for this key — try GEMINI_MODEL=gemini-2.5-flash."
        return f"Model not available on {label} — check the model name in .env."
    return f"Request failed: {text[:300]}"
