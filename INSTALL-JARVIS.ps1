#requires -Version 5.1
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Write-Host ""
Write-Host "JARVIS Personal AI - One-file Windows installer" -ForegroundColor Cyan

$installRoot = Join-Path $env:LOCALAPPDATA "Programs\JarvisPersonalAI"
$tempRoot = Join-Path $env:TEMP ("jarvis-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
try {
    $pythonExe = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) { $pythonExe = ($candidate | Select-Object -First 1).Trim() }
    }
    if (-not $pythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $candidate = & python -c "import sys; print(sys.executable)" 2>$null
        $version = & python -c "import sys; print(sys.version_info >= (3,11))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate -and ($version | Select-Object -First 1).Trim() -eq "True") {
            $pythonExe = ($candidate | Select-Object -First 1).Trim()
        }
    }
    if (-not $pythonExe) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "Python 3.11+ is required. Install it from https://www.python.org/downloads/windows/ and rerun this installer."
        }
        Write-Host "Installing Python 3.12 for this Windows user..." -ForegroundColor Yellow
        & winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "Python installation did not finish. Install Python 3.11+ and rerun this installer." }
        $pythonExe = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
            (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
        ) | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $pythonExe) { throw "Python was installed but is not visible yet. Close this window and rerun INSTALL-JARVIS.ps1." }
    }

    Write-Host "Downloading current JARVIS branch..."
    $zipPath = Join-Path $tempRoot "jarvis.zip"
    Invoke-WebRequest -Uri "https://codeload.github.com/Ashokkunchala/Jarvis-Personal-AI/zip/refs/heads/improve/security-quality-gates" -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $tempRoot -Force
    $sourceRoot = Get-ChildItem $tempRoot -Directory | Where-Object { Test-Path (Join-Path $_.FullName "requirements-dev.txt") } | Select-Object -First 1 -ExpandProperty FullName
    if (-not $sourceRoot) { throw "Could not find the downloaded JARVIS source tree." }

    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    Get-ChildItem $sourceRoot -Force | Where-Object { $_.Name -notin @(".env", ".venv", "data", "logs") } | ForEach-Object {
        Copy-Item $_.FullName -Destination $installRoot -Recurse -Force
    }
    foreach ($folder in @("data", "logs")) { New-Item -ItemType Directory -Force -Path (Join-Path $installRoot $folder) | Out-Null }

    $venvPython = Join-Path $installRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "Creating Python environment..."
        & $pythonExe -m venv (Join-Path $installRoot ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Could not create Python environment." }
    }
    Write-Host "Installing dependencies; this may take a few minutes..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $venvPython -m pip install -r (Join-Path $installRoot "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

    $envPath = Join-Path $installRoot ".env"
    if (-not (Test-Path $envPath)) {
        $token = & $venvPython -c "import secrets; print(secrets.token_urlsafe(48))"
        $secret = & $venvPython -c "import secrets; print(secrets.token_urlsafe(48))"
        $template = Get-Content (Join-Path $installRoot ".env.example") -Raw
        $template = $template -replace '(?m)^JARVIS_API_TOKEN=.*$', "JARVIS_API_TOKEN=$token"
        $template = $template -replace '(?m)^SECRET_KEY=.*$', "SECRET_KEY=$secret"
        $template = $template -replace '(?m)^HOST=.*$', "HOST=127.0.0.1"
        $template = $template -replace '(?m)^PORT=.*$', "PORT=8000"
        Write-Host ""
        Write-Host "Enter keys. They are saved only to your local .env file." -ForegroundColor Yellow
        Write-Host "Gemini is required for current live voice and terminal features." -ForegroundColor Yellow
        $gemini = Read-Host "Gemini API key (required)"
        if ([string]::IsNullOrWhiteSpace($gemini)) { throw "Gemini API key is required for voice. Rerun after obtaining one." }
        $openrouter = Read-Host "OpenRouter API key (optional, Enter to skip)"
        $groq = Read-Host "Groq API key (optional, Enter to skip)"
        $template = $template -replace '(?m)^GEMINI_API_KEY=.*
    } else {
        Write-Host "Keeping existing .env credentials and settings." -ForegroundColor Green
    }

    $sessionScript = Join-Path $installRoot "scripts\start-jarvis-session.ps1"
    if (-not (Test-Path $sessionScript)) { throw "Startup script is missing from installed package." }
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
    Write-Host "Disable auto-start in Task Scheduler by disabling the JARVIS Personal AI task."
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
, "GEMINI_API_KEY=$gemini"
        $template = $template -replace '(?m)^OPENROUTER_API_KEY=.*
    } else {
        Write-Host "Keeping existing .env credentials and settings." -ForegroundColor Green
    }

    $sessionScript = Join-Path $installRoot "scripts\start-jarvis-session.ps1"
    if (-not (Test-Path $sessionScript)) { throw "Startup script is missing from installed package." }
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
    Write-Host "Disable auto-start in Task Scheduler by disabling the JARVIS Personal AI task."
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
, "OPENROUTER_API_KEY=$openrouter"
        $template = $template -replace '(?m)^GROQ_API_KEY=.*
    } else {
        Write-Host "Keeping existing .env credentials and settings." -ForegroundColor Green
    }

    $sessionScript = Join-Path $installRoot "scripts\start-jarvis-session.ps1"
    if (-not (Test-Path $sessionScript)) { throw "Startup script is missing from installed package." }
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
    Write-Host "Disable auto-start in Task Scheduler by disabling the JARVIS Personal AI task."
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
, "GROQ_API_KEY=$groq"
        $template = $template -replace '(?m)^JARVIS_AI_PROVIDER=.*
    } else {
        Write-Host "Keeping existing .env credentials and settings." -ForegroundColor Green
    }

    $sessionScript = Join-Path $installRoot "scripts\start-jarvis-session.ps1"
    if (-not (Test-Path $sessionScript)) { throw "Startup script is missing from installed package." }
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
    Write-Host "Disable auto-start in Task Scheduler by disabling the JARVIS Personal AI task."
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
, "JARVIS_AI_PROVIDER=auto"
        Set-Content -Path $envPath -Value $template -Encoding utf8
    } else {
        Write-Host "Keeping existing .env credentials and settings." -ForegroundColor Green
    }

    $sessionScript = Join-Path $installRoot "scripts\start-jarvis-session.ps1"
    if (-not (Test-Path $sessionScript)) { throw "Startup script is missing from installed package." }
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
    Write-Host "Disable auto-start in Task Scheduler by disabling the JARVIS Personal AI task."
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
