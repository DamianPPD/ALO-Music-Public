"""Reuse existing CI provenance/phases; bounded selected contract cases only."""
from pathlib import Path
from datetime import datetime,timezone
import ctypes as C
import hashlib,importlib.util,json,os,sqlite3,subprocess,sys,threading,traceback,zipfile

HERE=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
old=module('original_fix_diagnostic',HERE/'fix_diagnostic.py')
ci=old.ci;ROOT=old.ROOT
job_types=module('original_handle_job',HERE/'handle_probe.py')
OUT=ci.EVIDENCE/'contract';OUT.mkdir(exist_ok=True)
PLAN=json.loads((HERE/'contract-cases.json').read_text())
CASES=PLAN['selected']

def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def bounded_child(cmd,env,folder):
    """Existing kill-on-close Job Object / GO gate, generalized to pytest."""
    k=C.WinDLL('kernel32',use_last_error=True);ptr=C.c_void_p;u32=C.c_uint32;boolean=C.c_int32
    def bind(name,args,result):
        f=getattr(k,name);f.argtypes=args;f.restype=result;return f
    create=bind('CreateJobObjectW',[ptr,C.c_wchar_p],ptr)
    setinfo=bind('SetInformationJobObject',[ptr,C.c_int32,ptr,u32],boolean)
    assign=bind('AssignProcessToJobObject',[ptr,ptr],boolean)
    close=bind('CloseHandle',[ptr],boolean)
    job=create(None,None);p=None
    if not job:raise C.WinError(C.get_last_error())
    try:
        limits=job_types.EXTENDED_LIMIT();limits.BasicLimitInformation.LimitFlags=0x2000
        assert C.sizeof(limits)==144
        if not setinfo(job,9,C.byref(limits),C.sizeof(limits)):raise C.WinError(C.get_last_error())
        with (folder/'stdout.log').open('wb') as out,(folder/'stderr.log').open('wb') as err:
            p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=out,stderr=err,text=True)
            if not assign(job,int(p._handle)):raise C.WinError(C.get_last_error())
            write(folder/'job.json',{'kill_on_close':True,'pid':p.pid,'assigned_before_GO':True,
                'timeout_seconds':180,'scope':'only this test child and its descendants'})
            try:p.communicate(input='GO\n',timeout=180);code=p.returncode
            except subprocess.TimeoutExpired:code=124
        return code
    finally:
        try:
            if not close(job):raise C.WinError(C.get_last_error())
        finally:
            if p is not None:
                if p.poll() is None:p.terminate()
                p.wait(timeout=10)
                if p.stdin and not p.stdin.closed:p.stdin.close()
                p._handle.Close()

def install_callback_observer(folder):
    errors=folder/'callback-exceptions.jsonl';errors.write_text('')
    def record_error(kind,typ,value,tb):
        with errors.open('a',encoding='utf-8') as f:
            f.write(json.dumps({'kind':kind,'type':typ.__module__+'.'+typ.__qualname__,
                'message':str(value),'traceback':''.join(traceback.format_exception(typ,value,tb))})+'\n')
    hook=sys.excepthook;unraisable=sys.unraisablehook;threadhook=threading.excepthook
    def qt_error(typ,value,tb):record_error('sys.excepthook',typ,value,tb);hook(typ,value,tb)
    def unraised(args):
        record_error('sys.unraisablehook',args.exc_type,args.exc_value,args.exc_traceback);unraisable(args)
    def thread_error(args):
        record_error('threading.excepthook',args.exc_type,args.exc_value,args.exc_traceback);threadhook(args)
    sys.excepthook=qt_error;sys.unraisablehook=unraised;threading.excepthook=thread_error
    return errors

def child(case,folder):
    if sys.stdin.readline()!='GO\n':raise RuntimeError('No parent Job Object authorization')
    if case not in CASES or folder.resolve().parent!=OUT.resolve():raise ValueError('Unapproved case/path')
    old.windows_required();native=old.load_product()
    errors=install_callback_observer(folder)
    import pytest
    old.Phases.pytest_runtest_makereport=pytest.hookimpl(tryfirst=True)(old.Phases.pytest_runtest_makereport)
    code=pytest.main([case,'-v','--junitxml='+str(folder/'result.xml'),
        '--basetemp='+str(folder/'synthetic'),'-o','cache_dir='+str(folder/'cache'),
        '-W','error::pytest.PytestUnhandledThreadExceptionWarning',
        '-W','error::pytest.PytestUnraisableExceptionWarning'],plugins=[old.Phases(folder)])
    # Keep hooks installed through interpreter teardown. Parent checks the file
    # after process exit too, so late Qt/Python exceptions cannot become PASS.
    ci.verify_sources()
    final={'gate':native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED,
        'quarantined_owners':0,'pytest_exit':int(code)}
    from audio_library_organizer.safety import windows_output_lease as lease_module
    with lease_module._QUARANTINE_LOCK:final['quarantined_owners']=len(lease_module._UNCERTAIN_OWNERS)
    write(folder/'child-final.json',final)
    if final['gate'] is not False or final['quarantined_owners'] or errors.read_text().strip():return 2
    return int(code)

