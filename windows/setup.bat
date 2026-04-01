@echo off
echo lil agents - Windows setup
echo ==========================
echo.

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Please install Python 3.11+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo All done! To run lil agents:
echo   python lil_agents.py
echo.
echo NOTE: Character animations require the .mov files from the LilAgents/ folder.
echo       ffmpeg must be installed and in PATH for first-run sprite extraction.
echo       Download ffmpeg from https://ffmpeg.org/download.html
echo.
pause
