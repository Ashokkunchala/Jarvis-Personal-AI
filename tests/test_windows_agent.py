from fastapi.testclient import TestClient
from windows_agent.agent import app


def test_agent_requires_token(monkeypatch):
    monkeypatch.delenv("JARVIS_AGENT_TOKEN", raising=False)
    with TestClient(app) as client:
        assert client.get("/v1/status").status_code == 503


def test_open_url_requires_confirmation_and_allowlist(monkeypatch):
    monkeypatch.setenv("JARVIS_AGENT_TOKEN", "test-token-that-is-at-least-32-characters")
    monkeypatch.setenv("JARVIS_ALLOWED_URL_HOSTS", "github.com")
    opened = []
    monkeypatch.setattr("windows_agent.agent.webbrowser.open", lambda url, new=0: opened.append(url) or True)
    headers = {"Authorization": "Bearer test-token-that-is-at-least-32-characters"}
    with TestClient(app) as client:
        no_confirm = client.post("/v1/open-url", headers=headers,
                                 json={"url": "https://github.com", "confirmed": False})
        assert no_confirm.status_code == 409
        denied = client.post("/v1/open-url", headers=headers,
                             json={"url": "https://evil.example", "confirmed": True})
        assert denied.status_code == 403
        good = client.post("/v1/open-url", headers=headers,
                           json={"url": "https://github.com", "confirmed": True})
        assert good.status_code == 200
    assert opened == ["https://github.com"]
