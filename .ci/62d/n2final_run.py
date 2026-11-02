"""N2 remaining boundaries and one final regression; existing runner reused."""
from pathlib import Path
import importlib.util,json,os,sys,traceback
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('n2_final_base',HERE/'contract_run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
PREFIX='.ci/62d/n2final_cases.py::'
NEW=[PREFIX+'test_sqlite_delivery_boundaries['+m+']' for m in (
 'valid','read-only','write-denied','locked','unavailable','replace','binding','library-uuid',
 'track-uuid','source-uuid','source-registry-uuid','wal','metadata','read-denied')]+[
 PREFIX+'test_new_interpreter_reopens_without_restoring_authority']+[
 PREFIX+'test_active_qthread_boundaries['+m+']' for m in (
 'success','cancel','close','receiver-destroy','switch','binding','timeout','exception','quit')]+[
 PREFIX+'test_actual_dacl_refuses_pair_and_restores_access['+str(i)+']' for i in (0,1)]+[
 PREFIX+'test_sqlite_connection_lifetimes_and_timings']+[
 PREFIX+'test_actual_readtask_pool['+m+']' for m in ('success','source','cancel','receiver-destroy','reader-error')]+[
 PREFIX+'test_actual_invalid_close_api_and_missing_file',PREFIX+'test_real_ffmpeg_stderr_and_bounded_sample_of_temp_disk']
base.CASES+=NEW

def run(final=False,start=0):
    base.old.windows_required();base.ci.verify_sources()
    prepared=json.loads((base.ci.EVIDENCE/'prepared.json').read_text())
    # N1/I1 accepted separately. No new Semaphore/PSS/WeakMethod experiments.
    n1=[case for case in base.PLAN['selected'] if 'test_native_owner_has_zero_process_handle_delta' in case]
    assert len(n1)==1
    originals=[case for case in base.PLAN['selected'] if case not in n1]
    selected=(originals+NEW if final else NEW)[start:]
    report={'scope':'Native Windows Server2022 / NTFS / CPython3.11.9, NOT Desktop',
      'candidate_tree':base.ci.TREE,'gate':'OFF','status':'INCOMPLETE','selected':len(selected),
      'cases':[],'source_before':True,'source_after':False,'final_regression':final,
      'original':len(originals) if final else 0,'new_boundaries':len(NEW),'historical_7_I1_not_selected':7,
      'historical_N1_not_selected':n1,'reason':'User forbids repeating N1/I1 investigations; preserve accepted evidence'}
    try:
        for i,case in enumerate(selected,201+start):
            folder=base.OUT/f'{i:03d}-case';folder.mkdir(exist_ok=False)
            profile=folder/'profile';profile.mkdir()
            env=base.old.child_environment(Path(prepared['python']),Path(prepared['bin']))
            env.update(ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),
               APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
            code=base.bounded_child([prepared['python'],'-I','-B',str(Path(__file__).resolve()),
               'pytest-wait',case,str(folder)],env,folder)
            (folder/'exit.txt').write_text(str(code));outcome=base.classify(folder,code)
            report['cases'].append({'case':case,'exit':code,'outcome':outcome,
              'category':'protocol-model' if 'test_windows_output_lease_' in case else 'native'})
            base.write(base.OUT/'run.json',report);base.ci.verify_sources()
            if outcome!='PASS':raise RuntimeError('STOP '+case+' / '+outcome)
            base.audit_synthetic(folder)
        report['status']='N2_FINAL_SELECTED_SCOPE_PASS' if final else 'I3_I4_I5_SELECTED_SCOPE_PASS_NOT_FULL_N2'
    except BaseException as error:report.update(status='STOP',error=repr(error));raise
    finally:
        base.ci.verify_sources();report['source_after']=True;base.write(base.OUT/'run.json',report)
    return 0
if __name__=='__main__':
    try:
        if sys.argv[1]=='pytest-wait':code=base.child(sys.argv[2],Path(sys.argv[3]))
        else:code=run(sys.argv[1]=='final',int(sys.argv[2]) if len(sys.argv)>2 else 0)
    except BaseException:
        (base.OUT/'n2final-exception.log').write_text(traceback.format_exc());raise
    sys.exit(code)
