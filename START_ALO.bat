@echo off
setlocal
cd /d "%~dp0"

title ALO Music v0.4.23 - uruchamianie z repozytorium

echo.
echo ============================================================
echo   ALO Music v0.4.23 - tryb developerski / GitHub Desktop
echo ============================================================
echo.
echo Pierwsze uruchomienie moze potrwac kilka minut.
echo Program przygotuje lokalne srodowisko .venv i wymagane biblioteki.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1"
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ============================================================
    echo   ALO Music nie zostal uruchomiony. Kod bledu: %EXIT_CODE%
    echo ============================================================
    echo.
    pause
    exit /b %EXIT_CODE%
)

endlocal
