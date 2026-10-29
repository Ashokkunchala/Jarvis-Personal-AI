[CmdletBinding()]
param(
    [switch]$SkipDependencyInstall,
    [switch]$SkipTests,
    [switch]$StartAfterSetup,
    [switch]$NoApiKeyPrompt
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Location).Path
$Failures = New-Object System.Collections.Generic.List[string]

function Write-Section([string]$Message) {
    Write-Host ""
    Write-Host ("=" * 68) -ForegroundColor DarkCyan
    Write-Host ("  " + $Message) -ForegroundColor Cyan
    Write-Host ("=" * 68) -ForegroundColor DarkCyan
}
function Pass([string]$Message) { Write-Host "[PASS] $Message" -ForegroundColor Green }
function Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Fail([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    $script:Failures.Add($Message)
}
function Test-Placeholder([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $true }
    return ($Value.Trim() -match '^(replace_|your_.*_here|changeme|change_me|placeholder)')
}
function Set-EnvValue([string]$Text, [string]$Name, [string]$Value) {
    $escaped = [regex]::Escape($Name)
    $line = "$Name=$Value"
    if ($Text -match "(?m)^\s*$escaped=") {
        return [regex]::Replace($Text, "(?m)^\s*$escaped=.*$", [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line })
    }
    return $Text.TrimEnd() + [Environment]::NewLine + $line + [Environment]::NewLine
}
function New-Secret {
    $bytes = New-Object byte[] 48
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}

Write-Section "JARVIS Personal AI — setup and validation"
Write-Host "Repository: $RepoRoot"
if (!(Test-Path (Join-Path $RepoRoot "app\main.py")) -or !(Test-Path (Join-Path $RepoRoot "requirements-dev.txt"))) {
    throw "Run this script from the Jarvis-Personal-AI repository root. Expected app\main.py and requirements-dev.txt."
}
if (!(Test-Path (Join-Path $RepoRoot "scripts\start-windows.ps1"))) {
    throw "scripts\start-windows.ps1 is missing from this checkout."
}
Pass "Repository structure"

Write-Section "Check prerequisites"
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) { Pass "Git is installed" } else { Warn "Git not found; local setup can continue, but updating the repository requires Git." }

$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$pythonExe = $null
if ($pythonLauncher) {
    $versionOutput = (& py -3 --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $versionOutput -match 'Python\s+(\d+)\.(\d+)') {
        $major = [int]$Matches[1]; $minor = [int]$Matches[2]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) { $pythonExe = "py -3" }
    }
}
if (!$pythonExe -and $pythonCommand) {
    $versionOutput = (& python --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $versionOutput -match 'Python\s+(\d+)\.(\d+)') {
        $major = [int]$Matches[1]; $minor = [int]$Matches[2]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) { $pythonExe = "python" }
    }
}
if (!$pythonExe) {
    throw "Python 3.11+ was not found. Install it from https://www.python.org/downloads/windows/, enable PATH, reopen PowerShell, and rerun."
}
Pass "Python 3.11+ ($versionOutput)"

$venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (!(Test-Path $venvPython)) {
    Write-Host "Creating local virtual environment..."
    if ($pythonExe -eq "py -3") { & py -3 -m venv (Join-Path $RepoRoot ".venv") }
    else { & python -m venv (Join-Path $RepoRoot ".venv") }
    if ($LASTEXITCODE -ne 0 -or !(Test-Path $venvPython)) { throw "Could not create .venv. Check Python installation and permissions." }
}
Pass "Virtual environment exists"

if (!$SkipDependencyInstall) {
    Write-Section "Install and verify dependencies"
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $venvPython -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Installing requirements-dev.txt failed. Review the pip output above." }
    Pass "requirements-dev.txt installed"
} else {
    Warn "Dependency installation skipped by -SkipDependencyInstall."
}

& $venvPython -c "import sys; print(sys.version)"
if ($LASTEXITCODE -ne 0) { Fail "Python runtime check failed." } else { Pass "Python runtime starts" }
& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { Fail "pip dependency consistency check failed." } else { Pass "pip dependency consistency" }

Write-Section "Environment and secret checks"
$envPath = Join-Path $RepoRoot ".env"
$examplePath = Join-Path $RepoRoot ".env.example"
if (!(Test-Path $envPath)) {
    if (!(Test-Path $examplePath)) { throw ".env.example is missing; cannot create a safe environment file." }
    Copy-Item $examplePath $envPath
    Warn "Created .env from .env.example. Review it before using JARVIS."
}
$text = Get-Content -Raw -Path $envPath

