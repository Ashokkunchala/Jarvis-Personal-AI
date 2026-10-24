# Windows reminder notifications (experimental)

The backend stores timezone-aware reminders. The optional Windows worker polls `/api/reminders/due` and displays a Windows toast notification using `winotify`. It runs only while its terminal/process is running; it is not a guaranteed alarm and does not yet support Android push notifications, recurrence, delivery acknowledgements, or reboot persistence. A process restart may display a due reminder again.

## Setup

1. Start the local backend with `HOST=127.0.0.1` and set a random `JARVIS_API_TOKEN` (32+ characters) in `.env`.
2. In a second PowerShell terminal, activate the project's virtual environment and set the same token for the worker:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements-windows-agent.txt
   $env:JARVIS_API_TOKEN = "paste-the-same-local-token-here"
   python -m windows_agent.reminder_notifier
   ```
3. Keep the worker running. Allow notifications for Windows/Python if prompted.

Do not paste the token into source code or commit it. Keep the backend local. The worker marks an ID as notified only in its current process memory; it does not delete or complete the reminder after showing a toast.
