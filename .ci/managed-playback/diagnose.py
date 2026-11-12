"""Native A/B reproduction only. Never modifies either measured source tree."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'apev2'))
import validate as shared
spec = importlib.util.spec_from_file_location('qt_wrapper', HERE.parent / 'qt-cover' / 'validate.py')
qt = importlib.util.module_from_spec(spec); spec.loader.exec_module(qt)

A = 'tests/test_managed_playback_v0427.py::test_managed_only_restart_can_play_edit_and_read_cover'
B = 'tests/test_managed_playback_v0427.py::test_stale_cover_or_waveform_generation_is_ignored'
INPUT_TREE = '379812add6795a1964e65d15405890cfdfee3f20'


def main():
    repo = HERE.parents[1]
    evidence = Path(os.environ['RUNNER_TEMP']) / 'alo-managed-playback-diagnosis'
    evidence.mkdir(exist_ok=True)
    results = []
    error = None
    try:
        shared.require(sys.platform == 'win32', 'Native Windows required')
        private = shared.select_volume(evidence)
        shared.native_environment(evidence, private, repo)
        patch = shared.git(repo, 'show', 'HEAD:.ci/qt-cover/candidate.patch')
        shared.require(shared.sha256(patch) == '61d4bbfaba8da8f90012dd5e849891d427529119dd1613d3209515dc40531f72', 'Input patch hash mismatch')
        tree = shared.prepare_index(repo, private, patch)
        shared.require(tree == INPUT_TREE, 'Input tree mismatch')
        env_before = os.environ.copy()
        for side, tree in (('base', shared.BASE_TREE), ('input', INPUT_TREE)):
            root = private / (side + '-source'); root.mkdir()
            rows = shared.tree_manifest(repo, tree, root)
            seal = dict(tree=tree, manifest_sha256=shared.sha256(shared.json_bytes(rows)))
            qt.verify_manifest(root, rows, seal, evidence, side + '-pre')
            # Plain controls and observational repeats use identical unchanged tests.
            for repeat in (1, 2):
                for label, targets in (('A', (A,)), ('B', (B,)), ('AB', (A, B)), ('BA', (B, A))):
                    name = f'{side}-{label}-{repeat}'
                    options = ['-c', str(root/'pyproject.toml'), '-p', 'no:cacheprovider',
                               '--capture=tee-sys', '-o', 'junit_logging=all']
                    if repeat == 2:
                        os.environ['PYTHONPATH'] = str(HERE)
                        os.environ['ALO_MEDIA_OBSERVATIONS'] = str(evidence/(name+'.jsonl'))
                        options += ['-p', 'media_observe']
                        # shared.pytest_stage sets PYTHONPATH to product src. Use
                        # PYTEST_PLUGINS plus an external .pth-free bootstrap below.
                    command = [sys.executable, '-B', str(HERE/'pytest_bootstrap.py'), str(root), str(HERE),
                               *options, '--basetemp', str(private/name), '--junitxml', str(evidence/(name+'.xml')), *targets]
                    log = evidence/(name+'.log')
                    env = env_before | dict(PYTHONPATH=str(root/'src'), TEMP=str(private), TMP=str(private),
                                            ALO_MEDIA_OBSERVATIONS=str(evidence/(name+'.jsonl')),
                                            ALO_EVIDENCE=str(evidence), ALO_PHASE='diagnosis')
                    with log.open('wb') as stream:
                        try:
                            code = subprocess.run(command, cwd=root, env=env, stdout=stream,
                                                  stderr=subprocess.STDOUT, timeout=100).returncode
                        except subprocess.TimeoutExpired:
                            code = 124
                    row = dict(stage=name, tree=tree, exit_code=code, observed=repeat==2, targets=list(targets))
                    import xml.etree.ElementTree as ET
                    try:
                        suite = ET.parse(evidence/(name+'.xml')).getroot().find('testsuite')
                        row.update({key:int(suite.get(key,'0')) for key in ('tests','failures','errors','skipped')})
                        row['cases'] = [dict(name=c.get('name'), outcome='FAIL' if c.find('failure') is not None else 'ERROR' if c.find('error') is not None else 'SKIP' if c.find('skipped') is not None else 'PASS') for c in suite.findall('testcase')]
                    except Exception as exc:
                        row['junit_error'] = repr(exc)
                    results.append(row); shared.record(evidence, name+'-summary', row)
            if side == 'input':
                for label, targets in (('cover-AB', ('tests/test_qt_cover_lifecycle_v0427.py', A, B)),
                                       ('cover-BA', ('tests/test_qt_cover_lifecycle_v0427.py', B, A))):
                    options = ('-c',str(root/'pyproject.toml'),'-p','no:cacheprovider','--capture=tee-sys')
                    suite = shared.pytest_stage('input-'+label, 'diagnosis', root, (*options,*targets),evidence,private,timeout=180)
                    results.append(suite)
            qt.verify_manifest(root, rows, seal, evidence, side + '-post')
    except Exception as exc:
        error = repr(exc)
        (evidence/'harness-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        traceback.print_exc()
    shared.record(evidence,'summary',dict(error=error, stages=results, diagnostic_only=True))
    shared.record(evidence,'evidence-sha256',{p.name:shared.sha256(p.read_bytes()) for p in sorted(evidence.iterdir()) if p.is_file() and p.name!='evidence-sha256.json'})
    return 1 if error else 0


if __name__ == '__main__':
    sys.exit(main())
