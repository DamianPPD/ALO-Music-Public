"""Offline portable entry point. The product and 42-case runner are unchanged."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import ctypes
import hashlib
import importlib
import importlib.util
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import traceback
import threading
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile

TREE='42d7476ff4a740008ddbda3fbb82440ddae163ef'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def relative(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or any(x in name for x in ('\\',':')) or any(x in ('','..','.') for x in name.split('/')):
        raise ValueError('Unsafe package relative path')
    return Path(*p.parts)


def redirected(path):
    return path.is_symlink() or bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)


def verify_package(root):
    manifest=json.loads((root/'MANIFEST.json').read_text(encoding='utf-8'))
    names=set()
    for f in manifest['files']:
        rel=relative(f['path']); key=f['path'].casefold()
        if key in names:raise ValueError('Duplicate package path')
        names.add(key); path=root/rel
        if any(redirected(root/Path(*rel.parts[:i])) for i in range(1,len(rel.parts)+1)) or not path.is_file():raise ValueError('Missing or redirected package file: '+f['path'])
        if path.stat().st_size!=f['bytes'] or digest(path)!=f['sha256']:
            raise ValueError('Package hash mismatch: '+f['path'])
    pending=[root]
    while pending:
        directory=pending.pop()
        for path in directory.iterdir():
            r=path.relative_to(root)
            if redirected(path):raise ValueError('Unexpected reparse point or symbolic link')
            if r.parts[0]=='wyniki':continue
            if path.is_dir():pending.append(path)
            elif path.is_file() and r.as_posix()!='MANIFEST.json' and r.as_posix().casefold() not in names:
                raise ValueError('Unlisted package file: '+r.as_posix())
    return manifest


def environment(root,session):
    # Private profile and bounded PATH. No GitHub/PAT/SSH/PYTHONPATH variables.
    win=Path(os.environ['SystemRoot'])
    profile=session/'profil'; profile.mkdir()
    for n in ('appdata','localappdata','temp'):(profile/n).mkdir()
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','OS'}}
    env.update(USERPROFILE=str(profile),APPDATA=str(profile/'appdata'),LOCALAPPDATA=str(profile/'localappdata'),TEMP=str(profile/'temp'),TMP=str(profile/'temp'))
    env['PATH']=os.pathsep.join(map(str,[root/'narzedzia/ffmpeg',root/'runtime',win/'System32',win]))
    env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',QT_QPA_PLATFORM='windows',PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1')
    return env


def probe(root):
    if sys.platform!='win32' or sys.version_info[:3]!=(3,11,9) or struct.calcsize('P')!=8:
        raise ValueError('Wymagany natywny Windows x64 i prywatny CPython 3.11.9')
    if Path(sys.executable).resolve()!=root/'runtime/python.exe' or not sys.flags.isolated:
        raise ValueError('Interpreter is not the isolated bundled interpreter')
    for item in sys.path:
        if item and not Path(item).resolve().is_relative_to(root/'runtime'):
            raise ValueError('External Python search path')
    if importlib.util.find_spec('pip') is not None:raise ValueError('Unexpected package installer')
    if not getattr(sys,'_alo_portable_offline_audit',False):raise ValueError('Missing offline network protection')
    import socket
    try:socket.getaddrinfo('invalid.example',443)
    except PermissionError:pass
    else:raise ValueError('Python network protection did not refuse DNS')
    version=sys.getwindowsversion()
    if version.major!=10 or version.build<17763:raise ValueError('Windows 10 1809+, Windows 11, or Server 2022 required')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetVolumePathNameW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint]
    kernel.GetDriveTypeW.argtypes=[ctypes.c_wchar_p]
    kernel.GetVolumeInformationW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint]
    vol=ctypes.create_unicode_buffer(32768);fs=ctypes.create_unicode_buffer(256)
    for location in (root,Path.cwd()):
        if str(location).startswith('\\\\'):raise ValueError('UNC/network package location is not supported')
        if not kernel.GetVolumePathNameW(str(location),vol,len(vol)):raise ctypes.WinError(ctypes.get_last_error())
        if kernel.GetDriveTypeW(vol.value)!=3:raise ValueError('Local fixed volume required')
        if not kernel.GetVolumeInformationW(vol.value,None,0,None,None,None,fs,len(fs)):raise ctypes.WinError(ctypes.get_last_error())
        if fs.value!='NTFS':raise ValueError('Local NTFS required')
    names={'PySide6':'6.10.3','PySide6_Essentials':'6.10.3','PySide6_Addons':'6.10.3','shiboken6':'6.10.3','pytest':'8.4.2','mutagen':'1.47.0','Pillow':'11.3.0','requests':'2.32.5','numpy':'2.2.6','soundfile':'0.13.1','cffi':'1.17.1'}
    origins={}
    for name,wanted in names.items():
        dist=importlib.metadata.distribution(name)
        if dist.version!=wanted or not Path(dist.locate_file('')).resolve().is_relative_to(root/'runtime'):
            raise ValueError('External or wrong package: '+name)
    for name in ('PySide6.QtCore','PySide6.QtWidgets','PySide6.QtMultimedia','shiboken6','pytest','mutagen','PIL','requests','numpy','soundfile','_cffi_backend'):
        module=importlib.import_module(name);path=Path(module.__file__).resolve()
        if not path.is_relative_to(root/'runtime'):raise ValueError('External imported module: '+name)
        origins[name]=str(path.relative_to(root))
    from PySide6.QtCore import qVersion
    if qVersion()!='6.10.3':raise ValueError('Wrong native Qt version')
    kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];kernel.GetModuleHandleW.restype=ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint]
    native={}
    for name in ('Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','Qt6Multimedia.dll'):
        handle=kernel.GetModuleHandleW(name);buf=ctypes.create_unicode_buffer(32768)
        if not handle or not kernel.GetModuleFileNameW(handle,buf,len(buf)):raise ValueError('Missing native Qt module: '+name)
        path=Path(buf.value).resolve()
        if not path.is_relative_to(root/'runtime'):raise ValueError('External Qt DLL: '+name)
        native[name]=str(path.relative_to(root))
    return {'windows_version':platform.win32_ver(),'build':version.build,'product_type':version.product_type,'scope':'Windows Server' if version.product_type!=1 else 'Windows Desktop',
        'architecture':'x64','filesystem':fs.value,'python':sys.version,'python_executable':str(Path(sys.executable).relative_to(root)),
        'prefix_local':Path(sys.prefix).resolve()==root/'runtime','isolated':sys.flags.isolated,'versions':names,'qt':qVersion(),'origins':origins,'native_modules':native,
        'pip_available':False,'python_network':'denied by bundled sitecustomize audit hook','candidate_tree':TREE,'product_gate':'OFF'}


def summarize(run,directory):
    cases=run['cases'];planned=run.get('planned_cases',[])
    if len(planned)!=42 or len(cases)>42 or run['tests_executed']!=len(cases):raise ValueError('Incomplete 42-case collection evidence')
    result={'collected':42,'executed':len(cases),'passed':0,'failed':0,'errors':0,'skipped':0,'not_run':42-len(cases),'cases':[]}
    for i,case in enumerate(cases,1):
        xml=directory/(f'{i:02d}-case')/'result.xml'
        nodes=list(ET.parse(xml).iter('testcase'))
        if len(nodes)!=1:raise ValueError('Incomplete JUnit XML')
        node=nodes[0];status='PASS'
        for tag,key,value in [('failure','failed','FAIL'),('error','errors','ERROR'),('skipped','skipped','SKIP')]:
            if node.find(tag) is not None:result[key]+=1;status=value
        if status=='PASS':
            if case['exit']!=0 or case['status']!='PASS':raise ValueError('False process PASS')
            result['passed']+=1
        result['cases'].append({'index':i,'case':case['case'],'status':status,'exit':case['exit']})
    if result['passed']!=run['accepted_cases']:raise ValueError('Accepted count disagrees with XML')
    if not run['source_integrity_before'] or not run['source_integrity_after']:raise ValueError('Source integrity failure')
    result['classification']='NATIVE_42_PASS_REVIEW_REQUIRED' if result['passed']==42 else 'NATIVE_NOT_PASS'
    result['first_non_pass']=next((c for c in result['cases'] if c['status']!='PASS'),None)
    return result


class RunnerJob:
    """An unnamed Windows job owns only this newly spawned runner subtree."""
    def __init__(self,child):
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',w.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class Limits(ctypes.Structure):
            _fields_=[('basic',Basic),('io',ctypes.c_ulonglong*6),('process_mem',ctypes.c_size_t),('job_mem',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];self.api.CreateJobObjectW.restype=w.HANDLE
        self.api.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
        self.api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
        self.api.CloseHandle.argtypes=[w.HANDLE]
        self.handle=self.api.CreateJobObjectW(None,None)
        if not self.handle:child.kill();raise ctypes.WinError(ctypes.get_last_error())
        limits=Limits();limits.basic.flags=0x2000
        if not self.api.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) or not self.api.AssignProcessToJobObject(self.handle,w.HANDLE(child._handle)):
            child.kill();self.close();raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.handle:self.api.CloseHandle(self.handle);self.handle=None


def main():
    root=Path(__file__).resolve().parents[1]
    results=root/'wyniki'
    if results.exists() and redirected(results):raise ValueError('Redirected result directory; no writes permitted')
    results.mkdir(exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    session=results/('sesja-'+stamp);session.mkdir(exist_ok=False)
    summary={'status':'STOP','classification':'ENVIRONMENT_STOP','candidate_tree':TREE,'product_gate':'OFF','synthetic_only':True,'exit':2}
    code=2;work=None
    print('ALO Music 6.2D — testy na danych syntetycznych. Bramka produktu OFF.',flush=True)
    try:
        verify_package(root);summary['package_before']='PASS'
        # Run preflight in a fresh private-profile process: Qt imports may read
        # OS configuration, so even this process must not use the user's profile.
        env=environment(root,session)
        work=Path(tempfile.mkdtemp(prefix='alo62d-'))
        summary['work_directory']='new private alo62d-* directory under Windows TEMP; no cleanup of uncertain data'
        command=[str(root/'runtime/python.exe'),'-I','-B',str(root/'narzedzia/portable_launch.py'),'--probe',str(session/'environment.json')]
        cp=subprocess.run(command,cwd=work,env=env,capture_output=True,timeout=90)
        (session/'preflight.stdout.log').write_bytes(cp.stdout);(session/'preflight.stderr.log').write_bytes(cp.stderr)
        if cp.returncode:raise RuntimeError('Preflight STOP, exit '+str(cp.returncode))
        summary['preflight']='PASS'
        (work/'windows').mkdir();(work/'candidate').mkdir()
        for name in ('windows/run_windows.py','candidate/SOURCE-MANIFEST.json','candidate/sources.zip'):
            shutil.copyfile(root/'testy'/name,work/name)
        print('Srodowisko gotowe. Start oryginalnych 42 przypadkow; STOP przy pierwszym niezaliczonym.',flush=True)
        with (session/'runner.stdout.log').open('wb') as log,(session/'runner.stderr.log').open('wb') as err:
            summary['native_runner_started']=True
            child=subprocess.Popen([sys.executable,'-B',str(work/'windows/run_windows.py')],cwd=work,env=env,stdout=subprocess.PIPE,stderr=err)
            job=RunnerJob(child)
            def stream():
                for line in child.stdout:
                    log.write(line);log.flush();sys.stdout.buffer.write(line);sys.stdout.buffer.flush()
            reader=threading.Thread(target=stream,daemon=True);reader.start()
            try:
                # Original per-case120s and collection60s remain unchanged.
                exitcode=child.wait(timeout=5400)
            except subprocess.TimeoutExpired:
                summary['runner_timeout']=True;job.close();child.wait(timeout=20);exitcode=124
            finally:
                job.close();reader.join(timeout=20)
            if reader.is_alive():raise RuntimeError('Runner output stream did not close')
        summary['runner_exit']=exitcode
        directories=[p for p in work.glob('ALO-62D-Windows-wyniki-*') if p.is_dir()]
        if len(directories)!=1:raise ValueError('Missing or ambiguous original runner result')
        directory=directories[0];run=json.loads((directory/'run.json').read_text())
        summary.update(summarize(run,directory));summary['original_runner_status']=run['status']
        if exitcode not in (0,2):raise ValueError('Unexpected runner process termination')
        summary['status']=summary['classification']
        for f in (Path(str(directory)+'.zip'),Path(str(directory)+'.zip.sha256.txt')):
            shutil.copyfile(f,session/f.name)
        original_zip=session/(directory.name+'.zip')
        if digest(original_zip)!=(session/(original_zip.name+'.sha256.txt')).read_text().split()[0]:raise ValueError('Original result SHA mismatch')
        with zipfile.ZipFile(original_zip) as z:
            if z.testzip() is not None:raise ValueError('Original result CRC failure')
            for item in json.loads(z.read('MANIFEST.json')):
                data=z.read(item['path'])
                if hashlib.sha256(data).hexdigest()!=item['sha256'] or len(data)!=item['bytes']:raise ValueError('Original result manifest mismatch')
        summary['evidence_complete']=True
        code=0 if summary['passed']==42 else 2
    except Exception as exc:
        summary['status']='STOP';summary['classification']='ENVIRONMENT_OR_EVIDENCE_STOP';summary['evidence_complete']=False
        summary['error']=type(exc).__name__+': '+str(exc)
        if summary.get('native_runner_started') and not summary.get('evidence_complete'):
            summary['classification']='INCOMPLETE_NATIVE_EVIDENCE';summary['executed']=None;summary['not_run']=None
        (session/'exception.log').write_text(traceback.format_exc(),encoding='utf-8')
        print('STOP: '+summary['error'],flush=True)
    finally:
        try:verify_package(root);summary['package_after']='PASS'
        except Exception as exc:summary['package_after']='FAIL';summary['integrity_error']=str(exc);summary['status']='STOP';code=2
        if work is not None:
            # The original runner can stop before creating its own ZIP.
            # Copy only diagnostic types; never recurse into synthetic/source trees.
            pending=[work]
            while pending:
                folder=pending.pop()
                for path in folder.iterdir():
                    if redirected(path):continue
                    if path.is_dir():
                        if path.name not in {'synthetic','isolated-source','candidate','windows'}:pending.append(path)
                    elif path.is_file() and path.suffix.lower() in {'.json','.jsonl','.log','.txt','.xml','.png'}:
                        out=session/'native-evidence'/path.relative_to(work);out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,out)
        summary['exit']=code
        (session/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        # Preserve all available evidence even if an original runner crashed
        # before it could write run.json. Never copy synthetic music/databases.
        payload=[]
        for path in session.rglob('*'):
            rel=path.relative_to(session)
            if not path.is_file() or any(x in rel.parts for x in ('synthetic','isolated-source','profil','candidate','windows')):continue
            if path.suffix.lower() not in {'.json','.jsonl','.log','.txt','.xml','.png','.zip'}:continue
            payload.append(path)
        records=[{'path':p.relative_to(session).as_posix(),'sha256':digest(p),'bytes':p.stat().st_size} for p in payload]
        (session/'MANIFEST.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        output=results/('ALO-62D-Windows-wyniki-'+stamp+'.zip')
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
            for p in [*payload,session/'MANIFEST.json']:z.write(p,p.relative_to(session).as_posix())
        with zipfile.ZipFile(output) as z:
            if z.testzip() is not None:raise ValueError('Result CRC failure')
            for item in records:
                if hashlib.sha256(z.read(item['path'])).hexdigest()!=item['sha256']:raise ValueError('Result manifest failure')
        Path(str(output)+'.sha256.txt').write_text(digest(output)+'  '+output.name+'\n')
        print('\n'+summary['status'],flush=True)
        if summary.get('evidence_complete'):print('PASS {passed} / FAIL {failed} / ERROR {errors} / SKIP {skipped} / NOT RUN {not_run}'.format(**summary),flush=True)
        print('Testy zakonczone. Przeslij plik ZIP z folderu wyniki.\n'+str(output),flush=True)
    return code


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--probe':
        root=Path(__file__).resolve().parents[1]
        Path(sys.argv[2]).write_text(json.dumps(probe(root),indent=2),encoding='utf-8')
    elif len(sys.argv)==1:sys.exit(main())
    else:raise SystemExit('Unknown arguments; no test bypass mode')
