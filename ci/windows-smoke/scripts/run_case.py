"""Exactly one real Windows Library4.1 GUI case under a parent Job Object."""
import sys
if __name__=='__main__' and sys.platform=='win32':
    if sys.stdin.buffer.readline()!=b'LIB41-GO\n':raise SystemExit('STOP: missing parent Job Object handshake')
import faulthandler
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from contract import CASES,TREE,data_state,read_json,verify_source,write_json

def pytest_logging_options(folder,guard):
    """Configure the real pytest FileHandler within this case, independent of cwd."""
    folder=Path(folder).resolve()
    if folder!=guard.directory:guard.reject('pytest log outside case')
    directory=(folder/'sandbox/logs').resolve()
    if not guard.inside(directory):guard.reject('pytest log directory outside sandbox')
    directory.mkdir(parents=True,exist_ok=True)
    logfile=(directory/'pytest.log').resolve()
    if not guard.inside(logfile):guard.reject('pytest log file outside sandbox')
    options=['--log-file='+str(logfile),'--log-file-mode=w']
    write_json(folder/'pytest-logging.json',dict(path=str(logfile),mode='w',explicit=True,inside_sandbox=True))
    return options

def interactive_desktop():
    import ctypes
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.OpenInputDesktop.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];user.OpenInputDesktop.restype=wintypes.HANDLE
    user.CloseDesktop.argtypes=[wintypes.HANDLE];user.CloseDesktop.restype=wintypes.BOOL
    user.GetSystemMetrics.argtypes=[ctypes.c_int];user.GetSystemMetrics.restype=ctypes.c_int
    handle=user.OpenInputDesktop(0,False,0x0001)
    if not handle:raise ValueError('Interactive input desktop unavailable; offscreen is not accepted')
    user.CloseDesktop(handle)
    return dict(interactive_desktop=True,desktop_size=[user.GetSystemMetrics(0),user.GetSystemMetrics(1)])

