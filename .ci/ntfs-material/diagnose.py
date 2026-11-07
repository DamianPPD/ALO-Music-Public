"""Native NTFS material-identity diagnostics for two immutable ALO trees."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'apev2'))
import validate as shared

BASE_TREE = '71649c46fcda001874a79206c6666e54a781d754'
APE_TREE = 'bbddf5e27151942c0b0126af35e03833725fdaa1'
PATCH_SHA = '10ea189da18f73ca0f0583f0f248bcbbd939c45e021a3072fa849b5c1b33b22f'
MODULE = 'tests/test_windows_output_native_v0427.py'
NATIVE_SOURCE = 'src/audio_library_organizer/safety/windows_file_identity.py'
TEST = MODULE + '::test_native_material_identity'
CASES = ('same-size', 'restored-mtime')
ORDERS = {
    'only-same-size': CASES[:1],
    'only-restored-mtime': CASES[1:],
    'forward': CASES,
    'reverse': CASES[::-1],
}
REPEATS = 4


def run_probe(label, root, evidence, private):
    output = evidence / (label + '-probe.json')
    log = evidence / (label + '-probe.log')
    env = os.environ | {'PYTHONPATH': str(root / 'src'), 'TEMP': str(private), 'TMP': str(private)}
    with log.open('wb') as stream:
        process = subprocess.run(
            [sys.executable, '-B', str(HERE / 'probe.py'), '--output', str(output),
             '--temp', str(private / (label + '-probe-fixtures'))],
            cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
    return {'exit_code': process.returncode, 'evidence_exists': output.is_file(), 'log': log.name}


def diagnosis_ok(stage, order):
    cases = stage.get('cases', [])
    names = [case['name'] for case in cases]
    required = [f'test_native_material_identity[{name}]' for name in order]
    if names != required or stage.get('errors') != 0 or stage.get('skipped') != 0:
        return False
    if stage['exit_code'] == 0:
        return all(case['result'] == 'passed' for case in cases)
    return stage['exit_code'] == 1 and stage.get('failures', 0) > 0 and all(
        case['result'] == 'passed' or
        (case['result'] == 'failure' and 'assert not True' in case['message'])
        for case in cases)


def main():
    repo = HERE.parents[1]
    evidence = Path(os.environ['RUNNER_TEMP']) / 'alo-ntfs-diagnosis'
    evidence.mkdir()
    result = {'repeats_per_order': REPEATS, 'orders': ORDERS, 'trees': {}, 'complete': False}
    try:
        if sys.platform != 'win32':
            raise RuntimeError('Native Windows required')
        private = shared.select_volume(evidence)
        shared.native_environment(evidence, private, repo)
        red, green = shared.prepare_native(repo, evidence, private)
        seals = json.loads((evidence / 'verified-trees.json').read_text(encoding='utf-8'))
        if (seals['base_tree'], seals['tree'], seals['patch_sha256']) != (BASE_TREE, APE_TREE, PATCH_SHA):
            raise RuntimeError('Unexpected product trees or patch')
        for path in (MODULE, NATIVE_SOURCE):
            if (red / path).read_bytes() != (green / path).read_bytes():
                raise RuntimeError('Compared source differs across trees: ' + path)

        complete = True
        for label, root in (('base', red), ('candidate', green)):
            stages = []
            counts = {case: Counter() for case in CASES}
            for order, cases in ORDERS.items():
                for index in range(1, REPEATS + 1):
                    name = f'{label}-{order}-{index:02d}'
                    targets = tuple(f'{TEST}[{case}]' for case in cases)
                    stage = shared.pytest_stage(name, label, root, targets, evidence, private, timeout=45)
                    recognized = diagnosis_ok(stage, cases)
                    for case in stage.get('cases', ()):
                        for target in cases:
                            if case['name'] == f'test_native_material_identity[{target}]':
                                counts[target][case['result']] += 1
                    stages.append({key: value for key, value in stage.items() if key != 'cases'}
                                  | {'observed_expected_assertion_or_pass': recognized})
                    complete &= recognized
            probe = run_probe(label, root, evidence, private)
            complete &= probe['exit_code'] == 0 and probe['evidence_exists']
            result['trees'][label] = {'root': str(root), 'stages': stages, 'case_counts': counts, 'probe': probe}
        result['complete'] = complete
    except Exception:
        trace = traceback.format_exc()
        (evidence / 'harness-error.log').write_text(trace, encoding='utf-8')
        print(trace, flush=True)
    shared.record(evidence, 'diagnosis-summary', result)
    shared.record(evidence, 'evidence-sha256', {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(evidence.iterdir()) if path.is_file()
    })
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
