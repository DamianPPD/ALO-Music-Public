"""Verify the sealed APEv2 patch and exercise the exact product trees on Windows."""

import argparse
import ctypes
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET

BASE = 'c88a18b73f56732d1d906e00beabca2787592a00'
BASE_TREE = '71649c46fcda001874a79206c6666e54a781d754'
TEST = 'tests/test_apev2_identity_v0427.py'
HERE = Path(__file__).resolve().parent
MPEG_REFUSAL = 'Invalid MPEG frame boundary/header.'
GENERIC_REFUSAL = 'Source audio identity unverified.'

RED_REQUIRED_FAILURES = {
    **{
        f'test_valid_apev2_keeps_legacy_mpeg_digest[{location}-{layout}]': (MPEG_REFUSAL,)
        for location in ('eof', 'before-id3v1')
        for layout in ('footer-only', 'header-and-footer')
    },
    'test_mainwindow_creates_and_registers_valid_apev2_in_mixed_batch': (GENERIC_REFUSAL,),
    'test_mainwindow_audit_preserves_different_source_refusal_reasons': (MPEG_REFUSAL, GENERIC_REFUSAL),
    'test_apev2_metadata_edits_do_not_change_untagged_audio_proof': (MPEG_REFUSAL,),
    'test_coincidental_tail_signatures_do_not_change_mpeg_boundary[ape]': (MPEG_REFUSAL,),
    'test_single_frame_byte_change_changes_apev2_audio_digest': (MPEG_REFUSAL,),
    **{
        f'test_valid_apev2_does_not_mask_mpeg_or_real_ffmpeg_errors[{damage}-{reason}]': (MPEG_REFUSAL,)
        for damage, reason in (
            ('truncate', 'Truncated MPEG frame'), ('info-count', 'Xing/Info frame count'),
            ('side-info', 'Full MP3 decoding failed'),
        )
    },
    'test_apev2_cancellation_during_decode_never_returns_a_proof': ('False',),
    'test_apev2_same_bytes_replacement_during_validation_is_refused': (MPEG_REFUSAL,),
}

RED_REQUIRED_PASSES = {
    *{f'test_existing_id3_and_untagged_streams_keep_exact_frame_digest[{layout}]'
      for layout in ('none', 'leading', 'trailing')},
    'test_malformed_apev2_and_unknown_tails_remain_invalid[bad-ape-size]',
    'test_malformed_apev2_and_unknown_tails_remain_invalid[unknown-tail]',
}

NATIVE_MATERIAL_TESTS = tuple(
    f'tests/test_windows_output_native_v0427.py::test_native_material_identity[{kind}]'
    for kind in ('same-size', 'restored-mtime')
)

