@echo off
title MediaFlow - Local Media Downloader
setlocal enabledelayedexpansion

echo ===================================================
echo           MediaFlow - Starting Application
echo ===================================================
echo.

cd /d "%~dp0"

:: Add project-local bin (FFmpeg / FFprobe) to PATH for this session
if exist "%~dp0bin" set "PATH=%~dp0bin;%PATH%"

:: Check virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in .venv.
    echo Running setup first...
    call setup.bat
    if errorlevel 1 (
        echo [ERROR] Setup failed. Please check your Python installation.
        pause
        exit /b 1
    )
)

:: Run database migrations silently
echo [*] Checking database migrations...
".venv\Scripts\python.exe" manage.py migrate --noinput >nul 2>&1

:: Open default browser after a brief delay in the background
echo [*] Launching MediaFlow in your default browser...
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000/"

:: Start Django development server
echo [*] Starting web server on http://127.0.0.1:8000
echo [*] Press Ctrl+C to stop the application.
echo.
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000

pause
