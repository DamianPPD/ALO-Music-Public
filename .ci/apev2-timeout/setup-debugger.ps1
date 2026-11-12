$ErrorActionPreference = 'Stop'
$evidence = Join-Path $env:RUNNER_TEMP 'alo-apev2-timeout'
$dest = Join-Path $env:RUNNER_TEMP 'alo-native-debugger'
New-Item -ItemType Directory -Path $dest -Force | Out-Null
$report = [ordered]@{}
try {
  $archive = Join-Path $dest 'Procdump.zip'
  Invoke-WebRequest 'https://download.sysinternals.com/files/Procdump.zip' -OutFile $archive
  $report.procdump_archive_sha256 = (Get-FileHash $archive -Algorithm SHA256).Hash
  Expand-Archive $archive -DestinationPath (Join-Path $dest 'procdump')
  $exe = Join-Path $dest 'procdump/procdump64.exe'
  $sig = Get-AuthenticodeSignature $exe
  if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Microsoft') { throw 'Untrusted ProcDump' }
  $report.procdump_signature = $sig.SignerCertificate.Subject
  "ALO_PROCDUMP_EXE=$exe" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
} catch { $report.procdump_error = $_.ToString() }
try {
  $cdb = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/Debuggers/x64/cdb.exe'
  if (-not (Test-Path $cdb)) {
    $installer = Join-Path $dest 'winsdksetup.exe'
    Invoke-WebRequest 'https://download.microsoft.com/download/cb9de490-6e67-4ac6-8c2c-6dfabb824e8a/windowssdk/winsdksetup.exe' -OutFile $installer
    $sig = Get-AuthenticodeSignature $installer
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Microsoft') { throw 'Untrusted Windows SDK installer' }
    $report.sdk_installer_sha256 = (Get-FileHash $installer -Algorithm SHA256).Hash
    $report.sdk_signature = $sig.SignerCertificate.Subject
    $process = Start-Process $installer -ArgumentList @('/features','OptionId.WindowsDesktopDebuggers','/quiet','/norestart','/log', (Join-Path $dest 'sdk.log')) -PassThru
    if (-not $process.WaitForExit(240000)) { $process.Kill(); throw 'SDK setup timed out after240s' }
    $report.sdk_exit = $process.ExitCode
  }
  if (-not (Test-Path $cdb)) { throw 'CDB not installed' }
  $sig = Get-AuthenticodeSignature $cdb
  if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Microsoft') { throw 'Untrusted CDB' }
  $report.cdb = $cdb
  $report.cdb_signature = $sig.SignerCertificate.Subject
  "ALO_CDB_EXE=$cdb" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
} catch { $report.cdb_error = $_.ToString() }
try {
  $pdb = Join-Path $dest 'python-pdb.zip'
  Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64-pdb.zip' -OutFile $pdb
  Expand-Archive $pdb -DestinationPath (Join-Path $dest 'python-pdb')
  $report.python_pdb_sha256 = (Get-FileHash $pdb -Algorithm SHA256).Hash
  "ALO_PYTHON_PDB_DIR=$(Join-Path $dest 'python-pdb')" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
} catch { $report.python_pdb_error = $_.ToString() }
$report | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $evidence 'native-tools.json') -Encoding utf8
$report | ConvertTo-Json -Depth 5