def main():
    if sys.platform!='win32':print('STOP: native Windows NOT RUN');return 2
    folder=Path(sys.argv[1]).resolve();case=sys.argv[2]
    if not folder.is_relative_to(ROOT/'results') or case not in CASES:raise ValueError('Invalid case/output')
    code=2;observer=None;guard=None
    receipt=dict(status='STOP',exit_code=2,case=case)
    faulthandler.enable(all_threads=True)
    try:
        from private_runtime import verify_private_runtime
        verify_private_runtime();receipt['source_before']=verify_source(ROOT)
        pins=read_json(ROOT/'requirements/pins.json');versions={k:metadata.version(k)for k in pins}
        if versions!=pins:raise ValueError('Pinned versions differ')
        receipt['versions']=dict(python=sys.version,dependencies=versions)
        receipt['desktop']=interactive_desktop()
        if os.environ.get('QT_QPA_PLATFORM')!='windows':raise ValueError('Real windows QPA required')
        from native_probe import check_native
        catalog=os.environ['L41_RUNTIME_CATALOG'];digest=os.environ['L41_RUNTIME_CATALOG_SHA256']
        receipt['native_before']=check_native(catalog,digest)
        (folder/'data').mkdir(exist_ok=False);os.chdir(folder/'data')
        from PySide6 import QtCore,QtNetwork,QtGui,QtMultimedia
        from gui_isolation import GuiIsolation,prepare_platform_diagnostics
        guard=GuiIsolation(folder,ROOT/'snapshot/tests')
        guard.read_only_metadata={ROOT/'harness/pytest.ini'}
        guard.install_qt(QtCore,QtNetwork);guard.install_native_boundaries(QtGui,QtMultimedia)
        # QDesktopServices uses native ShellExecute, outside Python audit hooks.
        # Only a synthetic directory may reach the original shell; media-file launch is recorded NOT RUN.
        desktop=[]
        def guarded_url(url):
            if not url.isLocalFile() or not guard.inside(url.toLocalFile()):guard.reject('QDesktopServices outside synthetic sandbox')
            path=Path(url.toLocalFile()).resolve()
            if path.is_dir():
                ok=bool(guard.original_open_url(url));desktop.append(dict(path=str(path),kind='synthetic-folder',real_dispatch=True,result=ok))
                write_json(folder/'desktop-services.json',desktop);return ok
            if path.suffix.lower()not in ('.mp3','.wav') or not path.is_file():guard.reject('Unapproved external media target')
            desktop.append(dict(path=str(path),kind='synthetic-media-request',real_dispatch=False,status='NOT RUN: uncontrolled default application'))
            write_json(folder/'desktop-services.json',desktop)
            return False  # Honest declined launch, never a fabricated success.
        QtGui.QDesktopServices.openUrl=guarded_url
        sys.addaudithook(guard.audit);sys.meta_path.insert(0,guard)
        sys.path[:0]=[str(ROOT/'snapshot/src'),str(ROOT/'snapshot/tests'),str(ROOT/'harness')]
        prepared=prepare_platform_diagnostics()
        write_json(folder/'diagnostics-preparation.json',prepared)
        receipt['versions']['windows']=prepared['windows_version']
        from observe import Observer
        observer=Observer(ROOT,folder);observer.install()
        from audio_library_organizer import crash_debug
        if crash_debug.initialize() is None:raise ValueError('Real crash/waveform diagnostics unavailable')
        # Qt native threads do not inherit threading.setprofile. Observe the unchanged ReadTask.run in situ.
        from audio_library_organizer.ui.workers import ReadTask
        original_run=ReadTask.run
        def observed_run(task):
            previous=sys.getprofile();sys.setprofile(observer.profile)
            try:return original_run(task)
            finally:sys.setprofile(previous)
        ReadTask.run=observed_run
        import pytest
        node='test_library41.py::test_native_library41['+case+']'
        os.environ['L41_CASE_DIR']=str(folder);os.environ['L41_CASE']=case
        receipt['stage']='pytest.logging.prepare'
        log_options=pytest_logging_options(folder,guard)
        receipt['stage']='pytest.initialization'
        class Evidence:
            @pytest.hookimpl(tryfirst=True)
            def pytest_runtest_call(self,item):
                receipt['stage']='pytest.call'
                write_json(folder/'case-started.json',dict(nodeid=item.nodeid,stage='pytest_runtest_call'))
            def pytest_collection_finish(self,session):
                names=[i.nodeid for i in session.items];write_json(folder/'collection.json',names)
                if names!=[node]:raise pytest.UsageError('Exactly one requested Library4.1 case required')
            def pytest_runtest_logreport(self,report):
                receipt['stage']='pytest.'+report.when+'.'+report.outcome
                with (folder/'phases.jsonl').open('a',encoding='utf-8')as f:
                    f.write(json.dumps(dict(nodeid=report.nodeid,phase=report.when,outcome=report.outcome,
                        duration_seconds=report.duration,wasxfail=bool(getattr(report,'wasxfail',False)),longrepr=str(report.longrepr)if report.longrepr else None))+'\n')
        code=int(pytest.main(['-c',str(ROOT/'harness/pytest.ini'),'--rootdir='+str(ROOT/'harness'),'--noconftest',
            '-p','no:cacheprovider','--basetemp='+str(folder/'data/tmp'),'-vv','--capture=tee-sys','--tb=short',
            '--junitxml='+str(folder/'results.xml'),*log_options,str(ROOT/'harness'/node)],plugins=[Evidence()]))
        ReadTask.run=original_run
        # QApplication has been destroyed by the fixture teardown before this point.
        observations=observer.finish();observer=None
        write_json(folder/'desktop-services.json',desktop)
        debug=Path(os.environ['ALO_CRASH_DEBUG_LOG'])
        events=[json.loads(line)for line in debug.read_text(encoding='utf-8').splitlines()if line.strip()]
        starts=[r for r in events if r.get('event')=='decoder.start']
        reaped=[r for r in events if r.get('event')=='decoder.reaped']
        faults=[r for r in events if r.get('event')in ('decoder.failed','decoder.unavailable','decoder.stop.request')]
        write_json(folder/'waveform-processes.json',dict(starts=starts,reaped=reaped,faults=faults))
        if faults or {r['child_pid']for r in starts}!={r['child_pid']for r in reaped} or any(r.get('exit_code')!=0 for r in reaped):
            raise ValueError('Waveform child failure, cancellation, missing reap, or native crash')
        if case in ('menu-source','menu-managed','managed-offline') and not starts:raise ValueError('Missing actual waveform execution')
        write_json(folder/'isolation.json',guard.evidence())
        receipt['source_after']=verify_source(ROOT);receipt['native_after']=check_native(catalog,digest)
        integrity=data_state(folder/'data');write_json(folder/'integrity.json',integrity)
        if observations['errors'] or observations['violations'] or guard.attempts:raise ValueError('Safety/observation failure')
        if code!=0:raise ValueError('GUI pytest failed; see phases and XML')
        receipt.update(status='PASS',exit_code=0);code=0
    except BaseException as error:
        code=2;receipt.update(status='STOP',error=repr(error))
        (folder/'child-error.log').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        if observer is not None:
            try:observer.finish()
            except BaseException as error:receipt['observation_error']=repr(error)
        if guard is not None:write_json(folder/'isolation.json',guard.evidence())
        receipt['exit_code']=code;write_json(folder/'child.json',receipt)
    return code
if __name__=='__main__':raise SystemExit(main())
