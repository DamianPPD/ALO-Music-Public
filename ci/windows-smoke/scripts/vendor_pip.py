"""Vendor one pinned pip wheel into the current application-private embed runtime."""
import argparse
import base64
import csv
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import platform
import struct
import subprocess
import sys
import sysconfig
import zipfile

PIP_NAME = 'pip-25.3-py3-none-any.whl'
PIP_SHA256 = '9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd'
PIP_SIZE = 1778622
PIP_MODULE_ENTRY = '''import runpy, sys
sys.path.insert(0, sys.argv.pop(1))
runpy.run_module('pip', run_name='__main__', alter_sys=True)
'''


def verify_record(wheel):
    """Verify every immutable wheel member before executing its entry point."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(n.casefold() for n in names)) or archive.testzip() is not None:
            raise ValueError('STOP: duplicate members or damaged pip wheel CRC.')
        for item in archive.infolist():
            name = item.filename
            path = PurePosixPath(name)
            if (not name or name != path.as_posix() or path.is_absolute() or
                    '..' in path.parts or '\\' in name or ':' in name or
                    any(ord(c) < 32 for c in name) or item.is_dir() or
                    (item.external_attr >> 16) & 0o170000 == 0o120000 or
                    path.parts[0] not in ('pip', 'pip-25.3.dist-info')):
                raise ValueError('STOP: unsafe pip wheel member: ' + name)
        record_name = 'pip-25.3.dist-info/RECORD'
        rows = list(csv.reader(io.StringIO(archive.read(record_name).decode('utf-8'))))
        recorded = set()
        for row in rows:
            if len(row) != 3 or row[0] in recorded or row[0] not in names:
                raise ValueError('STOP: invalid/duplicate pip RECORD row.')
            name, expected_hash, expected_size = row
            recorded.add(name)
            if name == record_name:
                if expected_hash or expected_size:
                    raise ValueError('STOP: invalid pip RECORD self entry.')
                continue
            data = archive.read(name)
            actual = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode('ascii')
            if expected_hash != actual or expected_size != str(len(data)):
                raise ValueError('STOP: pip RECORD hash/size mismatch: ' + name)
        if recorded != set(names):
            raise ValueError('STOP: incomplete pip RECORD inventory.')


def prepare_pip(wheel, target, prefix):
    """Install only the pinned wheel, using real module-mode execution."""
    prefix = Path(prefix)
    target = Path(target)
    expected = prefix.resolve() / 'Lib' / 'site-packages'
    if (prefix.name != 'python' or prefix.is_symlink() or
            (prefix / 'Lib').is_symlink() or target.is_symlink() or
            target.resolve() != expected or not target.is_dir() or any(target.iterdir())):
        raise ValueError('STOP: pip target must be the empty application-private Lib/site-packages.')
    wheel = Path(wheel)
    if (wheel.name != PIP_NAME or wheel.is_symlink() or not wheel.is_file() or
            wheel.stat().st_size != PIP_SIZE or hashlib.sha256(wheel.read_bytes()).hexdigest() != PIP_SHA256):
        raise ValueError('STOP: pinned pip wheel SHA-256/size mismatch.')
    verify_record(wheel)
    environment = dict(os.environ, PIP_CONFIG_FILE=os.devnull)
    # alter_sys=True gives actual module __file__/__spec__/argv semantics,
    # like -m pip; no executable-name spoofing or change to pip's guard.
    command = [sys.executable, '-I', '-B', '-X', 'utf8', '-c', PIP_MODULE_ENTRY, str(wheel.resolve()),
        '--isolated', 'install', '--no-index', '--no-deps', '--require-hashes',
        '--only-binary=:all:', '--disable-pip-version-check', '--no-cache-dir',
        '--no-compile', '--no-warn-script-location', '--target', str(target.resolve()),
        wheel.resolve().as_uri() + '#sha256=' + PIP_SHA256]
    code = subprocess.run(command, env=environment, check=False, timeout=90).returncode
    if code != 0:
        return code
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            output = target / name
            if output.is_symlink() or not output.is_file():
                raise ValueError('STOP: missing/aliased prepared pip file: ' + name)
            if not name.endswith('.dist-info/RECORD') and output.read_bytes() != archive.read(name):
                raise ValueError('STOP: prepared pip file differs from pinned wheel: ' + name)
        if not (target / 'pip-25.3.dist-info/RECORD').stat().st_size:
            raise ValueError('STOP: empty installed pip RECORD.')
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel', required=True)
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    if (sys.platform != 'win32' or platform.python_implementation() != 'CPython' or
            sys.version_info[:3] != (3, 11, 9) or struct.calcsize('P') != 8 or
            sysconfig.get_platform() != 'win-amd64'):
        print('STOP: Windows CPython 3.11.9 x64 required; no installation attempted.', file=sys.stderr)
        return 2
    prefix = Path(sys.prefix).resolve()
    if (not sys.flags.isolated or not sys.flags.ignore_environment or
            prefix != Path(sys.base_prefix).resolve()):
        print('STOP: private interpreter isolation/prefix mismatch.', file=sys.stderr)
        return 2
    try:
        return prepare_pip(Path(args.wheel), Path(args.target), prefix)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.TimeoutExpired) as error:
        print('STOP: pip preparation failed: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
