$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
if (-not (Test-Path $pythonExe)) { throw "JARVIS environment missing. Run INSTALL-JARVIS.ps1 again." }
if (-not (Test-Path (Join-Path $root ".env"))) { throw "JARVIS .env missing. Run INSTALL-JARVIS.ps1 again." }
$healthy = $false
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
    $healthy = ($health.status -eq "ok")
} catch { $healthy = $false }
if (-not $healthy) {
    Start-Process -FilePath $pythonExe -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "backend.log") -RedirectStandardError (Join-Path $logs "backend-error.log") | Out-Null
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
Start-Process "http://127.0.0.1:8000"
$terminalScript = Join-Path $root "scripts\start-jarvis-terminal.ps1"
$terminalArgs = '-NoExit -NoProfile -ExecutionPolicy Bypass -File "' + $terminalScript + '"'
Start-Process -FilePath "powershell.exe" -ArgumentList $terminalArgs -WorkingDirectory $root
