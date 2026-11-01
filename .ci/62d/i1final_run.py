"""Small selector reusing existing bounded child, classifiers and evidence ZIP."""
from pathlib import Path
import importlib.util,json,os,sys,traceback
spec=importlib.util.spec_from_file_location('i1final_base',Path(__file__).with_name('contract_run.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
R1=[f'.ci/62d/i1final_pss.py::test_readonly_mainwindow_pss[{n}]' for n in (2,)]
GREEN=[f'.ci/62d/i1final_pss.py::test_strict_mainwindow_rounds[{n}]' for n in (1,2,8)]+['.ci/62d/i1final_pss.py::test_deliberate_owned_event_detection']
LIFECYCLE=['.ci/62d/i1final_lifecycle.py::test_multiple_operations_one_window']+[
    f'.ci/62d/i1final_lifecycle.py::test_lifecycle_matrix[{mode}]' for mode in ('D','E','F','G','H')]
TRANSPORT=['tests/test_audio_identity_v0427.py::test_windows_decode_transport_uses_real_ffmpeg_and_preserves_source']+[
    f'tests/test_audio_identity_v0427.py::test_windows_decode_transport_failure_reaps_and_closes[{mode}]'
    for mode in ('stderr','cancel','timeout','spawn-error','tempfile-error')]+[
    f'tests/test_audio_identity_v0427.py::test_windows_decode_transport_reaps_real_child_on_stop[{mode}]'
    for mode in ('cancel','deadline')]
base.CASES+=R1+GREEN+LIFECYCLE+TRANSPORT


def run(verify=False):
    selected=GREEN if verify else R1
    base.old.windows_required();base.ci.verify_sources()
    prepared=json.loads((base.ci.EVIDENCE/'prepared.json').read_text())
    report={'scope':('I1 R1 strict verification, not full I1' if verify else 'I1 R1 read-only diagnostic, never acceptance'),'candidate_tree':base.ci.TREE,
        'planned':len(selected),'cases':[],'gate':'OFF','status':'INCOMPLETE'}
    if verify:
        original=json.loads((base.OUT/'run.json').read_text())
        assert original['status']=='I1_SINGLE_SCOPE_PASS_NOT_N2_COMPLETE'
        base.write(base.OUT/'original-lifecycle-run.json',original)
        report['original_case']=original
    try:
        for index,case in enumerate(selected,91):
            folder=base.OUT/f'{index:03d}-case';folder.mkdir(exist_ok=False)
            profile=folder/'profile';profile.mkdir()
            env=base.old.child_environment(Path(prepared['python']),Path(prepared['bin']))
            env.update(ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),
                APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
            code=base.bounded_child([prepared['python'],'-I','-B',str(Path(__file__).resolve()),
                'pytest-wait',case,str(folder)],env,folder)
            (folder/'exit.txt').write_text(str(code));outcome=base.classify(folder,code)
            item={'case':case,'exit':code,'diagnostic_outcome':outcome,'r1_scope_verification':verify,'product_acceptance':False}
            report['cases'].append(item);base.write(base.OUT/'run.json',report)
            base.ci.verify_sources()
            if outcome!='PASS':raise RuntimeError('STOP unexpected diagnostic failure '+case+' / '+outcome)
            summary=json.loads((folder/'r1-summary.json').read_text())
            if summary.get('acceptance') is not verify:raise RuntimeError('Scope outcome mismatch')
            item['observations']=summary;base.audit_synthetic(folder)
        report['status']='R1_STRICT_SCOPE_PASS_NOT_FULL_I1' if verify else 'DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE'
    except BaseException as error:
        report.update(status='STOP',error=repr(error));raise
    finally:base.ci.verify_sources();base.write(base.OUT/'run.json',report)
    return 0

def run_r2(resume=False):
    # R1 was independently verified from complete raw run41318357029 on this
    # exact product TREE. A/C refer to its strict1/8, not a claim of this run.
    base.old.windows_required();base.ci.verify_sources()
    assert base.ci.TREE=='715aee6d642e0aa79e721a24b66a5c055729d05c'
    prepared=json.loads((base.ci.EVIDENCE/'prepared.json').read_text())
    report={'scope':'I1 remaining B/D/E/F/G/H + exact8 transport tests; native Windows Server2022, NOT Desktop',
        'candidate_tree':base.ci.TREE,'planned':13 if resume else 14,'cases':[],'gate':'OFF','status':'INCOMPLETE',
        'R1_verified_run':41318357029,'A_C_evidence':'strict1/8 in that run, not reexecuted here',
        'source_before':True,'source_after':False}
    try:
        selected=(LIFECYCLE[1:] if resume else LIFECYCLE)+TRANSPORT
        if resume:report['B_verified_run']=41338957532
        for index,case in enumerate(selected,102 if resume else 101):
            folder=base.OUT/f'{index:03d}-case';folder.mkdir(exist_ok=False)
            profile=folder/'profile';profile.mkdir()
            env=base.old.child_environment(Path(prepared['python']),Path(prepared['bin']))
            env.update(ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),
                APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
            code=base.bounded_child([prepared['python'],'-I','-B',str(Path(__file__).resolve()),
                'pytest-wait',case,str(folder)],env,folder)
            (folder/'exit.txt').write_text(str(code));outcome=base.classify(folder,code)
            item={'case':case,'exit':code,'outcome':outcome,
                'kind':'real-Qt-lifecycle' if case in LIFECYCLE else ('transport-model' if 'failure_reaps' in case else 'real-FFmpeg-transport')}
            report['cases'].append(item);base.write(base.OUT/'run.json',report)
            base.ci.verify_sources()
            if outcome!='PASS':raise RuntimeError('STOP '+case+' / '+outcome)
            if case in LIFECYCLE:
                summary=json.loads((folder/'r2-summary.json').read_text())
                assert summary['acceptance'] is True and summary['strict_global_equality'] is True
                item['observations']=summary
            base.audit_synthetic(folder)
        assert len(report['cases'])==report['planned']
        report['status']='I1_REMAINING_SCOPE_PASS_NOT_FULL_N2'
    except BaseException as error:
        report.update(status='STOP',error=repr(error));raise
    finally:
        base.ci.verify_sources();report['source_after']=True;base.write(base.OUT/'run.json',report)
    return 0

if __name__=='__main__':
    try:
        code=base.child(sys.argv[2],Path(sys.argv[3])) if sys.argv[1]=='pytest-wait' else {'r1-observe':run,'r1-verify':lambda:run(True),'r2':run_r2,'r2-resume':lambda:run_r2(True),'finish':base.finish}[sys.argv[1]]()
    except BaseException:
        (base.OUT/'i1final-exception.log').write_text(traceback.format_exc());raise
    sys.exit(code)
