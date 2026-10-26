# Windows reminder notifications (experimental)

The backend stores timezone-aware reminders. The optional Windows worker polls `/api/reminders/due` and displays a Windows toast notification using `winotify`. It runs only while its terminal/process is running; it is not a guaranteed alarm and does not support Android push notifications, recurrence, or reboot scheduling. The worker saves delivery attempts in `data/reminder-notifier-state.json` by default, so restarting it does not normally repeat a successfully delivered toast. If a toast call fails, it retries with exponential backoff (30 seconds up to 15 minutes). Delivery and retry messages are printed in the worker terminal. The state file is local and can be moved with `JARVIS_REMINDER_STATE_PATH`.

## Setup

1. Start the local backend with `HOST=127.0.0.1` and set a random `JARVIS_API_TOKEN` (32+ characters) in `.env`.
2. In a second PowerShell terminal, activate the project's virtual environment and set the same token for the worker:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements-windows-agent.txt
   $env:JARVIS_API_TOKEN = "paste-the-same-local-token-here"
   python -m windows_agent.reminder_notifier
   ```
3. Keep the worker running. Allow notifications for Windows/Python if prompted. Watch its terminal for delivered, retrying, or backend connection status messages.

Do not paste the token into source code or commit it. Keep the backend local. A toast delivery does not delete or complete the reminder; completion remains a separate user action in the dashboard. Keep the state file with the same local profile if you want deduplication to persist across restarts. If it is deleted, an already due reminder may be shown again. The worker cannot confirm whether Windows displayed the toast to the user; “delivered” means the local toast library accepted the notification without raising an error.
