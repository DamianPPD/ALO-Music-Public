"""Run ALO APEv2 adoption validation on the sealed candidate's exact Git blobs."""

import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'apev2'))
import validate as shared

DIAGNOSTIC = '.ci/qt-cover'
ADOPTION = 'tests/test_apev2_adoption_v0427.py'
NATIVE = 'tests/test_windows_output_native_v0427.py'
CONTRACT = 'tests/test_output_contract_windows_v0427.py'
SELECTED = CONTRACT + '::test_two_bindings_only_assess_the_selected_record'
PUBLICATION = 'test_publication_integration.py'
PROTECTION = 'test_protected_adoption_reads.py'
MATERIAL = NATIVE + '::test_native_material_identity'
ORDERS = (
    ('same-size',),
    ('restored-mtime',),
    ('same-size', 'restored-mtime'),
    ('restored-mtime', 'same-size'),
)


def read_diagnostic(repo, filename):
    return shared.git(repo, 'show', f'HEAD:{DIAGNOSTIC}/{filename}')


def prepare_candidate(repo, evidence, private):
    patch = read_diagnostic(repo, 'candidate.patch')
    seal_bytes = read_diagnostic(repo, 'sealed.json')
    expected = json.loads(seal_bytes)
    shared.require(shared.sha256(patch) == expected['patch_sha256'], 'Candidate patch SHA-256 mismatch')
    shared.require(expected['base'] == shared.BASE and expected['base_tree'] == shared.BASE_TREE,
                   'Seal does not name the immutable published baseline')
    shared.require(shared.git(repo, 'rev-parse', shared.BASE + '^{commit}').decode().strip() == shared.BASE,
                   'Fetched baseline commit mismatch')

    # Applying the patch to a private index is independent of checkout filters
    # and the diagnostic branch's working tree.
    tree = shared.prepare_index(repo, private, patch)
    shared.require(tree == expected['tree'], 'Candidate patch does not produce the sealed Git tree')
    candidate = private / 'green'
    candidate.mkdir()
    rows = shared.tree_manifest(repo, tree, candidate)
    by_path = {row['path']: row for row in rows}
    shared.require({shared.TEST, ADOPTION, NATIVE} <= by_path.keys(), 'Required tests missing from candidate')
    actual = dict(base=shared.BASE, base_tree=shared.BASE_TREE, tree=tree,
                  patch_sha256=shared.sha256(patch), manifest_sha256=shared.sha256(shared.json_bytes(rows)),
                  red_test_sha256=by_path[shared.TEST]['sha256'])
    shared.require(actual == expected, 'Recreated candidate manifest does not match the seal')
    (evidence / 'candidate.patch').write_bytes(patch)
    (evidence / 'sealed.json').write_bytes(seal_bytes)
    shared.record(evidence, 'verified-tree', actual | dict(files=len(rows), materialization='raw Git blobs'))

    # This additional test targets the exact candidate; it never replaces or
    # adds a file in the product tree.
    supplemental = private / 'diagnostic-tests'
    supplemental.mkdir()
    diagnostic_tests = {}
    for name in (PUBLICATION, PROTECTION):
        content = read_diagnostic(repo, name)
        path = supplemental / name
        path.write_bytes(content)
        (evidence / name).write_bytes(content)
        diagnostic_tests[path] = content
    shared.record(evidence, 'supplemental-tests', {
        'outside_candidate': True,
        'sha256': {path.name: shared.sha256(content) for path, content in diagnostic_tests.items()},
    })
    return candidate, rows, expected, diagnostic_tests


