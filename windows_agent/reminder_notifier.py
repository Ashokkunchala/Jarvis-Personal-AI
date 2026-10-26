"""Opt-in Windows toast worker for reminders stored by the local JARVIS backend."""
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

API_BASE = os.getenv("JARVIS_API_BASE", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.getenv("JARVIS_API_TOKEN", "")
POLL_SECONDS = max(15, int(os.getenv("JARVIS_REMINDER_POLL_SECONDS", "30")))
STATE_PATH = Path(os.getenv("JARVIS_REMINDER_STATE_PATH", "data/reminder-notifier-state.json"))
MAX_RETRY_SECONDS = 15 * 60


def fetch_due():
    request = Request(API_BASE + "/api/reminders/due", headers={"Authorization": "Bearer " + TOKEN})
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8")).get("items", [])


def show_toast(title: str, message: str):
    # Imported lazily so non-Windows CI can import/test this module.
    from winotify import Notification
    Notification(app_id="JARVIS Personal AI", title=title, msg=message[:240]).show()


def _load_state(path: Path = STATE_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("reminders", {}), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"reminders": {}}


def _save_state(state: dict, path: Path = STATE_PATH):
    """Atomically persist status so a crash cannot leave a partially written state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def process_due(items: list[dict], state: dict, notify=show_toast, now: float | None = None) -> list[str]:
    """Deliver due reminders once, persist retry state, and return user-visible status lines."""
    now = time.time() if now is None else now
    statuses = []
    reminders = state.setdefault("reminders", {})
    for item in items:
        reminder_id = str(item["id"])
        previous = reminders.get(reminder_id, {})
        if previous.get("status") == "delivered":
            continue
        if previous.get("next_retry_at", 0) > now:
            continue
        attempts = int(previous.get("attempts", 0)) + 1
        try:
            notify("JARVIS reminder", item["title"])
        except Exception as exc:
            delay = min(30 * (2 ** (attempts - 1)), MAX_RETRY_SECONDS)
            message = str(exc).replace("\r", " ").replace("\n", " ")[:300]
            reminders[reminder_id] = {
                "status": "retrying", "attempts": attempts,
                "last_error": message, "next_retry_at": now + delay,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            statuses.append(f"Reminder #{reminder_id}: delivery failed (attempt {attempts}); retrying in {delay}s: {message}")
        else:
            reminders[reminder_id] = {
                "status": "delivered", "attempts": attempts, "last_error": "",
                "delivered_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            statuses.append(f"Reminder #{reminder_id}: toast delivered (attempt {attempts}).")
    return statuses


def run():
    if len(TOKEN) < 32:
        raise SystemExit("Set JARVIS_API_TOKEN to the same random token configured in the local backend.")
    state = _load_state()
    print(f"JARVIS reminder notifier polling {API_BASE}; Ctrl+C stops it.")
    print(f"Delivery state is saved in {STATE_PATH.resolve()}")
    while True:
        try:
            statuses = process_due(fetch_due(), state)
            _save_state(state)
            for status in statuses:
                print(status, flush=True)
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            print(f"Reminder check failed; will retry after {POLL_SECONDS}s: {exc}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run()
