@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo lil agents - Build standalone .exe
echo ====================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause & exit /b 1
)

echo Installing build dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pillow pystray numpy pyinstaller
echo Done.
echo.

REM ── Locate sprite cache ───────────────────────────────────────────────────────
set BRUCE_DIR=
set JAZZ_DIR=

for %%D in ("..\\.cache\\windows-sprites" "..\\.cache\\linux-sprites") do (
    if exist "%%~D\bruce\frame-0001.png" if "!BRUCE_DIR!"=="" set BRUCE_DIR=%%~D\bruce
    if exist "%%~D\jazz\frame-0001.png"  if "!JAZZ_DIR!"==""  set JAZZ_DIR=%%~D\jazz
)

REM ── Extract sprites if needed ─────────────────────────────────────────────────
if "!BRUCE_DIR!"=="" (
    echo Sprites not found. Extracting with ffmpeg...
    where ffmpeg >nul 2>&1
    if errorlevel 1 (
        echo.
        echo ERROR: ffmpeg not found in PATH.
        echo Download from https://ffmpeg.org/download.html and add ffmpeg\bin to PATH.
        pause & exit /b 1
    )
    mkdir "..\\.cache\\windows-sprites\\bruce" 2>nul
    mkdir "..\\.cache\\windows-sprites\\jazz"  2>nul
    ffmpeg -v error -y -i "..\LilAgents\walk-bruce-01.mov" -vf "fps=30,scale=56:98:flags=lanczos" -pix_fmt rgb24 "..\\.cache\\windows-sprites\\bruce\\frame-%%04d.png"
    ffmpeg -v error -y -i "..\LilAgents\walk-jazz-01.mov"  -vf "fps=30,scale=56:98:flags=lanczos" -pix_fmt rgb24 "..\\.cache\\windows-sprites\\jazz\\frame-%%04d.png"
    python -c "import sys; sys.path.insert(0,'.'); from lil_agents_standalone import _remove_black_bg; import os; [_remove_black_bg(os.path.join(r'..\\.cache\\windows-sprites\\bruce',f)) for f in os.listdir(r'..\\.cache\\windows-sprites\\bruce') if f.endswith('.png')]"
    python -c "import sys; sys.path.insert(0,'.'); from lil_agents_standalone import _remove_black_bg; import os; [_remove_black_bg(os.path.join(r'..\\.cache\\windows-sprites\\jazz',f)) for f in os.listdir(r'..\\.cache\\windows-sprites\\jazz') if f.endswith('.png')]"
    set BRUCE_DIR=..\.cache\windows-sprites\bruce
    set JAZZ_DIR=..\.cache\windows-sprites\jazz
)

if not exist "!BRUCE_DIR!\frame-0001.png" (
    echo ERROR: Sprite extraction failed. Check ffmpeg is installed correctly.
    pause & exit /b 1
)

echo Sprites ready.
echo.
echo Building lil-agents.exe...
echo.

pyinstaller --onefile --noconsole --name "lil-agents" ^
    --add-data "!BRUCE_DIR!;sprites\bruce" ^
    --add-data "!JAZZ_DIR!;sprites\jazz" ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageTk ^
    --hidden-import PIL.ImageDraw ^
    --hidden-import pystray ^
    --hidden-import pystray._win32 ^
    --hidden-import numpy ^
    lil_agents_standalone.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed.
    pause & exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo  Your file: dist\lil-agents.exe
echo.
echo  Copy it to any Windows PC and
echo  double-click to run. No setup needed.
echo ============================================
echo.
pause
