@echo off
setlocal
cd /d "%~dp0"
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1"
if errorlevel 1 (
  echo.
  echo Nie udalo sie uruchomic Audio Library Organizer.
  pause
)
endlocal
