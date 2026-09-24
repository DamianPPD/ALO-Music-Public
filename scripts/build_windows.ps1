$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

& PowerShell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\bootstrap_windows.ps1" -SetupOnly
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Python = Join-Path $Root '.venv\Scripts\python.exe'
$DistDir = Join-Path $Root 'dist\ALO-Music'
$Exe = Join-Path $DistDir 'ALO-Music.exe'

Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue

& $Python -m pip install --upgrade PyInstaller
if ($LASTEXITCODE -ne 0) { throw 'Instalacja/aktualizacja PyInstaller nie powiodla sie.' }

& $Python -m PyInstaller --noconfirm --clean "$Root\audio_library_organizer.spec"
if ($LASTEXITCODE -ne 0) { throw 'Build PyInstaller nie powiodl sie.' }
if (-not (Test-Path $Exe)) { throw "Brak pliku $Exe" }

Write-Host ''
Write-Host 'Gotowe. Program znajduje sie w:' -ForegroundColor Green
Write-Host "  $Exe"