def regular_path(path, kind):
    st = path.lstat()
    return kind(st.st_mode) and not (getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def verify_manifest(candidate, rows, expected, evidence, phase):
    by_path = {row['path']: row for row in rows}
    prefixes = {parent.as_posix() for rel in by_path for parent in PurePosixPath(rel).parents
                if parent.as_posix() != '.'}
    found = {}

    def propagate(exc):
        raise exc

    shared.require(regular_path(candidate, stat.S_ISDIR), 'Candidate root is not a regular directory')
    for parent, directories, files in os.walk(candidate, onerror=propagate, followlinks=False):
        for name in directories:
            path = Path(parent) / name
            relative = path.relative_to(candidate).as_posix()
            shared.require(relative in prefixes and regular_path(path, stat.S_ISDIR),
                           f'Unexpected or redirected candidate directory: {relative}')
        for name in files:
            path = Path(parent) / name
            relative = path.relative_to(candidate).as_posix()
            shared.require(relative in by_path and regular_path(path, stat.S_ISREG),
                           f'Unexpected or redirected candidate file: {relative}')
            row = by_path[relative]
            data = path.read_bytes()
            found[relative] = row | dict(sha256=shared.sha256(data), bytes=len(data))
            shared.require(found[relative] == row, f'Candidate bytes changed: {relative}')

    missing = sorted(by_path.keys() - found.keys())
    shared.require(not missing, f'Candidate files missing: {missing}')
    manifest = shared.json_bytes([found[row['path']] for row in rows])
    digest = shared.sha256(manifest)
    shared.require(digest == expected['manifest_sha256'], f'{phase} manifest SHA-256 mismatch')
    (evidence / f'{phase}-tree-manifest.json').write_bytes(manifest)
    shared.record(evidence, f'{phase}-tree-verification', dict(
        tree=expected['tree'], manifest_sha256=digest, files=len(found), overlays=[], exact_inventory=True,
    ))


def stages_for(publication, protection):
    yield 'qt-cover-lifecycle', ('tests/test_qt_cover_lifecycle_v0427.py',), 19, 180
    for repeat in range(1, 21):
        yield f'mainwindow-fresh-{repeat:02}', (ADOPTION+'::test_unchanged_ape_binary_tag_adoption_survives_main_window_restart',), 1, 70
    yield 'managed-cover-read-regressions', ('tests/test_managed_playback_v0427.py','-k','cover'), None, 240
    yield 'i7-waveform-lifetime', ('tests/test_waveform_signals_lifecycle.py','tests/test_waveform_submission.py'), None, 240
    yield 'library-rapid-selection', ('tests/test_library_waveform_switching.py',), None, 240

    identity = 'tests/test_windows_output_identity_v0427.py'
    yield 'targeted-identity-and-lease', (
        identity, 'tests/test_windows_output_lease_v0427.py',
    ), None, 240
    yield 'targeted-protected-adoption', (str(protection), '-o', 'pythonpath=src tests'), 1, 180
    yield 'targeted-native-mutation-and-lifecycle', (
        CONTRACT + '::test_real_lease_blocks_content_and_namespace_mutation',
        CONTRACT + '::test_close_while_delivery_is_active_revokes_and_finishes_thread',
        CONTRACT + '::test_abandoned_receiver_times_out_then_rejects_late_packet',
    ), 14, 240
    # Separate Qt processes for the long/previously order-dependent groups.
    yield 'apev2-adoption', (ADOPTION,), None, 320
    yield 'apev2-identity', (shared.TEST,), 48, 320
    yield 'publication-create-stop-restart', (str(publication), '-o', 'pythonpath=src tests'), 2, 240
    yield 'audio-and-audit', ('tests/test_audio_identity_v0427.py', 'tests/test_export_audit_v0427.py'), None, 240
    yield 'export-and-registration', (
        'tests/test_manual_cover_export_v0427.py', 'tests/test_created_output_registration_v0427.py',
        'tests/test_export_preflight_v0427.py', 'tests/test_export_window_v0427.py',
    ), None, 320
    yield 'binding-adoption', (
        'tests/test_managed_binding_file_ids_v0427.py', 'tests/test_legacy_adoption_v0427.py',
        'tests/test_adoption_integration_v0427.py', 'tests/test_legacy_adoption_optimization_v0427.py',
    ), None, 320
    yield 'adopted-output-and-sqlite', ('tests/test_adopted_output_spec_v0427.py',), None, 240
    yield 'output-session-ui', ('tests/test_output_session_ui_v0427.py',), None, 240
    yield 'ntfs-unit-and-lease', (
        'tests/test_windows_output_identity_v0427.py', 'tests/test_windows_output_lease_v0427.py',
    ), None, 240
    yield 'ntfs-material-and-native-delivery', (NATIVE,), None, 320
    yield 'selected-binding-isolated', (SELECTED,), 1, 120
    yield 'output-contract', (CONTRACT, '--deselect=' + SELECTED), None, 320
    yield 'qt-lifecycle', ('tests/test_identification_qt_lifecycle_v0427.py',), None, 240
    for order, cases in enumerate(ORDERS, 1):
        targets = tuple(f'{MATERIAL}[{case}]' for case in cases)
        for repeat in range(1, 5):
            yield f'corrected-order-{order}-{repeat}', targets, len(cases), 45


def run_stages(plan, candidate, evidence, private, stages):
    for name, targets, required_count, timeout in plan:
        options = ('-c', str(candidate / 'pyproject.toml'), '-p', 'no:cacheprovider', '--capture=tee-sys',
                   '-o', 'junit_logging=all', '-o', 'junit_log_passing_tests=true')
        suite = shared.pytest_stage(name, 'green', candidate, (*options, *targets), evidence, private,
                                    timeout=timeout)
        cases = suite.get('cases', [])
        ok = (shared.green_ok(suite) and 'junit_error' not in suite and bool(cases)
              and (required_count is None or suite.get('tests') == required_count)
              and all(case['result'] == 'passed' for case in cases))
        stages.append((suite | dict(timeout_seconds=timeout, required_count=required_count), ok))
        if (name.startswith(('targeted-','mainwindow-')) or name in {'qt-cover-lifecycle','managed-cover-read-regressions','i7-waveform-lifetime','library-rapid-selection'}) and not ok:
            break


def finish(evidence, plan, stages, error):
    results = {suite['stage']: (suite, ok) for suite, ok in stages}
    details = []
    for name, targets, required_count, timeout in plan:
        if name in results:
            suite, ok = results[name]
            details.append({key: value for key, value in suite.items() if key != 'cases'} |
                           dict(expectation_met=ok, status='passed' if ok else 'failed'))
        else:
            details.append(dict(stage=name, targets=list(targets), required_count=required_count,
                                timeout_seconds=timeout, status='not_run', expectation_met=False))
    success = error is None and bool(details) and all(row['expectation_met'] for row in details)
    run_url = (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/"
               f"{os.environ['GITHUB_RUN_ID']}")
    shared.record(evidence, 'exit-codes', {row['stage']: row.get('exit_code') for row in details})
    shared.record(evidence, 'summary', dict(success=success, error=error, run_url=run_url, stages=details))
    if step_summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        lines = ['## ALO Music APEv2 adoption: native Windows', '', f'[Actions run]({run_url})', '',
                 'All suites target the sealed candidate; no replacement overlay is applied.', '',
                 '| Stage | Exit | Tests | Failures | Errors | Skips | Status |',
                 '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
        for row in details:
            counts = [str(row.get(key, '—')) for key in ('exit_code', 'tests', 'failures', 'errors', 'skipped')]
            lines.append('| ' + ' | '.join([row['stage'], *counts, row['status']]) + ' |')
        if error:
            lines.extend(('', f'Harness error: {error}'))
        with Path(step_summary).open('a', encoding='utf-8') as stream:
            stream.write('\n'.join(lines) + '\n')
    hashes = {file.relative_to(evidence).as_posix(): shared.sha256(file.read_bytes())
              for file in sorted(evidence.rglob('*')) if file.is_file() and file.name != 'evidence-sha256.json'}
    (evidence / 'evidence-sha256.json').write_bytes(shared.json_bytes(hashes))
    return 0 if success else 1



def run_red_controls(repo, candidate, evidence, private):
    test_name = 'test_qt_cover_lifecycle_v0427.py'
    red_test = private / 'diagnostic-tests' / test_name
    red_test.write_bytes((candidate/'tests'/test_name).read_bytes())
    old_patch = read_diagnostic(repo,'input.patch')
    shared.require(shared.sha256(old_patch)=='91ca72339ba80deb79210f88f839b8fb26e45591acda0154cfb35ae941375304','Input patch changed')
    indexdir=private/'input-index';indexdir.mkdir()
    old_tree=shared.prepare_index(repo,indexdir,old_patch)
    shared.require(old_tree=='95f52e26be4826c235bd2ae033632d830fab48ac','Input tree changed')
    names = ['test_repeated_cover_requests_do_not_grow_destroyed_connections',
             'test_mainwindow_close_and_application_quit_path_cancel_cover',
             'test_closing_cancels_pending_external_reply_without_new_fallback[close]',
             'test_leaving_selected_track_cancels_without_renewing_old_request[context]',
             'test_leaving_selected_track_cancels_without_renewing_old_request[empty]']
    results=[]
    for side,tree in [('base',shared.BASE_TREE),('ape-input',old_tree)]:
        root=private/('red-'+side);root.mkdir()
        rows=shared.tree_manifest(repo,tree,root)
        expected={'tree':tree,'manifest_sha256':shared.sha256(shared.json_bytes(rows))}
        verify_manifest(root,rows,expected,evidence,'red-'+side+'-pre')
        options=('-c',str(root/'pyproject.toml'),'-p','no:cacheprovider','--capture=tee-sys','-o','pythonpath=src tests')
        targets=tuple(str(red_test)+'::'+name for name in names)
        suite=shared.pytest_stage('red-'+side,'red',root,(*options,*targets),evidence,private,timeout=90)
        verify_manifest(root,rows,expected,evidence,'red-'+side+'-post')
        ok=(suite.get('tests')==5 and suite.get('failures')==5 and suite.get('errors')==0 and suite.get('skipped')==0 and suite.get('exit_code')==1)
        results.append({'side':side,'tree':tree,'expected_five_failures':ok,'result':suite})
        shared.require(ok,'RED controls did not reproduce five lifecycle assertions on '+side)
    shared.require(red_test.read_bytes()==(candidate/'tests'/test_name).read_bytes(),'RED/GREEN tests differ')
    shared.record(evidence,'red-controls',results)

def main():
    repo = HERE.parents[1]
    evidence = Path(os.environ['RUNNER_TEMP']) / 'alo-qt-cover-validation'
    evidence.mkdir(parents=True, exist_ok=True)
    stages = []
    plan = list(stages_for(Path(PUBLICATION), Path(PROTECTION)))
    error = None
    try:
        shared.require(sys.platform == 'win32', 'Native Windows runner is required')
        private = shared.select_volume(evidence)
        shared.native_environment(evidence, private, repo)
        ffmpeg = shutil.which('ffmpeg')
        expected_ffmpeg = Path(os.environ['ALO_FFMPEG_EXE'])
        shared.require(ffmpeg is not None and expected_ffmpeg.samefile(ffmpeg),
                       'FFmpeg on PATH is not the verified pinned executable')
        ffmpeg_version = subprocess.check_output([ffmpeg, '-version'], encoding='utf-8').splitlines()[0]
        shared.require(ffmpeg_version.startswith('ffmpeg version 9.0.2-'), 'Unexpected FFmpeg build')
        candidate, rows, expected, diagnostic_tests = prepare_candidate(repo, evidence, private)
        verify_manifest(candidate, rows, expected, evidence, 'pre-test')
        plan = list(stages_for(*(next(path for path in diagnostic_tests if path.name == name)
                                for name in (PUBLICATION, PROTECTION))))
        try:
            run_red_controls(repo, candidate, evidence, private)
            run_stages(plan, candidate, evidence, private, stages)
        finally:
            verify_manifest(candidate, rows, expected, evidence, 'post-test')
            for path, content in diagnostic_tests.items():
                shared.require(path.read_bytes() == content, 'Supplemental test changed: ' + path.name)
    except Exception as exc:
        traceback.print_exc()
        (evidence / 'harness-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        error = f'{type(exc).__name__}: {exc}'
    return finish(evidence, plan, stages, error)


if __name__ == '__main__':
    sys.exit(main())
