@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0scripts\start_desktop.ps1"
if errorlevel 1 (
    echo.
    echo QPG could not start. Check the message above and README.md.
    pause
    exit /b 1
)
