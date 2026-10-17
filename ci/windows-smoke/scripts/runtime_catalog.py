"""Attest exact pre-Qt MSVC files once; GUI children only verify identities."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from native_provenance import BASE_RUNTIME_NAMES,RUNTIME_NAMES,runtime_record_valid,runtime_signature_valid
from support import native_identity,write_json

SIGNATURE_PROBE=r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$runtimeFiles = ConvertFrom-Json ([Console]::In.ReadToEnd())
$rows = @(
    foreach ($runtimeFile in $runtimeFiles) {
        $signature = Get-AuthenticodeSignature -LiteralPath $runtimeFile
        $info = [Diagnostics.FileVersionInfo]::GetVersionInfo($runtimeFile)
        $subject = ''
        $thumbprint = ''
        $issuer = ''
        if ($null -ne $signature.SignerCertificate) {
            $subject = $signature.SignerCertificate.Subject
            $thumbprint = $signature.SignerCertificate.Thumbprint
            $issuer = $signature.SignerCertificate.Issuer
        }
        [pscustomobject]@{
            path=$runtimeFile; signature_status=$signature.Status.ToString()
            signer_subject=$subject; signer_thumbprint=$thumbprint
            signer_issuer=$issuer; signature_type=[string]$signature.SignatureType
            company=$info.CompanyName; original_filename=$info.OriginalFilename
            file_version=('{0}.{1}.{2}.{3}' -f $info.FileMajorPart,$info.FileMinorPart,$info.FileBuildPart,$info.FilePrivatePart)
        }
    }
)
ConvertTo-Json -InputObject $rows -Depth 4 -Compress
'''

def candidates(loaded,base_executable,base_prefix):
    executable=Path(base_executable).resolve();base=Path(base_prefix).resolve()
    if executable.name.lower() not in ('python.exe','pythonw.exe') or executable.parent!=base:
        raise ValueError('Unsupported CPython base executable/prefix relationship')
    result={Path(path).resolve():'preloaded-before-Qt' for path in loaded
            if Path(path).name.lower() in RUNTIME_NAMES}
    for name in BASE_RUNTIME_NAMES:
        path=base/name
        if path.is_file():result[path.resolve()]='base-cpython'
    if not (base/'vcruntime140.dll').is_file():
        raise ValueError('Missing known CPython base vcruntime140.dll')
    return result

def make_catalog(loaded,output):
    if sys.platform!='win32':raise ValueError('Runtime attestation is Windows-only')
    base_executable=getattr(sys,'_base_executable',None)
    if not base_executable:raise ValueError('Missing actual CPython base executable')
    found=candidates(loaded,base_executable,sys.base_prefix)
    before={str(path):native_identity(path) for path in found}
    powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    if not powershell.is_file():raise ValueError('Missing built-in Windows PowerShell signature verifier')
    argv=[str(powershell),'-NoLogo','-NoProfile','-NonInteractive','-Command',SIGNATURE_PROBE]
    record=dict(executable=str(powershell),argv=argv,candidate_paths=list(before),timeout_seconds=25,
        operation='Authenticode + file version; read-only exact CRT paths')
    try:
        process=subprocess.run(argv,input=json.dumps(list(before)).encode('utf-8'),capture_output=True,timeout=25)
        (output/'runtime-authentication.stdout.log').write_bytes(process.stdout)
        (output/'runtime-authentication.stderr.log').write_bytes(process.stderr)
        record.update(exit_code=process.returncode,timeout=False)
        if process.returncode!=0 or process.stderr.strip():raise ValueError('Runtime signature probe failed; see authentication logs')
        signatures=json.loads(process.stdout.decode('utf-8-sig'))
    except subprocess.TimeoutExpired as error:
        record.update(exit_code=None,timeout=True)
        (output/'runtime-authentication.stdout.log').write_bytes(error.stdout or b'')
        (output/'runtime-authentication.stderr.log').write_bytes(error.stderr or b'')
        raise ValueError('Runtime signature probe timed out') from error
    finally:
        write_json(output/'runtime-authentication.process.json',record)
    if not isinstance(signatures,list) or len(signatures)!=len(found):raise ValueError('Incomplete runtime signature evidence')
    rows=[];seen=set()
    for signature in signatures:
        path=Path(signature['path']).resolve();key=str(path)
        if key not in before or key in seen:raise ValueError('Unexpected/duplicate attested runtime path')
        seen.add(key);identity=native_identity(path)
        if identity['sha256']!=before[key]['sha256']:raise ValueError('Runtime file changed during attestation')
        row=dict(signature,name=path.name.lower(),sha256=identity['sha256'],size_bytes=identity['size_bytes'],
                 pe_machine=identity.get('pe',{}).get('machine'),origin=found[path])
        rows.append(row)
    catalog=dict(base_executable=str(Path(base_executable).resolve()),base_prefix=str(Path(sys.base_prefix).resolve()),
        candidate_basis='CPython base files + exact CRT modules loaded before Qt import',records=rows)
    target=output/'trusted-runtime-catalog.json';write_json(target,catalog)
    checks=[dict(path=row['path'],signature_identity_valid=runtime_signature_valid(row),
                 runtime_record_valid=runtime_record_valid(row,Path(row['path']))) for row in rows]
    write_json(output/'runtime-identity-checks.json',checks)
    for row,check in zip(rows,checks):
        if not check['runtime_record_valid']:
            raise ValueError('Unverified MSVC runtime; STOP: '+row['path'])
    return {row['path']:row for row in rows}

def read_catalog(path,expected_sha):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha:raise ValueError('Runtime catalog SHA mismatch')
    catalog=json.loads(raw)
    if Path(catalog['base_executable']).resolve()!=Path(getattr(sys,'_base_executable','')).resolve() or \
       Path(catalog['base_prefix']).resolve()!=Path(sys.base_prefix).resolve():
        raise ValueError('Runtime catalog belongs to a different base interpreter')
    rows=catalog['records'];result={}
    for row in rows:
        key=str(Path(row['path']).resolve())
        if key in result or not runtime_record_valid(row,Path(key)):raise ValueError('Invalid or changed runtime catalog identity')
        result[key]=row
    if not result:raise ValueError('Empty runtime identity catalog')
    return result
