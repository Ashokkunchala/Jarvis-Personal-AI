# Windows Setup — Step by Step

This guide starts the JARVIS web interface and Gemini chat locally. It does **not** install an Android app or enable device control.

## 1. Create a Gemini API key
1. Open [Google AI Studio](https://aistudio.google.com/).
2. Sign in and create a Gemini API key according to the current Google AI Studio instructions.
3. Review current model availability, quotas, and pricing for your account. Do not assume all usage is free.
4. Never paste the key into the browser, chat UI, GitHub issue, screenshot, or source file.

## 2. Install prerequisites
- Install Git for Windows if you do not already have it.
- Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/windows/). Enable the PATH option if offered.
- Open PowerShell and clone the repository:

```powershell
git clone https://github.com/Ashokkunchala/Jarvis-Personal-AI.git
cd Jarvis-Personal-AI
```

If you already cloned it, update it:

```powershell
git pull
```

## 3. Run the setup script

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup-windows.ps1
```

This creates a virtual environment and installs dependencies. It creates `.env` from `.env.example` if the file does not exist.

## 4. Add your key
Open the local `.env` file in Notepad:

```powershell
notepad .env
```

Replace `replace_me` with your real key:

```dotenv
GEMINI_API_KEY=your_real_key_here
GEMINI_MODEL=gemini-2.5-flash
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
JARVIS_API_TOKEN=replace_with_a_random_secret_at_least_32_characters
JARVIS_DB_PATH=data/jarvis.sqlite3
```

Generate a random token in PowerShell with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and replace the placeholder `JARVIS_API_TOKEN` value with it. Never leave the example placeholder in place. The token protects memory, reminders, workout, research, and coaching APIs. The chat route now requires the configured bearer token. Keep the backend bound to localhost because shared-token authentication is not production device pairing. Do not include extra quotes unless required by the value. The suggested model is configurable; if Google changes model availability or your account cannot use it, select a currently supported model from Google's documentation. Keep the Gemini key and token only in this local file.

## 5. Start JARVIS

```powershell
.\scripts\start-windows.ps1
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Keep the PowerShell window open while using JARVIS. Press Ctrl+C in that window to stop the server.

## 6. Test the API

In a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Test chat:

```powershell
$body = @{ message = "Hello JARVIS. Introduce yourself in friendly Indian English."; language = "en" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/chat -Method Post -ContentType "application/json" -Body $body
```

Run automated tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The tests do not need a paid Gemini request. A real chat does.

With the backend running, verify your real Gemini key with the one-request smoke test (provider quota may apply):

```powershell
.\\scripts\\smoke-test.ps1
```

## Voice notes
- Browser voice recognition depends on browser support, microphone permission, and OS settings. Current Chrome/Edge usually provide the best support.
- The UI uses browser text-to-speech for spoken replies. Available Indian English and Telugu voices depend on the OS/browser.
- This is not continuous background listening. The microphone is activated only when you press Speak.

## Troubleshooting
- **503 / API not configured:** verify `.env` is in the repository root and the key is not still `replace_me`; restart the server after changing environment settings.
- **502 / AI request failed:** verify key validity, model availability, internet connection, quotas, billing, and server logs. Do not share the key when requesting help.
- **PowerShell blocks scripts:** use the process-scoped policy command above; do not change the machine-wide policy unnecessarily.
- **Port 8000 busy:** stop the other process or start with `--port 8001`, then open `http://127.0.0.1:8001`.
- **No microphone button support:** use a supported browser or type into the message box.
- **Telugu voice unavailable:** the model can return Telugu text, but local spoken output depends on installed browser/OS voices.

## Safety
The starter is deliberately bound to localhost. Do not bind it to `0.0.0.0`, port-forward it, or expose it via a public tunnel. Personal-data APIs require a bearer token, but the chat endpoint is still unauthenticated. Keep all routes local; do not expose this prototype to the internet.
