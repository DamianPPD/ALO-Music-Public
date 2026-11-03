"""Test-only confinement and executable pinning; no product edits."""
from pathlib import Path
import os,sys,json,hashlib,shutil,subprocess

def inside(path,root):
    try:return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError,ValueError,TypeError):return False

def junction_command(args,root):
    return (len(args)==6 and [str(x).lower()for x in args[:4]]==['/d','/c','mklink','/j']
        and all(inside(p,root)and not any(c in str(p)for c in '&|<>"%^!\r\n')for p in args[4:]))

def summary_status(outcomes,planned):
    return 'PASS' if len(outcomes)==planned and all(x=='PASS'for x in outcomes)else 'STOP'

def install(package,work,profile=None,output=None):
    """No read/write access to private music; not an OS sandbox for hostile code."""
    if getattr(sys,'_alo_portable_policy',False):return
    package=Path(package).resolve();work=Path(work).resolve()
    assert package.is_dir()and work.is_dir()and package!=work
    writable=(work,)if output is None else(work,Path(output).resolve())
    system=Path(os.environ['SystemRoot']).resolve();fd=os.open(work/('isolation-'+str(os.getpid())+'.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    from _thread import allocate_lock
    log_lock=allocate_lock()
    def emit(kind,**kw):
        row=json.dumps(dict(kind=kind,**kw),ensure_ascii=True,default=str)+'\n'
        with log_lock:os.write(fd,row.encode())
    def refuse(kind,detail):emit('VIOLATION',operation=kind,detail=detail);raise PermissionError('ISOLATION STOP: '+kind)
    def readable(p):return any(inside(p,r)for r in(package,work,system))
    def audit(event,args):
        if event.startswith(('socket.connect','socket.bind','socket.getaddrinfo')):refuse(event,'network disabled')
        if event in ('winreg.CreateKey','winreg.DeleteKey','winreg.DeleteValue','winreg.SetValue','winreg.SetValueEx','winreg.LoadKey','winreg.SaveKey'):refuse(event,'registry writes disabled')
        if event=='open':
            p,mode,flags=args
            if isinstance(p,int):return
            write=bool((flags or 0)&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if write and not any(inside(p,r)for r in writable):refuse(event,'write outside new synthetic workspace')
            if not write and not readable(p):refuse(event,'read outside package/workspace/system')
        if event in ('os.listdir','os.scandir') and args and not isinstance(args[0],int) and not readable(args[0]):refuse(event,'enumeration outside isolation')
        if event in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.utime','os.truncate'):
            if not isinstance(args[0],int)and not inside(args[0],work):refuse(event,'mutation outside workspace')
        if event in ('os.rename','os.link','os.symlink'):
            if not all(inside(p,work)for p in args[:2]):refuse(event,'link/rename outside workspace')
        if event=='sqlite3.connect':
            p=args[0]
            if p==':memory:':return
            if str(p).startswith('file:'):
                from urllib.request import url2pathname
                from urllib.parse import urlsplit
                p=url2pathname(urlsplit(str(p)).path)
            if not inside(p,work):refuse(event,'SQLite outside synthetic workspace')
        if event=='subprocess.Popen':
            executable=args[0]
            if executable is None:refuse(event,'unresolved executable')
            emit('subprocess.audit',executable=os.fsdecode(executable),argv=args[1])
    pinned={str((package/'runtime/python.exe').resolve()).casefold(),str((package/'tools/ffmpeg.exe').resolve()).casefold()}
    cmd=(system/'System32/cmd.exe').resolve();original=subprocess.Popen
    class PinnedPopen(original):
        def __init__(self,*a,**kw):
            argv=a[0]if a else kw.get('args')
            if not isinstance(argv,(list,tuple))or not argv or kw.get('shell'):refuse('Popen','argv list required, shell disabled')
            try:
                selected=os.fsdecode(kw.get('executable')or argv[0])
                executable=Path(selected)if Path(selected).is_absolute()else Path(shutil.which(selected)or '')
                executable=executable.resolve()
            except (TypeError,ValueError,OSError):refuse('Popen','invalid executable')
            if str(executable).casefold()not in pinned:
                if executable!=cmd or not junction_command(argv[1:],work):refuse('Popen','unapproved executable/command')
            if kw.get('cwd')and not readable(kw['cwd']):refuse('Popen','unapproved working directory')
            kw['executable']=str(executable)
            emit('subprocess.selected',executable=str(executable),argv=list(argv))
            super().__init__(*a,**kw)
    subprocess.Popen=PinnedPopen;sys.addaudithook(audit);sys._alo_portable_policy=True
    if profile is not None:
        from PySide6.QtCore import QSettings,QCoreApplication,qInstallMessageHandler
        def qt_start(kind,context,message):emit('Qt.startup',type=int(kind.value),message=message)
        qInstallMessageHandler(qt_start)
        profile=Path(profile).resolve();assert inside(profile,work);profile.mkdir(parents=True,exist_ok=True)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        for scope in(QSettings.Scope.UserScope,QSettings.Scope.SystemScope):QSettings.setPath(QSettings.Format.IniFormat,scope,str(profile))
        QCoreApplication.setOrganizationName('ALO-Isolated-W11');QCoreApplication.setApplicationName('N2-Synthetic')
        # Observe the real constructor before it can open a library.
        import audio_library_organizer.ui.main_window as module
        init=module.MainWindow.__init__
        def checked(window,settings,store,*a,**kw):
            if store.format()!=QSettings.Format.IniFormat or not inside(store.fileName(),work):refuse('QSettings','explicit isolated INI required')
            if not inside(settings.library.root,work):refuse('MainWindow','synthetic library required')
            emit('MainWindow.isolated',ini=store.fileName(),library=str(settings.library.root))
            return init(window,settings,store,*a,**kw)
        module.MainWindow.__init__=checked
