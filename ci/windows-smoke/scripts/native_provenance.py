"""Read-only installed DLL RECORD and loaded Qt path checks; no Qt imports."""
import base64
import hashlib
from importlib import metadata
from pathlib import Path
import sys
import re
import ntpath
from types import MappingProxyType

NAMES=('Pillow','charset-normalizer','PySide6-Essentials','PySide6-Addons','shiboken6','numpy','soundfile','cffi')
BASE_RUNTIME_NAMES=frozenset(('vcruntime140.dll','vcruntime140_1.dll'))
RUNTIME_NAMES=BASE_RUNTIME_NAMES|{'msvcp140.dll'}

# Reviewed against the preserved Windows STOP d9d448a0... . These are fixed
# file/certificate identities, never derived from the current runtime catalog.
# Windows/compatibility publisher signatures alone are not an authorization.
REVIEWED_RUNTIME_IDENTITIES = MappingProxyType({
    # Exact Microsoft runtimes bundled in the SHA-pinned official PSF3.11.9
    # embed archive. Still require live Windows signature Valid, PE and bytes.
    '4d292623516f65c80482081e62d5dadb759dc16e851de5db24c3cbb57b87db83': MappingProxyType({
        'name': 'vcruntime140.dll',
        'signer_subject': 'CN=Microsoft Windows Software Compatibility Publisher, O=Microsoft Corporation, L=Redmond, S=Washington, C=US',
        'signer_thumbprint': '111F0C73E08E19F2F9DDFC4D6ADA14EC300B5857',
        'file_version': '14.38.33126.1', 'size_bytes': 119192, 'origin': 'base-cpython'}),
    'a113f192195f245f17389e6ecbed8005990bcb2476ddad33f7c4c6c86327afe5': MappingProxyType({
        'name': 'vcruntime140_1.dll',
        'signer_subject': 'CN=Microsoft Windows Software Compatibility Publisher, O=Microsoft Corporation, L=Redmond, S=Washington, C=US',
        'signer_thumbprint': '5341AABA7B62C7350582F76222A1792D63AAE991',
        'file_version': '14.38.33126.1', 'size_bytes': 49528, 'origin': 'base-cpython'}),
    # Independently reviewed CRT census a27e10c6... . This is one file,
    # not permission for its directory, name family or Microsoft signers.
    '1e2e2bcb916931f0ee6d0a567212511244e7442da574757c331c1b91087f2a0f': MappingProxyType({
     'name': 'msvcp140.dll',
     'path': r'C:\Program Files\Norton\Suite\local.crt\msvcp140.dll',
     'signature_status': 'Valid', 'signature_type': 'Catalog',
     'signer_subject': 'CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US',
     'signer_issuer': 'CN=Microsoft Windows Production PCA 2011, O=Microsoft Corporation, L=Redmond, S=Washington, C=US',
     'signer_thumbprint': 'DC91E564D5BC1E3A8E02D6A8508682ABEA8A2443',
     'company': 'Microsoft Corporation', 'original_filename': 'msvcp140.dll',
     'file_version': '14.44.35112.1', 'pe_machine': '0x8664',
     'size_bytes': 557136, 'origin': 'preloaded-before-Qt'}),
    '052ad6a20d375957e82aa6a3c441ea548d89be0981516ca7eb306e063d5027f4': MappingProxyType({'name': 'vcruntime140.dll',
     'signer_subject': 'CN=Microsoft Windows Software Compatibility Publisher, O=Microsoft Corporation, '
                       'L=Redmond, S=Washington, C=US',
     'signer_thumbprint': '6C6D5882B6227B929967D1E389201A7BB5EBBD35',
     'file_version': '14.42.34438.0',
     'size_bytes': 120400,
     'origin': 'base-cpython'}),
    'e30b3f4979b63b50438d061858c9cde962f4494e585c627a11c98b6c5b7b2592': MappingProxyType({'name': 'vcruntime140_1.dll',
     'signer_subject': 'CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US',
     'signer_thumbprint': 'DC91E564D5BC1E3A8E02D6A8508682ABEA8A2443',
     'file_version': '14.44.35112.1',
     'size_bytes': 49792,
     'origin': 'preloaded-before-Qt'}),
    '60b813f8b87ff4fa344f081c163c1a2234b5e3e41f748721c28fbdecbcfecb8a': MappingProxyType({'name': 'vcruntime140.dll',
     'signer_subject': 'CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US',
     'signer_thumbprint': 'DC91E564D5BC1E3A8E02D6A8508682ABEA8A2443',
     'file_version': '14.44.35112.1',
     'size_bytes': 124520,
     'origin': 'preloaded-before-Qt'}),
    '6a99bc0128e0c7d6cbbf615fcc26909565e17d4ca3451b97f8987f9c6acbc6c8': MappingProxyType({'name': 'vcruntime140_1.dll',
     'signer_subject': 'CN=Microsoft Windows Software Compatibility Publisher, O=Microsoft Corporation, '
                       'L=Redmond, S=Washington, C=US',
     'signer_thumbprint': '1865C35307C0B7C8C5FE1EE98DF4CF6A0C081C30',
     'file_version': '14.42.34438.0',
     'size_bytes': 49776,
     'origin': 'base-cpython'}),
})

