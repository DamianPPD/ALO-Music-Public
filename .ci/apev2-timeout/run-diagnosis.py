"""Reproduce the native restart timeout on immutable baseline and candidate trees."""

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import traceback
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'sealed_runner', HERE.parent / 'apev2-publication-final' / 'validate-final.py')
sealed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sealed)
shared = sealed.shared

MODULE = 'tests/test_apev2_adoption_v0427.py'
TARGET = MODULE + '::test_unchanged_ape_binary_tag_adoption_survives_main_window_restart'
PREVIOUS = MODULE + '::test_unchanged_ape_binary_tag_adoption_remains_confirmed_after_restart'


def plan():
    for side in ('base', 'candidate'):
        for mode in ('weak-debugger','stable'):
            yield f'{side}-cleanup-{mode}', side, False, ('PROBE',mode)
    control = str(HERE / 'test_restart_baseline_control.py')
    yield 'base-id3-native-extra', 'base', True, (control,)
    yield 'candidate-ape-native-extra', 'candidate', True, (TARGET,)


def extract_child(candidate, evidence):
    tree = ast.parse((candidate / MODULE).read_bytes())
    function, = (node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == '_check_in_new_process')
    assignment = function.body[0]
    assert isinstance(assignment, ast.Assign) and assignment.targets[0].id == 'script'
    script = textwrap.dedent(ast.literal_eval(assignment.value.args[0]))
    path = evidence / 'exact-child-program.py'
    path.write_text(script, encoding='utf-8', newline='\n')
    return path


def stage(row, roots, evidence, private, child):
    name, side, traced, targets = row
    directory = evidence / name
    directory.mkdir()
    root = roots[side]
    clean = {k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('TOKEN','SECRET','PASSWORD','CREDENTIAL'))}
    env = clean | {
        'PYTHONPATH': os.pathsep.join((str(HERE), str(root / 'src'))),
        'ALO_EXACT_CHILD_SCRIPT': str(child), 'ALO_TIMEOUT_ATTEMPT': str(directory),
        'ALO_TRACE_CHILD': '1' if traced else '0',
        'TEMP': str(private), 'TMP': str(private), 'ALO_62D_EVIDENCE': str(directory),
    }
    xml = directory / 'junit.xml'
    command = [
        sys.executable, '-B', '-m', 'pytest', '-p', 'restart_parent', '-p', 'no:cacheprovider',
        '-c', str(root / 'pyproject.toml'), '-o', 'pythonpath=src tests',
        '-o', 'faulthandler_timeout=65', '--capture=tee-sys', '-vv', '-ra', '--tb=short',
        '--basetemp', str(private / name), '--junitxml', str(xml), *targets,
    ]
    if targets[0] == 'PROBE':
        import time
        from native_dump import collect, analyze
        started = time.monotonic()
        mode = targets[1]
        command = [sys.executable, str(HERE / 'receiver_cleanup_probe.py'), str(directory), 'weak' if mode=='weak-debugger' else mode]
        if mode == 'weak-debugger':
            cdb = os.environ.get('ALO_CDB_EXE')
            if not cdb:
                raise RuntimeError('CDB required for native abort diagnosis')
            dump = directory / 'hung-abort.dmp'
            commands = 'bu ucrtbase!abort \".echo ABORT_BREAKPOINT; ~*kp; .dump /ma ' + str(dump) + '; q\"; g'
            command = [cdb, '-o', '-G', '-y', os.environ.get('ALO_PYTHON_PDB_DIR',''), '-c', commands, *command]

        with (directory/'pytest.log').open('wb') as stream:
            process = subprocess.Popen(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=45)
                status = 'PASS' if code == 0 else 'FAIL'
            except subprocess.TimeoutExpired:
                code,status = 124,'TIMEOUT'
                shared.record(directory,'live-timeout',{'pid':process.pid,'poll':process.poll(),'limit':45})
                target_pid=process.pid
                if mode == 'weak-debugger':
                    marker=directory/'cleanup-probe.jsonl'
                    if marker.exists():target_pid=json.loads(marker.read_text().splitlines()[0])['pid']
                collect(target_pid,directory)
                process.kill();process.wait()
        analyze(directory)
        if mode == 'weak-debugger' and list(directory.glob('*.dmp')): status = 'RED_CAPTURED'
        result = dict(stage=name,tree=side,traced=False,target=status,exit_code=code,
                      target_seconds=time.monotonic()-started,diagnostic_probe=True)
        shared.record(directory,'result',result)
        return result
    log = directory / 'pytest.log'
    result = dict(stage=name, tree=side, traced=traced, targets=targets)
    with log.open('wb') as stream:
        try:
            result['exit_code'] = subprocess.run(command, cwd=root, env=env, stdout=stream,
                                                  stderr=subprocess.STDOUT, timeout=140).returncode
        except subprocess.TimeoutExpired:
            result['exit_code'] = 124
            stream.write(b'\nOuter diagnostic timeout after 140 seconds.\n')
    if xml.exists():
        suite = ET.parse(xml).getroot().find('testsuite')
        result.update({key: int(suite.get(key, '0')) for key in ('tests', 'failures', 'errors', 'skipped')})
        nodes = [node for node in suite.findall('testcase') if node.get('name') in (
            'test_unchanged_ape_binary_tag_adoption_survives_main_window_restart',
            'test_id3_restart_compatible_with_both_trees')]
        if len(nodes) == 1:
            case = nodes[0]
            failure = case.find('failure')
            details = '' if failure is None else (failure.text or '') + failure.get('message', '')
            result['target'] = ('TIMEOUT' if 'TimeoutExpired' in details else
                                'FAIL' if failure is not None or case.find('error') is not None else
                                'SKIP' if case.find('skipped') is not None else 'PASS')
            result['target_seconds'] = float(case.get('time', '0'))
    from native_dump import analyze
    analyze(directory)
    result.setdefault('target', 'TIMEOUT' if result['exit_code'] == 124 else 'UNKNOWN')
    if traced:
        logs = list(directory.glob('child-*.jsonl'))
        observations = [json.loads(line) for path in logs for line in path.read_text(encoding='utf-8').splitlines()]
        result['trace_files'] = len(logs)
        result['trace_records'] = len(observations)
        result['trace_installed'] = any(
            row.get('event') == 'observer_installed'
            and row.get('child_source_matches_command') is True for row in observations)
    shared.record(directory, 'result', result)
    print(name, result, flush=True)
    print(log.read_text(encoding='utf-8', errors='replace')[-8000:], flush=True)
    return result


