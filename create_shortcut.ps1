$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$shortcutPath = Join-Path $desktopPath "MediaFlow.lnk"
$targetPath = Join-Path $scriptDir "start.bat"

Write-Host "Creating desktop shortcut for MediaFlow..." -ForegroundColor Cyan

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description = "MediaFlow - Local Media Downloader & Audio Converter"

# Use shell32.dll audio icon
$iconPath = Join-Path $env:SystemRoot "System32\shell32.dll"
if (Test-Path $iconPath) {
    # 168 is the audio note/speaker icon
    $shortcut.IconLocation = "$iconPath, 168"
}

$shortcut.Save()

Write-Host "[OK] Shortcut successfully created on Desktop: $shortcutPath" -ForegroundColor Green
