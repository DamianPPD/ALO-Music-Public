"""Detached feasibility spike, not a production WindowsOutputLease.

Only synthetic MP3 below this run's evidence root. Native peers synchronize by
pipe messages, never sleeps. No Qt/product integration or gate activation.
"""
from dataclasses import asdict
from pathlib import Path
import ctypes as C
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import time
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('established_ci', HERE/'ci.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
OUT = ci.EVIDENCE/'handle-feasibility'
OUT.mkdir(exist_ok=True)
OFFSET = 128
NEW = b'fedcba9876543210'
ACCESSES = [('read-data-attributes', 0x81), ('generic-read', 0x80000000)]
SHARES = [('share-read', 1), ('exclusive', 0)]
PEERS = ['writer-open', 'view-file-closed', 'view-file-section-closed', 'section-file-closed']


def write(path, value):
    path.write_text(json.dumps(value, indent=2,
        default=lambda v: v.hex() if isinstance(v, bytes) else str(v))+'\n', encoding='utf-8')


def native_module():
    if sys.platform!='win32' or struct.calcsize('P')!=8 or sys.version_info[:3]!=(3,11,9):
        raise RuntimeError('Real Windows x64 CPython3.11.9 required')
    sys.path.insert(0, str(ROOT/'src'))
    from audio_library_organizer.safety import windows_file_identity as native
    if native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is not False:
        raise RuntimeError('Product gate must remain False')
    return native


def synthetic_path(value):
    p=Path(value).resolve()
    if p.parent!= (OUT/'synthetic').resolve() or p.suffix!='.mp3' or not p.is_file():
        raise ValueError('Only an existing direct synthetic MP3 is permitted')
    return p


class API:
    def __init__(self):
        self.native=native_module(); self.api=self.native._WinAPI();self.k=self.api.k
        self.events=[];self.owned={};self.views=set()
        def bind(name,args,result):
            f=getattr(self.k,name);f.argtypes=args;f.restype=result;return f
        ptr=C.c_void_p;u32=C.c_uint32;boolean=C.c_int32
        self.seek=bind('SetFilePointerEx',[ptr,C.c_int64,C.POINTER(C.c_int64),u32],boolean)
        self.read_file=bind('ReadFile',[ptr,ptr,u32,C.POINTER(u32),ptr],boolean)
        self.write_file=bind('WriteFile',[ptr,ptr,u32,C.POINTER(u32),ptr],boolean)
        self.flush=bind('FlushFileBuffers',[ptr],boolean)
        self.mapping=bind('CreateFileMappingW',[ptr,ptr,u32,u32,u32,C.c_wchar_p],ptr)
        self.map_view=bind('MapViewOfFile',[ptr,u32,u32,u32,C.c_size_t],ptr)
        self.unmap_view=bind('UnmapViewOfFile',[ptr],boolean)
        self.flush_view=bind('FlushViewOfFile',[ptr,C.c_size_t],boolean)
        self.delete=bind('DeleteFileW',[C.c_wchar_p],boolean)
        self.move=bind('MoveFileExW',[C.c_wchar_p,C.c_wchar_p,u32],boolean)

    def log(self, event, **data):
        self.events.append({'event':event,'qpc_ns':time.perf_counter_ns(),**data})

    def open(self,path,access,share,role):
        start=time.perf_counter_ns()
        h=self.api.create(str(path),access,share,None,3,0x00200000,None)
        invalid=h in (None,C.c_void_p(-1).value)
        error=(C.get_last_error() or 31) if invalid else 0
        self.log('CreateFileW',path=str(path),access=access,share=share,
                 error=error,handle=h,duration_ns=time.perf_counter_ns()-start,role=role)
        if error:raise C.WinError(error)
        self.owned[h]=role;return h

    def close(self,h):
        if h is None:return
        role=self.owned[h]
        self.api.close(h);del self.owned[h];self.log('CloseHandle',handle=h,role=role)

    def query(self,h):
        n=self.api.query(h)
        if n.filesystem!='NTFS' or n.drive_type!=3 or n.directory or n.reparse_tag or n.links!=1 or n.delete_pending:
            raise ValueError('Actual synthetic object is not a supported fixed-NTFS regular file')
        return n

    def section(self,h):
        value=self.mapping(h,None,4,0,0,None)  # PAGE_READWRITE, anonymous section
        if not value:raise C.WinError(C.get_last_error())
        self.owned[value]='section';self.log('CreateFileMappingW',handle=value,file_handle=h,protect=4)
        return value

    def view(self,section):
        value=self.map_view(section,2|4,0,0,0)  # FILE_MAP_WRITE | FILE_MAP_READ
        if not value:raise C.WinError(C.get_last_error())
        self.views.add(value);self.log('MapViewOfFile',address=value,section=section,access=6)
        return value

    def unmap(self,v):
        if v is None:return
        if not self.unmap_view(v):raise C.WinError(C.get_last_error())
        self.views.remove(v);self.log('UnmapViewOfFile',address=v)

    def read(self,h):
        if not self.seek(h,0,None,0):raise C.WinError(C.get_last_error())
        chunks=[]
        while True:
            buf=C.create_string_buffer(65536);size=C.c_uint32()
            if not self.read_file(h,buf,len(buf),C.byref(size),None):raise C.WinError(C.get_last_error())
            if not size.value:break
            chunks.append(buf.raw[:size.value])
            if sum(map(len,chunks))>1048576:raise ValueError('Synthetic file unexpectedly large')
        b=b''.join(chunks);self.log('ReadFile-complete',handle=h,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
        return b

    def mutate(self,h):
        if not self.seek(h,OFFSET,None,0):raise C.WinError(C.get_last_error())
        n=C.c_uint32();buf=C.create_string_buffer(NEW)
        if not self.write_file(h,buf,len(NEW),C.byref(n),None):raise C.WinError(C.get_last_error())
        if n.value!=len(NEW):raise ValueError('Short write')
        if not self.flush(h):raise C.WinError(C.get_last_error())
        self.log('WriteFile-complete',handle=h,offset=OFFSET,bytes=n.value,flush=True)

    def dispose(self):
        # All views and handles are owned by this test process, never foreign.
        errors=[]
        for v in tuple(self.views):
            try:self.unmap(v)
            except OSError as e:errors.append(str(e))
        for h in reversed(tuple(self.owned)):
            try:self.close(h)
            except OSError as e:errors.append(str(e))
        if errors:raise RuntimeError('Native cleanup failure: '+repr(errors))


def reply(value):
    print(json.dumps(value,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)),flush=True)


def peer(mode,path):
    path=synthetic_path(path);api=API();h=section=view=None
    try:
        h=api.open(path,0xC0000000,7,'prior-writer')
        if mode!='writer-open':
            section=api.section(h)
            if mode!='section-file-closed':view=api.view(section)
            api.close(h);h=None
            if mode=='view-file-section-closed':api.close(section);section=None
        reply({'event':'ready','pid':os.getpid(),'mode':mode,'file_handle_open':h is not None,
               'section_handle_open':section is not None,'view_open':view is not None,'events':api.events})
        for line in sys.stdin:
            command=json.loads(line)['command']
            if command=='write':
                if mode=='writer-open':api.mutate(h)
                else:
                    if view is None:view=api.view(section)
                    C.memmove(view+OFFSET,NEW,len(NEW))
                    if not api.flush_view(view,0):raise C.WinError(C.get_last_error())
                    api.log('mapped-write-complete',address=view,offset=OFFSET,bytes=len(NEW),
                            file_handle_open=h is not None,section_handle_open=section is not None,
                            actual_hex=C.string_at(view+OFFSET,len(NEW)).hex())
                reply({'event':'written','events':api.events})
            elif command=='close':
                api.dispose();reply({'event':'closed','owned_handles':len(api.owned),'views':len(api.views),'events':api.events})
                return 0
            else:raise ValueError('Unknown peer command')
        return 2  # Parent went away. Finally still deterministically cleans up.
    finally:api.dispose()


class Peer:
    def __init__(self,mode,path,env):
        self.path=path;self.messages=[]
        self.err=(OUT/(path.stem+'.peer.stderr.log')).open('wb')
        self.p=subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__).resolve()),'peer',mode,str(path)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,text=True,env=env,cwd=ROOT)
        try:self.ready=self.receive('ready')
        except BaseException:self.close();raise

    def receive(self,event):
        line=self.p.stdout.readline()
        if not line:raise RuntimeError('Native peer ended before '+event)
        message=json.loads(line);self.messages.append(message)
        if message.get('event')!=event:raise RuntimeError('Unexpected native peer message')
        return message

    def send(self,command,event):
        self.p.stdin.write(json.dumps({'command':command})+'\n');self.p.stdin.flush()
        return self.receive(event)

    def close(self):
        if self.p.poll() is None:
            if not self.p.stdin.closed:self.p.stdin.close()
            try:self.p.wait(timeout=5)
            except subprocess.TimeoutExpired:self.p.kill();self.p.wait(timeout=5)
        if not self.p.stdin.closed:self.p.stdin.close()
        self.p.stdout.close();self.err.close()
        # Pinned CPython3.11 Windows Popen owns this process HANDLE separately
        # from its pipes. Explicitly release it, rather than waiting for GC.
        if sys.platform=='win32':self.p._handle.Close()