foreach ($name in @("JARVIS_API_TOKEN", "SECRET_KEY", "JARVIS_AGENT_TOKEN")) {
    $match = [regex]::Match($text, "(?m)^\s*$([regex]::Escape($name))=(.*)$")
    if (!$match.Success -or (Test-Placeholder $match.Groups[1].Value) -or $match.Groups[1].Value.Trim().Length -lt 32) {
        $text = Set-EnvValue $text $name (New-Secret)
        Pass "Generated/renewed $name (value hidden)"
    } else {
        Pass "$name present with sufficient length (value hidden)"
    }
}
# Keep the local server bound to loopback by default.
if ($text -match '(?m)^\s*HOST=(.*)$' -and $Matches[1].Trim() -ne "127.0.0.1") {
    Warn "HOST is not 127.0.0.1. For this prototype, set HOST=127.0.0.1 and do not expose it publicly."
}
if ($text -notmatch '(?m)^\s*HOST=') { $text = Set-EnvValue $text "HOST" "127.0.0.1" }

$providerNames = @("GEMINI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY")
$hasProvider = $false
foreach ($name in $providerNames) {
    $m = [regex]::Match($text, "(?m)^\s*$([regex]::Escape($name))=(.*)$")
    if ($m.Success -and !(Test-Placeholder $m.Groups[1].Value)) { $hasProvider = $true }
}
if (!$hasProvider -and !$NoApiKeyPrompt) {
    Write-Host "No AI provider API key is configured. A key is required for real AI responses; tests can run without one." -ForegroundColor Yellow
    $secureKey = Read-Host "Gemini API key (press Enter to configure it later)" -AsSecureString
    if ($secureKey.Length -gt 0) {
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        try { $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); $secureKey.Dispose() }
        if (Test-Placeholder $apiKey) { throw "The entered key looks like a placeholder. No API key was saved." }
        $text = Set-EnvValue $text "GEMINI_API_KEY" $apiKey
        $apiKey = $null
        $hasProvider = $true
        Pass "Gemini key saved locally (value hidden)"
    } else {
        $secureKey.Dispose()
        Warn "No provider key entered. Setup/tests may continue, but real AI chat and Live Voice will not work until a valid key is configured."
    }
} elseif ($hasProvider) {
    Pass "At least one AI provider key appears configured (not tested against the provider)"
} else {
    Warn "API-key prompt skipped by -NoApiKeyPrompt. Real AI requests need a valid provider key."
}
# Write UTF-8 without BOM for Windows PowerShell 5.1 compatibility.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($envPath, $text, $utf8NoBom)
Pass ".env saved; secret values were not printed"

Write-Section "Static and feature-presence checks"
$requiredPaths = @(
    "app\main.py",
    "app\live_voice.py",
    "jarvis_cli.py",
    "scripts\setup-windows.ps1",
    "scripts\start-windows.ps1",
    "tests"
)
foreach ($relative in $requiredPaths) {
    if (Test-Path (Join-Path $RepoRoot $relative)) { Pass "$relative exists" }
    else { Fail "$relative is missing" }
}

& $venvPython -m compileall -q app jarvis
if ($LASTEXITCODE -ne 0) { Fail "Python compile check failed." } else { Pass "Python modules compile" }

if (!$SkipTests) {
    Write-Section "Automated test suite"
    & $venvPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { Fail "pytest failed. Fix reported tests before treating setup as validated." }
    else { Pass "pytest suite passed" }
} else {
    Warn "Tests skipped by -SkipTests."
}

Write-Section "Local API check (no server started by this check)"
$healthUrl = "http://127.0.0.1:8000/health"
try {
    $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
    Pass "Existing local API responded at $healthUrl"
    Write-Host ("Health response: " + ($health | ConvertTo-Json -Compress -Depth 4))
} catch {
    Warn "No responding JARVIS API found at $healthUrl. This is normal before startup; run the start script to check the live endpoint."
}

Write-Section "Summary"
if ($Failures.Count -gt 0) {
    Write-Host ("Setup completed with {0} failure(s):" -f $Failures.Count) -ForegroundColor Red
    foreach ($item in $Failures) { Write-Host " - $item" -ForegroundColor Red }
    throw "JARVIS setup/validation failed. Resolve the failures above and rerun this script."
}
Write-Host "Setup and local checks completed. This does not prove provider connectivity, microphone/speaker behavior, Android hardware actions, or production readiness." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Review local .env; keep all API keys and tokens private."
Write-Host ('  2. Start JARVIS with: .\scripts\start-windows.ps1')
Write-Host ('  3. Open http://127.0.0.1:8000 and test chat/voice manually.')
Write-Host ('  4. For terminal UI: .\.venv\Scripts\python.exe jarvis_cli.py tui')
Write-Host ('  5. For Android, build/install the separate APK and test on a physical device.')

if ($StartAfterSetup) {
    Write-Section "Starting JARVIS"
    & (Join-Path $RepoRoot "scripts\start-windows.ps1")
}
