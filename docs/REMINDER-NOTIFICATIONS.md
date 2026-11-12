# Reminder notifications (experimental)

The backend stores timezone-aware reminders and supports `none`, `daily`, `weekly`, or `monthly` recurrence when a user completes an occurrence. Notifications are best-effort and are not guaranteed alarms.

A saved plan with a target date creates a linked one-time reminder visible through `/api/reminders/due`. Completing or cancelling the plan marks that reminder complete; deleting the plan removes it. This delivers a due notification only when a notification worker is enabled, and never executes the plan's checklist or computer actions.

## Android

The Android app can optionally poll `/api/reminders/due` using WorkManager. Enable it from the app after connecting to the private HTTPS backend and grant the Android notification permission when prompted. Android 13 and later require the runtime `POST_NOTIFICATIONS` permission for regular notifications ([Android permission guide](https://developer.android.com/develop/ui/compose/notifications/notification-permission)). The worker reads the backend URL and bearer token from Android Keystore-encrypted storage; it does not place credentials in WorkManager input data. It requires network connectivity and checks about every 15 minutes; WorkManager's periodic work has a 15-minute minimum interval and can be delayed by constraints or system scheduling ([WorkManager guide](https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work)). Disable it in the app or clear the stored token to stop polling. Android notifications have not yet been verified on a physical device.

## Windows

The optional Windows worker polls `/api/reminders/due` and displays a Windows toast notification using `winotify`. It runs only while its terminal/process is running. The worker saves delivery attempts in `data/reminder-notifier-state.json` by default, so restarting it does not normally repeat a successfully delivered toast. If a toast call fails, it retries with exponential backoff (30 seconds up to 15 minutes). Delivery and retry messages are printed in the worker terminal. The state file is local and can be moved with `JARVIS_REMINDER_STATE_PATH`.

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
