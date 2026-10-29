[CmdletBinding()]
param(
    [switch]$InstallDependencies,
    [switch]$StartAfterSetup
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Location).Path
$EnvExample = Join-Path $RepoRoot ".env.example"
$EnvFile = Join-Path $RepoRoot ".env"
$SetupScript = Join-Path $RepoRoot "scripts\setup-windows.ps1"
$StartScript = Join-Path $RepoRoot "scripts\start-windows.ps1"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Set-EnvValue([string]$Text, [string]$Name, [string]$Value) {
    $escapedName = [regex]::Escape($Name)
    $line = "$Name=$Value"
    if ($Text -match "(?m)^\s*$escapedName=") {
        return [regex]::Replace(
            $Text,
            "(?m)^\s*$escapedName=.*$",
            [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line }
        )
    }
    return $Text.TrimEnd() + [Environment]::NewLine + $line + [Environment]::NewLine
}

function New-Secret {
    # Compatible with Windows PowerShell 5.1 / .NET Framework.
    $bytes = New-Object byte[] 48
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    try { $rng.GetBytes($bytes) }
    finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}

Write-Host "JARVIS Live Voice setup (Windows PowerShell)" -ForegroundColor Green
Write-Host "Repository: $RepoRoot"

if (!(Test-Path (Join-Path $RepoRoot "app\core\config.py"))) {
    throw "Run this script from the Jarvis-Personal-AI repository root (app\core\config.py not found)."
}
if (!(Test-Path $EnvFile)) {
    if (!(Test-Path $EnvExample)) { throw ".env.example not found. Cannot create .env safely." }
    Copy-Item $EnvExample $EnvFile
    Write-Host "Created .env from .env.example."
}

Write-Step "Configure Live Voice"
$text = Get-Content -Raw -Path $EnvFile

$apiKeyMatch = [regex]::Match($text, '(?m)^GEMINI_API_KEY=(.*)$')
if (!$apiKeyMatch.Success -or [string]::IsNullOrWhiteSpace($apiKeyMatch.Groups[1].Value) -or $apiKeyMatch.Groups[1].Value.Trim().StartsWith("replace_")) {
    $secureKey = Read-Host "Enter your Gemini API key (input is hidden)" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try { $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey -match '^replace_') {
        throw "A real Gemini API key is required for Live Voice."
    }
    $text = Set-EnvValue $text "GEMINI_API_KEY" $apiKey
    $apiKey = $null
    $secureKey.Dispose()
} else {
    Write-Host "Keeping the existing GEMINI_API_KEY value."
}

$text = Set-EnvValue $text "GEMINI_LIVE_VOICE" "Charon"
$text = Set-EnvValue $text "GEMINI_LIVE_MODEL" "gemini-3.8-live"

foreach ($name in @("JARVIS_API_TOKEN", "SECRET_KEY", "JARVIS_AGENT_TOKEN")) {
    $match = [regex]::Match($text, "(?m)^$([regex]::Escape($name))=(.*)$")
    if (!$match.Success -or $match.Groups[2].Value.Trim().StartsWith("replace_") -or $match.Groups[2].Value.Trim().Length -lt 32) {
        $text = Set-EnvValue $text $name (New-Secret)
        Write-Host "Generated $name."
    } else {
        Write-Host "Keeping existing $name."
    }
}

# Write UTF-8 without BOM so dotenv parsing remains predictable on Windows PowerShell 5.1.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($EnvFile, $text, $utf8NoBom)
Write-Host "Updated .env (secrets are not displayed)." -ForegroundColor Green

Write-Step "Validate local configuration"
$finalText = Get-Content -Raw -Path $EnvFile
$apiKeyMatch = [regex]::Match($finalText, '(?m)^GEMINI_API_KEY=(.*)$')
$apiTokenMatch = [regex]::Match($finalText, '(?m)^JARVIS_API_TOKEN=(.*)$')
$secretMatch = [regex]::Match($finalText, '(?m)^SECRET_KEY=(.*)$')
$agentTokenMatch = [regex]::Match($finalText, '(?m)^JARVIS_AGENT_TOKEN=(.*)$')
$checks = @(
    @{ Name = "Gemini API key configured"; Pass = ($apiKeyMatch.Success -and $apiKeyMatch.Groups[1].Value.Trim().Length -gt 10 -and !$apiKeyMatch.Groups[1].Value.Trim().StartsWith("replace_")) },
    @{ Name = "Live voice set to Charon"; Pass = ($finalText -match '(?m)^GEMINI_LIVE_VOICE=Charon\s*$') },
    @{ Name = "Live model configured"; Pass = ($finalText -match '(?m)^GEMINI_LIVE_MODEL=.+\S') },
    @{ Name = "API token is at least 32 characters"; Pass = ($apiTokenMatch.Success -and $apiTokenMatch.Groups[1].Value.Trim().Length -ge 32) },
    @{ Name = "Secret key is at least 32 characters"; Pass = ($secretMatch.Success -and $secretMatch.Groups[1].Value.Trim().Length -ge 32) },
    @{ Name = "Agent token is at least 32 characters"; Pass = ($agentTokenMatch.Success -and $agentTokenMatch.Groups[1].Value.Trim().Length -ge 32) },
    @{ Name = "Voice backend and Windows start script exist"; Pass = ((Test-Path (Join-Path $RepoRoot "app\live_voice.py")) -and (Test-Path $StartScript)) }
)
$failed = $false
foreach ($check in $checks) {
    if ($check.Pass) { Write-Host "[PASS] $($check.Name)" -ForegroundColor Green }
    else { Write-Host "[FAIL] $($check.Name)" -ForegroundColor Red; $failed = $true }
}
if ($failed) { throw "One or more configuration checks failed. Review the messages above." }

if ($InstallDependencies -or ($StartAfterSetup -and !(Test-Path (Join-Path $RepoRoot ".venv\Scripts\python.exe")))) {
    Write-Step "Install project dependencies"
    if (!(Test-Path $SetupScript)) { throw "Setup script not found: $SetupScript" }
    & $SetupScript
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Dependency setup failed with exit code $LASTEXITCODE." }
}

Write-Step "Setup complete"
Write-Host "Voice profile: Charon"
Write-Host "Configured model: gemini-3.8-live. Confirm that this model ID is currently available to your Gemini API project."
Write-Host "Next: run .\scripts\start-windows.ps1, open http://127.0.0.1:8000, enter JARVIS_API_TOKEN from .env, and click Start Live Voice."
Write-Host "Do not share or commit .env. These checks do not prove live API connectivity or audible playback."

if ($StartAfterSetup) {
    if (!(Test-Path $StartScript)) { throw "Start script not found: $StartScript" }
    Write-Step "Starting JARVIS"
    & $StartScript
}
