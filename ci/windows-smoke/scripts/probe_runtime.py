"""Fail-closed probe for the one application-private CPython 3.11.9 x64 runtime."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import site
import struct
import sys
import sysconfig
import traceback


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--phase', choices=('base', 'pip'), required=True)
    args = parser.parse_args()
    root = Path(args.expected_root).resolve()
    record = dict(status='STOP', phase=args.phase, utc=datetime.now(timezone.utc).isoformat(),
        native_windows_execution=sys.platform == 'win32', executable=sys.executable,
        implementation=platform.python_implementation(), version=platform.python_version(),
        version_info=list(sys.version_info), machine=platform.machine(),
        pointer_bits=struct.calcsize('P') * 8, prefix=sys.prefix, base_prefix=sys.base_prefix,
        sysconfig_platform=sysconfig.get_platform(), sys_path=list(sys.path),
        flags=dict(isolated=sys.flags.isolated, ignore_environment=sys.flags.ignore_environment,
            no_user_site=sys.flags.no_user_site, safe_path=sys.flags.safe_path),
        enable_user_site=site.ENABLE_USER_SITE)
    code = 2
    try:
        if sys.platform != 'win32':
            raise RuntimeError('Windows CPython 3.11.9 x64 required; no native Windows test ran.')
        if platform.python_implementation() != 'CPython' or sys.version_info[:3] != (3, 11, 9):
            raise RuntimeError('Interpreter must be exactly CPython 3.11.9.')
        if struct.calcsize('P') != 8 or sysconfig.get_platform() != 'win-amd64':
            raise RuntimeError('Interpreter architecture must be win-amd64.')
        if Path(sys.executable).resolve() != root / 'python.exe':
            raise RuntimeError('Unexpected interpreter location.')
        if Path(sys.prefix).resolve() != root or Path(sys.base_prefix).resolve() != root:
            raise RuntimeError('Runtime must be application-private and must not use a venv.')
        if not (sys.flags.isolated and sys.flags.ignore_environment and
                sys.flags.no_user_site and sys.flags.safe_path) or site.ENABLE_USER_SITE is not False:
            raise RuntimeError('Interpreter isolation is not active.')
        expected_pth = b'python311.zip\n.\nLib/site-packages\nimport site\n'
        if (root / 'python311._pth').read_bytes() != expected_pth:
            raise RuntimeError('Unexpected controlled _pth configuration.')
        allowed = {root, root / 'python311.zip', root / 'Lib' / 'site-packages'}
        paths = [Path(value).resolve() for value in sys.path]
        if len(paths) != len(set(paths)) or set(paths) != allowed:
            raise RuntimeError('Unexpected import search paths: ' + repr(paths))
        modules = {}
        for name in ('ssl', '_ssl', 'sqlite3', '_sqlite3', 'hashlib', '_hashlib', 'ctypes', '_ctypes'):
            module = importlib.import_module(name)
            origin = Path(module.__file__).resolve()
            if origin != root and root not in origin.parents:
                raise RuntimeError('Module came from outside private runtime: ' + name)
            modules[name] = str(origin)
        import ssl
        import sqlite3
        record.update(module_origins=modules, openssl_version=ssl.OPENSSL_VERSION,
            sqlite_version=sqlite3.sqlite_version, pth_sha256=digest(root / 'python311._pth'))
        if args.phase == 'pip':
            import pip
            origin = Path(pip.__file__).resolve()
            if pip.__version__ != '25.3' or (root / 'Lib' / 'site-packages') not in origin.parents:
                raise RuntimeError('Unexpected pip version or origin.')
            record.update(pip_version=pip.__version__, pip_origin=str(origin))
        record['status'] = 'PASS'
        code = 0
    except Exception as error:
        record.update(error=str(error), traceback=traceback.format_exc())
    Path(args.output).write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=record['status'], phase=args.phase, version=record['version'],
        native_windows_execution=record['native_windows_execution']), ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
