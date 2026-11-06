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
import tempfile
import xml.etree.ElementTree as ET

BASE = 'a80207b5097e037bc90350cedc80bb1b87b3ea93'
BASE_TREE = 'e8af09488e92aefd2b25efaa899ddcb7d3011dfb'
TREE = '676b4d19639168151443cbfc10a89943f0f8de91'
PATCH_SHA = 'e2955e46eb19f687ad92f9dd7fe4fc52b05a5d18ed999d342b435adc1d86ca6c'
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TEMP = Path(os.environ['RUNNER_TEMP'])
EVIDENCE = TEMP / 'alo-ntfs-evidence'
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


def high_volume():
    observations = []
    for base in dict.fromkeys((TEMP, Path(os.environ['LOCALAPPDATA']) / 'Temp',
                               Path(os.environ['USERPROFILE']), Path(os.environ['SystemDrive'] + chr(92)))):
        try:
            path = Path(tempfile.mkdtemp(prefix='alo-ntfs-', dir=base)).resolve()
        except OSError as exc:
            observations.append(dict(base=str(base), error=str(exc)))
            continue
        fs = subprocess.check_output(['pwsh', '-NoProfile', '-Command',
                                       f'(Get-Volume -DriveLetter {path.drive[0]}).FileSystem'],
                                      text=True).strip()
        device = path.stat().st_dev
        observations.append(dict(base=str(base), filesystem=fs, device=device))
        if fs == 'NTFS' and 2**63 <= device < 2**64:
            record('volume-selection', observations)
            return path
        path.rmdir()
    record('volume-selection', observations)
    raise RuntimeError('No writable local NTFS volume with a high-bit serial on this runner')


def prepare(name, tree, patch_ref, patch_sha, manifest_sha):
    patch = PRIVATE / f'{name}.patch'
    patch.write_bytes(git('show', patch_ref))
    assert sha(patch.read_bytes()) == patch_sha
    index = PRIVATE / f'{name}.index'
    git('read-tree', BASE, index=index)
    git('apply', '--cached', '--check', str(patch), index=index)
    git('apply', '--cached', str(patch), index=index)
    git('diff', '--cached', '--check', BASE, index=index)
    assert git('write-tree', index=index).decode().strip() == tree
    root = PRIVATE / name
    rows = materialize(tree, root)
    manifest = (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    assert sha(manifest) == manifest_sha
    (EVIDENCE / f'{name}-manifest.json').write_bytes(manifest)
    return root


def run_pytest(name, root, tests, observer=False):
    command = [HERE / 'pytest_observe.py'] if observer else ['-m', 'pytest']
    junit = EVIDENCE / f'{name}.xml'
    code = stage(name, root, [*command, '-vv', '-ra', '--basetemp', PRIVATE / name,
                              '--junitxml', junit, *tests])
    suite = ET.parse(junit).getroot().find('testsuite')
    record(f'{name}-summary', dict(suite.attrib))
    return code, suite


def main():
    global PRIVATE
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    assert sys.platform == 'win32' and platform.python_implementation() == 'CPython'
    assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8
    assert platform.machine().upper() in ('AMD64', 'X86_64')
    PRIVATE = high_volume()
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
                               architecture=platform.machine(), filesystem=filesystem, temp=str(PRIVATE), device=PRIVATE.stat().st_dev,
                               python=sys.version, qt=qVersion(), qt_platform=app.platformName(),
                               sqlite=sqlite3.sqlite_version, packages=modules,
                               ffmpeg=ffmpeg, ffmpeg_version=ffmpeg_version))
    app.quit()

    expected = json.loads((HERE / 'sealed.json').read_text(encoding='utf-8'))
    assert git('rev-parse', BASE + '^{tree}').decode().strip() == BASE_TREE
    red = prepare('red-tree', TREE, 'HEAD:.ci/manual-cover/candidate.patch', PATCH_SHA,
                  expected['red_manifest_sha256'])
    green = prepare('green-tree', expected['tree'], 'HEAD:.ci/ntfs-sqlite/candidate.patch',
                    expected['patch_sha256'], expected['manifest_sha256'])
    record('verified-trees', dict(base=BASE, base_tree=BASE_TREE, red_tree=TREE,
                                  red_patch_sha256=PATCH_SHA, **expected))
    red_code, red_suite = run_pytest('native-red', red, (
        'tests/test_created_output_registration_v0427.py::test_worker_registers_verified_outputs_and_repeat_does_not_duplicate',
        'tests/test_legacy_adoption_v0427.py::test_adoption_survives_restart_without_changing_manual_work'))
    assert red_code == 1 and red_suite.get('failures') == '2' and red_suite.get('errors') == '0'
    assert all('Python int too large to convert to SQLite INTEGER' in (node.text or '')
               for node in red_suite.findall('testcase/failure'))

    probe = REPO / '.ci' / 'manual-cover' / 'native_probe.py'
    codes = [stage('native-cover-probe', green, [probe, 'candidate'])]
    tests = ['test_manual_cover_export_v0427.py', 'test_created_output_registration_v0427.py',
             'test_export_preflight_v0427.py', 'test_export_window_v0427.py']
    target_code, previous = run_pytest('native-previous-61', green,
        [f'tests/{name}' for name in tests], observer=True)
    assert previous.get('tests') == '61' and previous.get('skipped') == '0'
    for scenario in ('full', 'cancel'):
        if (EVIDENCE / f'before-close-{scenario}.json').exists():
            codes.append(stage(f'restart-{scenario}', green, [HERE / 'restart.py', scenario]))
        else:
            codes.append(1)

    extra = ['test_managed_binding_file_ids_v0427.py', 'test_legacy_adoption_v0427.py',
             'test_adoption_integration_v0427.py', 'test_legacy_adoption_optimization_v0427.py',
             'test_output_session_ui_v0427.py']
    extra_code, extra_suite = run_pytest('native-extra', green, [f'tests/{name}' for name in extra])
    codes.append(stage('native-adoption', green, [HERE / 'native_adoption.py']))
    return int(bool(target_code or extra_code or int(extra_suite.get('skipped')) or any(codes)))


if __name__ == '__main__':
    sys.exit(main())
