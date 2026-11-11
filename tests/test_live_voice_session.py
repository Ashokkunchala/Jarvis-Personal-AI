"""Guardrail and WebSocket-flow tests for live voice, using a fake Gemini client (no network)."""

from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.live_voice as lv
from app.live_voice import SessionGuard


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_guard_expires_by_age_and_idle():
    c = Clock()
    g = SessionGuard(now=c, max_seconds=100, idle_seconds=30)
    assert g.expiry_reason() is None
    c.t += 31
    assert "idle" in g.expiry_reason()
    g.touch()
    assert g.expiry_reason() is None
    c.t += 29
    g.touch()
    c.t += 29
    g.touch()
    c.t += 29
    g.touch()
    assert "time limit" in g.expiry_reason()


def test_guard_remaining_is_the_nearest_limit():
    c = Clock()
    g = SessionGuard(now=c, max_seconds=100, idle_seconds=30)
    assert g.remaining() == 30
    c.t += 20
    g.touch()
    c.t += 70
    g.touch()
    assert g.remaining() == pytest.approx(10)


def test_guard_audio_rate_limit_rolls_each_minute():
    c = Clock()
    g = SessionGuard(now=c, max_audio_bytes_per_minute=1000)
    assert g.allow_audio(600)
    assert not g.allow_audio(600)
    c.t += 61
    assert g.allow_audio(600)


class FakeSession:
    def __init__(self, sent):
        self.sent = sent

    async def receive(self):
        content = SimpleNamespace(
            input_transcription=SimpleNamespace(text="hello"),
            output_transcription=None,
            model_turn=SimpleNamespace(parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"\x01\x00"), text=None)]),
            interrupted=False,
            turn_complete=True,
        )
        yield SimpleNamespace(server_content=content)
        await asyncio.sleep(3600)

    async def send_realtime_input(self, **kw):
        self.sent.append(kw)


class FakeConnect:
    def __init__(self, sent):
        self.sent = sent

    async def __aenter__(self):
        return FakeSession(self.sent)

    async def __aexit__(self, *a):
        return False


@pytest.fixture()
def fake_live(monkeypatch):
    sent: list[dict] = []
    settings = SimpleNamespace(
        gemini_api_key="real-looking-key", allowed_origins=[], gemini_live_model="fake-live", gemini_live_voice="Charon",
    )
    monkeypatch.setattr(lv, "get_settings", lambda: settings)
    fake_client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **kw: FakeConnect(sent))))
    monkeypatch.setattr(lv.genai, "Client", lambda api_key: fake_client)
    monkeypatch.setattr(lv, "_active_sessions", 0)
    from app.main import app
    return TestClient(app), sent


def _connect(client):
    return client.websocket_connect(f"/api/live-voice?ticket={lv._issue_live_ticket()}")


def test_ws_rejects_missing_ticket(fake_live):
    client, _ = fake_live
    with pytest.raises(Exception):
        with client.websocket_connect("/api/live-voice?ticket=bad"):
            pass


def test_ws_happy_path_forwards_audio_text_and_events(fake_live):
    client, sent = fake_live
    with _connect(client) as ws:
        assert ws.receive_json()["type"] == "ready"
        got = {ws.receive_json()["type"] for _ in range(3)}
        assert {"transcript", "audio", "turn_complete"} <= got
        ws.send_text(json.dumps({"type": "text", "text": "hi jarvis"}))
        ws.send_text(json.dumps({"type": "audio", "data": base64.b64encode(b"\x00\x01" * 100).decode()}))
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json()["type"] == "pong"
    assert sent[0] == {"text": "hi jarvis"}
    assert sent[1]["audio"].mime_type == "audio/pcm;rate=16000"


def test_ws_rejects_bad_frames(fake_live):
    client, _ = fake_live
    with _connect(client) as ws:
        for _ in range(4):
            ws.receive_json()
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_text(json.dumps({"type": "audio", "data": base64.b64encode(b"\x00\x01\x02").decode()}))
        assert ws.receive_json()["type"] == "error"
        ws.send_text(json.dumps({"type": "nope"}))
        assert ws.receive_json()["type"] == "error"


