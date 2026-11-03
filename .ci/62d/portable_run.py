"""Offline adapter for the existing N2 runner. Product and assertions unchanged."""
from pathlib import Path
import os,sys,json,hashlib,struct,importlib.util,subprocess,tempfile,traceback,zipfile,uuid
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;APP=HERE.parents[1];PACKAGE=APP.parent
TREE='bea8fc4fbc128fbfd99f2c6c1a3d0b62493844ee'

def select_continuation(cases):
    assert len(cases)==145 and len({r['case']for r in cases})==145
    assert cases[38]['case'].endswith('column_filter_sort[en]')
    return cases[38:]

def safe_isolated_timeout(row,proof,integrity_ok,observers_ok):
    return (row.get('exit')==124 and row.get('raw_outcome')=='STOP_PROCESS'
        and all(proof.get(k)is True for k in('job_closed','process_reaped','kill_on_close'))
        and integrity_ok is True and observers_ok is True)

def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,default=str)+'\n',encoding='utf-8')
def load():
    spec=importlib.util.spec_from_file_location('portable_n2',HERE/'n2final_run.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n);return n

def verify_package():
    manifest=json.loads((PACKAGE/'PACKAGE-MANIFEST.json').read_text())
    for f in manifest:
        p=PACKAGE/f['path'];assert p.resolve().is_relative_to(PACKAGE.resolve())
        b=p.read_bytes();assert len(b)==f['bytes'] and hashlib.sha256(b).hexdigest()==f['sha256'],'Changed package file: '+f['path']
    actual={p.relative_to(PACKAGE).as_posix()for folder in('runtime','app','tools')for p in(PACKAGE/folder).rglob('*')if p.is_file()}
    expected={f['path']for f in manifest if f['path'].split('/')[0]in('runtime','app','tools')}
    assert actual==expected,'Unexpected files in immutable package'
    return len(manifest)

def environment(work):
    import ctypes as C
    class VERSION(C.Structure):
        _fields_=[('size',C.c_uint32),('major',C.c_uint32),('minor',C.c_uint32),('build',C.c_uint32),('platform',C.c_uint32),('csd',C.c_wchar*128),('spmajor',C.c_uint16),('spminor',C.c_uint16),('suite',C.c_uint16),('product_type',C.c_ubyte),('reserved',C.c_ubyte)]
    v=VERSION();v.size=C.sizeof(v);rtl=C.WinDLL('ntdll').RtlGetVersion;rtl.argtypes=[C.POINTER(VERSION)];rtl.restype=C.c_long;assert rtl(C.byref(v))==0
    k=C.WinDLL('kernel32',use_last_error=True);fs=C.create_unicode_buffer(64)
    info=k.GetVolumeInformationW;info.argtypes=[C.c_wchar_p,C.c_void_p,C.c_uint32,C.c_void_p,C.c_void_p,C.c_void_p,C.c_wchar_p,C.c_uint32];info.restype=C.c_int
    assert info(Path(work).anchor,None,0,None,None,None,fs,64)
    from PySide6.QtCore import qVersion
    import importlib.metadata as m
    return dict(windows=dict(major=v.major,minor=v.minor,build=v.build,product_type=v.product_type,scope='Windows Server'if v.product_type!=1 else 'Windows 11'if v.build>=22000 else 'Windows 10'),filesystem=fs.value,
        python=sys.version,python_relative='runtime/python.exe',architecture=struct.calcsize('P')*8,qt=qVersion(),tree=TREE,
        versions={n:m.version(n)for n in ['PySide6','shiboken6','pytest','mutagen','Pillow','requests','numpy','soundfile']})

def prerequisites(n,work):
    blocked={};p=work/'prerequisites';(p/'synthetic').mkdir(parents=True)
    path=p/'synthetic/only-owned.bin';path.write_bytes(b'private synthetic prerequisite')
    before=os.environ.get('ALO_62D_EVIDENCE');os.environ['ALO_62D_EVIDENCE']=str(p)
    try:
        from n2final_dacl import deny
        with deny(path,1):
            try:path.read_bytes()
            except PermissionError:pass
            else:raise RuntimeError('DACL did not deny owned synthetic read')
        assert path.read_bytes()==b'private synthetic prerequisite'
        write(p/'dacl.json',{'status':'PASS','synthetic_only':True,'restored':True})
    except (OSError,RuntimeError)as e:
        # A restore failure is not silently downgraded.
        try:assert path.read_bytes()==b'private synthetic prerequisite'
        except Exception:raise RuntimeError('Cannot verify restored synthetic DACL')from e
        write(p/'dacl.json',{'status':'BLOCKED','reason':str(e)})
        for case in json.loads((HERE/'cases.json').read_text())['cases']:
            node=case['case']
            if any(t in node for t in ('test_actual_dacl_refuses','test_sqlite_delivery_boundaries[write-denied]','test_sqlite_delivery_boundaries[read-denied]')):blocked[node]='DACL prerequisite unavailable'
    finally:
        if before is None:os.environ.pop('ALO_62D_EVIDENCE',None)
        else:os.environ['ALO_62D_EVIDENCE']=before
    target=p/'synthetic/junction-target';target.mkdir();link=p/'synthetic/junction-link'
    try:
        assert not any(c in str(p)for c in '&|<>"%^!\r\n'),'Shell-sensitive path'
        cmd=Path(os.environ['SystemRoot'])/'System32/cmd.exe'
        result=subprocess.run([str(cmd),'/d','/c','mklink','/J',str(link),str(target)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError('Junction unavailable: '+result.stderr)
        os.rmdir(link)
        write(p/'junction.json',{'status':'PASS','synthetic_only':True,'removed_link_only':True})
    except (OSError,RuntimeError,AssertionError)as e:
        blocked['tests/test_output_contract_windows_v0427.py::test_real_junction_is_refused_without_opening_the_target_leaf']=str(e)
        write(p/'junction.json',{'status':'BLOCKED','reason':str(e)})
    return blocked

def archive_results(work,destination,report,redactions):
    write(work/'final-summary.json',report)
    records=[];path=destination/'ALO-Music-Windows11-WYNIKI-KONTYNUACJA.zip'
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED)as z:
        for p in sorted(work.rglob('*')):
            rel=p.relative_to(work)
            if not p.is_file()or any(t in rel.parts for t in('synthetic','profile','cache','temp'))or p.suffix not in('.json','.jsonl','.xml','.log','.txt','.png'):continue
            b=p.read_bytes()
            if p.suffix!='.png':
                s=b.decode('utf-8',errors='replace')
                for source,replacement in sorted(redactions,key=lambda x:len(x[0]),reverse=True):
                    if source:
                        for form in (source,source.replace('\\','/')):
                            s=s.replace(json.dumps(form)[1:-1],replacement).replace(form,replacement)
                b=s.encode('utf-8')
            name=rel.as_posix();z.writestr(name,b);records.append(dict(path=name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
        z.writestr('MANIFEST.json',json.dumps(records,indent=2))
    with zipfile.ZipFile(path)as z:
        assert z.testzip()is None
        for f in records:assert hashlib.sha256(z.read(f['path'])).hexdigest()==f['sha256']
    Path(str(path)+'.sha256.txt').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
    return path

def main():
    from portable_policy import install,summary_status
    original_profile=os.environ.get('USERPROFILE','')
    assert sys.platform=='win32'and struct.calcsize('P')==8
    assert Path(sys.executable).resolve()==(PACKAGE/'runtime/python.exe').resolve()
    work=Path(tempfile.mkdtemp(prefix='ALO-W11-')).resolve()
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    destination=PACKAGE/'wyniki'/stamp;destination.mkdir(parents=True,exist_ok=False)
    # Parent may write only this new workspace or this newly created result directory.
    # Results are created after tests; no unknown contents are removed.
    original_out=os.environ.get('RUNNER_TEMP');os.environ['RUNNER_TEMP']=str(work)
    os.environ.update(TEMP=str(work),TMP=str(work),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    planned=json.loads((HERE/'cases.json').read_text());all_cases=planned['cases'];cases=select_continuation(all_cases)
    mode=os.environ.get('ALO_TIMEOUT39_CI_TARGET')if os.environ.get('ALO_PACKAGE_CI_SMOKE')=='1'else None
    if mode is not None:
        assert mode in('pl','en');cases=[all_cases[37 if mode=='pl'else 38]]
    rows=[dict(c,outcome='NOT RUN',exit=None)for c in cases]
    report=dict(status='STOP',tree=TREE,planned=len(rows),selected=0,executed=0,cases=rows,gate=False,source_before=False,source_after=False,
        scope='CI_DIAGNOSTIC_'+mode if mode else 'WINDOWS11_CONTINUATION_39_TO_145',historical_not_rerun=38,
        historical_archive_sha256='18b8fe411ed1a175f4a4acd62337b2939dc23adbe717d10addbbd3c4a80733a8')
    class Tee:
        def __init__(self,stream,file):self.stream=stream;self.file=file
        def write(self,text):self.file.write(text);self.file.flush();return self.stream.write(text)
        def flush(self):self.file.flush();self.stream.flush()
        def __getattr__(self,name):return getattr(self.stream,name)
    stdout=(work/'runner.stdout.log').open('w',encoding='utf-8');stderr=(work/'runner.stderr.log').open('w',encoding='utf-8')
    sys.stdout=Tee(sys.stdout,stdout);sys.stderr=Tee(sys.stderr,stderr)
    n=None
    try:
        count=verify_package();assert sys.version_info[:3]==(3,11,9)
        sys.path[:0]=[str(APP/'src'),str(APP/'tests'),str(HERE)]
        n=load();n.base.ci.verify_sources();report['source_before']=True
        envinfo=environment(work);write(work/'environment.json',envinfo)
        assert envinfo['windows']['build']>=19041 and envinfo['filesystem']=='NTFS' and envinfo['qt']=='6.10.3'
        # Confine parent I/O too, allowing only its private result directory as a
        # second owned root during packaging (not while product tests execute).
        install(PACKAGE,work,output=destination)
        blocked=prerequisites(n,work)
        for row in rows:
            if row['case']in blocked:row.update(outcome='BLOCKED',reason=blocked[row['case']])
        resumed_nodes={r['case']for r in rows}
        # Retain the unexecuted prefix in the original runner's list so its
        # start=38 offset remains exact even when a historical junction probe
        # is unavailable. Only selected continuation cases can be filtered.
        n.base.PLAN['selected']=[c for c in n.base.PLAN['selected']if c not in blocked or c not in resumed_nodes]
        n.NEW=[c for c in n.NEW if c not in blocked];n.ADDED=[c for c in n.ADDED if c not in blocked];n.TRANSPORT=[c for c in n.TRANSPORT if c not in blocked]
        start=38
        if mode:
            target=cases[0]['case'];n1=[c for c in n.base.PLAN['selected']if 'test_native_owner_has_zero_process_handle_delta'in c]
            assert len(n1)==1;n.base.PLAN['selected']=n1+[target];n.NEW=[];n.ADDED=[];n.TRANSPORT=[];start=0
        selected=[r['case']for r in rows if r['case']not in blocked];report['selected']=len(selected)
        write(n.base.ci.EVIDENCE/'prepared.json',{'python':str(PACKAGE/'runtime/python.exe'),'bin':str(PACKAGE/'tools'),'candidate_tree':TREE})
        bound=n.base.bounded_child;classify=n.base.classify
        def bounded(cmd,env,folder):
            temp=folder/'temp';temp.mkdir();env.update(ALO_PORTABLE_WORK=str(work),ALO_PORTABLE_CASE=str(folder),ALO_PORTABLE_PROFILE=str(folder/'profile'),TEMP=str(temp),TMP=str(temp),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
            cmd=list(cmd);cmd[3]=str(Path(__file__).resolve())
            return bound(cmd,env,folder)
        def classified(folder,code):
            outcome=classify(folder,code)
            for log in work.glob('isolation-*.jsonl'):
                for line in log.read_text().splitlines():
                    event=json.loads(line)
                    if event['kind']=='VIOLATION' or(event['kind']=='Qt.startup'and event['type']in(2,3)):
                        print('ISOLATION/Qt EVIDENCE:',json.dumps(event),flush=True)
                        outcome='ISOLATION_OR_QT_ERROR'
            i=int(folder.name.split('-')[0])-201-start;node=selected[i]
            row=next(r for r in rows if r['case']==node)
            row.update(outcome=outcome if outcome in('PASS','FAIL','ERROR','SKIP')else'ERROR',raw_outcome=outcome,exit=code)
            if code==124:row['failure_kind']='TIMEOUT'
            elif code<0 or code>0x7fffffff:row['failure_kind']='CRASH'
            print(f'{i+1:03d}/{len(selected)} {outcome}  {node}',flush=True)
            return outcome
        original_write=n.base.write
        def factual_write(path,value):
            if isinstance(value,dict)and 'scope'in value:
                value=dict(value,original_runner_scope=value['scope'],scope=envinfo['windows']['scope']+' / native x64 / NTFS / CPython3.11.9')
            return original_write(path,value)
        n.base.write=factual_write
        n.base.bounded_child=bounded;n.base.classify=classified
        sys.argv=[str(Path(__file__).resolve()),'final']
        try:n.run(final=True,start=start)
        except RuntimeError:
            first=rows[0];folder=n.base.OUT/'239-case'
            if mode or first.get('exit')!=124 or any(r['exit']is not None for r in rows[1:]):raise
            proof=json.loads((folder/'process-final.json').read_text())if(folder/'process-final.json').is_file()else{}
            n.base.ci.verify_sources();verify_package()
            callbacks=folder/'callback-exceptions.jsonl'
            messages=folder/'qt-messages.jsonl'
            qt_ok=messages.is_file()and not any(json.loads(line).get('lifecycle_error')for line in messages.read_text().splitlines())
            allowed=safe_isolated_timeout(first,proof,True,callbacks.is_file()and not callbacks.read_text().strip()and qt_ok)
            write(work/'timeout-isolation-decision.json',{'continue_remaining_106':allowed,'proof':proof,'first_case_status':'ERROR/TIMEOUT — NOT PASS'})
            if not allowed:raise
            (n.base.OUT/'run-EN-timeout-before-resume.json').write_bytes((n.base.OUT/'run.json').read_bytes())
            print('EN39 TIMEOUT zachowany. JobObject zamkniety, proces rozliczony; uruchamiam pozostale 106.',flush=True)
            n.run(final=True,start=39)
        report['status']=summary_status([r['outcome']for r in rows],len(rows))
        if rows[0].get('exit')==124 and all(r['outcome']=='PASS'for r in rows[1:]):report['status']='CONTINUATION_COMPLETE_WITH_TIMEOUT'
    except BaseException as e:
        report['error']=type(e).__name__+': '+str(e);write(work/'runner-error.json',{'traceback':traceback.format_exc()})
        print('STOP:',e,flush=True)
    finally:
        if n:
            try:n.base.ci.verify_sources();report['source_after']=True
            except BaseException as e:report.update(status='STOP',source_error=str(e))
        try:verify_package();report['package_after']=True
        except BaseException as e:report.update(status='STOP',package_after=False,package_error=str(e))
        report['executed']=sum(r['exit']is not None for r in rows)
        report['counts']={name:sum(r['outcome']==name for r in rows)for name in('PASS','FAIL','ERROR','SKIP','BLOCKED','NOT RUN')}
        report['phases_expected_for_PASS']=3*report['counts']['PASS']
        report['not_scheduled_historical']=n.base.PLAN['not_scheduled']if n else []
        report['privacy']='Only generated audio/SQLite. Known user/package/workspace path prefixes redacted in exported text; raw local logs preserved.'
        redactions=[(str(work),'WORKSPACE'),(str(PACKAGE),'PACKAGE'),(original_profile,'USER_PROFILE')]
        try:
            import socket
            host=socket.gethostname();redactions.append((host,'TEST-HOST'))
        except OSError:pass
        print('SUMMARY',json.dumps(report['counts']),report['status'],flush=True)
        result=archive_results(work,destination,report,redactions)
        print('SUMMARY',json.dumps(report['counts']),report['status'],flush=True)
        print('RESULT_ZIP='+str(result),flush=True)
        print('Testy zakończone. Prześlij ZIP z wynikami do ChatGPT.',flush=True)
    return 0 if report['status']=='PASS'else 2

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='pytest-wait':
        sys.path[:0]=[str(APP/'src'),str(APP/'tests'),str(HERE)];n=load()
        if 'test_diagnostic_real_mp3_worker_mainwindow_column_filter_sort['in sys.argv[2]:
            from timeout39_observer import instrument
            instrument(n,Path(sys.argv[3]))
        sys.exit(n.base.child(sys.argv[2],Path(sys.argv[3])))
    sys.exit(main())
