$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VersionFile = Join-Path $Root 'src\audio_library_organizer\__init__.py'
$VersionText = Get-Content $VersionFile -Raw
$Match = [regex]::Match($VersionText, '__version__\s*=\s*[''"]([^''"]+)[''"]')
if (-not $Match.Success) { throw 'Nie mozna odczytac __version__.' }
$Version = $Match.Groups[1].Value

$ReleaseDir = Join-Path $Root "release\v$Version"
$DistDir = Join-Path $Root 'dist\ALO-Music'
$Exe = Join-Path $DistDir 'ALO-Music.exe'
$Portable = Join-Path $ReleaseDir "ALO-Music-v$Version-Windows-Portable.zip"
$Installer = Join-Path $ReleaseDir "ALO-Music-v$Version-Setup.exe"
$Sums = Join-Path $ReleaseDir 'SHA256SUMS.txt'

Remove-Item $ReleaseDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

& PowerShell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\build_windows.ps1"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build nie powiodl sie.' }
if (-not (Test-Path $Exe)) { throw "Brak pliku $Exe" }

$SmokeProcess = Start-Process -FilePath $Exe -ArgumentList '--smoke-test' -Wait -PassThru
if ($SmokeProcess.ExitCode -ne 0) { throw "Smoke test EXE nie powiodl sie. Kod: $($SmokeProcess.ExitCode)" }

# Antywirus moze przez chwile skanowac swiezo zbudowane biblioteki PyInstallera.
# Poczekaj przed pierwsza proba i ponawiaj pakowanie zamiast przerywac caly release.
Start-Sleep -Seconds 2
$MaxArchiveAttempts = 6
$ArchiveCreated = $false
for ($Attempt = 1; $Attempt -le $MaxArchiveAttempts; $Attempt++) {
    try {
        Remove-Item $Portable -Force -ErrorAction SilentlyContinue
        Compress-Archive -Path $DistDir -DestinationPath $Portable -CompressionLevel Optimal -Force
        if (-not (Test-Path $Portable)) { throw 'Nie utworzono Portable ZIP.' }
        $ArchiveCreated = $true
        break
    }
    catch {
        Remove-Item $Portable -Force -ErrorAction SilentlyContinue
        if ($Attempt -ge $MaxArchiveAttempts) {
            throw "Nie udalo sie utworzyc Portable ZIP po $MaxArchiveAttempts probach. Ostatni blad: $($_.Exception.Message)"
        }
        Write-Warning "Plik buildu jest chwilowo zajety (proba $Attempt/$MaxArchiveAttempts). Ponawiam za 2 s."
        Start-Sleep -Seconds 2
    }
}
if (-not $ArchiveCreated) { throw 'Nie utworzono Portable ZIP.' }

$IsccCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
) | Where-Object { $_ -and (Test-Path $_) }
$Iscc = $IsccCandidates | Select-Object -First 1
if (-not $Iscc) {
    throw 'Nie znaleziono Inno Setup 6 (ISCC.exe). Zainstaluj Inno Setup 6 i uruchom skrypt ponownie.'
}

& $Iscc "/DMyAppVersion=$Version" (Join-Path $Root 'installer\ALO-Music.iss')
if ($LASTEXITCODE -ne 0) { throw 'Kompilacja instalatora Inno Setup nie powiodla sie.' }
if (-not (Test-Path $Installer)) { throw "Brak instalatora $Installer" }

$HashLines = foreach ($File in @($Portable, $Installer)) {
    $Hash = (Get-FileHash -Algorithm SHA256 $File).Hash.ToLowerInvariant()
    "$Hash  $([System.IO.Path]::GetFileName($File))"
}
Set-Content -Path $Sums -Value $HashLines -Encoding ascii

Write-Host ''
Write-Host "Gotowe wydanie ALO Music v${Version}:" -ForegroundColor Green
Write-Host "  $Portable"
Write-Host "  $Installer"
Write-Host "  $Sums"
