#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Call,
    [switch]$NoLaptop,
    [switch]$SkipBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "logs"
$envFile = Join-Path $root ".env"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "JARVIS environment missing. Run INSTALL-JARVIS.ps1 again."
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "JARVIS .env missing. Run INSTALL-JARVIS.ps1 again."
}
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$healthy = $false
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
    $healthy = ($health.status -eq "ok")
} catch { $healthy = $false }

if (-not $healthy) {
    $backendArgs = @(
        "-m", "uvicorn", "app.main_enhanced:app",
        "--host", "127.0.0.1", "--port", "8000"
    )
    Start-Process -FilePath $pythonExe -ArgumentList $backendArgs -WorkingDirectory $root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "backend.log") `
        -RedirectStandardError (Join-Path $logs "backend-error.log") | Out-Null

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 750
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
            if ($health.status -eq "ok") { $healthy = $true; break }
        } catch {}
    }
}

if (-not $healthy) {
    Start-Process notepad.exe -ArgumentList (Join-Path $logs "backend-error.log")
    throw "JARVIS backend did not start. Check logs\backend-error.log."
}

if (-not $SkipBrowser) {
    Start-Process "http://127.0.0.1:8000"
}

$terminalScript = Join-Path $root "scripts\start-jarvis-terminal.ps1"
$terminalArgs = '-NoExit -NoProfile -ExecutionPolicy Bypass -File "' + $terminalScript + '"'
if ($Call) { $terminalArgs += " -Call" }
if ($NoLaptop) { $terminalArgs += " -NoLaptop" }
Start-Process -FilePath "powershell.exe" -ArgumentList $terminalArgs -WorkingDirectory $root
