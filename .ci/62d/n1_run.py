"""N1 only: original case023 plus read-only self-process observations."""
from pathlib import Path
import importlib.util,json,os,re,sys,traceback,xml.etree.ElementTree as ET
_spec=importlib.util.spec_from_file_location('n1_contract_base',Path(__file__).with_name('contract_run.py'))
base=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(base)

CASE='tests/test_output_contract_windows_v0427.py::test_native_owner_has_zero_process_handle_delta_after_complete_close'
PROBES=[str(base.HERE/'n1_cases.py')+'::'+name for name in (
    'test_trace_original_eight_cycles','test_attribute_lock_event_and_owner','test_deliberate_owned_event_is_detected')]
GREEN_CASES=[CASE]+[str(base.HERE/'n1_cases.py')+'::'+node for node in (
    *[f'test_fixed_live_helpers_success[{n}]' for n in (1,8,32,64)],
    *[f'test_constructor_churn_equal_helper_types[{n}]' for n in (1,32,64)],
    *[f'test_fixed_live_helpers_failure_or_end[{mode}]' for mode in ('refusal','query-fault','cancel','timeout-zero')],
    'test_deliberate_owned_event_is_detected')]
base.CASES=list(dict.fromkeys([CASE]+PROBES+GREEN_CASES))



def execute(case,index):
    base.old.windows_required();base.ci.verify_sources()
    prepared=json.loads((base.ci.EVIDENCE/'prepared.json').read_text())
    env=base.old.child_environment(Path(prepared['python']),Path(prepared['bin']))
    folder=base.OUT/f'{index:03d}-case';folder.mkdir(exist_ok=False)
    profile=folder/'profile';profile.mkdir()
    env.update(ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),
        APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
    code=base.bounded_child([prepared['python'],'-I','-B',str(Path(__file__).resolve()),
        'pytest-wait',case,str(folder)],env,folder)
    (folder/'exit.txt').write_text(str(code))
    outcome=base.classify(folder,code)
    base.ci.verify_sources()
    return folder,code,outcome


def original():
    folder,code,outcome=execute(CASE,1)
    report={'case':CASE,'exit':code,'raw_outcome':outcome,'status':'STOP','expected_failure_not_masked':True}
    try:
        if outcome=='PASS':
            report['status']='ORIGINAL_PASS_NOT_REPRODUCED'
        elif outcome=='FAIL':
            final=json.loads((folder/'child-final.json').read_text())
            assert final=={'gate':False,'quarantined_owners':0,'pytest_exit':1}
            assert not (folder/'callback-exceptions.jsonl').read_text().strip()
            failures=ET.parse(folder/'result.xml').findall('.//failure');assert len(failures)==1
            text=failures[0].attrib['message']
            assert text.startswith('AssertionError: Native owner handle count did not return after close\n')
            values=re.findall(r'assert (\d+) == (\d+)',text);assert len(values)==1
            before,after=map(int,values[0]);assert before!=after
            report.update(status='ORIGINAL_EQUALITY_FAIL_REPRODUCED',before=before,after=after,delta=after-before,
                original_199_to_201=(before,after)==(199,201))
        else:raise RuntimeError('Unexpected original outcome: '+outcome)
    finally:
        base.write(base.OUT/'n1-original.json',report);base.write(base.OUT/'run.json',report)
    return 0


def probe():
    report={'scope':'N1 observations only; N2 not started','candidate_tree':base.ci.TREE,
        'gate':'OFF','status':'INCOMPLETE','original':json.loads((base.OUT/'n1-original.json').read_text()),'cases':[]}
    try:
        for i,case in enumerate(PROBES,2):
            folder,code,outcome=execute(case,i)
            report['cases'].append({'case':case,'exit':code,'outcome':outcome})
            base.write(base.OUT/'n1-run.json',report)
            if outcome!='PASS':raise RuntimeError('N1 probe STOP '+case+' / '+outcome)
            base.audit_synthetic(folder)
        report['status']='DIAGNOSTIC_COMPLETE_NOT_PRODUCT_PASS'
    except BaseException as exc:
        report.update(status='STOP',error=repr(exc));raise
    finally:
        base.write(base.OUT/'n1-run.json',report);base.write(base.OUT/'run.json',report)
    return 0

def green():
    assert len(GREEN_CASES)==13 and len(set(GREEN_CASES))==13
    report={'scope':'N1 only; no N2/MainWindow','candidate_tree':base.ci.TREE,
        'gate':'OFF','status':'INCOMPLETE','original_red_run':41237840474,'planned':len(GREEN_CASES),'cases':[]}
    try:
        for i,case in enumerate(GREEN_CASES,1):
            folder,code,outcome=execute(case,i)
            report['cases'].append({'case':case,'exit':code,'outcome':outcome})
            base.write(base.OUT/'run.json',report)
            if outcome!='PASS':raise RuntimeError('N1 GREEN STOP '+case+' / '+outcome)
            base.audit_synthetic(folder)
        report['status']='N1_SCOPE_PASS_NOT_N2_OR_PRODUCT_ACCEPTANCE'
    except BaseException as exc:
        report.update(status='STOP',error=repr(exc));raise
    finally:
        base.write(base.OUT/'n1-green.json',report);base.write(base.OUT/'run.json',report)
    return 0

if __name__=='__main__':
    try:
        if sys.argv[1]=='pytest-wait':code=base.child(sys.argv[2],Path(sys.argv[3]))
        else:code={'original':original,'probe':probe,'green':green,'finish':base.finish}[sys.argv[1]]()
    except BaseException:
        (base.OUT/'n1-exception.log').write_text(traceback.format_exc());raise
    sys.exit(code)
