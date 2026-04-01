@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo lil agents - Build standalone .exe
echo ====================================
echo.

REM ── Check Python ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause & exit /b 1
)

REM ── Install build dependencies ────────────────────────────────────────────────
echo Installing build dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pillow pystray numpy pyinstaller
echo Done.
echo.

REM ── Locate sprite cache ───────────────────────────────────────────────────────
REM Prefer windows-sprites, fall back to linux-sprites (same PNG format).
set BRUCE_DIR=
set JAZZ_DIR=

for %%D in (
    "..\\.cache\\windows-sprites"
    "..\\.cache\\linux-sprites"
) do (
    if exist "%%~D\bruce\frame-0001.png" (
        if "!BRUCE_DIR!"=="" set BRUCE_DIR=%%~D\bruce
    )
    if exist "%%~D\jazz\frame-0001.png" (
        if "!JAZZ_DIR!"=="" set JAZZ_DIR=%%~D\jazz
    )
)

REM ── Extract sprites if not cached ─────────────────────────────────────────────
if "!BRUCE_DIR!"=="" (
    echo Sprites not found — attempting extraction with ffmpeg...
    python -c "import sys; sys.path.insert(0,'.');  from lil_agents_standalone import _remove_black_bg, _SPRITE_FPS, CHAR_WIDTH, CHAR_HEIGHT; import subprocess, shutil, os; ff=shutil.which('ffmpeg') or shutil.which('ffmpeg.exe'); mov=os.path.join('..','LilAgents','walk-bruce-01.mov'); dst=os.path.join('..', '.cache','windows-sprites','bruce'); os.makedirs(dst,exist_ok=True); subprocess.run([ff,'-v','error','-y','-i',mov,'-vf',f'fps={int(_SPRITE_FPS)},scale={CHAR_WIDTH}:{CHAR_HEIGHT}:flags=lanczos','-pix_fmt','rgb24',os.path.join(dst,'frame-%%04d.png')],check=False); [_remove_black_bg(os.path.join(dst,f)) for f in sorted(os.listdir(dst)) if f.endswith('.png')]" 2>nul
    python -c "import sys; sys.path.insert(0,'.');  from lil_agents_standalone import _remove_black_bg, _SPRITE_FPS, CHAR_WIDTH, CHAR_HEIGHT; import subprocess, shutil, os; ff=shutil.which('ffmpeg') or shutil.which('ffmpeg.exe'); mov=os.path.join('..','LilAgents','walk-jazz-01.mov'); dst=os.path.join('..', '.cache','windows-sprites','jazz'); os.makedirs(dst,exist_ok=True); subprocess.run([ff,'-v','error','-y','-i',mov,'-vf',f'fps={int(_SPRITE_FPS)},scale={CHAR_WIDTH}:{CHAR_HEIGHT}:flags=lanczos','-pix_fmt','rgb24',os.path.join(dst,'frame-%%04d.png')],check=False); [_remove_black_bg(os.path.join(dst,f)) for f in sorted(os.listdir(dst)) if f.endswith('.png')]" 2>nul
    set BRUCE_DIR=..\.cache\windows-sprites\bruce
    set JAZZ_DIR=..\.cache\windows-sprites\jazz
)

if not exist "!BRUCE_DIR!\frame-0001.png" (
    echo.
    echo ERROR: Sprite frames not found and could not be extracted.
    echo.
    echo You need ffmpeg in your PATH to build the .exe.
    echo Download from https://ffmpeg.org/download.html
    echo Then add ffmpeg\bin to your PATH and run this script again.
    pause & exit /b 1
)

echo Sprites found: !BRUCE_DIR!
echo Sprites found: !JAZZ_DIR!
echo.

REM ── Run PyInstaller ───────────────────────────────────────────────────────────
echo Building lil-agents.exe...
echo.

pyinstaller ^
    --onefile ^
    --noconsole ^
    --name "lil-agents" ^
    --add-data "!BRUCE_DIR!;sprites\bruce" ^
    --add-data "!JAZZ_DIR!;sprites\jazz" ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageTk ^
    --hidden-import PIL.ImageDraw ^
    --hidden-import pystray ^
    --hidden-import pystray._win32 ^
    lil_agents_standalone.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed. See output above.
    pause & exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo  Your .exe is at:  dist\lil-agents.exe
echo.
echo  Copy dist\lil-agents.exe to any Windows
echo  machine and double-click to run.
echo ============================================
echo.
pause
