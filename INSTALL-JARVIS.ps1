#requires -Version 5.1
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host ""
Write-Host "JARVIS Personal AI - Windows installer" -ForegroundColor Cyan

$installRoot = Join-Path $env:LOCALAPPDATA "Programs\JarvisPersonalAI"
$tempRoot = Join-Path $env:TEMP ("jarvis-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

function Set-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $escapedName = [regex]::Escape($Name)
    $line = "$Name=$Value"
    if ($Text -match "(?m)^$escapedName=.*$") {
        return [regex]::Replace($Text, "(?m)^$escapedName=.*$", [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line })
    }
    return $Text.TrimEnd() + [Environment]::NewLine + $line + [Environment]::NewLine
}

# Return only an executable that actually runs Python 3.11+ (the project minimum).
# Use one invocation so a failed candidate cannot borrow another probe's exit code.
function Test-PythonRuntime {
    param([string]$Executable, [string[]]$LauncherArgs = @())
    try {
        $probeOutput = @(& $Executable @LauncherArgs -c "import sys; sys.exit(1) if sys.version_info < (3, 11) else print(sys.executable)" 2>$null)
        $probeExitCode = $LASTEXITCODE
        $candidate = $probeOutput | Select-Object -First 1
        if ($probeExitCode -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate.Trim() -PathType Leaf)) {
            return $candidate.Trim()
        }
    } catch {
        # Missing runtimes, Store aliases and launcher errors are failed probes.
    }
    return $null
}

function Find-PythonRuntime {
    $pyCommand = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
    if ($pyCommand) {
        # A launcher's default can be old even when a supported runtime exists.
        foreach ($selector in @("-3", "-3.14", "-3.13", "-3.12", "-3.11")) {
            $candidate = Test-PythonRuntime -Executable $pyCommand.Source -LauncherArgs @($selector)
            if ($candidate) { return $candidate }
        }
    }
    foreach ($name in @("python", "python3")) {
        foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            $candidate = Test-PythonRuntime -Executable $command.Source
            if ($candidate) { return $candidate }
        }
    }
    # Some existing per-user installs have neither a launcher nor PATH entries.
    foreach ($version in @("314", "313", "312", "311")) {
        $path = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe"
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $candidate = Test-PythonRuntime -Executable $path
            if ($candidate) { return $candidate }
        }
    }
    return $null
}

