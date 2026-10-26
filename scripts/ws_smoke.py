"""Integration check for the /ws endpoint (no server process needed)."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SECRET_KEY", "x" * 40)
os.environ.setdefault("JARVIS_API_TOKEN", "ws-test-token-at-least-32-characters-long")
TOKEN = os.environ["JARVIS_API_TOKEN"]

from fastapi.testclient import TestClient  # noqa: E402

from app.main_enhanced import app  # noqa: E402

client = TestClient(app)

# 1. unauthenticated handshake must be refused
try:
    with client.websocket_connect("/ws") as ws:  # noqa: F841
        print("FAIL: unauthenticated connection was accepted")
        sys.exit(1)
except Exception as exc:
    print(f"[ok] unauthenticated handshake refused ({type(exc).__name__})")


def recv_until(websocket, types_wanted, timeout_frames=200):
    got = []
    for _ in range(timeout_frames):
        frame = json.loads(websocket.receive_text())
        got.append(frame)
        if frame.get("type") in types_wanted:
            return got, frame
    raise AssertionError(f"never saw {types_wanted}; got {[g.get('type') for g in got]}")


with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
    frames, ready = recv_until(ws, {"ready"})
    print(f"[ok] ready: model={ready['model']} tools={ready['tools']} configured={ready['configured']}")
    assert ready["tools"] == 135, ready

    ws.send_text(json.dumps({"type": "ping"}))
    _, pong = recv_until(ws, {"pong"})
    print("[ok] ping/pong")

    ws.send_text(json.dumps({"type": "tools"}))
    _, tools = recv_until(ws, {"tools_list"})
    names = [t["name"] for t in tools["tools"]]
    assert "battery_status" in names and "set_volume" in names, names[:5]
    print(f"[ok] tools_list returned {len(names)} schemas")

    ws.send_text(json.dumps({"type": "status"}))
    _, snap = recv_until(ws, {"status_snapshot"})
    print(f"[ok] status_snapshot laptop={snap.get('laptop', {}).get('success')} "
          f"android={snap.get('android', {}).get('connected')}")

    ws.send_text(json.dumps({"type": "chat", "message": "Reply with exactly: WS OK"}))
    seen = []
    for _ in range(300):
        frame = json.loads(ws.receive_text())
        seen.append(frame["type"])
        if frame["type"] == "text_delta":
            print(f"       delta: {frame['text']!r}")
        if frame["type"] == "error":
            print(f"FAIL: {frame['error']}")
            sys.exit(1)
        if frame["type"] == "done":
            print(f"[ok] chat turn streamed: tools={frame.get('tools_used')} elapsed={frame.get('elapsed')}")
            break
    else:
        print(f"FAIL: no done frame; saw {sorted(set(seen))}")
        sys.exit(1)

    ws.send_text(json.dumps({"type": "chat", "message": ""}))
    _, err = recv_until(ws, {"error"})
    assert "empty" in err["error"], err
    print("[ok] empty message rejected")

    ws.send_text(json.dumps({"type": "nope"}))
    _, err = recv_until(ws, {"error"})
    assert "unknown frame" in err["error"], err
    print("[ok] unknown frame rejected")

print("WS integration checks passed")
