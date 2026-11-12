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
echo   1. Floating robot (default): .\.venv\Scripts\python.exe jarvis_cli.py
echo   2. Live voice call: .\.venv\Scripts\python.exe jarvis_cli.py call
echo   3. Local backend: .\.venv\Scripts\python.exe jarvis_cli.py serve
echo   4. Wake-word voice mode: .\.venv\Scripts\python.exe jarvis_cli.py start
echo   5. Quick CLI: .\.venv\Scripts\python.exe jarvis_cli.py --help
echo.
pause
exit /b 0

:error
echo.
echo Installation failed. Review the error above and retry.
pause
exit /b 1
