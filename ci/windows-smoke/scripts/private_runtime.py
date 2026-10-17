"""Attest this package's pinned application-private CPython; never a host venv."""
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import sys
import sysconfig

def verify_private_runtime():
    package=Path(os.environ['I7_311_PACKAGE_ROOT']).resolve()
    runtime=Path(os.environ['I7_311_RUNTIME_DIR']).resolve()
    if runtime.parent!=package/'work' or not runtime.name.startswith('runtime-'):
        raise ValueError('Private runtime outside this package work directory')
    python=runtime/'python'
    if sys.platform!='win32' or platform.python_implementation()!='CPython' or sys.version_info[:3]!=(3,11,9) \
        or struct.calcsize('P')!=8 or sysconfig.get_platform()!='win-amd64':
        raise ValueError('Exactly Windows CPython3.11.9 AMD64 required')
    if Path(sys.executable).resolve()!=python/'python.exe' or Path(sys.prefix).resolve()!=python or Path(sys.base_prefix).resolve()!=python:
        raise ValueError('Unexpected private interpreter prefix/executable')
    if not(sys.flags.isolated and sys.flags.ignore_environment and sys.flags.no_user_site):
        raise ValueError('Interpreter isolation is not active')
    catalog=json.loads((package/'metadata/environment-catalog.json').read_text(encoding='utf-8'))
    if catalog['python_version']!='3.11.9' or catalog['platform']!='win-amd64':
        raise ValueError('Unexpected interpreter catalog')
    expected_pth=b'python311.zip\n.\nLib/site-packages\nimport site\n'
    for name,row in catalog['python_embed']['files'].items():
        p=python/name
        if p.is_symlink()or not p.is_file():raise ValueError('Missing/aliased interpreter file '+name)
        data=p.read_bytes()
        if name=='python311._pth':
            if data!=expected_pth:raise ValueError('Unexpected private import path configuration')
        elif len(data)!=row['size_bytes']or hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Private interpreter file changed: '+name)
    for name,row in catalog['pip']['files'].items():
        if name.endswith('.dist-info/RECORD'):continue # pip writes its installation RECORD.
        p=python/'Lib/site-packages'/name
        if p.is_symlink()or not p.is_file():raise ValueError('Missing/aliased pinned pip file '+name)
        data=p.read_bytes()
        if len(data)!=row['size_bytes']or hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Pinned vendored pip changed: '+name)
    import site
    if site.ENABLE_USER_SITE is not False:raise ValueError('User site must stay disabled')
    return dict(status='PASS',python=sys.version,executable=str(python/'python.exe'),prefix=str(python),
        version='3.11.9',architecture='AMD64',application_private=True,venv=False,
        original_files_checked=len(catalog['python_embed']['files']),
        pip_original_files_checked=len(catalog['pip']['files'])-1,pth_controlled=True)