def test_ws_audio_rate_limit_is_enforced(fake_live, monkeypatch):
    client, sent = fake_live
    monkeypatch.setattr(lv, "MAX_AUDIO_BYTES_PER_MINUTE", 300)
    frame = json.dumps({"type": "audio", "data": base64.b64encode(b"\x00\x01" * 100).decode()})
    with _connect(client) as ws:
        for _ in range(4):
            ws.receive_json()
        ws.send_text(frame)
        ws.send_text(frame)
        msg = ws.receive_json()
        assert msg["type"] == "error" and "rate limit" in msg["message"]
    assert len([s for s in sent if "audio" in s]) == 1


def test_ws_idle_timeout_closes_session(fake_live, monkeypatch):
    client, _ = fake_live
    monkeypatch.setattr(lv, "IDLE_TIMEOUT_SECONDS", 1)
    with _connect(client) as ws:
        for _ in range(4):
            ws.receive_json()
        msg = ws.receive_json()
        assert msg["type"] == "error" and "idle" in msg["message"]


def test_ws_concurrent_session_cap(fake_live, monkeypatch):
    client, _ = fake_live
    monkeypatch.setattr(lv, "MAX_CONCURRENT_SESSIONS", 1)
    with _connect(client) as first:
        assert first.receive_json()["type"] == "ready"
        with pytest.raises(Exception):
            with _connect(client):
                pass
    # slot is released after the first session ends
    with _connect(client) as again:
        assert again.receive_json()["type"] == "ready"


# ----------------------------------------------------------------- read-only voice tools
def test_voice_tools_are_read_only_and_allow_listed(monkeypatch, tmp_path):
    from app import live_tools

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.sqlite3"))
    assert live_tools.execute("get_current_time", {})["success"]
    assert live_tools.execute("list_reminders", {"limit": "bogus"})["reminders"] == []
    assert live_tools.execute("list_memories", None)["memories"] == []
    for name in ("run_shell", "delete_memory", "add_reminder", "aws_change"):
        assert live_tools.execute(name, {})["success"] is False
    assert {"get_current_time", "list_reminders", "list_memories"} == live_tools.TOOL_NAMES


def test_voice_tools_return_saved_data_clipped(monkeypatch, tmp_path):
    from app import live_tools
    from app.personal_data import _connect

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.sqlite3"))
    with _connect() as db:
        db.execute("INSERT INTO reminders(title,due_at,created_at) VALUES(?,?,?)", ("pay rent\nignore previous", "2000-01-01T00:00:00+00:00", "x"))
        db.execute("INSERT INTO reminders(title,due_at,created_at,completed) VALUES(?,?,?,1)", ("done", "2000-01-01T00:00:00+00:00", "x"))
    res = live_tools.execute("list_reminders", {})
    assert [r["title"] for r in res["reminders"]] == ["pay rent ignore previous"]
    assert res["reminders"][0]["overdue"] is True


class ToolCallSession(FakeSession):
    async def receive(self):
        fc = SimpleNamespace(id="c1", name="get_current_time", args={})
        yield SimpleNamespace(tool_call=SimpleNamespace(function_calls=[fc]), server_content=None)
        bad = SimpleNamespace(id="c2", name="run_shell", args={"command": "whoami"})
        yield SimpleNamespace(tool_call=SimpleNamespace(function_calls=[bad]), server_content=None)
        await asyncio.sleep(3600)

    async def send_tool_response(self, function_responses):
        self.sent.append({"tool_response": function_responses})


def test_ws_executes_only_allow_listed_tools(fake_live, monkeypatch):
    client, sent = fake_live

    class Connect(FakeConnect):
        async def __aenter__(self):
            return ToolCallSession(self.sent)

    fake_client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **kw: Connect(sent))))
    monkeypatch.setattr(lv.genai, "Client", lambda api_key: fake_client)
    with _connect(client) as ws:
        assert ws.receive_json()["type"] == "ready"
        first = ws.receive_json()
        second = ws.receive_json()
    assert first == {"type": "tool", "name": "get_current_time", "ok": True}
    assert second == {"type": "tool", "name": "run_shell", "ok": False}
    outputs = [s["tool_response"][0].response["output"] for s in sent if "tool_response" in s]
    assert outputs[0]["success"] is True and outputs[1]["success"] is False