def main():
    repo = HERE.parents[1]
    evidence = Path(os.environ['RUNNER_TEMP']) / 'alo-apev2-timeout'
    evidence.mkdir(parents=True, exist_ok=True)
    results, manifests = [], {}
    error = None
    try:
        shared.require(sys.platform == 'win32', 'Native Windows runner required')
        private = shared.select_volume(evidence)
        shared.native_environment(evidence, private, repo)
        patch = shared.git(repo, 'show', 'HEAD:.ci/apev2-timeout/candidate.patch')
        raw_seal = shared.git(repo, 'show', 'HEAD:.ci/apev2-timeout/sealed.json')
        seal = json.loads(raw_seal)
        shared.require(shared.sha256(patch) == seal['patch_sha256'], 'Patch hash mismatch')
        shared.require(seal['base'] == shared.BASE and seal['base_tree'] == shared.BASE_TREE, 'Wrong baseline')
        tree = shared.prepare_index(repo, private, patch)
        shared.require(tree == seal['tree'], 'Candidate tree mismatch')
        (evidence / 'sealed.json').write_bytes(raw_seal)
        (evidence / 'candidate.patch').write_bytes(patch)
        roots = {side: private / side for side in ('base', 'candidate')}
        for side, root in roots.items():
            root.mkdir()
            tree_id = shared.BASE_TREE if side == 'base' else tree
            rows = shared.tree_manifest(repo, tree_id, root)
            digest = shared.sha256(shared.json_bytes(rows))
            if side == 'candidate':
                shared.require(digest == seal['manifest_sha256'], 'Manifest hash mismatch')
            metadata = {'tree': tree_id, 'manifest_sha256': digest}
            manifests[side] = rows, metadata
            sealed.verify_manifest(root, rows, metadata, evidence, side + '-pre')
        child = extract_child(roots['candidate'], evidence)
        try:
            for row in plan():
                result = stage(row, roots, evidence, private, child)
                results.append(result)
                if result['target'] == 'TIMEOUT' and not result.get('diagnostic_probe'):
                    break
        finally:
            for side, root in roots.items():
                rows, metadata = manifests[side]
                sealed.verify_manifest(root, rows, metadata, evidence, side + '-post')
    except Exception:
        error = traceback.format_exc()
        print(error, flush=True)
        (evidence / 'harness-error.log').write_text(error, encoding='utf-8')
    shared.record(evidence, 'summary', {'error': error, 'stages': results, 'diagnostic_only': True})
    hashes = {p.relative_to(evidence).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(evidence.rglob('*')) if p.is_file() and p.name != 'evidence-sha256.json'}
    shared.record(evidence, 'evidence-sha256', hashes)
    return int(bool(error) or any(row['exit_code'] or row['target'] != 'PASS'
                                 or (row['traced'] and not row.get('trace_installed')) for row in results))


if __name__ == '__main__':
    sys.exit(main())
