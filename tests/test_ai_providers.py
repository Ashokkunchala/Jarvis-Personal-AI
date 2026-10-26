from app.ai_providers import configured_provider_order, openai_compatible_chat
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
