#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Call,
    [switch]$NoLaptop,
    [switch]$Remove,
    [string]$Name = "JARVIS.lnk",
    [string]$StartupFolder = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if ([string]::IsNullOrWhiteSpace($StartupFolder)) {
    $StartupFolder = [Environment]::GetFolderPath("Startup")
}
if ([string]::IsNullOrWhiteSpace($StartupFolder)) {
    throw "Could not resolve the per-user Startup folder."
}
$linkPath = Join-Path $StartupFolder $Name

if ($Remove) {
    if (Test-Path -LiteralPath $linkPath) {
        Remove-Item -LiteralPath $linkPath -Force
        Write-Host "Removed startup shortcut: $linkPath" -ForegroundColor Green
    } else {
        Write-Host "No startup shortcut at $linkPath" -ForegroundColor Yellow
    }
    return
}

$terminalScript = Join-Path $root "scripts\start-jarvis-terminal.ps1"
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $terminalScript)) {
    throw "Missing $terminalScript."
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Missing $pythonExe. Run INSTALL-JARVIS.ps1 first."
}
New-Item -ItemType Directory -Force -Path $StartupFolder | Out-Null

$launchArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$terminalScript`""
)
if ($Call) { $launchArgs += "-Call" }
if ($NoLaptop) { $launchArgs += "-NoLaptop" }

$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $powershellExe
$shortcut.Arguments = $launchArgs -join " "
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 1
$shortcut.Description = "JARVIS floating robot"
$shortcut.Save()

Write-Host "Installed startup shortcut: $linkPath" -ForegroundColor Green
if ($Call) {
    Write-Host "It starts a live voice call at sign-in (the microphone opens immediately)." -ForegroundColor Yellow
} else {
    Write-Host "It starts the robot at sign-in. Press v for a voice call; the microphone stays closed until then." -ForegroundColor Cyan
}
Write-Host "Remove it with: .\scripts\install-jarvis-startup.ps1 -Remove" -ForegroundColor DarkGray
