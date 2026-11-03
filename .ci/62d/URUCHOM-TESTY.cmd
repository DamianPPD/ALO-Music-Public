@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\chcp.com" 65001 >nul
cd /d "%~dp0"
title ALO MUSIC — KOŃCOWA WALIDACJA WINDOWS 11
echo ALO MUSIC — KOŃCOWA WALIDACJA WINDOWS 11
echo.
set "ALO_PORTABLE_WORK="
set "ALO_PORTABLE_PROFILE="
set "ALO_PORTABLE_CASE="
set "PYTHONHOME="
set "PYTHONPATH="
set "QT_PLUGIN_PATH="
set "QT_QPA_PLATFORM_PLUGIN_PATH="
set "QML_IMPORT_PATH="
set "QML2_IMPORT_PATH="
set "PATH=%~dp0tools;%~dp0runtime;%SystemRoot%\System32;%SystemRoot%"
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUNBUFFERED=1"
if not exist "%~dp0runtime\python.exe" (
 echo STOP: Brak kompletnego prywatnego Pythona. Rozpakuj caly ZIP.
 pause
 exit /b 2
)
"%~dp0runtime\python.exe" -I -X utf8 -B "%~dp0app\.ci\62d\portable_run.py"
set "ALO_TEST_EXIT=%ERRORLEVEL%"
echo.
echo Kod zakonczenia: %ALO_TEST_EXIT%
echo Testy zakończone. Prześlij ZIP z wynikami do ChatGPT.
echo Wyniki: nowy podfolder wyniki obok tego pliku.
echo.
if defined ALO_PACKAGE_CI_SMOKE exit /b %ALO_TEST_EXIT%
pause
exit /b %ALO_TEST_EXIT%
