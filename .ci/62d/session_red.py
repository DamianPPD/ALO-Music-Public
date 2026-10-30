"""Bounded native contract RED gate; no product edits and no hidden FAIL."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import traceback
import zipfile
import hashlib

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_fix_diagnostic',HERE/'fix_diagnostic.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
ci=old.ci;ROOT=old.ROOT
OUT=ci.EVIDENCE/'handle-integration-red';OUT.mkdir(exist_ok=True)
CASES=[
 ('tests/test_windows_output_native_v0427.py::test_diagnostic_real_mp3_worker_mainwindow_column_filter_sort[pl]','baseline'),
 ('tests/test_windows_output_native_v0427.py::test_diagnostic_real_mp3_worker_mainwindow_column_filter_sort[en]','baseline'),
 ('.ci/62d/test_short_delivery.py::test_closed_receipt_refresh[pl]','unchanged'),
 ('.ci/62d/test_short_delivery.py::test_closed_receipt_refresh[en]','unchanged'),
 ('.ci/62d/test_short_delivery.py::test_closed_receipt_after_mutation[source]','mutation'),
 ('.ci/62d/test_short_delivery.py::test_closed_receipt_after_mutation[managed]','mutation')]
SENTINEL='CLOSED_RECEIPT_REUSED_AS_CURRENT'


def write(p,data):p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')


class Phases(old.Phases):
    def __init__(self,folder):super().__init__(folder);self.lines={}
    def pytest_runtest_makereport(self,item,call):
        super().pytest_runtest_makereport(item,call)
        self.lines[call.when]=str(call.excinfo.value).split('\n',1)[0] if call.excinfo else None
    def pytest_runtest_logreport(self,report):
        exc,is_assertion=self.exceptions.get(report.when,(None,False))
        with (self.folder/'phases.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome,
                'duration':report.duration,'wasxfail':getattr(report,'wasxfail',None),
                'exception_type':exc,'assertion_error':is_assertion,'exception_firstline':self.lines.get(report.when)})+'\n')


def strict_outcome(folder,code,kind):
    outcome=old.classify(folder,code)
    if kind=='baseline':return 'PASS' if outcome=='PASS' else 'STOP_BASELINE_'+outcome
    if outcome not in ('PASS','FAIL'):return 'STOP_'+outcome
    try:
        state=json.loads((folder/'short-delivery.json').read_text())
        phases=[json.loads(x) for x in (folder/'phases.jsonl').read_text().splitlines()]
        valid=(state.get('complete') is True and not state.get('actor_errors') and state.get('delivery_present') is True
            and state.get('same_guard_material') is True and state.get('guard_at_gui_entry') is True
            and state.get('guard_at_gui_exit') is True and state.get('accepted_confirmed') is True
            and state.get('accepted_needs_update') is True and state.get('accepted_delivery_is_actual') is True
            and state.get('accepted_request_is_actual') is True
            and isinstance(state.get('accepted_operation_id'),str) and bool(state.get('accepted_operation_id'))
            and state.get('closed_before_refresh') is True and state.get('thread_finished') is True
            and state.get('owned_handles_end')==0 and state.get('binding_unchanged') is True
            and state.get('sqlite_integrity')=='ok' and state.get('ack_received') is True
            and state.get('worker_thread')!=state.get('gui_thread'))
        if kind=='unchanged':valid=valid and state.get('actual_bytes_unchanged') is True
        else:valid=valid and state.get('actual_bytes_changed') is True and state.get('size_unchanged') is True and state.get('mtime_restored') is True
        if not valid:return 'STOP_PRECONDITIONS'
        if outcome=='FAIL':
            if (phases[1].get('exception_firstline')!=SENTINEL or state.get('confirmed_after_refresh') is not True
                or state.get('state_after_refresh')!='NEEDS_UPDATE' or state.get('retained_actual_delivery') is not True
                or state.get('retained_actual_request') is not True
                or state.get('retained_operation_id')!=state.get('accepted_operation_id')):
                return 'STOP_UNEXPECTED_ASSERTION'
            return 'FAIL_POLICY_RED'
        return 'PASS' if state.get('confirmed_after_refresh') is False else 'STOP_STATUS_MISMATCH'
    except (OSError,ValueError,KeyError,IndexError):return 'STOP_EVIDENCE'


def pytest_child(case,folder):
    old.windows_required();old.load_product()
    if case not in [x[0] for x in CASES] or folder.resolve().parent!=OUT.resolve():raise ValueError('Unexpected case/path')
    import pytest
    Phases.pytest_runtest_makereport=pytest.hookimpl(tryfirst=True)(Phases.pytest_runtest_makereport)
    return pytest.main([case,'-v','--junitxml='+str(folder/'result.xml'),
        '--basetemp='+str(folder/'synthetic'),'-o','cache_dir='+str(folder/'cache')],plugins=[Phases(folder)])


def run():
    old.windows_required();ci.verify_sources()
    prepared=json.loads((ci.EVIDENCE/'prepared.json').read_text())
    env=old.child_environment(Path(prepared['python']),Path(prepared['bin']))
    status={'scope':'Native Windows Server2022 contract RED; no product patch','gate':'OFF',
        'source_before':True,'source_after':False,'product_changes':0,'cases':[],'status':'INCOMPLETE'}
    try:
        for i,(case,kind) in enumerate(CASES,1):
            folder=OUT/f'{i:02d}-case';folder.mkdir(exist_ok=False)
            profile=folder/'profile';profile.mkdir()
            childenv=dict(env,ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
            cmd=[prepared['python'],'-I','-B',str(Path(__file__).resolve()),'pytest-child',case,str(folder)]
            with (folder/'stdout.log').open('wb') as out,(folder/'stderr.log').open('wb') as err:
                try:code=subprocess.run(cmd,cwd=ROOT,env=childenv,stdout=out,stderr=err,timeout=120).returncode
                except subprocess.TimeoutExpired:code=124
            (folder/'exit.txt').write_text(str(code));outcome=strict_outcome(folder,code,kind)
            status['cases'].append({'case':case,'kind':kind,'exit':code,'outcome':outcome})
            ci.verify_sources();write(OUT/'run.json',status)
            if outcome not in ('PASS','FAIL_POLICY_RED'):raise RuntimeError('STOP: '+outcome)
        status['status']='CONTRACT_RED_CONFIRMED' if any(c['outcome']=='FAIL_POLICY_RED' for c in status['cases']) else 'NO_RED_OBSERVED_REVIEW_REQUIRED'
    except BaseException as exc:
        status['status']='STOP';status['error']=repr(exc);raise
    finally:
        ci.verify_sources();status['source_after']=True;write(OUT/'run.json',status)
    return 1 if status['status']=='CONTRACT_RED_CONFIRMED' else 0


def finish():
    integrity='NOT RUN'
    try:
        if (ci.EVIDENCE/'prepared.json').exists():ci.verify_sources();integrity='PASS'
    except Exception as exc:integrity='FAIL';write(ci.EVIDENCE/'integration-integrity-error.json',{'error':repr(exc)})
    write(ci.EVIDENCE/'INTEGRATION-SUMMARY.json',{'integrity':integrity,'gate':'OFF','run':json.loads((OUT/'run.json').read_text()) if (OUT/'run.json').exists() else {'status':'NOT RUN'}})
    files=[p for p in ci.EVIDENCE.rglob('*') if p.is_file() and not any(x in ('synthetic','profile','cache') for x in p.relative_to(ci.EVIDENCE).parts)
        and p.suffix in ('.json','.jsonl','.log','.xml','.txt','.png') and p.name!='INTEGRATION-MANIFEST.json']
    manifest=[{'path':p.relative_to(ci.EVIDENCE).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    write(ci.EVIDENCE/'INTEGRATION-MANIFEST.json',manifest)
    p=ci.EVIDENCE/'ALO-62D-INTEGRATION-evidence.zip'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files:z.write(f,f.relative_to(ci.EVIDENCE).as_posix())
        z.write(ci.EVIDENCE/'INTEGRATION-MANIFEST.json','INTEGRATION-MANIFEST.json')
    with zipfile.ZipFile(p) as z:
        if z.testzip() is not None:raise RuntimeError('Evidence CRC failure')
        for e in manifest:
            if hashlib.sha256(z.read(e['path'])).hexdigest()!=e['sha256']:raise RuntimeError('Manifest mismatch')
    Path(str(p)+'.sha256.txt').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n')
    return 2 if integrity=='FAIL' else 0


if __name__=='__main__':
    try:code=pytest_child(sys.argv[2],Path(sys.argv[3])) if sys.argv[1]=='pytest-child' else {'run':run,'finish':finish}[sys.argv[1]]()
    except BaseException:
        (OUT/'exception.log').write_text(traceback.format_exc());raise
    sys.exit(code)
