
import pytest

from app.ai_providers import (
    build_openai_messages,
    complete_chat,
    configured_provider_order,
    openai_compatible_chat,
    openai_to_gemini_contents,
    stream_chat,
)
from app.config import Settings


def test_provider_order_prefers_configured_choice_and_keeps_fallbacks():
    settings = Settings(
        gemini_api_key="gemini-test-key",
        openrouter_api_key="openrouter-test-key",
        groq_api_key="groq-test-key",
        jarvis_ai_provider="groq",
    )
    assert configured_provider_order(settings) == ["groq", "gemini", "openrouter"]


def test_provider_order_ignores_placeholder_keys():
    settings = Settings(
        gemini_api_key="replace_me",
        openrouter_api_key="replace_me",
        groq_api_key="groq-test-key",
        jarvis_ai_provider="auto",
    )
    assert configured_provider_order(settings) == ["groq"]


def test_openrouter_chat_uses_server_key_and_openai_compatible_response(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Hello from a mocked provider"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.ai_providers.httpx.post", fake_post)
    settings = Settings(openrouter_api_key="server-only-test-key", openrouter_model="test/model")
    model, reply = openai_compatible_chat(
        settings,
        "openrouter",
        [{"role": "user", "content": "Hello"}],
    )

    assert model == "test/model"
    assert reply == "Hello from a mocked provider"
    assert captured["headers"]["Authorization"] == "Bearer server-only-test-key"
    assert captured["json"]["model"] == "test/model"
    assert "server-only-test-key" not in reply


def test_build_openai_messages_maps_model_role_to_assistant():
    messages = build_openai_messages(
        "System prompt",
        [{"role": "user", "content": "Hi"}, {"role": "model", "content": "Hello"}],
        "Next question",
    )
    assert messages[0] == {"role": "system", "content": "System prompt"}
    assert messages[1]["role"] == "user"
    assert messages[2] == {"role": "assistant", "content": "Hello"}
    assert messages[3] == {"role": "user", "content": "Next question"}


def test_openai_to_gemini_contents_skips_system_and_maps_roles():
    contents = openai_to_gemini_contents([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hey"},
    ])
    assert contents == [
        {"role": "user", "parts": [{"text": "hi"}]},
        {"role": "model", "parts": [{"text": "hey"}]},
    ]


def test_complete_chat_falls_back_to_openrouter_when_gemini_fails(monkeypatch):
    settings = Settings(
        gemini_api_key="gemini-test-key",
        openrouter_api_key="openrouter-test-key",
        jarvis_ai_provider="gemini",
    )

    class BrokenGemini:
        class Models:
            @staticmethod
            def generate_content(**kwargs):
                raise RuntimeError("503 UNAVAILABLE")

        models = Models()

    captured = {}

    def fake_chat(settings_arg, provider, messages, temperature=0.8):
        captured["provider"] = provider
        captured["messages"] = messages
        return "openai/gpt-4o-mini", "fallback reply"

    monkeypatch.setattr("app.ai_providers.openai_compatible_chat", fake_chat)
    model_id, reply = complete_chat(
        settings,
        ["gemini", "openrouter"],
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        gemini_client=BrokenGemini(),
    )
    assert model_id == "openrouter/openai/gpt-4o-mini"
    assert reply == "fallback reply"
    assert captured["provider"] == "openrouter"
    # System prompt stays a system message for the OpenAI-compatible call.
    assert captured["messages"][0]["role"] == "system"


def test_complete_chat_raises_when_every_provider_fails(monkeypatch):
    settings = Settings(
        gemini_api_key="gemini-test-key",
        openrouter_api_key="openrouter-test-key",
        groq_api_key="groq-test-key",
    )

    class BrokenGemini:
        class Models:
            @staticmethod
            def generate_content(**kwargs):
                raise RuntimeError("boom")

        models = Models()

    def always_fail(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.ai_providers.openai_compatible_chat", always_fail)
    with pytest.raises(RuntimeError, match="All configured AI providers failed"):
        complete_chat(
            settings,
            ["gemini", "openrouter", "groq"],
            [{"role": "user", "content": "hi"}],
            gemini_client=BrokenGemini(),
        )


def test_complete_chat_without_providers_raises_no_provider_detail():
    settings = Settings(gemini_api_key="", openrouter_api_key="", groq_api_key="")
    with pytest.raises(RuntimeError, match="No AI provider configured"):
        complete_chat(settings, [], [{"role": "user", "content": "hi"}])


def test_stream_chat_falls_back_before_emitting_text(monkeypatch):
    settings = Settings(
        gemini_api_key="gemini-test-key",
        groq_api_key="groq-test-key",
        jarvis_ai_provider="gemini",
    )

    class BrokenGemini:
        class Models:
            @staticmethod
            def generate_content_stream(**kwargs):
                raise RuntimeError("429 rate limit")

        models = Models()

    def fake_stream(settings_arg, provider, messages, temperature=0.8):
        yield "hello "
        yield "from groq"

    monkeypatch.setattr("app.ai_providers.openai_compatible_stream", fake_stream)
    events = list(
        stream_chat(
            settings,
            ["gemini", "groq"],
            [{"role": "user", "content": "hi"}],
            gemini_client=BrokenGemini(),
        )
    )
    assert events[0] == {"text": "hello "}
    assert events[1] == {"text": "from groq"}
    assert events[2] == {"done": True, "model": "groq/llama-3.3-70b-versatile"}
