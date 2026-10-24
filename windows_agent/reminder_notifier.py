"""Opt-in Windows toast worker for reminders stored by the local JARVIS backend."""
import json
import os
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

API_BASE = os.getenv("JARVIS_API_BASE", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.getenv("JARVIS_API_TOKEN", "")
POLL_SECONDS = max(15, int(os.getenv("JARVIS_REMINDER_POLL_SECONDS", "30")))


def fetch_due():
    request = Request(API_BASE + "/api/reminders/due", headers={"Authorization": "Bearer " + TOKEN})
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8")).get("items", [])


def show_toast(title: str, message: str):
    # Imported lazily so non-Windows CI can import/test this module.
    from winotify import Notification
    Notification(app_id="JARVIS Personal AI", title=title, msg=message[:240]).show()


def run():
    if len(TOKEN) < 32:
        raise SystemExit("Set JARVIS_API_TOKEN to the same random token configured in the local backend.")
    notified = set()
    print(f"JARVIS reminder notifier polling {API_BASE}; Ctrl+C stops it.")
    while True:
        try:
            for item in fetch_due():
                reminder_id = item["id"]
                if reminder_id in notified:
                    continue
                show_toast("JARVIS reminder", item["title"])
                notified.add(reminder_id)
                print(f"Displayed reminder #{reminder_id}")
        except (URLError, TimeoutError, ValueError) as exc:
            print(f"Reminder check failed: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run()