def child_env(python,binpath):
    env=ci.safe_environment(Path(python),Path(binpath));env['RUNNER_TEMP']=str(ci.EVIDENCE.parent)
    profile=OUT/'profile';profile.mkdir(exist_ok=True)
    env.update(APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
    return env


def observe(path, access, share, mode, env):
    api=API();h=None;other=None
    row={'path':str(path),'access':access,'share':share,'mode':mode,'status':'INCOMPLETE'}
    try:
        initial=path.read_bytes();row['initial_sha256']=hashlib.sha256(initial).hexdigest()
        other=Peer(mode,path,env);row['peer_ready']=other.ready
        try:h=api.open(path,access,share,'lease-prototype')
        except OSError as exc:
            row['acquire_error']=exc.winerror
            if exc.winerror not in (5,32,33):raise
        if h is not None:
            row['before']=asdict(api.query(h));before=api.read(h)
            if before!=initial:raise AssertionError('Wrong initial file bytes')
            row['before_hex']=before.hex();row['before_sha256']=hashlib.sha256(before).hexdigest()
            row['acquired_before_write']=True
        other.send('write','written')
        if h is not None:
            after=api.read(h);row['after']=asdict(api.query(h))
            row['after_hex']=after.hex();row['after_sha256']=hashlib.sha256(after).hexdigest()
            row['changed_while_held']=after!=before
            row['same_native_node']=row['before']==row['after']
            row['changed_region_hex']=after[OFFSET:OFFSET+len(NEW)].hex()
            row['held_until_after_read']=h in api.owned
            row['status']='CONTRACT_FALSIFIED' if after!=before else 'NO_CHANGE_OBSERVED'
            if after==before or len(after)!=len(before) or after[OFFSET:OFFSET+len(NEW)]!=NEW:
                raise AssertionError('Mutation/readback protocol incomplete')
            api.close(h);h=None
        else:row['status']='ACQUISITION_REFUSED'
        closed=other.send('close','closed')
        if closed['owned_handles'] or closed['views']:raise AssertionError('Peer resources remain')
        other.p.stdin.close();code=other.p.wait(timeout=5)
        if code!=0:raise RuntimeError('Peer exit '+str(code))
        row['peer_exit']=code;row['peer_messages']=other.messages
        h=api.open(path,access,share,'after-peer-close')
        final=api.read(h)
        if len(final)!=len(initial) or final==initial or final[OFFSET:OFFSET+len(NEW)]!=NEW:
            raise AssertionError('Peer did not actually change final bytes')
        row['final_sha256']=hashlib.sha256(final).hexdigest();row['reacquired_after_peer_release']=True
        api.close(h);h=None
    finally:
        cleanup=[]
        if other is not None:
            row['peer_messages']=other.messages
            try:other.close()
            except BaseException as exc:cleanup.append('peer: '+repr(exc))
        try:api.dispose()
        except BaseException as exc:cleanup.append('native: '+repr(exc))
        row['events']=api.events;row['cleanup_errors']=cleanup
        row['owned_handles_end']=len(api.owned);row['views_end']=len(api.views)
        write(OUT/(path.stem+'.json'),row)
        if cleanup:raise RuntimeError('Incomplete cleanup: '+repr(cleanup))
    return row


def ordinary_controls(path, env):
    api=API();h=None
    row={'kind':'ordinary-controls','path':str(path),'status':'INCOMPLETE'}
    initial=path.read_bytes()
    try:
        h=api.open(path,0x81,1,'lease-prototype')
        row['before']=asdict(api.query(h));row['sha_before']=hashlib.sha256(api.read(h)).hexdigest()
        errors={}
        for name,access in [('write',0x40000000),('delete-access',0x10000)]:
            try:
                unexpected=api.open(path,access,7,'unexpected-contender');api.close(unexpected)
                raise AssertionError('Unexpected concurrent '+name)
            except OSError as e:
                errors[name]=e.winerror
                if e.winerror not in (5,32,33):raise
        for name,target,flags in [('rename',path.with_name('renamed.mp3'),0),
                                  ('replace',path,1)]:
            source=path if name=='rename' else path.with_name('replacement.mp3')
            if name=='replace':source.write_bytes(initial)
            if api.move(str(source),str(target),flags):raise AssertionError('Unexpected '+name)
            error=C.get_last_error();errors[name]=error
            if error not in (5,32,33):raise C.WinError(error)
        if api.delete(str(path)):raise AssertionError('Unexpected delete')
        errors['DeleteFileW']=C.get_last_error()
        if errors['DeleteFileW'] not in (5,32,33):raise C.WinError(errors['DeleteFileW'])
        if api.read(h)!=initial:raise AssertionError('Controls modified protected file')
        row['refusals']=errors;row['status']='PASS';api.close(h);h=None
        h=api.open(path,0xC0000000,7,'write-after-release');api.mutate(h);api.close(h);h=None
        if path.read_bytes()==initial:raise AssertionError('File stayed blocked after release')
        row['write_after_release']='PASS'
        renamed=path.with_name('renamed.mp3')
        replacement=path.with_name('replacement.mp3')
        for source,target,flags in [(path,renamed,0),(renamed,path,0),(replacement,path,1)]:
            if not api.move(str(source),str(target),flags):raise C.WinError(C.get_last_error())
        if not api.delete(str(path)):raise C.WinError(C.get_last_error())
        row['rename_replace_delete_after_release']='PASS'
    finally:
        try:api.dispose()
        finally:
            row['events']=api.events;row['owned_handles_end']=len(api.owned)
            write(OUT/'ordinary-controls.json',row)
    return row


def run_native():
    native_module();ci.verify_sources()
    data=json.loads((ci.EVIDENCE/'prepared.json').read_text());env=child_env(data['python'],data['bin'])
    work=OUT/'synthetic';work.mkdir(exist_ok=False)
    template=work/'template.mp3'
    cmd=[str(Path(data['bin'])/'ffmpeg.exe'),'-v','error','-nostdin','-f','lavfi','-i',
         'sine=frequency=440:duration=0.2','-c:a','libmp3lame','-b:a','128k',str(template)]
    with (OUT/'ffmpeg.stdout.log').open('wb') as out,(OUT/'ffmpeg.stderr.log').open('wb') as err:
        code=subprocess.run(cmd,cwd=ROOT,env=env,stdout=out,stderr=err,timeout=20).returncode
    (OUT/'ffmpeg.exit.txt').write_text(str(code))
    if code:raise RuntimeError('Synthetic FFmpeg generation failed')
    raw=template.read_bytes()
    if len(raw)<512 or len(raw)>1048576:raise ValueError('Unexpected synthetic MP3')
    rows=[];summary={'scope':'Native Windows Server 2022; detached prototype only',
        'candidate_tree':ci.TREE,'product_gate':'OFF','product_changes':0,'cases':rows,
        'status':'INCOMPLETE','source_before':True,'source_after':False}
    write(OUT/'run.json',summary)
    try:
        p=work/'ordinary.mp3';p.write_bytes(raw);rows.append(ordinary_controls(p,env))
        for access_name,access in ACCESSES:
            for share_name,share in SHARES:
                for mode in PEERS:
                    p=work/(access_name+'-'+share_name+'-'+mode+'.mp3');p.write_bytes(raw)
                    rows.append(observe(p,access,share,mode,env));write(OUT/'run.json',summary)
        summary['status']='FEASIBILITY_FALSIFIED' if any(r['status']=='CONTRACT_FALSIFIED' for r in rows) else 'NO_COUNTEREXAMPLE_OBSERVED_NOT_ACCEPTED'
    except BaseException:
        summary['status']='STOP_INFRASTRUCTURE';raise
    finally:
        ci.verify_sources();summary['source_after']=True;write(OUT/'run.json',summary)
    return 1 if summary['status']=='FEASIBILITY_FALSIFIED' else 0


def validate_result(result,code):
    """Strict evidence check. NO_COUNTEREXAMPLE never means contract accepted."""
    def need(value,reason):
        if not value:raise ValueError(reason)
    need(code in (0,1),'Native crash/timeout/invalid exit')
    need(result.get('product_gate')=='OFF' and result.get('product_changes')==0,'Product changed or gate enabled')
    need(result.get('source_before') is True and result.get('source_after') is True,'Missing source integrity')
    rows=result.get('cases',[])
    need(len(rows)==1+len(ACCESSES)*len(SHARES)*len(PEERS),'Incomplete feasibility matrix')
    control=rows[0]
    need(control.get('kind')=='ordinary-controls' and control.get('status')=='PASS'
         and control.get('owned_handles_end')==0 and control.get('write_after_release')=='PASS','Control incomplete')
    need(set(control.get('refusals',{}))=={'write','delete-access','rename','replace','DeleteFileW'}
         and all(v in (5,32,33) for v in control['refusals'].values()),'Missing ordinary refusal')
    expected={(a,s,m) for _,a in ACCESSES for _,s in SHARES for m in PEERS}
    seen=set();falsified=False
    for row in rows[1:]:
        key=(row.get('access'),row.get('share'),row.get('mode'))
        need(key in expected and key not in seen,'Wrong/duplicate native case');seen.add(key)
        need(row.get('peer_exit')==0 and row.get('owned_handles_end')==0 and row.get('views_end')==0
             and not row.get('cleanup_errors') and row.get('reacquired_after_peer_release') is True,'Unfinished peer/cleanup')
        need(row.get('final_sha256') and row['final_sha256']!=row.get('initial_sha256'),'Missing successful writer control')
        if row.get('status')=='ACQUISITION_REFUSED':
            need(row.get('acquire_error') in (5,32,33),'Unexpected acquire failure')
        elif row.get('status')=='CONTRACT_FALSIFIED':
            need(row.get('acquired_before_write') is True and row.get('held_until_after_read') is True
                 and row.get('changed_while_held') is True,'No held protection counterexample')
            before=bytes.fromhex(row.get('before_hex',''));after=bytes.fromhex(row.get('after_hex',''))
            need(before and len(before)==len(after) and before!=after,'Missing same-size changed readback')
            need(hashlib.sha256(before).hexdigest()==row.get('before_sha256')
                 and hashlib.sha256(after).hexdigest()==row.get('after_sha256'),'Readback SHA mismatch')
            old=row.get('before',{});new=row.get('after',{})
            need(old.get('file_id')==new.get('file_id') and old.get('file_id') is not None,'Different file object')
            falsified=True
        else:raise ValueError('Unknown/incomplete native case status')
    outcome='FEASIBILITY_FALSIFIED' if falsified else 'NO_COUNTEREXAMPLE_OBSERVED_NOT_ACCEPTED'
    need(result.get('status')==outcome and (code==1)==falsified,'Exit/status/evidence mismatch')
    return outcome


class BASIC_LIMIT(C.Structure):
    _fields_=[('PerProcessUserTimeLimit',C.c_int64),('PerJobUserTimeLimit',C.c_int64),
        ('LimitFlags',C.c_uint32),('MinimumWorkingSetSize',C.c_size_t),('MaximumWorkingSetSize',C.c_size_t),
        ('ActiveProcessLimit',C.c_uint32),('Affinity',C.c_size_t),('PriorityClass',C.c_uint32),('SchedulingClass',C.c_uint32)]


class EXTENDED_LIMIT(C.Structure):
    _fields_=[('BasicLimitInformation',BASIC_LIMIT),('IoInfo',C.c_uint64*6),
        ('ProcessMemoryLimit',C.c_size_t),('JobMemoryLimit',C.c_size_t),
        ('PeakProcessMemoryUsed',C.c_size_t),('PeakJobMemoryUsed',C.c_size_t)]


def bounded_native(data,env,out,err):
    """Private Job Object kills controller + peer tree on timeout/owner exit.

    The child waits for GO before doing anything; assignment precedes GO, so
    there is no spawn-before-job race. No process outside this test is assigned.
    """
    k=C.WinDLL('kernel32',use_last_error=True);ptr=C.c_void_p;boolean=C.c_int32;u32=C.c_uint32
    def bind(name,args,result):
        f=getattr(k,name);f.argtypes=args;f.restype=result;return f
    create=bind('CreateJobObjectW',[ptr,C.c_wchar_p],ptr)
    setinfo=bind('SetInformationJobObject',[ptr,C.c_int32,ptr,u32],boolean)
    assign=bind('AssignProcessToJobObject',[ptr,ptr],boolean)
    close=bind('CloseHandle',[ptr],boolean)
    job=create(None,None)
    if not job:raise C.WinError(C.get_last_error())
    p=None
    try:
        limits=EXTENDED_LIMIT();limits.BasicLimitInformation.LimitFlags=0x2000  # KILL_ON_JOB_CLOSE
        if C.sizeof(EXTENDED_LIMIT)!=144:raise RuntimeError('Unexpected x64 Job Object ABI')
        if not setinfo(job,9,C.byref(limits),C.sizeof(limits)):raise C.WinError(C.get_last_error())
        p=subprocess.Popen([data['python'],'-I','-B',str(Path(__file__).resolve()),'native-wait'],
            cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=out,stderr=err,text=True)
        if not assign(job,int(p._handle)):raise C.WinError(C.get_last_error())
        write(OUT/'job.json',{'kill_on_close':True,'controller_pid':p.pid,'assigned_before_GO':True})
        try:p.communicate(input='GO\n',timeout=180);code=p.returncode
        except subprocess.TimeoutExpired:code=124
        return code
    finally:
        # This also kills a wedged peer if the native controller was killed or
        # returned unexpectedly. A timeout never counts as successful cleanup.
        if not close(job):raise C.WinError(C.get_last_error())
        if p is not None:
            # Assignment may fail while the child is waiting for GO. Such a
            # child is not in our job yet, so terminate it explicitly as well.
            if p.poll() is None:p.terminate()
            p.wait(timeout=10)
            if p.stdin and not p.stdin.closed:p.stdin.close()
            p._handle.Close()


def run():
    native_module();ci.verify_sources();data=json.loads((ci.EVIDENCE/'prepared.json').read_text())
    env=child_env(data['python'],data['bin'])
    with (OUT/'native.stdout.log').open('wb') as out,(OUT/'native.stderr.log').open('wb') as err:
        code=bounded_native(data,env,out,err)
    (OUT/'native.exit.txt').write_text(str(code));ci.verify_sources()
    path=OUT/'run.json'
    if not path.exists():raise RuntimeError('No native feasibility evidence; STOP')
    result=json.loads(path.read_text())
    validate_result(result,code)
    return code


def finish():
    integrity='NOT RUN'
    try:
        if (ci.EVIDENCE/'prepared.json').exists():ci.verify_sources();integrity='PASS'
    except Exception as exc:
        integrity='FAIL';write(ci.EVIDENCE/'handle-integrity-error.json',{'error':str(exc)})
    write(ci.EVIDENCE/'HANDLE-SUMMARY.json',{'source_integrity':integrity,'product_gate':'OFF',
        'native_run':json.loads((OUT/'run.json').read_text()) if (OUT/'run.json').exists() else {'status':'NOT RUN'}})
    files=[p for p in ci.EVIDENCE.rglob('*') if p.is_file()
        and not any(x in ('synthetic','profile','cache') for x in p.relative_to(ci.EVIDENCE).parts)
        and p.suffix in ('.json','.jsonl','.log','.txt','.xml') and p.name!='HANDLE-MANIFEST.json']
    manifest=[{'path':p.relative_to(ci.EVIDENCE).as_posix(),'bytes':p.stat().st_size,
               'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    write(ci.EVIDENCE/'HANDLE-MANIFEST.json',manifest)
    target=ci.EVIDENCE/'ALO-62D-HANDLE-evidence.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(ci.EVIDENCE).as_posix())
        z.write(ci.EVIDENCE/'HANDLE-MANIFEST.json','HANDLE-MANIFEST.json')
    with zipfile.ZipFile(target) as z:
        if z.testzip() is not None:raise RuntimeError('Bad evidence CRC')
        for f in manifest:
            if hashlib.sha256(z.read(f['path'])).hexdigest()!=f['sha256']:raise RuntimeError('Evidence mismatch')
    Path(str(target)+'.sha256.txt').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n')
    return 2 if integrity=='FAIL' else 0


if __name__=='__main__':
    try:
        action=sys.argv[1]
        if action=='native-wait':
            if sys.stdin.readline()!='GO\n':raise RuntimeError('Missing parent Job Object acknowledgement')
            code=run_native()
        else:code=peer(sys.argv[2],sys.argv[3]) if action=='peer' else {'run':run,'finish':finish}[action]()
    except BaseException:
        (OUT/('exception-'+str(os.getpid())+'.log')).write_text(traceback.format_exc());raise
    sys.exit(code)
