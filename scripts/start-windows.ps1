$ErrorActionPreference = "Stop"
$pythonExe = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Virtual environment not found. Run: .\scripts\setup-windows.ps1" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path ".env")) {
    Write-Host ".env not found. Run setup and add your Gemini API key." -ForegroundColor Yellow
    exit 1
}
& $pythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
