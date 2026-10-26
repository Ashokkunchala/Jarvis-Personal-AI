$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
Write-Host "JARVIS terminal assistant. Type /help for commands; /quit exits." -ForegroundColor Cyan
& $pythonExe (Join-Path $root "jarvis_cli.py") tui
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Terminal assistant exited. Check GEMINI_API_KEY in the local .env file." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
}
