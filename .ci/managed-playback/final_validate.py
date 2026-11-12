"""Complete the exact-tree native managed playback and remaining 34 stages."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'apev2'))
import validate as shared
spec = importlib.util.spec_from_file_location('qt_wrapper', HERE.parent/'qt-cover'/'validate.py')
qt = importlib.util.module_from_spec(spec); spec.loader.exec_module(qt)
qt.DIAGNOSTIC = '.ci/managed-playback'

MANAGED = 'tests/test_managed_playback_v0427.py'
A = MANAGED+'::test_managed_only_restart_can_play_edit_and_read_cover'
B = MANAGED+'::test_stale_cover_or_waveform_generation_is_ignored'


def plan_for(publication, protection):
    # Phase 1 precedes all remaining historical stages. Every final GREEN test
    # comes from the exact sealed tree or an explicitly external supplemental.
    yield 'managed-playback-full', (MANAGED,), None, 320
    for label, targets in (('A', (A,)), ('B', (B,)), ('AB', (A,B)), ('BA', (B,A))):
        for repeat in (1,2):
            yield f'managed-final-{label}-{repeat}', targets, len(targets), 100
    original = list(qt.stages_for(publication, protection))
    for row in original:
        if row[0] == 'managed-cover-read-regressions':
            continue  # Superset is the entire unchanged module, first above.
        yield row
        if row[0] == 'qt-cover-lifecycle':
            for label, targets in (('AB',(A,B)),('BA',(B,A))):
                yield 'managed-after-cover-'+label, ('tests/test_qt_cover_lifecycle_v0427.py',*targets), 21, 240


def main():
    repo = HERE.parents[1]
    evidence = Path(os.environ['RUNNER_TEMP'])/'alo-managed-playback-final'
    evidence.mkdir(exist_ok=True)
    stages = []
    plan = list(plan_for(Path(qt.PUBLICATION), Path(qt.PROTECTION)))
    error = None
    try:
        shared.require(sys.platform == 'win32','Native Windows required')
        private = shared.select_volume(evidence)
        shared.native_environment(evidence,private,repo)
        exe = shutil.which('ffmpeg')
        shared.require(exe and Path(os.environ['ALO_FFMPEG_EXE']).samefile(exe),'Pinned FFmpeg mismatch')
        candidate, rows, expected, supplemental = qt.prepare_candidate(repo,evidence,private)
        qt.verify_manifest(candidate,rows,expected,evidence,'pre-test')
        plan = list(plan_for(*(next(p for p in supplemental if p.name == n)
                               for n in (qt.PUBLICATION,qt.PROTECTION))))
        required = json.loads(shared.git(repo,'show','HEAD:.ci/managed-playback/required-phase2.json'))
        shared.require(len(required)==34 and len(set(required))==34,'Missing historical phase 2 inventory')
        shared.require(all(n in {p[0] for p in plan} for n in required),'Final stage plan omits prior not-run stages')
        shared.record(evidence,'stage-contract',dict(required_previously_not_run=required,
                      exact_tree=expected['tree'],no_product_overlays=True,plan=[p[0] for p in plan]))
        try:
            for entry in plan:
                name,targets,count,timeout=entry
                options = ('-c',str(candidate/'pyproject.toml'),'-p','no:cacheprovider',
                           '--capture=tee-sys','-o','junit_logging=all','-o','junit_log_passing_tests=true')
                suite=shared.pytest_stage(name,'green',candidate,(*options,*targets),evidence,private,timeout=timeout)
                ok=(shared.green_ok(suite) and 'junit_error' not in suite and bool(suite.get('cases'))
                    and (count is None or suite.get('tests')==count)
                    and all(c['result']=='passed' for c in suite.get('cases',[])))
                stages.append((suite|dict(timeout_seconds=timeout,required_count=count),ok))
                # Fail visibly and preserve the real remaining inventory. No
                # automatic retry, weakened timeouts or replacement assertions.
                if not ok:
                    break
        finally:
            qt.verify_manifest(candidate,rows,expected,evidence,'post-test')
            for p,content in supplemental.items():
                shared.require(p.read_bytes()==content,'Supplemental test changed')
    except Exception as exc:
        traceback.print_exc()
        (evidence/'harness-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        error=f'{type(exc).__name__}: {exc}'
    return qt.finish(evidence,plan,stages,error)


if __name__ == '__main__':
    sys.exit(main())
