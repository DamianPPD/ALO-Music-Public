# Windows PowerShell 5.1. Application-private bootstrap; no Python installation.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$Package = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$Runner = Join-Path $PSScriptRoot 'run_standalone.py'
$ProbeFile = Join-Path $PSScriptRoot 'probe_runtime.py'
$PipVendor = Join-Path $PSScriptRoot 'vendor_pip.py'
$Results = Join-Path $Package 'results'
$Work = Join-Path $Package 'work'
$Token = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$RunId = 'bootstrap-' + $Token
$Bootstrap = Join-Path $Results $RunId
$Runtime = Join-Path $Work ('runtime-' + $Token)
$PythonRoot = Join-Path $Runtime 'python'
$RunnerStarted = $false
$BootstrapReady = $false
$Utf8 = [Text.UTF8Encoding]::new($false)

function Save-Json([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 15), $Utf8)
}
function Assert-PlainPath([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $Item = Get-Item -LiteralPath $Path -Force
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw ('Reparse point is not allowed: ' + $Path)
        }
    }
}
function Assert-Child([string]$Child, [string]$Parent) {
    $Full = [IO.Path]::GetFullPath($Child)
    $Prefix = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $Full.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw ('Path escaped expected parent: ' + $Child)
    }
}
function Assert-Relative([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name) -or $Name.StartsWith('/') -or
        $Name.Contains('\') -or $Name.Contains(':') -or $Name -match '[\x00-\x1f]' -or
        @($Name.Split('/') | Where-Object { $_ -eq '' -or $_ -eq '.' -or $_ -eq '..' }).Count -gt 0) {
        throw ('Unsafe relative path: ' + $Name)
    }
}
function Log([string]$Message) {
    Write-Host $Message
    if ($BootstrapReady) {
        ($Message) | Add-Content -LiteralPath (Join-Path $Bootstrap 'bootstrap.log') -Encoding UTF8
        ($Message) | Add-Content -LiteralPath (Join-Path $Bootstrap 'bootstrap.stdout.log') -Encoding UTF8
    }
}
function Assert-File([string]$Path, $Row) {
    Assert-PlainPath $Path
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw ('Missing file: ' + $Path) }
    if ([string]$Row.sha256 -notmatch '^[0-9a-f]{64}$' -or [long]$Row.size_bytes -lt 0) {
        throw ('Invalid catalog file row: ' + $Path)
    }
    $Item = Get-Item -LiteralPath $Path -Force
    if ($Item.Length -ne [long]$Row.size_bytes -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$Row.sha256) {
        throw ('SHA-256/size mismatch: ' + $Path)
    }
}
function Get-KitFiles {
    $Queue = [Collections.Generic.Stack[string]]::new()
    $Queue.Push($Package)
    while ($Queue.Count -gt 0) {
        $Folder = $Queue.Pop()
        foreach ($Item in @(Get-ChildItem -LiteralPath $Folder -Force)) {
            $Relative = $Item.FullName.Substring($Package.Length + 1).Replace('\','/')
            if ($Folder -eq $Package -and $Item.Name -in @('work','results')) { continue }
            Assert-PlainPath $Item.FullName
            if ($Item.PSIsContainer) { $Queue.Push($Item.FullName) }
            else { $Relative }
        }
    }
}
function Assert-Kit {
    Assert-PlainPath $Package
    $ManifestFile = Join-Path $Package 'manifest-SHA256.json'
    Assert-PlainPath $ManifestFile
    $Manifest = Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $Expected = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($Property in @($Manifest.files.PSObject.Properties)) {
        $Name = [string]$Property.Name
        Assert-Relative $Name
        if ($Name.Split('/')[0] -in @('work','results') -or $Name -eq 'manifest-SHA256.json' -or
            -not $Expected.Add($Name)) { throw ('Invalid package inventory: ' + $Name) }
        $Path = Join-Path $Package $Name.Replace('/', '\')
        Assert-Child $Path $Package
        Assert-File $Path $Property.Value
    }
    $Actual = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($Name in @(Get-KitFiles)) {
        if ($Name -ne 'manifest-SHA256.json' -and -not $Actual.Add($Name)) {
            throw ('Duplicate package file: ' + $Name)
        }
    }
    if (-not $Expected.SetEquals($Actual)) { throw 'Package inventory mismatch (missing or extra file).' }
    Log ('Outer package manifest verified: ' + $Actual.Count + ' files; no runtime executed.')
}
function Assert-PeAmd64([string]$Path) {
    $Stream = [IO.File]::OpenRead($Path)
    $Reader = [IO.BinaryReader]::new($Stream)
    try {
        if ($Stream.Length -lt 64 -or $Reader.ReadUInt16() -ne 0x5a4d) { throw ('Not PE: ' + $Path) }
        $Stream.Position = 0x3c
        $Offset = $Reader.ReadUInt32()
        if ($Offset -gt ($Stream.Length - 26)) { throw ('Invalid PE offset: ' + $Path) }
        $Stream.Position = $Offset
        if ($Reader.ReadUInt32() -ne 0x00004550 -or $Reader.ReadUInt16() -ne 0x8664) {
            throw ('PE must be AMD64: ' + $Path)
        }
        $Stream.Position = $Offset + 24
        if ($Reader.ReadUInt16() -ne 0x020b) { throw ('PE must be PE32+: ' + $Path) }
    } finally { $Reader.Dispose(); $Stream.Dispose() }
}
function Extract-PinnedZip([string]$Archive, [string]$Destination, $Files) {
    if (Test-Path -LiteralPath $Destination) { throw ('Extraction target already exists: ' + $Destination) }
    $Expected = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($Property in @($Files.PSObject.Properties)) {
        Assert-Relative ([string]$Property.Name)
        if (-not $Expected.Add([string]$Property.Name)) { throw 'Duplicate catalog ZIP member.' }
    }
    $Zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $Actual = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($Entry in $Zip.Entries) {
            $Name = [string]$Entry.FullName
            Assert-Relative $Name
            if (-not $Actual.Add($Name) -or -not $Expected.Contains($Name) -or
                (($Entry.ExternalAttributes -shr 16) -band 0xf000) -eq 0xa000) {
                throw ('Unsafe or unexpected ZIP member: ' + $Name)
            }
            if ($Entry.Length -ne [long]$Files.PSObject.Properties[$Name].Value.size_bytes) {
                throw ('ZIP size mismatch: ' + $Name)
            }
        }
        if (-not $Expected.SetEquals($Actual)) { throw 'ZIP inventory mismatch.' }
        New-Item -ItemType Directory -Path $Destination | Out-Null
        foreach ($Entry in $Zip.Entries) {
            $Target = Join-Path $Destination $Entry.FullName.Replace('/', '\')
            Assert-Child $Target $Destination
            $Parent = Split-Path -Parent $Target
            if (-not (Test-Path -LiteralPath $Parent)) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
            $InputStream = $Entry.Open()
            $OutputStream = [IO.File]::Open($Target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try { $InputStream.CopyTo($OutputStream) } finally { $OutputStream.Dispose(); $InputStream.Dispose() }
            Assert-File $Target $Files.PSObject.Properties[$Entry.FullName].Value
        }
    } finally { $Zip.Dispose() }
}
function Assert-PythonSignature([string]$Path, $Policy) {
    $Signature = Get-AuthenticodeSignature -LiteralPath $Path
    $Certificate = $Signature.SignerCertificate
    $Timestamp = $Signature.TimeStamperCertificate
    $Record = [ordered]@{ file=[IO.Path]::GetFileName($Path); status=[string]$Signature.Status;
        status_message=[string]$Signature.StatusMessage; subject=$null; thumbprint=$null;
        timestamp_subject=$null; verified_before_execution=$false }
    if ($null -ne $Certificate) { $Record.subject=$Certificate.Subject; $Record.thumbprint=$Certificate.Thumbprint.ToLowerInvariant() }
    if ($null -ne $Timestamp) { $Record.timestamp_subject=$Timestamp.Subject }
    $Good = ($Signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid -and
        $null -ne $Certificate -and $null -ne $Timestamp -and
        $Certificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false) -eq [string]$Policy.signer_common_name -and
        $Certificate.Thumbprint.ToLowerInvariant() -eq [string]$Policy.signer_thumbprint)
    $Record.verified_before_execution = $Good
    Save-Json (Join-Path $Bootstrap ([IO.Path]::GetFileName($Path) + '.authenticode.json')) $Record
    if (-not $Good) { throw ('Authenticode PSF validation failed: ' + $Path + ' (' + $Signature.Status + ')') }
}
function Assert-CrtSignature([string]$Path, $Policy) {
    $Signature = Get-AuthenticodeSignature -LiteralPath $Path
    $Certificate = $Signature.SignerCertificate
    $Timestamp = $Signature.TimeStamperCertificate
    $VersionInfo = (Get-Item -LiteralPath $Path).VersionInfo
    $Record = [ordered]@{ file=[IO.Path]::GetFileName($Path); status=[string]$Signature.Status;
        status_message=[string]$Signature.StatusMessage; subject=$null; thumbprint=$null;
        file_version=$VersionInfo.FileVersion; original_filename=$VersionInfo.OriginalFilename;
        timestamp_subject=$null; verified_before_execution=$false; exact_pinned_cpython_crt=$true }
    if ($null -ne $Certificate) { $Record.subject=$Certificate.Subject; $Record.thumbprint=$Certificate.Thumbprint.ToLowerInvariant() }
    if ($null -ne $Timestamp) { $Record.timestamp_subject=$Timestamp.Subject }
    $Good = ($Signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid -and
        $null -ne $Certificate -and $null -ne $Timestamp -and
        $Certificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false) -eq [string]$Policy.publisher_common_name -and
        $Certificate.Thumbprint.ToLowerInvariant() -eq [string]$Policy.signer_thumbprint -and
        $VersionInfo.FileVersion -eq [string]$Policy.file_version -and
        $VersionInfo.OriginalFilename -eq [string]$Policy.original_filename)
    $Record.verified_before_execution = $Good
    Save-Json (Join-Path $Bootstrap ([IO.Path]::GetFileName($Path) + '.authenticode.json')) $Record
    if (-not $Good) { throw ('Exact bundled CPython CRT validation failed: ' + $Path + ' (' + $Signature.Status + ')') }
}
function Invoke-PrivatePython([string]$Stage, [string[]]$Arguments) {
    $Stdout = Join-Path $Bootstrap ($Stage + '.stdout.log')
    $Stderr = Join-Path $Bootstrap ($Stage + '.stderr.log')
    $Started = [DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText($Stdout, '', $Utf8)
    [IO.File]::WriteAllText($Stderr, '', $Utf8)
    $Code = $null
    $global:LASTEXITCODE = $null
    Log ('Python stage: ' + $Stage)
    $Previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $PythonExe @Arguments 1> $Stdout 2> $Stderr
        $Code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $Previous }
    Save-Json (Join-Path $Bootstrap ($Stage + '.process.json')) ([ordered]@{
        executable=$PythonExe; arguments=$Arguments; started_utc=$Started; ended_utc=[DateTime]::UtcNow.ToString('o');
        exit_code=$Code; stdout=[IO.Path]::GetFileName($Stdout); stderr=[IO.Path]::GetFileName($Stderr) })
    foreach ($Line in @(Get-Content -LiteralPath $Stdout -ErrorAction SilentlyContinue)) { Write-Host $Line }
    if ($null -eq $Code -or $Code -ne 0) { throw ('Private Python stage failed: ' + $Stage + '; exit ' + $Code + '; see stdout/stderr logs.') }
}

try {
    Assert-PlainPath $Package
    Assert-PlainPath $Results
    Assert-PlainPath $Work
    if (-not (Test-Path -LiteralPath $Results)) { New-Item -ItemType Directory -Path $Results | Out-Null }
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Bootstrap)) -ne [IO.Path]::GetFullPath($Results) -or
        [IO.Path]::GetFileName($Bootstrap) -notmatch '^bootstrap-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$') {
        throw 'Invalid direct bootstrap results directory.'
    }
    New-Item -ItemType Directory -Path $Bootstrap | Out-Null
    $BootstrapReady = $true
    [IO.File]::WriteAllText((Join-Path $Bootstrap 'bootstrap.stdout.log'), '', $Utf8)
    [IO.File]::WriteAllText((Join-Path $Bootstrap 'bootstrap.stderr.log'), '', $Utf8)
    Log ('Bootstrap UTC: ' + [DateTime]::UtcNow.ToString('o'))
    Log 'Library4.1: private CPython 3.11.9 x64, Qt6.10.3; 6 technical CI SMOKE checks; no product GUI.'
    Assert-Kit
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or
        -not [Environment]::Is64BitOperatingSystem -or [IntPtr]::Size -ne 8) {
        throw 'Windows x64 and 64-bit Windows PowerShell 5.1 are required.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\ucrtbase.dll') -PathType Leaf)) {
        throw 'Required existing Windows UCRT (ucrtbase.dll) is unavailable; no system installation attempted.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $CatalogPath = Join-Path $Package 'metadata\environment-catalog.json'
    $Catalog = Get-Content -LiteralPath $CatalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Catalog.schema_version -ne 1 -or $Catalog.python_version -ne '3.11.9' -or
        $Catalog.platform -ne 'win-amd64' -or $Catalog.pip.version -ne '25.3') { throw 'Unexpected environment catalog.' }
    if (-not (Test-Path -LiteralPath $Work)) { New-Item -ItemType Directory -Path $Work | Out-Null }
    New-Item -ItemType Directory -Path $Runtime | Out-Null
    $Archive = Join-Path $Package ('runtime-source\' + $Catalog.python_embed.filename)
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        if ($Catalog.python_embed.source_url -ne 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip') {
            throw 'Only the exact official CPython 3.11.9 x64 ZIP is permitted.'
        }
        $Archive = Join-Path $Runtime $Catalog.python_embed.filename
        Log 'Downloading exact pinned CPython ZIP from official python.org.'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $Catalog.python_embed.source_url -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 120 -OutFile $Archive
    } else { Log 'Using bundled original CPython ZIP; no interpreter download needed.' }
    Assert-File $Archive $Catalog.python_embed
    Save-Json (Join-Path $Bootstrap 'interpreter-source.json') ([ordered]@{
        source_url=$Catalog.python_embed.source_url; used_archive=$Archive; sha256=$Catalog.python_embed.sha256;
        size_bytes=$Catalog.python_embed.size_bytes; version='3.11.9'; platform='win-amd64';
        original_archive_verified=$true; native_windows_execution='NOT_STARTED' })
    Extract-PinnedZip $Archive $PythonRoot $Catalog.python_embed.files
    foreach ($Property in @($Catalog.python_embed.files.PSObject.Properties)) {
        $Path = Join-Path $PythonRoot $Property.Name
        Assert-File $Path $Property.Value
        if ($Property.Name -match '\.(exe|dll|pyd)$') { Assert-PeAmd64 $Path }
    }
    foreach ($Name in $Catalog.authenticode.required_files) { Assert-PythonSignature (Join-Path $PythonRoot $Name) $Catalog.authenticode }
    foreach ($Crt in $Catalog.bundled_crt) { Assert-CrtSignature (Join-Path $PythonRoot $Crt.filename) $Crt }
    Log 'Original CPython per-file hashes, all PE AMD64 headers, PSF signatures and exact bundled CRT signatures verified before execution.'
    $SitePackages = Join-Path $PythonRoot 'Lib\site-packages'
    New-Item -ItemType Directory -Path $SitePackages -Force | Out-Null
    $Pth = Join-Path $PythonRoot 'python311._pth'
    [IO.File]::WriteAllText($Pth, [string]$Catalog.controlled_pth.content, $Utf8)
    if ((Get-FileHash -LiteralPath $Pth -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Catalog.controlled_pth.sha256) {
        throw 'Controlled _pth SHA mismatch.'
    }
    $PythonExe = Join-Path $PythonRoot 'python.exe'
    $BaseProbe = Join-Path $Bootstrap 'runtime-base.json'
    Invoke-PrivatePython -Stage 'probe-base' -Arguments @('-I','-B','-X','utf8',$ProbeFile,'--expected-root',$PythonRoot,'--output',$BaseProbe,'--phase','base')
    $Wheel = Join-Path $Package ('runtime-source\' + $Catalog.pip.filename)
    Assert-File $Wheel $Catalog.pip
    $env:PIP_CONFIG_FILE = 'NUL'
    Invoke-PrivatePython -Stage 'vendor-pip' -Arguments @('-I','-B','-X','utf8',$PipVendor,'--wheel',$Wheel,'--target',$SitePackages)
    foreach ($Property in @($Catalog.pip.files.PSObject.Properties)) {
        # pip recreates RECORD and adds its installation metadata. Package code and immutable metadata remain exact.
        if ($Property.Name -notmatch '(^|/)RECORD$') {
            Assert-File (Join-Path $SitePackages $Property.Name.Replace('/', '\')) $Property.Value
        }
    }
    foreach ($Property in @($Catalog.python_embed.files.PSObject.Properties)) {
        if ($Property.Name -ne 'python311._pth') { Assert-File (Join-Path $PythonRoot $Property.Name) $Property.Value }
    }
    $PipProbe = Join-Path $Bootstrap 'runtime-pip.json'
    Invoke-PrivatePython -Stage 'probe-pip' -Arguments @('-I','-B','-X','utf8',$ProbeFile,'--expected-root',$PythonRoot,'--output',$PipProbe,'--phase','pip')
    $env:I7_311_BOOTSTRAP_DIR = $Bootstrap
    $env:I7_311_RUNTIME_DIR = $Runtime
    $env:I7_311_PYTHON_SOURCE = $Archive
    $env:I7_311_ENVIRONMENT_CATALOG = $CatalogPath
    $env:I7_311_RUN_TOKEN = $Token
    Save-Json (Join-Path $Bootstrap 'bootstrap-ready.json') ([ordered]@{
        status='READY_FOR_RUNNER'; python=$PythonExe; runtime=$Runtime; private_site_packages=$SitePackages;
        interpreter_source=$Archive; python_version='3.11.9'; pip_version='25.3'; bootstrap=$Bootstrap;
        system_python_modified=$false; venv=$false; SMOKE_tests_started=$false; requested_SMOKE=6 })
    # Recheck immutable kit immediately before handing control to its runner.
    Assert-Kit
    $RunnerStarted = $true
    $Previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $PythonExe -I -B -X utf8 $Runner 1> (Join-Path $Bootstrap 'runner.stdout.log') 2> (Join-Path $Bootstrap 'runner.stderr.log')
        $RunExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $Previous }
    foreach ($Line in @(Get-Content -LiteralPath (Join-Path $Bootstrap 'runner.stdout.log') -ErrorAction SilentlyContinue)) { Write-Host $Line }
    $ReceiptFile = Join-Path $Bootstrap 'runner-receipt.json'
    Assert-PlainPath $ReceiptFile
    if (-not (Test-Path -LiteralPath $ReceiptFile -PathType Leaf)) { throw ('Runner did not save a results receipt; exit ' + $RunExit) }
    $Receipt = Get-Content -LiteralPath $ReceiptFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $ResultArchive = [IO.Path]::GetFullPath([string]$Receipt.archive)
    if ([IO.Path]::GetDirectoryName($ResultArchive) -ne [IO.Path]::GetFullPath($Results) -or
        [IO.Path]::GetExtension($ResultArchive) -ne '.zip') { throw 'Invalid results ZIP location.' }
    Assert-PlainPath $ResultArchive
    if (-not (Test-Path -LiteralPath $ResultArchive -PathType Leaf) -or
        [string]$Receipt.sha256 -notmatch '^[0-9a-f]{64}$' -or
        (Get-FileHash -LiteralPath $ResultArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$Receipt.sha256) {
        throw 'Invalid results ZIP SHA-256.'
    }
    if ([int]$Receipt.exit_code -ne $RunExit -or $RunExit -notin @(0,2)) { throw 'Runner exit code disagrees with results receipt.' }
    $ShaFile = [IO.Path]::ChangeExtension($ResultArchive, '.sha256.txt')
    Assert-PlainPath $ShaFile
    if (-not (Test-Path -LiteralPath $ShaFile -PathType Leaf) -or
        (Get-Content -LiteralPath $ShaFile -Raw -Encoding UTF8).Trim() -ne ([string]$Receipt.sha256 + '  ' + [IO.Path]::GetFileName($ResultArchive))) {
        throw 'Missing or inconsistent ZIP SHA-256 sidecar.'
    }
    Write-Host ('ZIP: ' + $ResultArchive)
    Write-Host ('SHA: ' + $ShaFile)
    exit $RunExit
} catch {
    $Failure = $_
    $ErrorActionPreference = 'Stop'
    Write-Host ('STOP: ' + $Failure.Exception.Message)
    try {
        Assert-PlainPath $Results
        Assert-PlainPath $Bootstrap
        if (-not $BootstrapReady) {
            if (-not (Test-Path -LiteralPath $Results)) { New-Item -ItemType Directory -Path $Results | Out-Null }
            New-Item -ItemType Directory -Path $Bootstrap | Out-Null
            $BootstrapReady = $true
        }
        ($Failure | Out-String) | Set-Content -LiteralPath (Join-Path $Bootstrap 'bootstrap-error.log') -Encoding UTF8
        ($Failure | Out-String) | Add-Content -LiteralPath (Join-Path $Bootstrap 'bootstrap.stderr.log') -Encoding UTF8
        if (-not (Test-Path -LiteralPath (Join-Path $Bootstrap 'bootstrap.stdout.log'))) {
            [IO.File]::WriteAllText((Join-Path $Bootstrap 'bootstrap.stdout.log'), '', $Utf8)
        }
        $Execution = $(if ($RunnerStarted) { 'UNKNOWN_AFTER_RUNNER' } else { 'NOT_STARTED' })
        Save-Json (Join-Path $Bootstrap 'run.json') ([ordered]@{
            status='STOP'; exit_code=2; bootstrap=$Bootstrap; runner_started=$RunnerStarted;
            Library41_execution=$Execution; requested_SMOKE=6;
            GUI16_rerun=$false; F1_F3_rerun=$false; QRunnable19_rerun=$false;
            native_windows_validation='NOT_CONFIRMED'; error=$Failure.Exception.Message })
        $Manifest = @{}
        foreach ($Item in @(Get-ChildItem -LiteralPath $Bootstrap -File -Recurse -Force)) {
            Assert-PlainPath $Item.FullName
            if ($Item.Name -eq 'SHA256.json') { continue }
            $Relative = $Item.FullName.Substring($Bootstrap.Length + 1).Replace('\','/')
            $Manifest[$Relative] = @{ sha256=(Get-FileHash -LiteralPath $Item.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); size_bytes=$Item.Length }
        }
        Save-Json (Join-Path $Bootstrap 'SHA256.json') $Manifest
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $FailureArchive = Join-Path $Results ('ALO-Library41-Windows-wyniki-' + $RunId + '.zip')
        [IO.Compression.ZipFile]::CreateFromDirectory($Bootstrap, $FailureArchive)
        $Digest = (Get-FileHash -LiteralPath $FailureArchive -Algorithm SHA256).Hash.ToLowerInvariant()
        $FailureSha = [IO.Path]::ChangeExtension($FailureArchive, '.sha256.txt')
        [IO.File]::WriteAllText($FailureSha, ($Digest + '  ' + [IO.Path]::GetFileName($FailureArchive) + "`r`n"), [Text.Encoding]::ASCII)
        Write-Host ('ZIP: ' + $FailureArchive)
        Write-Host ('SHA: ' + $FailureSha)
    } catch { Write-Host ('Could not save bootstrap evidence ZIP: ' + $_.Exception.Message) }
    exit 2
}
