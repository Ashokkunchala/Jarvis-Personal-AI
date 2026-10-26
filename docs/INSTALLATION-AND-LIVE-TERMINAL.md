# Windows Installation and Live Terminal Guide

This guide is for the `improve/security-quality-gates` branch. It covers setup, the realtime terminal, and the optional one-shot microphone input. Do not paste API keys or tokens into chat, issues, screenshots, or Git.

## 1. Update the local checkout

Open PowerShell in your existing repository folder:

```powershell
cd "$env:USERPROFILE\Desktop\Jarvis-Personal-AI"
git switch improve/security-quality-gates
git pull origin improve/security-quality-gates
```

If Git reports local changes or a merge conflict, stop and resolve those changes before proceeding. Do not run `git reset --hard`.

For a new checkout:

```powershell
cd "$env:USERPROFILE\Desktop"
git clone --branch improve/security-quality-gates https://github.com/Ashokkunchala/Jarvis-Personal-AI.git
cd Jarvis-Personal-AI
```

## 2. Check Python and create the virtual environment

The project requires Python 3.11 or newer. Use the Python launcher if available:

```powershell
py -3 --version
```

Create the environment if it does not exist:

```powershell
if (-not (Test-Path .venv\Scripts\python.exe)) {
    py -3 -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

If `py -3` cannot find a suitable runtime, install a current stable Python release from https://www.python.org/downloads/windows/ (or use the official Windows package manager), reopen PowerShell, and repeat the version check. Ensure the selected Python is 3.11+.

## 3. Install project and Windows dependencies

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[windows]"
```

This installs the project in editable mode and its Windows extras, including its declared runtime dependencies. The terminal microphone dependency is declared in `pyproject.toml`; if you need to install it separately while troubleshooting, run:

```powershell
.\.venv\Scripts\python.exe -m pip install "SpeechRecognition[audio]"
```

If installation reports a TOML parsing error, first confirm that `git pull origin improve/security-quality-gates` succeeded and that `pyproject.toml` does not contain a literal `\n` inside a dependency line. Then retry the installation command. Do not manually paste escaped newline characters into TOML.

## 4. Configure the Gemini key

Check whether the local environment file exists:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `GEMINI_API_KEY` to your own key from https://aistudio.google.com/. Keep real credentials in the local `.env` only; do not commit the file. For the direct terminal assistant, `GEMINI_API_KEY` is the essential setting.

## 5. Launch the realtime terminal

```powershell
.\.venv\Scripts\python.exe jarvis_cli.py tui
```

The terminal streams model text as it arrives, displays tool calls and their outcomes, and refreshes system telemetry. Try a read-only request first, such as “Check my laptop battery and system status.” Tool actions that require confirmation should still ask before running.

Other useful commands:

```powershell
.\.venv\Scripts\python.exe jarvis_cli.py ask "What is my battery status?"
.\.venv\Scripts\python.exe jarvis_cli.py laptop status
.\.venv\Scripts\python.exe jarvis_cli.py tools
```

## 6. Use terminal microphone input

In the TUI, click **MIC** to capture one utterance. Speak after the listening message; the transcript is then submitted to the normal Gemini tool-calling loop. Click MIC again for another utterance.

- Allow microphone access in Windows Settings → Privacy & security → Microphone.
- Use a working default recording device in Windows Sound settings.
- This is push-to-capture, one utterance at a time. It is **not** an always-on microphone or a “Hey JARVIS” wake-word listener.
- The current transcription adapter uses Google Speech Recognition and sends the captured speech audio to that service for transcription. Do not use it for sensitive conversations if that data flow is unsuitable.
- If the optional audio backend fails to install or cannot open the microphone, inspect the full error and your Python architecture/version before trying a compatible PyAudio wheel. Do not install random binaries from untrusted websites.

## 7. Run checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Automated tests do not prove the microphone works on your specific laptop. Verify microphone capture and a real Gemini request on the target device. API requests may incur provider quota or charges.

## Troubleshooting

- **TOMLDecodeError:** update the branch and retry; verify dependency lines in `pyproject.toml` are ordinary separate lines, not literal escaped newline text.
- **Python runtime not found:** run `py -0p` to list installed runtimes, install Python 3.11+, and recreate `.venv` only if it was created with an unavailable interpreter. Back up any local work before recreating the environment.
- **No Gemini response:** check `GEMINI_API_KEY`, network access, model availability, account quota and provider status. Never share the key in logs.
- **No speech recognized:** use a quiet environment, check the default microphone, speak clearly in English, and check internet access for transcription.
- **Permission or device error:** verify Windows microphone privacy settings and that no other application exclusively owns the device.

## Safety notes

The direct terminal can execute laptop actions through its tool registry. Keep confirmation prompts enabled for risky actions; do not pre-approve tools you do not trust. The local web backend should remain bound to localhost and must not be exposed to the public internet without a security review.