REGRESSIONS = {
    'native-audio-regressions': (
        'test_audio_identity_v0427.py', 'test_export_audit_v0427.py',
    ),
    'native-export-regressions': (
        'test_manual_cover_export_v0427.py', 'test_created_output_registration_v0427.py',
        'test_export_preflight_v0427.py', 'test_export_window_v0427.py',
    ),
    'native-binding-regressions': (
        'test_managed_binding_file_ids_v0427.py', 'test_legacy_adoption_v0427.py',
        'test_adoption_integration_v0427.py', 'test_legacy_adoption_optimization_v0427.py',
        'test_output_session_ui_v0427.py',
    ),
    'native-lease-and-qt-regressions': (
        'test_windows_output_identity_v0427.py', 'test_windows_output_lease_v0427.py',
        'test_windows_output_native_v0427.py', 'test_output_contract_windows_v0427.py',
        'test_identification_qt_lifecycle_v0427.py',
    ),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def record(folder, name, value):
    data = json_bytes(value)
    (folder / f'{name}.json').write_bytes(data)
    print(f'{name}: {data.decode().rstrip()}', flush=True)


def git(repo, *args, index=None, data=None):
    env = os.environ.copy()
    env.pop('GIT_INDEX_FILE', None)
    if index is not None:
        env['GIT_INDEX_FILE'] = str(index)
    return subprocess.run(
        ['git', '-c', 'core.autocrlf=false', '-C', str(repo), *args],
        input=data, stdout=subprocess.PIPE, check=True, env=env,
    ).stdout


def prepare_index(repo, private, patch):
    require(git(repo, 'rev-parse', BASE + '^{tree}').decode().strip() == BASE_TREE,
            'Fetched commit does not match the immutable product tree')
    patch_path = private / 'candidate.patch'
    patch_path.write_bytes(patch)
    index = private / 'candidate.index'
    git(repo, 'read-tree', BASE, index=index)
    git(repo, 'apply', '--cached', '--check', str(patch_path), index=index)
    git(repo, 'apply', '--cached', str(patch_path), index=index)
    git(repo, 'diff', '--cached', '--check', BASE, index=index)
    return git(repo, 'write-tree', index=index).decode().strip()


def tree_manifest(repo, tree, dest=None):
    rows = []
    paths = set()
    for line in git(repo, 'ls-tree', '-rz', tree).split(b'\0')[:-1]:
        metadata, name = line.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        path = name.decode()
        parts = PurePosixPath(path).parts
        require(kind == 'blob' and mode in ('100644', '100755'), f'Unsupported tree entry: {path}')
        require(parts and not any(part in ('/', '..') or '\\' in part or ':' in part
                                  for part in parts), f'Unsupported materialization path: {path}')
        folded = path.casefold()
        require(folded not in paths, f'Case collision in materialization: {path}')
        paths.add(folded)
        rows.append(dict(path=path, mode=mode, blob=blob))

    requests = ''.join(row['blob'] + '\n' for row in rows).encode()
    objects = io.BytesIO(git(repo, 'cat-file', '--batch', data=requests))
    for row in rows:
        blob, kind, length = objects.readline().decode().split()
        content = objects.read(int(length))
        require((blob, kind, len(content), objects.read(1)) ==
                (row['blob'], 'blob', int(length), b'\n'), f'Invalid Git object: {row["path"]}')
        if dest is not None:
            path = dest.joinpath(*PurePosixPath(row['path']).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as file:
                file.write(content)
            content = path.read_bytes()
        header = b'blob ' + str(len(content)).encode() + b'\0'
        require(hashlib.sha1(header + content).hexdigest() == blob, f'Blob mismatch: {row["path"]}')
        row.update(sha256=sha256(content), bytes=len(content))
    require(not objects.read(), 'Extra output while reading Git blobs')
    return rows


def make_seal(tree, patch, red, green):
    require(TEST not in {row['path'] for row in red}, 'RED overlay would replace a baseline file')
    tests = [row for row in green if row['path'] == TEST]
    require(len(tests) == 1, 'Candidate does not contain the required tests-only RED overlay')
    return dict(base=BASE, base_tree=BASE_TREE, tree=tree, patch_sha256=sha256(patch),
                manifest_sha256=sha256(json_bytes(green)), red_test_sha256=tests[0]['sha256'])


def local_seal(args):
    patch = args.patch.read_bytes()
    with tempfile.TemporaryDirectory(prefix='alo-apev2-seal-') as folder:
        tree = prepare_index(args.repo, Path(folder), patch)
        red = tree_manifest(args.repo, BASE_TREE)
        green = tree_manifest(args.repo, tree)
    seal = make_seal(tree, patch, red, green)
    args.output.write_bytes(json_bytes(seal))
    (args.output.parent / 'candidate-tree-manifest.json').write_bytes(json_bytes(green))
    print(json_bytes(seal).decode().rstrip())


def native_volume(root):
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    drive_type = kernel.GetDriveTypeW
    drive_type.argtypes = [wintypes.LPCWSTR]
    drive_type.restype = wintypes.UINT
    volume_info = kernel.GetVolumeInformationW
    volume_info.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
    volume_info.restype = wintypes.BOOL
    filesystem = ctypes.create_unicode_buffer(261)
    if not volume_info(root, None, 0, None, None, None, filesystem, len(filesystem)):
        raise ctypes.WinError(ctypes.get_last_error())
    return drive_type(root), filesystem.value


def select_volume(evidence):
    observations = []
    eligible = []
    bases = (Path(os.environ['RUNNER_TEMP']), Path(os.environ['LOCALAPPDATA']) / 'Temp',
             Path(os.environ['USERPROFILE']), Path(os.environ['SystemDrive'] + '\\'))
    for base in dict.fromkeys(bases):
        path = None
        try:
            path = Path(tempfile.mkdtemp(prefix='alo-ape-', dir=base)).resolve()
            drive_type, filesystem = native_volume(path.anchor)
            device = path.stat().st_dev
            eligible_here = drive_type == 3 and filesystem.upper() == 'NTFS'
            high_bit = 2**63 <= device < 2**64
            observations.append(dict(base=str(base), path=str(path), drive_type=drive_type,
                                     filesystem=filesystem, device=device, eligible=eligible_here,
                                     high_bit=high_bit))
            if eligible_here:
                eligible.append((path, high_bit))
                if high_bit:
                    break
                continue
        except OSError as exc:
            observations.append(dict(base=str(base), error=str(exc)))
        if path is not None:
            path.rmdir()
    selected = next((path for path, high_bit in eligible if high_bit), None)
    if selected is None and eligible:
        selected = eligible[0][0]
    for path, _ in eligible:
        if path != selected:
            path.rmdir()
    record(evidence, 'volume-selection', dict(selected=str(selected) if selected else None,
                                              observations=observations))
    require(selected is not None, 'No writable fixed local NTFS volume on the runner')
    return selected


def native_environment(evidence, private, repo):
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    require(sys.platform == 'win32' and sys.getwindowsversion().build == 20348,
            'Windows Server 2022 is required')
    require(platform.python_implementation() == 'CPython' and sys.version_info[:3] == (3, 12, 10)
            and struct.calcsize('P') == 8 and platform.machine().upper() in ('AMD64', 'X86_64'),
            'CPython 3.12.10 x64 is required')
    ffmpeg = shutil.which('ffmpeg')
    require(ffmpeg is not None, 'Native FFmpeg is missing')
    version = subprocess.check_output([ffmpeg, '-version'], text=True, encoding='utf-8')
    encoders = subprocess.check_output([ffmpeg, '-hide_banner', '-encoders'], text=True, encoding='utf-8')
    require('libmp3lame' in encoders, 'Native FFmpeg lacks the MP3 encoder used by synthetic fixtures')
    app = QApplication([])
    require(app.platformName() == 'windows', 'The native Qt Windows platform is required')
    packages = {package: importlib.metadata.version(package) for package in
                ('PySide6', 'shiboken6', 'Pillow', 'mutagen', 'requests', 'pytest')}
    require(packages['PySide6'] == packages['shiboken6'] == qVersion() == '6.10.3',
            'PySide6, Qt and shiboken6 6.10.3 are required')
    with sqlite3.connect(private / 'sqlite-probe.db') as db:
        require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'SQLite check failed')
    diagnostic = git(repo, 'rev-parse', 'HEAD').decode().strip()
    require(diagnostic == os.environ['GITHUB_SHA'], 'Diagnostic checkout does not match this run')
    record(evidence, 'environment', dict(
        platform=platform.platform(), win32=platform.win32_ver(), architecture=platform.machine(),
        runner_image=os.environ.get('ImageOS'), runner_image_version=os.environ.get('ImageVersion'),
        filesystem='NTFS', local_fixed_volume=True, temp=str(private), device=private.stat().st_dev,
        python=sys.version, qt=qVersion(), qt_platform=app.platformName(),
        sqlite=sqlite3.sqlite_version, packages=packages, ffmpeg=ffmpeg, ffmpeg_version=version,
        diagnostic_commit=diagnostic, run_id=os.environ.get('GITHUB_RUN_ID'),
        run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
    ))
    app.quit()


def prepare_native(repo, evidence, private):
    patch = git(repo, 'show', 'HEAD:.ci/apev2/candidate.patch')
    expected = json.loads(git(repo, 'show', 'HEAD:.ci/apev2/sealed.json'))
    require(expected.get('patch_sha256') == sha256(patch), 'Candidate patch hash mismatch')
    tree = prepare_index(repo, private, patch)
    require(expected.get('tree') == tree, 'Candidate patch does not reproduce the sealed tree')
    red, green = private / 'red', private / 'green'
    red_rows = tree_manifest(repo, BASE_TREE, red)
    green_rows = tree_manifest(repo, tree, green)
    actual = make_seal(tree, patch, red_rows, green_rows)
    require(actual == expected, 'Candidate seal does not match the materialized trees')
    (evidence / 'red-base-tree-manifest.json').write_bytes(json_bytes(red_rows))
    (evidence / 'green-tree-manifest.json').write_bytes(json_bytes(green_rows))
    overlay = (green / TEST).read_bytes()
    require(sha256(overlay) == actual['red_test_sha256'], 'RED overlay hash mismatch')
    with (red / TEST).open('xb') as file:
        file.write(overlay)
    require((red / TEST).read_bytes() == overlay, 'RED and GREEN test code differs')
    record(evidence, 'verified-trees', dict(**actual, red_test_overlay=TEST,
                                           red_base_manifest_sha256=sha256(json_bytes(red_rows)),
                                           red_base_files=len(red_rows), green_files=len(green_rows)))
    return red, green


def pytest_stage(name, phase, root, tests, evidence, private, *, timeout=600):
    junit = evidence / f'{name}.xml'
    log = evidence / f'{name}.log'
    env = os.environ | dict(
        PYTHONPATH=str(root / 'src'), TEMP=str(private), TMP=str(private),
        ALO_EVIDENCE=str(evidence), ALO_PHASE=phase, ALO_62D_EVIDENCE=str(evidence),
    )
    command = [sys.executable, '-B', '-m', 'pytest', '-vv', '-ra', '--tb=short',
               '-o', 'faulthandler_timeout=90',
               '--basetemp', str(private / name), '--junitxml', str(junit), *tests]
    print(f'Running {name}: {tests}', flush=True)
    summary = dict(stage=name, targets=list(tests))
    with log.open('wb') as out:
        try:
            summary['exit_code'] = subprocess.run(command, cwd=root, env=env,
                                                  stdout=out, stderr=subprocess.STDOUT,
                                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            summary['exit_code'] = 124
            out.write(f'\nHarness timeout after {timeout} seconds\n'.encode())
    print(log.read_text(encoding='utf-8', errors='replace')[-30000:], flush=True)
    try:
        suite = ET.parse(junit).getroot().find('testsuite')
        require(suite is not None, 'JUnit report has no testsuite')
        summary.update({key: int(suite.get(key, '0')) for key in ('tests', 'failures', 'errors', 'skipped')})
        summary['cases'] = [
            dict(name=case.get('name'), classname=case.get('classname'), result=outcome,
                 message=detail.get('message', '') if detail is not None else '')
            for case in suite.findall('testcase')
            for outcome, detail in [next(((tag, case.find(tag)) for tag in ('error', 'failure', 'skipped')
                                          if case.find(tag) is not None), ('passed', None))]
        ]
    except (OSError, ET.ParseError, RuntimeError) as exc:
        summary['junit_error'] = str(exc)
    (evidence / f'{name}-summary.json').write_bytes(json_bytes(summary))
    print(name, {key: value for key, value in summary.items() if key != 'cases'}, flush=True)
    return summary


def green_ok(suite):
    return (suite['exit_code'] == 0 and suite.get('tests', 0) > 0
            and all(suite.get(key) == 0 for key in ('failures', 'errors', 'skipped')))


def red_checks(suite):
    # The unchanged product must run the suite to assertions; missing dependencies,
    # skipped tests, collection errors and crashes do not reproduce the defect.
    cases = {case['name']: case for case in suite.get('cases', [])}
    expected_failures = {}
    for name, fragments in RED_REQUIRED_FAILURES.items():
        case = cases.get(name, {})
        expected_failures[name] = (case.get('result') == 'failure'
                                   and all(fragment in case['message'] for fragment in fragments))
    expected_passes = {name: cases.get(name, {}).get('result') == 'passed'
                       for name in sorted(RED_REQUIRED_PASSES)}
    unexpected_failures = [
        name for name, case in cases.items()
        if case['result'] == 'failure' and (
            name not in RED_REQUIRED_FAILURES or not case['message'].startswith(('AssertionError', 'assert '))
        )
    ]
    return dict(expected_failures=expected_failures, expected_passes=expected_passes,
                unexpected_failures=unexpected_failures,
                success=(suite['exit_code'] == 1 and suite.get('errors') == suite.get('skipped') == 0
                         and all(expected_failures.values()) and all(expected_passes.values())
                         and not unexpected_failures))


def finish(evidence, stages, error=None):
    record(evidence, 'exit-codes', {suite['stage']: suite['exit_code'] for suite, _ in stages})
    summary = dict(success=error is None and bool(stages) and all(ok for _, ok in stages),
                   error=error, stages=[{key: value for key, value in suite.items() if key != 'cases'}
                                        | dict(expectation_met=ok) for suite, ok in stages])
    record(evidence, 'summary', summary)
    if step_summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        lines = ['## ALO Music APEv2 native validation', '',
                 '| Stage | Tests | Failures | Errors | Skips | Expectation met |',
                 '| --- | ---: | ---: | ---: | ---: | --- |']
        for suite, ok in stages:
            counts = [str(suite.get(key, '—')) for key in ('tests', 'failures', 'errors', 'skipped')]
            lines.append('| ' + ' | '.join([suite['stage'], *counts, 'yes' if ok else 'no']) + ' |')
        lines.extend(('', 'RED expects assertion failures on the immutable product baseline. '
                      'The RED overlay consists of the same test module executed on GREEN.', ''))
        if error:
            lines.extend(('Harness error: ' + error, ''))
        with Path(step_summary).open('a', encoding='utf-8') as stream:
            stream.write('\n'.join(lines) + '\n')
    hashes = {file.name: sha256(file.read_bytes()) for file in sorted(evidence.iterdir()) if file.is_file()}
    (evidence / 'evidence-sha256.json').write_bytes(json_bytes(hashes))
    return 0 if summary['success'] else 1


def run_native(*, lease_recheck=False):
    repo = HERE.parents[1]
    evidence = Path(os.environ['RUNNER_TEMP']) / 'alo-apev2-evidence'
    evidence.mkdir()
    stages = []
    error = None
    try:
        require(sys.platform == 'win32', 'Native Windows runner is required')
        private = select_volume(evidence)
        native_environment(evidence, private, repo)
        red, green = prepare_native(repo, evidence, private)
        if lease_recheck:
            contract = 'tests/test_output_contract_windows_v0427.py'
            selected = f'{contract}::test_two_bindings_only_assess_the_selected_record'
            isolated = (
                ('native-selected-binding-recheck', green, (selected,), 120),
                ('native-selected-binding-base', red, (selected,), 120),
                ('native-output-contract-recheck', green, (contract, '--deselect=' + selected), 360),
                ('native-metadata-lease-recheck', green,
                 ('tests/test_windows_output_identity_v0427.py',
                  'tests/test_windows_output_lease_v0427.py',
                  'tests/test_windows_output_native_v0427.py'), 360),
                ('native-qt-lifecycle-recheck', green, ('tests/test_identification_qt_lifecycle_v0427.py',), 300),
            )
            for name, root, targets, timeout in isolated:
                suite = pytest_stage(name, 'recheck', root, targets, evidence, private, timeout=timeout)
                stages.append((suite, green_ok(suite)))
            return finish(evidence, stages)
        baseline = pytest_stage('native-red', 'red', red, (TEST,), evidence, private)
        red_result = red_checks(baseline)
        record(evidence, 'native-red-expected', red_result)
        stages.append((baseline, red_result['success']))
        candidate = pytest_stage('native-green', 'green', green, (TEST,), evidence, private)
        stages.append((candidate, green_ok(candidate)))
        # Report the same NTFS assertions on the published tree. A baseline
        # failure is evidence for comparison, never an expected PASS.
        base_material = pytest_stage('native-base-material', 'base', red, NATIVE_MATERIAL_TESTS, evidence, private)
        stages.append((base_material, green_ok(base_material)))
        for name, targets in REGRESSIONS.items():
            suite = pytest_stage(name, 'regression', green, tuple(f'tests/{test}' for test in targets),
                                 evidence, private)
            stages.append((suite, green_ok(suite)))
    except Exception as exc:
        traceback.print_exc()
        (evidence / 'harness-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        error = f'{type(exc).__name__}: {exc}'
    return finish(evidence, stages, error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest='command')
    seal = subcommands.add_parser('seal', help='Produce a seal and candidate manifest from patch bytes')
    seal.add_argument('--repo', type=Path, required=True)
    seal.add_argument('--patch', type=Path, required=True)
    seal.add_argument('--output', type=Path, required=True)
    subcommands.add_parser('lease-recheck', help='Isolate the timed-out Windows regression stages')
    args = parser.parse_args()
    if args.command == 'seal':
        local_seal(args)
        return 0
    return run_native(lease_recheck=args.command == 'lease-recheck')


if __name__ == '__main__':
    sys.exit(main())
