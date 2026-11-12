#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Call,
    [switch]$NoLaptop
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
$cli = Join-Path $root "jarvis_cli.py"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "JARVIS environment missing at $pythonExe. Run INSTALL-JARVIS.ps1 first."
}

$cliArgs = @($cli, "robot")
if ($Call) { $cliArgs += "--call" }
if ($NoLaptop) { $cliArgs += "--no-laptop" }

Write-Host "JARVIS floating robot. Press v for a voice call, space to pause, q to quit." -ForegroundColor Cyan
& $pythonExe @cliArgs
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host ""
    Write-Host "JARVIS robot exited with code $code. Check .env and the voice stack." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
}
exit $code