def runtime_signature_valid(row):
    if row.get('signature_status') != 'Valid':
        return False
    if row.get('name')=='msvcp140.dll':
        profile=REVIEWED_RUNTIME_IDENTITIES.get(row.get('sha256'))
        return bool(profile) and all(
            ntpath.normcase(ntpath.normpath(row.get(key,'')))==ntpath.normcase(ntpath.normpath(value))
            if key=='path' else row.get(key)==value for key,value in profile.items())
    if re.search(r'(?:^|,\s*)CN=Microsoft Corporation(?:,|$)', row.get('signer_subject', '')):
        return True  # Existing Microsoft Corporation path; other checks remain.
    profile = REVIEWED_RUNTIME_IDENTITIES.get(row.get('sha256'))
    return bool(profile) and all(row.get(key) == value for key, value in profile.items())

def runtime_record_valid(row,path):
    name=path.name.lower()
    if not row or name not in RUNTIME_NAMES or Path(row.get('path','')).resolve()!=path:
        return False
    if (row.get('name')!=name or row.get('signature_status')!='Valid'
            or not runtime_signature_valid(row)
            or row.get('company')!='Microsoft Corporation'
            or row.get('original_filename','').lower()!=name
            or not re.fullmatch(r'14\.\d+\.\d+\.\d+',row.get('file_version',''))
            or row.get('pe_machine')!='0x8664'
            or row.get('origin') not in ('base-cpython','preloaded-before-Qt')):
        return False
    try:
        content=path.read_bytes()
    except OSError:
        return False
    return len(content)==row.get('size_bytes') and hashlib.sha256(content).hexdigest()==row.get('sha256')

def installed_native_paths():
    paths=set()
    for name in NAMES:
        distribution=metadata.distribution(name)
        for item in distribution.files or []:
            path=Path(distribution.locate_file(item)).resolve()
            if path.suffix.lower() in ('.dll','.pyd'):paths.add(path)
    return paths

def path_problem(loaded,installed,venv,runtime_identities=None,*,original_names=None):
    installed={Path(p).resolve() for p in installed}
    known_names={p.name.lower() for p in installed}
    for raw in loaded:
        path=Path(raw).resolve();name=path.name.lower()
        if name in known_names or name.startswith(('qt6','pyside','shiboken')) or name=='qwindows.dll':
            if path not in installed or not path.is_relative_to(Path(venv).resolve()):
                # Only attested individual MSVC CRT files, never a directory.
                # Qt/binding names cannot satisfy a reviewed CRT identity.
                if name in RUNTIME_NAMES and runtime_record_valid((runtime_identities or {}).get(str(path)),path):
                    continue
                return 'Loaded Qt/binding/native dependency outside pinned venv: '+str(path)
        if path not in installed or not path.is_relative_to(Path(venv).resolve()):
            originals=()
            if original_names is not None:originals=original_names.get(str(path),())
            elif sys.platform=='win32' and path.suffix.lower() in ('.dll','.pyd'):
                from native_version import original_filenames
                originals=original_filenames(path)
            for original in originals:
                original=ntpath.basename(original).lower()
                if original.startswith(('qt','pyside','shiboken')) or original=='qwindows.dll':
                    return 'Foreign Qt/binding OriginalFilename '+original+': '+str(path)
    return None

def verify_installed_record():
    rows=[]
    for name in NAMES:
        distribution=metadata.distribution(name)
        for item in distribution.files or []:
            path=Path(distribution.locate_file(item)).resolve()
            if path.suffix.lower() not in ('.dll','.pyd'):continue
            if not path.is_relative_to(Path(sys.prefix).resolve()):raise ValueError('Native distribution file outside venv')
            data=path.read_bytes();digest=hashlib.sha256(data).digest()
            if item.hash is None or item.hash.mode!='sha256' or item.size!=len(data) or \
               item.hash.value!=base64.urlsafe_b64encode(digest).rstrip(b'=').decode():
                raise ValueError('Native DLL/PYD RECORD mismatch: '+str(path))
            rows.append(dict(path=str(path),sha256=digest.hex(),size_bytes=len(data),distribution=name))
    if not rows:raise ValueError('Missing pinned backend native inventory')
    return rows
