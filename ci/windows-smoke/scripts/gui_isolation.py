"""Test-only data boundary for real MainWindow, SQLite and INI preferences."""
import os
import stat
from pathlib import Path
from urllib.parse import unquote,urlsplit

def _is_devnull_open(value,mode,flags):
    """Only the literal runtime null device and Popen's non-creating os.open mode."""
    canonical={'nt':'nul','posix':'/dev/null'}.get(os.name)
    if canonical is None or os.devnull!=canonical or mode is not None or type(flags)is not int:
        return False
    try:
        if os.fsdecode(os.fspath(value))!=canonical:return False
    except (TypeError,ValueError,UnicodeError):return False
    allowed=os.O_RDWR|getattr(os,'O_NOINHERIT',0)|getattr(os,'O_BINARY',0)|getattr(os,'O_CLOEXEC',0)
    if flags & (os.O_WRONLY|os.O_RDWR)!=os.O_RDWR or flags & ~allowed:return False
    if os.name=='posix':
        # Allows real non-GUI infrastructure integration tests, never a symlink/replaced regular file.
        try:
            record=os.lstat(canonical)
            if not stat.S_ISCHR(record.st_mode):return False
        except OSError:return False
    return True


def prepare_platform_diagnostics(module=None):
    """Use genuine stdlib/Windows API fallback, never authorize an optional shell probe."""
    import platform
    import sys
    module=platform if module is None else module
    blocked=[];active=True;armed=False
    def deny_optional_process(event,args):
        nonlocal armed
        if active and event=='alo.library41.diagnostics.guard_check':armed=True
        if active and event=='subprocess.Popen':
            executable,argv=args[:2]
            blocked.append(dict(executable=None if executable is None else os.fsdecode(executable),
                argv=argv if isinstance(argv,str)else [os.fsdecode(a)for a in argv],started=False))
            raise PermissionError('Diagnostic platform discovery cannot start subprocesses')
    sys.addaudithook(deny_optional_process)
    try:
        sys.audit('alo.library41.diagnostics.guard_check')
        if not armed:raise ValueError('Diagnostic subprocess audit guard not installed')
        value=module.platform()  # Its ordinary cache is also used by unchanged crash_debug.initialize().
        windows=list(module.win32_ver())
        api=list(sys.getwindowsversion().platform_version)if hasattr(sys,'getwindowsversion')else None
        if not isinstance(value,str)or not value:raise ValueError('Missing actual platform diagnostic')
        if os.name=='nt' and (api is None or len(api)!=3 or not windows[1]
                or list(map(int,windows[1].split('.')))!=api):
            raise ValueError('Windows API and diagnostic version disagree')
    finally:active=False
    return dict(status='PREPARED_WITHOUT_SUBPROCESS',platform=value,windows_version=windows,
        windows_api_version=api,blocked_optional_probes=blocked,subprocesses_started=0,audit_guard_verified=armed)


