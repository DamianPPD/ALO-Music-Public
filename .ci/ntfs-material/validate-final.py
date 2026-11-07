"""Final native verification of the sealed ALO tree with an isolated test overlay."""
import difflib
import hashlib
import os
from pathlib import Path
import sys
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'apev2'))
import validate as shared

MODULE = 'tests/test_windows_output_native_v0427.py'
CONTRACT = 'tests/test_output_contract_windows_v0427.py'
SELECTED = CONTRACT + '::test_two_bindings_only_assess_the_selected_record'
TEST = MODULE + '::test_native_material_identity'
ORDERS = (
    ('same-size',),
    ('restored-mtime',),
    ('same-size', 'restored-mtime'),
    ('restored-mtime', 'same-size'),
)
SUITES = {
    'apev2': (shared.TEST,),
    'audio-and-audit': ('tests/test_audio_identity_v0427.py', 'tests/test_export_audit_v0427.py'),
    'export-and-registration': (
        'tests/test_manual_cover_export_v0427.py', 'tests/test_created_output_registration_v0427.py',
        'tests/test_export_preflight_v0427.py', 'tests/test_export_window_v0427.py',
    ),
    'binding-adoption': (
        'tests/test_managed_binding_file_ids_v0427.py', 'tests/test_legacy_adoption_v0427.py',
        'tests/test_adoption_integration_v0427.py', 'tests/test_legacy_adoption_optimization_v0427.py',
    ),
    'output-session-ui': ('tests/test_output_session_ui_v0427.py',),
    'ntfs-unit-and-lease': (
        'tests/test_windows_output_identity_v0427.py', 'tests/test_windows_output_lease_v0427.py',
    ),
    'ntfs-material-and-native-delivery': (MODULE,),
    'selected-binding-isolated': (SELECTED,),
    'output-contract': (CONTRACT, '--deselect=' + SELECTED),
    'qt-lifecycle': ('tests/test_identification_qt_lifecycle_v0427.py',),
}


def install_test_overlay(candidate, evidence):
    target = candidate / MODULE
    original = target.read_bytes()
    corrected = (HERE / 'native-test-overlay.py').read_bytes()
    if original == corrected:
        raise RuntimeError('Expected an isolated test correction')
    delta = ''.join(difflib.unified_diff(
        original.decode().splitlines(keepends=True), corrected.decode().splitlines(keepends=True),
        fromfile='product-tree/' + MODULE, tofile='diagnostic-overlay/' + MODULE,
    ))
    (evidence / 'test-overlay.diff').write_text(delta, encoding='utf-8', newline='\n')
    target.write_bytes(corrected)
    if target.read_bytes() != corrected:
        raise RuntimeError('Incorrect native test overlay')
    shared.record(evidence, 'test-overlay', {
        'path': MODULE,
        'original_sha256': hashlib.sha256(original).hexdigest(),
        'overlay_sha256': hashlib.sha256(corrected).hexdigest(),
        'application_code_overlays': [],
    })


def main():
    repo = HERE.parents[1]
    evidence = Path(os.environ['RUNNER_TEMP']) / 'alo-ntfs-final'
    evidence.mkdir()
    stages = []
    error = None
    try:
        if sys.platform != 'win32':
            raise RuntimeError('Native Windows required')
        private = shared.select_volume(evidence)
        shared.native_environment(evidence, private, repo)
        _, candidate = shared.prepare_native(repo, evidence, private)
        install_test_overlay(candidate, evidence)

        for order, cases in enumerate(ORDERS, 1):
            targets = tuple(f'{TEST}[{case}]' for case in cases)
            for repeat in range(1, 5):
                name = f'corrected-order-{order}-{repeat}'
                suite = shared.pytest_stage(name, 'green', candidate, targets, evidence, private, timeout=45)
                stages.append((suite, shared.green_ok(suite) and suite.get('tests') == len(cases)))

        for name, targets in SUITES.items():
            suite = shared.pytest_stage(name, 'green', candidate, targets, evidence, private, timeout=320)
            required_count = 48 if name == 'apev2' else 1 if name == 'selected-binding-isolated' else None
            stages.append((suite, shared.green_ok(suite) and
                           (required_count is None or suite.get('tests') == required_count)))

        # The sealed tree manifest records exact blobs before the test overlay.
        # Recheck every materialized path, applying only the declared exception.
        import json
        rows = json.loads((evidence / 'green-tree-manifest.json').read_text(encoding='utf-8'))
        for row in rows:
            if row['path'] == MODULE:
                expected = hashlib.sha256((HERE / 'native-test-overlay.py').read_bytes()).hexdigest()
            else:
                expected = row['sha256']
            if hashlib.sha256(candidate.joinpath(*row['path'].split('/')).read_bytes()).hexdigest() != expected:
                raise RuntimeError('Materialized file changed: ' + row['path'])
        shared.record(evidence, 'post-test-tree-verification', {
            'all_manifest_paths_verified': len(rows), 'test_only_overlay': MODULE})
    except Exception as exc:
        traceback.print_exc()
        (evidence / 'harness-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        error = f'{type(exc).__name__}: {exc}'
    return shared.finish(evidence, stages, error)


if __name__ == '__main__':
    sys.exit(main())
