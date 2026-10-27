@echo off
setlocal
cd /d "%~dp0.."
echo Testy 6.2D: wymagany istniejacy CPython 3.11.9 x64, Qt 6.10.3 i FFmpeg.
echo Pakiet nie instaluje ani nie zmienia systemowego Pythona.
py -3.11 -B windows\run_windows.py
set "ALO_TEST_EXIT=%ERRORLEVEL%"
echo Kod zakonczenia: %ALO_TEST_EXIT%
pause
exit /b %ALO_TEST_EXIT%
