"""Observe real backend calls; deny private music/DB/network and foreign executables."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from urllib.parse import unquote, urlsplit
from contract import data_state, sha256, write_json


FUNCTIONS={'check_library','adopt_legacy_output','binding_facts','read_managed_bindings',
           'inspect_audio','_decode','resolve_read_path','recheck_read_path','read_material','_hash_file'}

WINDOWS=os.name=='nt'


def _text(value):
    """Decode filesystem arguments, never stringify missing/invalid values."""
    text=os.fsdecode(os.fspath(value))
    if any(ord(c)<32 for c in text):raise ValueError('Control character in subprocess argument')
    return text


def _command_argv(value):
    if isinstance(value,(list,tuple)):
        result=[_text(item) for item in value]
    elif WINDOWS and isinstance(value,str):
        # CPython 3.11 Windows audits the result of list2cmdline, not the list.
        # Invert its MS C quoting rules and accept only its canonical encoding.
        result=[];i=0
        while i<len(value):
            while i<len(value) and value[i] in ' \t':i+=1
            if i==len(value):break
            word='';quoted=False
            while i<len(value):
                if value[i] in ' \t' and not quoted:break
                slashes=0
                while i<len(value) and value[i]=='\\':slashes+=1;i+=1
                if i<len(value) and value[i]=='"':
                    word+='\\'*(slashes//2)
                    if slashes%2:word+='"'
                    else:quoted=not quoted
                    i+=1
                else:
                    word+='\\'*slashes
                    if i==len(value) or (value[i] in ' \t' and not quoted):break
                    word+=value[i];i+=1
            if quoted:raise ValueError('Unterminated Windows command line')
            result.append(_text(word))
        if subprocess.list2cmdline(result)!=value:
            raise ValueError('Ambiguous/noncanonical Windows command line')
    else:raise ValueError('Missing or invalid audited argv')
    if not result or not result[0]:raise ValueError('Missing program in audited argv')
    return result


def _windows_directories():
    """Use Windows APIs, not a caller-supplied system-directory whitelist."""
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    values=[]
    for name in ('GetSystemDirectoryW','GetWindowsDirectoryW'):
        function=getattr(kernel,name);function.argtypes=[wintypes.LPWSTR,wintypes.UINT];function.restype=wintypes.UINT
        buffer=ctypes.create_unicode_buffer(32768);count=function(buffer,len(buffer))
        if not 0<count<len(buffer):raise ValueError('Cannot determine Windows search directories')
        values.append(Path(buffer.value).resolve())
    system,windows=values
    return [system,windows/'System',windows]


def _verified_windows_path(trusted):
    """Accept only the canonical PATH, or the exact initialized/pinned private Qt prefix."""
    raw=os.environ.get('PATH','').split(os.pathsep)
    if any(not part or not Path(part).is_absolute()for part in raw):raise ValueError('Unverified subprocess PATH')
    paths=[Path(part).resolve()for part in raw]
    if paths==trusted:return paths
    python=Path(sys.executable).resolve().parent
    qt=python/'Lib/site-packages/PySide6';module=sys.modules.get('PySide6')
    init=qt/'__init__.py'
    if (paths!=[qt,*trusted]or module is None or getattr(module,'__version__',None)!='6.10.3'
            or Path(getattr(module,'__file__','')).absolute()!=init
            or qt.resolve()!=qt or init.is_symlink()or not init.is_file()
            or sha256(init)!='dd003a2fb0fa4f45a2158458f3c9a2bf4ed4c4eecc0bacbd895de120a21dff71'):
        raise ValueError('Unverified subprocess PATH')
    return paths

def _select_executable(executable,argv):
    raw=_text(os.environ['I7_FFMPEG_EXE']);expected=Path(raw)
    digest=os.environ['I7_FFMPEG_SHA256']
    if (not expected.is_absolute() or expected.is_symlink() or not expected.is_file()
            or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest)
            or sha256(expected)!=digest):raise ValueError('Pinned FFmpeg identity/hash unavailable or changed')
    expected=expected.resolve()
    program=argv[0] if executable is None else _text(executable)
    if not program:raise ValueError('Empty executable')
    if WINDOWS:
        if expected.name.lower()!='ffmpeg.exe':raise ValueError('Invalid pinned Windows FFmpeg name')
        systems=_windows_directories();python=Path(sys.executable).resolve().parent
        trusted=[expected.parent,python,systems[0],systems[-1]]
        path=_verified_windows_path(trusted)
        # Explicit lpApplicationName never uses PATH or an implicit .exe suffix.
        if executable is not None or Path(program).is_absolute() or '/' in program or '\\' in program:
            selected=Path(program).absolute()
        else:
            if program.lower() not in ('ffmpeg','ffmpeg.exe'):raise ValueError('Unapproved program')
            # CreateProcessW searches parent application/cwd/system slots before PATH.
            selected=None
            for directory in [python,Path.cwd(),*systems,*path]:
                candidate=directory/'ffmpeg.exe'
                if candidate.exists():selected=candidate;break
    else:
        selected=Path(program) if Path(program).is_absolute() else shutil.which(program)
    if (selected is None or Path(selected).is_symlink() or Path(selected).absolute()!=expected
            or Path(selected).resolve()!=expected):raise ValueError('Only pinned FFmpeg may execute in a backend test')
    return expected,digest


def _raw_argv(value):
    return value if isinstance(value,str) else [_text(item) for item in value]


class Observer:
    def __init__(self,kit,folder):
        self.kit=Path(kit); self.folder=Path(folder); self.data=folder/'data'
        self.record=dict(operations=[],subprocesses=[],completed=[],checks=[],errors=[],violations=[])
        self.pending={}; self.local=threading.local(); self.counter=0

    def production_decoder(self):
        frame=sys._getframe(1)
        while frame:
            if frame.f_globals.get('__name__')=='audio_library_organizer.audio.identity' and frame.f_code.co_name=='_decode':
                return True
            frame=frame.f_back
        return False

    def allowed_data(self,value):
        text=os.fsdecode(value)
        if text==':memory:': return True
        if text.startswith('file:'):
            text=unquote(urlsplit(text).path)
            if os.name=='nt' and len(text)>2 and text[0]=='/' and text[2]==':':text=text[1:]
        return Path(text).resolve().is_relative_to(self.data.resolve())

    def waveform_command(self,executable,argv,cwd,env):
        if len(argv)!=8 or argv[1]!='-I':return False
        expected=Path(sys.executable).resolve()
        if (Path(argv[0]).resolve()!=expected or (executable is not None and Path(_text(executable)).resolve()!=expected)
                or argv[0]!=str(expected)):
            raise ValueError('Foreign private waveform executable')
        if sha256(expected)!=os.environ['L41_PYTHON_SHA256']:raise ValueError('Private Python changed')
        script=self.kit/'snapshot/src/audio_library_organizer/audio/waveform_worker.py'
        if not Path(argv[2]).is_absolute() or argv[2]!=str(script.resolve()) or sha256(script)!=os.environ['L41_WAVEFORM_SHA256']:
            raise ValueError('Foreign waveform worker')
        if (not Path(argv[3]).is_absolute() or Path(argv[3]).is_symlink() or not self.allowed_data(argv[3])
                or Path(argv[3]).suffix.lower()not in ('.mp3','.wav')):
            raise ValueError('Private waveform input outside synthetic data')
        if not argv[4].isdigit() or not 1<=int(argv[4])<=8192 or not argv[7].isdigit():raise ValueError('Bad waveform arguments')
        for value in argv[5:7]:
            path=Path(value).resolve()
            if not Path(value).is_absolute() or not path.is_relative_to(self.folder.resolve()) or Path(value).is_symlink():raise ValueError('Waveform output outside case')
        if cwd is not None and not self.allowed_data(_text(cwd)):raise ValueError('Waveform cwd outside data')
        if not isinstance(env,dict) or env.get('PATH')!=os.environ.get('PATH'):raise ValueError('Unverified waveform env')
        return True

    def audit(self,event,args):
        if getattr(self.local,'busy',False): return
        self.local.busy=True
        try:
            problem=None
            if event=='sqlite3.connect' and not self.allowed_data(args[0]): problem='SQLite outside synthetic data'
            elif event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
                if Path(os.fsdecode(args[0])).suffix.lower() in ('.mp3','.wav','.sqlite3','.sqlite','.db') and not self.allowed_data(args[0]):
                    problem='Audio/SQLite path outside synthetic data'
            elif event=='socket.connect': problem='Network forbidden in test process'
            elif event=='subprocess.Popen':
                try:
                    if not isinstance(args,tuple) or len(args)!=4:raise ValueError('Invalid Popen audit payload')
                    executable,raw,cwd,env=args;argv=_command_argv(raw)
                    if self.waveform_command(executable,argv,cwd,env):
                        self.record['subprocesses'].append(dict(executable=argv[0],argv=argv,kind='verified-private-waveform'))
                        return
                    expected,digest=_select_executable(executable,argv)
                    if cwd is not None and not self.allowed_data(_text(cwd)):raise ValueError('Subprocess cwd outside synthetic data')
                    if env is not None and (not isinstance(env,dict) or env.get('PATH')!=os.environ.get('PATH')):
                        raise ValueError('Unverified subprocess environment/PATH')
                    # Only the two real synthetic-fixture/production decoder commands.
                    fixture=(len(argv)==11 and argv[1:5]==['-v','error','-nostdin','-i']
                             and argv[6:10]==['-c:a','libmp3lame','-b:a','128k'])
                    decoder=(len(argv)==24 and argv[1:13]==['-hide_banner','-v','error','-nostdin','-xerror','-err_detect','explode',
                             '-protocol_whitelist','file,pipe','-f','mp3','-i']
                             and argv[14:]==['-map','0:a:0','-vn','-sn','-dn','-threads','1','-f','null','-'])
                    if not fixture and not decoder:raise ValueError('Unexpected FFmpeg command outside synthetic workflows')
                    audio=[argv[5],argv[10]] if fixture else [argv[13]]
                    for value in audio:
                        path=Path(value)
                        if (not path.is_absolute() or path.suffix.lower() not in ('.mp3','.wav')
                                or not self.allowed_data(value) or path.is_symlink()):
                            raise ValueError('FFmpeg audio path outside synthetic data')
                    self.record['subprocesses'].append(dict(executable=str(expected),argv=argv,
                        audit_executable=None if executable is None else _text(executable),audit_argv=_raw_argv(raw),
                        sha256=digest,production_decoder=self.production_decoder()))
                except (TypeError,ValueError,OSError,KeyError) as error:problem='Cannot safely authorize subprocess: '+str(error)
            if problem:
                self.record['violations'].append(dict(event=event,reason=problem))
                raise PermissionError('STOP: '+problem)
        finally:self.local.busy=False

    def profile(self,frame,event,arg):
        name=frame.f_code.co_name
        if event not in ('call','return') or getattr(self.local,'busy',False):return
        module=frame.f_globals.get('__name__','')
        relevant=name in FUNCTIONS and module.startswith('audio_library_organizer.')
        completed=event=='return' and name=='communicate' and module=='subprocess' and isinstance(arg,tuple) and len(arg)==2
        if not relevant and not completed:return
        self.local.busy=True
        try:
            if completed:
                process=frame.f_locals.get('self'); number=len(self.record['completed'])+1
                self.folder.joinpath('native').mkdir(exist_ok=True)
                logs={}
                for label,value in zip(('stdout','stderr'),arg):
                    path=self.folder/'native'/f'{number:03d}.{label}.log'
                    path.write_bytes(value if isinstance(value,bytes)else str(value or '').encode('utf-8'))
                    logs[label]=str(path.relative_to(self.folder))
                self.record['completed'].append(dict(pid=process.pid,argv=_raw_argv(process.args),exit_code=process.returncode,
                    production_decoder=self.production_decoder(),**logs))
                return
            row=dict(event=event,function=name,module=module,thread=threading.get_ident())
            if event=='return':
                for key in ('status','reason','reason_code','is_verified','binding_id','track_id','full_sha256'):
                    value=getattr(arg,key,None)
                    if isinstance(value,(str,int,bool)) or value is None:row[key]=value
            self.record['operations'].append(row)
            if name=='check_library':
                key=id(frame)
                if event=='call':
                    self.counter+=1; number=self.counter
                    state=data_state(self.data,protected=True); self.pending[key]=(number,state)
                    write_json(self.folder/f'protected/check-{number:03d}-before.json',state)
                elif key in self.pending:
                    number,before=self.pending.pop(key); after=data_state(self.data,protected=True)
                    write_json(self.folder/f'protected/check-{number:03d}-after.json',after)
                    unchanged=before==after
                    self.record['checks'].append(dict(number=number,protected_tables_and_audio_unchanged=unchanged))
                    if not unchanged:self.record['violations'].append(dict(event='check_library',reason='Protected data changed'))
        except Exception as error:
            self.record['errors'].append(dict(function=name,event=event,error=repr(error)))
        finally:self.local.busy=False

    def install(self):
        if sys.getprofile() is not None:raise ValueError('Unexpected existing profiler')
        sys.addaudithook(self.audit); sys.setprofile(self.profile); threading.setprofile(self.profile)

    def finish(self):
        sys.setprofile(None); threading.setprofile(None)
        if self.pending:self.record['errors'].append(dict(error='Incomplete check_library observation'))
        write_json(self.folder/'observations.json',self.record)
        return self.record
