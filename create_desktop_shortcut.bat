@echo off
title MediaFlow - Create Desktop Shortcut
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ===================================================
echo       MediaFlow - Creating Desktop Shortcut
echo ===================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [NOTICE] PowerShell shortcut creation had an issue. Trying fallback method...
    
    :: VBScript fallback
    set "VBS_SCRIPT=%TEMP%\make_mediaflow_shortcut.vbs"
    (
        echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
        echo sDesktop = oWS.SpecialFolders^("Desktop"^)
        echo Set oLink = oWS.CreateShortcut^(sDesktop ^& "\MediaFlow.lnk"^)
        echo oLink.TargetPath = "%~dp0start.bat"
        echo oLink.WorkingDirectory = "%~dp0"
        echo oLink.Description = "MediaFlow - Local Media Downloader & Audio Converter"
        echo oLink.IconLocation = "%SystemRoot%\System32\shell32.dll, 168"
        echo oLink.Save
    ) > "!VBS_SCRIPT!"
    cscript //nologo "!VBS_SCRIPT!"
    del "!VBS_SCRIPT!" >nul 2>&1
    echo [OK] Shortcut created via fallback method.
)

echo.
echo [INFO] Shortcut setup complete.
echo.
pause