class GuiIsolation:
    def __init__(self,directory,fixtures):
        self.directory=Path(directory).resolve()
        self.fixtures=Path(fixtures).resolve()
        self.attempts=[];self.connections=[];self.ini_files=[]
        self.qt_guards_installed=False;self.rejected_operations=[]
        self.read_only_metadata=set();self.devnull_opens=[]

    def reject(self,operation):
        self.attempts.append(operation)
        raise RuntimeError('I7 GUI isolation forbids '+operation)

    def inside(self,path):
        return Path(path).resolve().is_relative_to(self.directory)

    def sqlite_path(self,value):
        value=os.fsdecode(value)
        if value==':memory:':return value
        if value.startswith('file:'):
            url=urlsplit(value)
            if url.netloc:self.reject('SQLite network locator')
            value=unquote(url.path)
            if os.name=='nt' and value.startswith('/') and len(value)>3 and value[2]==':':value=value[1:]
        if not self.inside(value):self.reject('SQLite outside synthetic sandbox')
        return str(Path(value).resolve())

    def _redact_path(self,value):
        raw=os.fsdecode(value)
        if raw in ('nul','/dev/null',r'\\.\NUL',r'\\?\NUL'):return raw
        try:return '<CASE>/'+Path(os.path.abspath(raw)).relative_to(self.directory).as_posix()
        except ValueError:return '<outside-sandbox>'

    def audit(self,event,args):
        if event=='sqlite3.connect':
            self.connections.append(self.sqlite_path(args[0]))
        elif event=='open' and not isinstance(args[0],int):
            if _is_devnull_open(*args):
                self.devnull_opens.append(dict(device=os.devnull,mode=args[1],flags=args[2]));return
            path=Path(os.fsdecode(args[0])).resolve()
            mode=args[1] or '';flags=args[2] or 0
            writing=any(c in mode for c in 'wax+') or bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing and not self.inside(path):
                self.rejected_operations.append(dict(event='open',operation='write',
                    input_path=self._redact_path(args[0]),resolved_path=self._redact_path(path),
                    mode=args[1],flags=args[2],reason='file write outside sandbox'))
                self.reject('file write outside sandbox')
            if not writing and path.suffix.lower() in ('.mp3','.wav','.flac','.ogg','.m4a','.aac','.opus','.wma','.aiff','.aif','.sqlite3','.db','.ini'):
                if not self.inside(path) and not path.is_relative_to(self.fixtures) and path not in self.read_only_metadata:self.reject('private data read')
        elif event in ('os.mkdir','os.remove','os.rmdir','os.truncate','os.chmod'):
            if not self.inside(args[0]):self.reject('filesystem mutation outside sandbox')
        elif event in ('os.rename','os.link','os.symlink'):
            if not self.inside(args[0]) or not self.inside(args[1]):self.reject('filesystem move/link outside sandbox')
        elif event in ('socket.connect','socket.getaddrinfo'):
            self.reject('network access')
        elif event=='import' and args[0] in ('audio_library_organizer.main','audio_library_organizer.__main__'):
            self.reject('normal application entry')

    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('audio_library_organizer.main','audio_library_organizer.__main__'):
            self.reject('normal application entry')
        return None

    def install_qt(self,core,network):
        guard=self;original=core.QSettings
        class SandboxSettings(original):
            def __init__(self,*args,**kwargs):
                if len(args)<2 or args[1]!=original.Format.IniFormat or not guard.inside(args[0]):
                    guard.reject('QSettings default/native/external store')
                guard.ini_files.append(str(Path(args[0]).resolve()))
                super().__init__(*args,**kwargs)
        core.QSettings=SandboxSettings
        class NoNetwork(network.QNetworkAccessManager):
            def createRequest(self,*args):guard.reject('Qt network request')
            def get(self,*args):guard.reject('Qt network GET')
            def post(self,*args):guard.reject('Qt network POST')
            def put(self,*args):guard.reject('Qt network PUT')
            def deleteResource(self,*args):guard.reject('Qt network DELETE')
            def sendCustomRequest(self,*args):guard.reject('Qt network custom request')
        network.QNetworkAccessManager=NoNetwork
        import requests
        def no_request(*args,**kwargs):guard.reject('Requests network request')
        requests.sessions.Session.request=no_request
        self.qt_guards_installed=True

    def install_native_boundaries(self,gui,multimedia):
        guard=self;source=multimedia.QMediaPlayer.setSource
        def synthetic_source(player,url):
            if not url.isEmpty() and (not url.isLocalFile() or not guard.inside(url.toLocalFile())):
                guard.reject('native media outside synthetic sandbox')
            return source(player,url)
        multimedia.QMediaPlayer.setSource=synthetic_source
        self.original_open_url=gui.QDesktopServices.openUrl

    def evidence(self):
        return dict(synthetic_sandbox=str(self.directory),fixtures=str(self.fixtures),
                    attempts=self.attempts,sqlite_connections=self.connections,INI_stores=self.ini_files,
                    Qt_guards_installed=self.qt_guards_installed,no_private_library_argument=True,canonical_devnull_opens=self.devnull_opens,
                    rejected_operations=self.rejected_operations)
