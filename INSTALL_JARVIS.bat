@echo off
echo ========================================
echo JARVIS Installation - Iron Man Style
echo ========================================
echo.

echo [1/3] Creating virtual environment...
python -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate

echo [2/3] Installing JARVIS and developer dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -e ".[dev]"
if errorlevel 1 goto :error

echo [3/3] Preparing the local configuration...
if not exist .env copy .env.example .env >nul
python -c "from app.core.config import get_settings; get_settings()"
if errorlevel 1 goto :error

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Edit .env and set at least one AI provider key plus a random JARVIS_API_TOKEN.
echo.
echo To start JARVIS:
echo   1. Terminal UI: .\.venv\Scripts\jarvis.exe tui
echo   2. Local backend: .\.venv\Scripts\jarvis.exe serve
echo   3. Full voice mode: .\.venv\Scripts\jarvis.exe start
echo   4. Quick CLI: .\.venv\Scripts\jarvis.exe --help
echo.
pause
exit /b 0

:error
echo.
echo Installation failed. Review the error above and retry.
pause
exit /b 1