function Update-SessionPath {
    # Read the persisted PATH again; keep any process-only entries as fallbacks.
    $paths = @(
        [Environment]::GetEnvironmentVariable("Path", "Machine"),
        [Environment]::GetEnvironmentVariable("Path", "User"),
        $env:Path
    )
    $env:Path = ($paths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ";"
}

try {
    $pythonExe = Find-PythonRuntime
    if (-not $pythonExe) {
        # An earlier Python install may not yet be on this PowerShell's PATH.
        Update-SessionPath
        $pythonExe = Find-PythonRuntime
    }

    if (-not $pythonExe) {
        $wingetCommand = Get-Command winget -CommandType Application -ErrorAction SilentlyContinue
        if (-not $wingetCommand) {
            throw "Python 3.11+ is required and winget is unavailable. Install Python from https://www.python.org/downloads/windows/ and rerun this installer."
        }

        Write-Host "No suitable Python runtime was found. Installing Python 3.14 for this Windows user..." -ForegroundColor Yellow
        try {
            & $wingetCommand.Source install --id Python.Python.3.14 -e --scope user --silent --accept-package-agreements --accept-source-agreements
        } catch {
            # Native-command errors must not skip the refresh and runtime check.
            Write-Warning "winget did not finish normally; checking for an existing Python runtime."
        }

        # winget also returns nonzero when the package is already up to date.
        # Runtime availability, not winget's exit code or localized text, decides success.
        Update-SessionPath
        $pythonExe = Find-PythonRuntime
        if (-not $pythonExe) {
            throw "No working Python 3.11+ runtime was found after refreshing PATH and checking py, python and python3. Install Python from https://www.python.org/downloads/windows/ (enable Add python.exe to PATH) and rerun this installer."
        }
    }

    Write-Host "Downloading current JARVIS branch..."
    $zipPath = Join-Path $tempRoot "jarvis.zip"
    Invoke-WebRequest -Uri "https://codeload.github.com/Ashokkunchala/Jarvis-Personal-AI/zip/refs/heads/jarvis-cinematic-local-voice" -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $tempRoot -Force

    $sourceRoot = Get-ChildItem $tempRoot -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "requirements-dev.txt") } |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $sourceRoot) {
        throw "Could not find the downloaded JARVIS source tree."
    }

    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    Get-ChildItem $sourceRoot -Force |
        Where-Object { $_.Name -notin @(".env", ".venv", "data", "logs") } |
        ForEach-Object { Copy-Item $_.FullName -Destination $installRoot -Recurse -Force }

    foreach ($folder in @("data", "logs")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $installRoot $folder) | Out-Null
    }

    $venvPath = Join-Path $installRoot ".venv"
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "Creating Python environment..."
        & $pythonExe -m venv $venvPath
        if ($LASTEXITCODE -ne 0) { throw "Could not create Python environment." }
    }

    Write-Host "Installing dependencies; this may take a few minutes..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

    & $venvPython -m pip install -r (Join-Path $installRoot "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

    $envPath = Join-Path $installRoot ".env"
    if (-not (Test-Path $envPath)) {
        $token = (& $venvPython -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
        $secret = (& $venvPython -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
        $templatePath = Join-Path $installRoot ".env.example"
        if (-not (Test-Path $templatePath)) { throw ".env.example is missing from the downloaded source." }
        $template = Get-Content $templatePath -Raw

        $template = Set-EnvValue -Text $template -Name "JARVIS_API_TOKEN" -Value $token
        $template = Set-EnvValue -Text $template -Name "SECRET_KEY" -Value $secret
        $template = Set-EnvValue -Text $template -Name "HOST" -Value "127.0.0.1"
        $template = Set-EnvValue -Text $template -Name "PORT" -Value "8000"

        Write-Host ""
        Write-Host "Enter API keys. They are saved only in your local .env file." -ForegroundColor Yellow
        Write-Host "Gemini is required for current live voice features." -ForegroundColor Yellow
        $gemini = Read-Host "Gemini API key (required)"
        if ([string]::IsNullOrWhiteSpace($gemini)) {
            throw "Gemini API key is required for current live voice features. Rerun after obtaining one."
        }
        $openrouter = Read-Host "OpenRouter API key (optional; press Enter to skip)"
        $groq = Read-Host "Groq API key (optional; press Enter to skip)"

        $template = Set-EnvValue -Text $template -Name "GEMINI_API_KEY" -Value $gemini.Trim()
        $template = Set-EnvValue -Text $template -Name "OPENROUTER_API_KEY" -Value $openrouter.Trim()
        $template = Set-EnvValue -Text $template -Name "GROQ_API_KEY" -Value $groq.Trim()
        $template = Set-EnvValue -Text $template -Name "JARVIS_AI_PROVIDER" -Value "auto"

        Set-Content -Path $envPath -Value $template -Encoding UTF8
    }
    else {
        Write-Host "Keeping existing .env credentials and settings." -ForegroundColor Green
    }

    $sessionScript = Join-Path $installRoot "scripts\start-jarvis-session.ps1"
    if (-not (Test-Path $sessionScript)) {
        throw "Startup script is missing from installed package."
    }

    $actionArgs = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $sessionScript + '"'
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

    Register-ScheduledTask -TaskName "JARVIS Personal AI" -Action $action -Trigger $trigger -Principal $principal -Settings $taskSettings -Description "Starts the local JARVIS assistant after this user signs in." -Force | Out-Null

    Write-Host "Installation complete. Starting JARVIS..." -ForegroundColor Green
    & $sessionScript

    Write-Host "JARVIS will start after you sign in to Windows."
    Write-Host "UI: http://127.0.0.1:8000"
    Write-Host "Installed at: $installRoot"
    Write-Host "Disable auto-start by disabling the JARVIS Personal AI task in Task Scheduler."
}
finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
