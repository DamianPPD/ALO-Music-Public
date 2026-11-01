"""Small selector reusing existing bounded child, classifiers and evidence ZIP."""
from pathlib import Path
import importlib.util,json,os,sys,traceback
spec=importlib.util.spec_from_file_location('i1final_base',Path(__file__).with_name('contract_run.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
R1=[f'.ci/62d/i1final_pss.py::test_readonly_mainwindow_pss[{n}]' for n in (1,2,8)]
base.CASES+=R1

def run():
    base.old.windows_required();base.ci.verify_sources()
    prepared=json.loads((base.ci.EVIDENCE/'prepared.json').read_text())
    report={'scope':'I1 R1 read-only diagnostic, never acceptance','candidate_tree':base.ci.TREE,
        'planned':len(R1),'cases':[],'gate':'OFF','status':'INCOMPLETE'}
    try:
        for index,case in enumerate(R1,91):
            folder=base.OUT/f'{index:03d}-case';folder.mkdir(exist_ok=False)
            profile=folder/'profile';profile.mkdir()
            env=base.old.child_environment(Path(prepared['python']),Path(prepared['bin']))
            env.update(ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),
                APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
            code=base.bounded_child([prepared['python'],'-I','-B',str(Path(__file__).resolve()),
                'pytest-wait',case,str(folder)],env,folder)
            (folder/'exit.txt').write_text(str(code));outcome=base.classify(folder,code)
            item={'case':case,'exit':code,'diagnostic_outcome':outcome,'product_acceptance':False}
            report['cases'].append(item);base.write(base.OUT/'run.json',report)
            base.ci.verify_sources()
            if outcome!='PASS':raise RuntimeError('STOP unexpected diagnostic failure '+case+' / '+outcome)
            summary=json.loads((folder/'r1-summary.json').read_text())
            if summary.get('acceptance') is not False:raise RuntimeError('Diagnostic mislabeled')
            item['observations']=summary;base.audit_synthetic(folder)
        report['status']='DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE'
    except BaseException as error:
        report.update(status='STOP',error=repr(error));raise
    finally:base.ci.verify_sources();base.write(base.OUT/'run.json',report)
    return 0

if __name__=='__main__':
    try:
        code=base.child(sys.argv[2],Path(sys.argv[3])) if sys.argv[1]=='pytest-wait' else {'r1-observe':run,'finish':base.finish}[sys.argv[1]]()
    except BaseException:
        (base.OUT/'i1final-exception.log').write_text(traceback.format_exc());raise
    sys.exit(code)
