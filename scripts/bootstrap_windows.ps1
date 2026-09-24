param(
    [switch]$SetupOnly
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$Python = Join-Path $Venv 'Scripts\python.exe'
$FpDir = Join-Path $Root 'tools\chromaprint'
$FpExe = Join-Path $FpDir 'fpcalc.exe'
$FpUrl = 'https://github.com/acoustid/chromaprint/releases/download/v1.6.1/chromaprint-fpcalc-1.6.1-windows-x86_64.zip'
$FpSha256 = '735d6182b38e9f364b84ce6f4ccd682c75e2851de89735711d6b762d12b92a4e'

function Find-SystemPython {
    $launchers = @(
        @{ Exe = 'py'; Args = @('-3.13') },
        @{ Exe = 'py'; Args = @('-3.12') },
        @{ Exe = 'py'; Args = @('-3.11') },
        @{ Exe = 'python'; Args = @() }
    )
    foreach ($candidate in $launchers) {
        try {
            $cmd = Get-Command $candidate.Exe -ErrorAction Stop
            & $cmd.Source @($candidate.Args) -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { }
    }
    throw 'Nie znaleziono Python 3.11 lub nowszego. Zainstaluj Python 3.11+ z python.org i zaznacz Add Python to PATH.'
}

function Ensure-Venv {
    if (-not (Test-Path $Python)) {
        Write-Host 'Tworzenie lokalnego srodowiska Python...' -ForegroundColor Cyan
        $sys = Find-SystemPython
        & $sys.Exe @($sys.Args) -m venv $Venv
    }
    & $Python -c "import sys; print('Python', sys.version.split()[0])"
}

function Ensure-PythonDependencies {
    $probe = @'
import importlib.util
mods = ['PySide6','mutagen','requests','librosa','soundfile','numpy','PIL']
raise SystemExit(0 if all(importlib.util.find_spec(m) for m in mods) else 1)
'@
    & $Python -c $probe 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Instalowanie bibliotek aplikacji (pierwsze uruchomienie)...' -ForegroundColor Cyan
        & $Python -m pip install --upgrade pip
        & $Python -m pip install -e ".[gui,analysis]"
    }
}

function Ensure-Fpcalc {
    if (Test-Path $FpExe) { return }
    New-Item -ItemType Directory -Force -Path $FpDir | Out-Null
    $TempZip = Join-Path $env:TEMP 'alo-chromaprint-1.6.1.zip'
    $TempExtract = Join-Path $env:TEMP 'alo-chromaprint-1.6.1'
    Write-Host 'Pobieranie Chromaprint fpcalc 1.6.1...' -ForegroundColor Cyan
    Invoke-WebRequest -Uri $FpUrl -OutFile $TempZip -UseBasicParsing
    $Actual = (Get-FileHash -Algorithm SHA256 $TempZip).Hash.ToLowerInvariant()
    if ($Actual -ne $FpSha256) {
        Remove-Item $TempZip -Force -ErrorAction SilentlyContinue
        throw "Suma SHA-256 Chromaprint nie zgadza sie. Oczekiwano $FpSha256, otrzymano $Actual."
    }
    Remove-Item $TempExtract -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $TempZip -DestinationPath $TempExtract -Force
    $Found = Get-ChildItem -Path $TempExtract -Filter 'fpcalc.exe' -File -Recurse | Select-Object -First 1
    if (-not $Found) { throw 'Archiwum Chromaprint nie zawiera fpcalc.exe.' }
    Copy-Item -Path (Join-Path $Found.Directory.FullName '*') -Destination $FpDir -Recurse -Force
    Remove-Item $TempZip -Force -ErrorAction SilentlyContinue
    Remove-Item $TempExtract -Recurse -Force -ErrorAction SilentlyContinue
}

try {
    Set-Location $Root
    Ensure-Venv
    Ensure-PythonDependencies
    Ensure-Fpcalc
    if (-not $SetupOnly) {
        Write-Host 'Uruchamianie Audio Library Organizer...' -ForegroundColor Green
        & $Python -m audio_library_organizer
        exit $LASTEXITCODE
    }
} catch {
    Write-Host ''
    Write-Host ('BLAD: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
