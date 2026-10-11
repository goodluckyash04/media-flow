@echo off
title MediaFlow - Setup
setlocal enabledelayedexpansion

echo ===================================================
echo             MediaFlow - Environment Setup
echo ===================================================
echo.

cd /d "%~dp0"

:: 1. Check for Python / UV
where uv >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Found 'uv' package manager.
    set USE_UV=1
) else (
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python 3.12+ was not found in your PATH.
        echo Please install Python from https://www.python.org/ or install 'uv'.
        pause
        exit /b 1
    )
    set USE_UV=0
)

:: 2. Create virtual environment if missing
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment (.venv)...
    if "!USE_UV!"=="1" (
        uv venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: 3. Install dependencies
echo [*] Installing dependencies...
if "!USE_UV!"=="1" (
    uv sync
) else (
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -e .
)

:: 4. Setup .env file
if not exist ".env" (
    if exist ".env.example" (
        echo [*] Creating .env file from template...
        copy ".env.example" ".env" >nul
    )
)

:: 5. Create directories
if not exist "data\downloads" mkdir "data\downloads"
if not exist "data\logs" mkdir "data\logs"

:: 6. Run database migrations
echo [*] Applying database migrations...
".venv\Scripts\python.exe" manage.py migrate

:: 7. Check for FFmpeg
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [NOTICE] FFmpeg is not detected in your system PATH.
    echo Audio conversion and post-processing require FFmpeg.
    echo To install FFmpeg on Windows:
    echo   winget install Gyan.FFmpeg
    echo or download from https://ffmpeg.org/download.html
    echo.
) else (
    echo [*] FFmpeg detected.
)

:: 8. Create desktop shortcut
echo [*] Creating desktop shortcut...
call create_desktop_shortcut.bat

echo.
echo ===================================================
echo           Setup Complete! You can now run:
echo                   start.bat
echo ===================================================
echo.
pause
