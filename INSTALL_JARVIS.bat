@echo off
echo ========================================
echo JARVIS Installation - Iron Man Style
echo ========================================
echo.

echo [1/4] Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate

echo [2/4] Installing core dependencies...
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-jarvis.txt
pip install -r requirements-jarvis-full.txt

echo [3/4] Installing additional packages...
pip install rich textual typer pyqt6 qasync adbutils

echo [4/4] Downloading wake word models...
python -c "import openwakeword; openwakeword.utils.download_models()" 2>nul

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo To start JARVIS:
echo   1. Terminal UI: jarvis tui
echo   2. Voice Mode: jarvis start
echo   3. Quick CLI: jarvis --help
echo.
echo Or run: python jarvis_cli.py start
echo.
pause
