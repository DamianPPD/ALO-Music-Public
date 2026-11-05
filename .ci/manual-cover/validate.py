"""Verify and exercise the unmodified baseline and candidate on native Windows."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

BASE = 'a80207b5097e037bc90350cedc80bb1b87b3ea93'
BASE_TREE = 'e8af09488e92aefd2b25efaa899ddcb7d3011dfb'
TREE = '676b4d19639168151443cbfc10a89943f0f8de91'
PATCH_SHA = 'e2955e46eb19f687ad92f9dd7fe4fc52b05a5d18ed999d342b435adc1d86ca6c'
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TEMP = Path(os.environ['RUNNER_TEMP'])
PRIVATE = TEMP / 'alo-cover-private'
EVIDENCE = TEMP / 'alo-cover-evidence'
PRIVATE.mkdir()
EVIDENCE.mkdir()
EXIT = {}


def record(name, data):
    message = json.dumps(data, ensure_ascii=False, indent=2)
    (EVIDENCE / f'{name}.json').write_text(message + '\n', encoding='utf-8')
    print(name, message, flush=True)


def git(*args, input_bytes=None, index=None):
    env = os.environ.copy()
    if index:
        env['GIT_INDEX_FILE'] = str(index)
    return subprocess.run(['git', '-C', str(REPO), *args], input=input_bytes,
                          stdout=subprocess.PIPE, check=True, env=env).stdout


def entries(tree):
    for row in git('ls-tree', '-rz', tree).split(b'\0')[:-1]:
        head, path = row.split(b'\t', 1)
        mode, kind, blob = head.decode().split()
        assert kind == 'blob'
        yield dict(path=path.decode(), mode=mode, blob=blob)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def materialize(tree, dest):
    import io

    rows = list(entries(tree))
    objects = io.BytesIO(git('cat-file', '--batch',
                             input_bytes=''.join(f"{row['blob']}\n" for row in rows).encode()))
    for row in rows:
        blob, kind, length = objects.readline().decode().split()
        assert (blob, kind) == (row['blob'], 'blob')
        data = objects.read(int(length))
        assert objects.read(1) == b'\n'
        file = dest / row['path']
        assert not file.exists(), file
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        data = file.read_bytes()
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == blob
        row.update(sha256=sha(data), bytes=len(data))
    assert not objects.read()
    return rows


def stage(name, root, args):
    env = os.environ | dict(PYTHONPATH=str(root / 'src'), ALO_EVIDENCE=str(EVIDENCE),
                            TEMP=str(PRIVATE), TMP=str(PRIVATE))
    print(f'Running {name}', flush=True)
    with (EVIDENCE / f'{name}.log').open('wb') as out:
        code = subprocess.run([sys.executable, '-B', *map(str, args)], cwd=root, env=env,
                              stdout=out, stderr=subprocess.STDOUT, timeout=600).returncode
    EXIT[name] = code
    record('exit-codes', EXIT)
    log = (EVIDENCE / f'{name}.log').read_text(encoding='utf-8', errors='replace')
    print(log[-18000:], flush=True)
    return code


def main():
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    assert sys.platform == 'win32' and platform.python_implementation() == 'CPython'
    assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8
    assert platform.machine().upper() in ('AMD64', 'X86_64')
    filesystem = subprocess.check_output(['pwsh', '-NoProfile', '-Command',
                                          f'(Get-Volume -DriveLetter {PRIVATE.drive[0]}).FileSystem'],
                                         text=True).strip()
    assert filesystem == 'NTFS', filesystem
    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg
    ffmpeg_version = subprocess.check_output([ffmpeg, '-version'], text=True)
    assert 'libmp3lame' in subprocess.check_output([ffmpeg, '-hide_banner', '-encoders'], text=True)
    app = QApplication([])
    assert app.platformName() == 'windows'
    modules = {package: importlib.metadata.version(package) for package in
               ['PySide6', 'shiboken6', 'Pillow', 'mutagen', 'requests', 'pytest']}
    assert modules['PySide6'] == modules['shiboken6'] == '6.10.3'
    record('environment', dict(platform=platform.platform(), win32=platform.win32_ver(),
                               runner_image=os.environ.get('ImageOS'),
                               runner_image_version=os.environ.get('ImageVersion'),
                               architecture=platform.machine(), filesystem=filesystem, temp=str(PRIVATE),
                               python=sys.version, qt=qVersion(), qt_platform=app.platformName(),
                               sqlite=sqlite3.sqlite_version, packages=modules,
                               ffmpeg=ffmpeg, ffmpeg_version=ffmpeg_version))
    app.quit()

    patch = PRIVATE / 'candidate.patch'
    patch.write_bytes(git('show', 'HEAD:.ci/manual-cover/candidate.patch'))
    assert sha(patch.read_bytes()) == PATCH_SHA
    assert git('rev-parse', BASE + '^{tree}').decode().strip() == BASE_TREE
    index = PRIVATE / 'candidate.index'
    git('read-tree', BASE, index=index)
    git('apply', '--cached', '--check', str(patch), index=index)
    git('apply', '--cached', str(patch), index=index)
    git('diff', '--cached', '--check', BASE, index=index)
    candidate = git('write-tree', index=index).decode().strip()
    assert candidate == TREE
    changed = git('diff', '--name-status', BASE_TREE, TREE).decode().splitlines()
    assert len(changed) == 9
    base_root, product_root = PRIVATE / 'base', PRIVATE / 'candidate'
    base_rows = materialize(BASE_TREE, base_root)
    product_rows = materialize(TREE, product_root)
    manifest = dict(head=BASE, base_tree=BASE_TREE, tree=TREE, files=product_rows)
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    assert sha(manifest_bytes) == 'c675850978f6407375f79536f1d0bcc0115a75d53fa117302ba3f8a368cd8b48'
    (EVIDENCE / 'SOURCE-MANIFEST.json').write_bytes(manifest_bytes)
    record('verified-tree', dict(base_head=BASE, base_tree=BASE_TREE, candidate_tree=TREE,
                                 patch_sha256=PATCH_SHA, base_files=len(base_rows),
                                 candidate_files=len(product_rows), changed=changed,
                                 all_blob_ids_modes_and_bytes_match=True, diff_check='clean',
                                 diagnostic_head=git('rev-parse', 'HEAD').decode().strip()))

    reproducer = PRIVATE / 'reproduce_cover_stat.py'
    reproducer.write_bytes(git('show', 'HEAD:.ci/manual-cover/reproduce_cover_stat.py'))
    if stage('saved-base-reproducer', base_root, [reproducer]):
        return 2
    if stage('base-native-probe', base_root, [HERE / 'native_probe.py', 'base']):
        return 2
    if stage('candidate-native-probe', product_root, [HERE / 'native_probe.py', 'candidate']):
        return 1

    tests = ['test_manual_cover_export_v0427.py', 'test_created_output_registration_v0427.py',
             'test_export_preflight_v0427.py', 'test_export_window_v0427.py']
    junit = EVIDENCE / 'targeted.xml'
    code = stage('targeted', product_root,
                 [HERE / 'pytest_observe.py', '-vv', '-ra', '--basetemp', PRIVATE / 'pytest',
                  '--junitxml', junit, *(f'tests/{t}' for t in tests)])
    if junit.exists():
        suite = ET.parse(junit).getroot().find('testsuite')
        record('targeted-summary', dict(suite.attrib))
    if code:
        return code
    assert int(suite.get('skipped')) == 0
    for scenario in ('full', 'cancel'):
        if stage(f'restart-{scenario}', product_root, [HERE / 'restart.py', scenario]):
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