def audit_synthetic(folder):
    result=[]
    for db in (folder/'synthetic').rglob('*.sqlite3'):
        conn=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True,timeout=0)
        try:
            integrity=conn.execute('PRAGMA integrity_check').fetchall()
            foreign=conn.execute('PRAGMA foreign_key_check').fetchall()
        finally:conn.close()
        result.append({'path':str(db.relative_to(folder)),'integrity':integrity,'foreign_key_violations':foreign})
        if integrity!=[('ok',)] or foreign:raise RuntimeError('Synthetic SQLite integrity failure')
    write(folder/'sqlite-audit.json',result)

def classify(folder,code):
    outcome=old.classify(folder,code)
    if outcome!='PASS':return outcome
    errors=folder/'callback-exceptions.jsonl';final=folder/'child-final.json'
    if not errors.exists() or not final.exists():return 'MISSING_CHILD_FINAL_EVIDENCE'
    if errors.read_text().strip():return 'CALLBACK_ERROR'
    state=json.loads(final.read_text())
    if state.get('gate') is not False or state.get('quarantined_owners')!=0 or state.get('pytest_exit')!=0:
        return 'UNSAFE_CHILD_FINAL'
    return 'PASS'

def run():
    old.windows_required();ci.verify_sources()
    prepared=json.loads((ci.EVIDENCE/'prepared.json').read_text())
    env=old.child_environment(Path(prepared['python']),Path(prepared['bin']))
    assert len(CASES)==83 and len(set(CASES))==len(CASES)
    status={'scope':'Native Windows Server 2022. NOT Windows10/11 Desktop.',
        'candidate_tree':ci.TREE,'gate':'OFF','planned':len(CASES),'not_scheduled':PLAN['not_scheduled'],
        'source_before':True,'source_after':False,'cases':[],'status':'INCOMPLETE'}
    try:
        for i,case in enumerate(CASES,1):
            folder=OUT/f'{i:03d}-case';folder.mkdir(exist_ok=False)
            profile=folder/'profile';profile.mkdir()
            childenv=dict(env,ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),
                APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
            cmd=[prepared['python'],'-I','-B',str(Path(__file__).resolve()),'pytest-wait',case,str(folder)]
            code=bounded_child(cmd,childenv,folder)
            (folder/'exit.txt').write_text(str(code))
            outcome=classify(folder,code)
            item={'case':case,'category':'protocol-model' if 'test_windows_output_lease_' in case else 'native',
                'exit':code,'outcome':outcome}
            status['cases'].append(item);write(OUT/'run.json',status)
            ci.verify_sources()
            if outcome!='PASS':raise RuntimeError('STOP: '+case+' / '+outcome)
            audit_synthetic(folder)
        status['status']='CONTRACT_WINDOWS_SERVER_PASS'
    except BaseException as exc:
        status['status']='STOP';status['error']=repr(exc);raise
    finally:
        ci.verify_sources();status['source_after']=True;write(OUT/'run.json',status)
    return 0

def finish():
    integrity='NOT RUN'
    try:
        if (ci.EVIDENCE/'prepared.json').exists():ci.verify_sources();integrity='PASS'
    except Exception as exc:
        integrity='FAIL';write(ci.EVIDENCE/'contract-integrity-error.json',{'error':repr(exc)})
    write(ci.EVIDENCE/'CONTRACT-SUMMARY.json',{'integrity':integrity,'gate':'OFF',
        'run':json.loads((OUT/'run.json').read_text()) if (OUT/'run.json').exists() else {'status':'NOT RUN'}})
    files=[p for p in ci.EVIDENCE.rglob('*') if p.is_file()
        and not any(x in ('synthetic','profile','cache') for x in p.relative_to(ci.EVIDENCE).parts)
        and p.suffix in ('.json','.jsonl','.log','.xml','.txt','.png') and p.name!='CONTRACT-MANIFEST.json']
    manifest=[{'path':p.relative_to(ci.EVIDENCE).as_posix(),'bytes':p.stat().st_size,
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    write(ci.EVIDENCE/'CONTRACT-MANIFEST.json',manifest)
    path=ci.EVIDENCE/'ALO-62D-CONTRACT-evidence.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(ci.EVIDENCE).as_posix())
        z.write(ci.EVIDENCE/'CONTRACT-MANIFEST.json','CONTRACT-MANIFEST.json')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise RuntimeError('Evidence CRC failure')
        for f in manifest:
            if hashlib.sha256(z.read(f['path'])).hexdigest()!=f['sha256']:raise RuntimeError('Evidence manifest mismatch')
    Path(str(path)+'.sha256.txt').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
    return 2 if integrity=='FAIL' else 0

if __name__=='__main__':
    try:
        code=child(sys.argv[2],Path(sys.argv[3])) if sys.argv[1]=='pytest-wait' else {'run':run,'finish':finish}[sys.argv[1]]()
    except BaseException:
        (OUT/'exception.log').write_text(traceback.format_exc());raise
    sys.exit(code)
