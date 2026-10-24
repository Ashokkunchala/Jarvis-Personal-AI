$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "JARVIS Personal AI - Windows setup" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan

$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Host "Python 3.11+ was not found. Install it from https://www.python.org/downloads/windows/ and enable PATH, then rerun this script." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    if ($python.Name -eq "py.exe" -or $python.Name -eq "py") {
        & py -3 -m venv .venv
    } else {
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create virtual environment." }
}

$pythonExe = Join-Path (Get-Location) ".venv\Scripts\python.exe"
Write-Host "Installing dependencies..."
& $pythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $pythonExe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from template. Edit .env and set GEMINI_API_KEY before chatting." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete. Start the app with:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "Then open http://127.0.0.1:8000"
Write-Host "Keep the host as 127.0.0.1. Do not expose this starter publicly without authentication and a security review."
