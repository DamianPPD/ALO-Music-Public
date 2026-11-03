"""Observations only for the original PL/EN test. No Slot or assertion replaced."""
from pathlib import Path
import ast,atexit,faulthandler,functools,json,os,sys,time,weakref
from _thread import allocate_lock,get_ident

class Observer:
    def __init__(self,folder,root):
        self.folder=Path(folder);self.root=Path(root);self.lock=allocate_lock();self.seq=0;self.seen=set();self.windows=[];self.patches=[]
        self.timer=None;self.beats=0;self.old_trace=None;self.labels={};self.t0=time.monotonic()
        self.fd=os.open(self.folder/'timeout39-checkpoints.jsonl',os.O_CREAT|os.O_WRONLY|os.O_APPEND,0o600)
        self.stacks=(self.folder/'python-stacks-before-timeout.log').open('wb',buffering=0)
        atexit.register(self.process_exit)
    def emit(self,stage,**kw):
        with self.lock:
            self.seq+=1;self.seen.add(stage)
            b=(json.dumps(dict(seq=self.seq,seconds=time.monotonic()-self.t0,pid=os.getpid(),thread=get_ident(),stage=stage,**kw),default=str)+'\n').encode()
            os.write(self.fd,b)
    def process_exit(self):self.emit('process.exit',note='QApplication process lifetime ends here; no forced quit added')
    def snapshot(self):
        from PySide6.QtWidgets import QApplication
        from shiboken6 import isValid
        states=[]
        for ref in self.windows:
            w=ref()
            if w is None or not isValid(w):continue
            t=getattr(w,'_thread',None)
            states.append(dict(visible=w.isVisible(),thread_present=t is not None,
                thread_running=t.isRunning()if t is not None and isValid(t)else None,
                result_present=getattr(w,'last_reconciliation_result',None)is not None))
        modal=QApplication.activeModalWidget()
        return dict(windows=states,modal=None if modal is None else dict(type=type(modal).__name__,title=modal.windowTitle()))
    def heartbeat(self):
        self.beats+=1;state=self.snapshot();self.emit('Qt.event-loop.alive',heartbeat=self.beats,**state)
        if self.beats==5 and state['modal'] is not None:
            from PySide6.QtWidgets import QApplication
            QApplication.activeModalWidget().grab().save(str(self.folder/'synthetic-modal-at-5s.png'))
    def ensure_timer(self,window):
        if not any(r()is window for r in self.windows):self.windows.append(weakref.ref(window))
        if self.timer is not None:return
        from PySide6.QtCore import QTimer,Qt
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance()
        self.timer=QTimer(app);self.timer.setInterval(1000)
        self.timer.timeout.connect(self.heartbeat,Qt.ConnectionType.DirectConnection);self.timer.start()
        app.aboutToQuit.connect(lambda:self.emit('QApplication.aboutToQuit'),Qt.ConnectionType.DirectConnection)
        self.emit('QApplication.observed',explicit_exec_used=False,heartbeat='observational 1s; no test condition/deadline modified')
    def trace(self,frame,event,arg):
        mod=frame.f_globals.get('__name__','');name=frame.f_code.co_name
        main_names={'__init__','refresh_data','_check_library_clicked','_file_check_finished','_consume_file_check_result','_accept_output_delivery','_file_check_thread_done','closeEvent','_stop_file_check_on_quit'}
        test_names={'test_diagnostic_real_mp3_worker_mainwindow_column_filter_sort','test_real_check_reaches_column_filter_sort_and_survives_selection_refresh','run_check','pump','adopted_window'}
        wanted=(mod=='audio_library_organizer.ui.main_window'and name in main_names
            or mod=='audio_library_organizer.ui.library_page'and name in('select_track','refresh','_file_filter_changed')
            or mod=='audio_library_organizer.ui.i18n'and name=='apply_static_language'
            or mod in('test_output_session_ui_v0427','test_windows_output_native_v0427')and name in test_names)
        if not wanted:return None
        if event=='call':
            self.emit('python.enter',function=mod+'.'+name,line=frame.f_lineno)
            if mod=='audio_library_organizer.ui.main_window'and name=='__init__'and type(frame.f_locals.get('self')).__name__=='MainWindow':
                self.emit('MainWindow.create.begin');self.ensure_timer(frame.f_locals['self'])
            frame.f_trace_lines=frame.f_code.co_filename in self.labels and name in test_names
            return self.local_trace
        return None
    def local_trace(self,frame,event,arg):
        mod=frame.f_globals.get('__name__','');name=frame.f_code.co_name
        if event=='line':
            label=self.labels.get(frame.f_code.co_filename,{}).get(frame.f_lineno)
            if label:self.emit('test.statement',function=name,line=frame.f_lineno,statement=label)
        elif event=='return':
            self.emit('python.return',function=mod+'.'+name,line=frame.f_lineno)
            if mod=='audio_library_organizer.ui.main_window':
                if name=='__init__'and type(frame.f_locals.get('self')).__name__=='MainWindow':self.emit('MainWindow.create.end')
                if name=='_file_check_finished':self.emit('MainWindow.result.received.end')
                if name=='_file_check_thread_done':self.emit('QThread.GUI-finished-slot.end')
                if name=='closeEvent':self.emit('MainWindow.close.end')
                if name=='_check_library_clicked':
                    from PySide6.QtCore import Qt
                    from shiboken6 import isValid
                    w=frame.f_locals.get('self');t=getattr(w,'_thread',None)
                    if t is not None and isValid(t):
                        ident=id(t);t.finished.connect(lambda:self.emit('QThread.finished.signal',object_id=ident),Qt.ConnectionType.DirectConnection)
                    self.emit('worker.start.request.returned',thread_present=t is not None)
        elif event=='exception':self.emit('python.exception',function=mod+'.'+name,line=frame.f_lineno,type=arg[0].__name__)
        return self.local_trace
    def wrap(self,obj,name,label):
        original=getattr(obj,name)
        @functools.wraps(original)
        def observed(*a,**kw):
            started=time.monotonic();self.emit(label+'.begin')
            try:value=original(*a,**kw)
            except BaseException as e:self.emit(label+'.error',type=type(e).__name__);raise
            self.emit(label+'.end',elapsed=time.monotonic()-started)
            return value
        setattr(obj,name,observed);self.patches.append((obj,name,original))
    def start(self):
        self.emit('observer.start',stack_dump_seconds=150,process_timeout_seconds=180)
        faulthandler.dump_traceback_later(150,repeat=False,file=self.stacks,exit=False)
        # This does not replace any Qt Slot or change its metaobject/affinity.
        from audio_library_organizer.storage.repository import LibraryRepository
        from audio_library_organizer.safety import windows_output_lease as leases
        from audio_library_organizer.audio import identity
        from audio_library_organizer.ui.workers import FileReconciliationWorker
        from PySide6.QtCore import Qt
        self.wrap(LibraryRepository,'file_check_snapshot','SQLite.file_check_snapshot')
        self.wrap(LibraryRepository,'adopted_assessment_snapshot','SQLite.adopted_snapshot')
        self.wrap(leases,'acquire_output_lease','SOURCE_MANAGED.protection')
        self.wrap(leases.WindowsOutputLease,'close','SOURCE_MANAGED.release')
        self.wrap(identity,'inspect_audio','audio.inspect_audio')
        original=FileReconciliationWorker.__init__
        @functools.wraps(original)
        def init(worker,*a,**kw):
            original(worker,*a,**kw);identifier=id(worker)
            self.emit('worker.created',object_id=identifier)
            worker.progress.connect(lambda *args:self.emit('worker.progress.signal',object_id=identifier),Qt.ConnectionType.DirectConnection)
            worker.finished.connect(lambda result:self.emit('worker.finished.signal',object_id=identifier,has_delivery=getattr(result,'output_delivery',None)is not None),Qt.ConnectionType.DirectConnection)
            worker.failed.connect(lambda *args:self.emit('worker.failed.signal',object_id=identifier),Qt.ConnectionType.DirectConnection)
            worker.destroyed.connect(lambda *args:self.emit('worker.destroyed.signal',object_id=identifier),Qt.ConnectionType.DirectConnection)
        FileReconciliationWorker.__init__=init;self.patches.append((FileReconciliationWorker,'__init__',original))
        for name in('test_output_session_ui_v0427.py','test_windows_output_native_v0427.py'):
            path=self.root/'tests'/name;text=path.read_text(encoding='utf-8');labels={}
            for node in ast.walk(ast.parse(text)):
                if isinstance(node,ast.FunctionDef)and node.name in('test_real_check_reaches_column_filter_sort_and_survives_selection_refresh','test_diagnostic_real_mp3_worker_mainwindow_column_filter_sort'):
                    for stmt in node.body:labels[stmt.lineno]=ast.get_source_segment(text,stmt).splitlines()[0][:180]
            self.labels[str(path)]=labels
        self.old_trace=sys.gettrace()
        if self.old_trace is not None:raise RuntimeError('Existing tracer: observational timeout instrumentation not installed')
        sys.settrace(self.trace)
    def stop(self):
        sys.settrace(self.old_trace);faulthandler.cancel_dump_traceback_later()
        if self.timer is not None:self.timer.stop()
        for obj,name,original in reversed(self.patches):setattr(obj,name,original)
        self.emit('observer.stop',heartbeats=self.beats)
        (self.folder/'timeout39-observer-summary.json').write_text(json.dumps({'seen':sorted(self.seen),'heartbeats':self.beats,
            'stacks_written':self.stacks.tell()>0,'product_edited':False,'forced_quit_added':False},indent=2))


def instrument(n,folder):
    # The original child reads GO and installs callback hooks before invoking
    # this wrapper. A parent JobObject is already assigned at that boundary.
    original_install=n.base.install_callback_observer
    def installed(path):
        result=original_install(path)
        import pytest
        original_phases=n.base.old.Phases
        class Phases(original_phases):
            def __init__(self,folder):super().__init__(folder);self.observer=Observer(folder,n.base.ROOT)
            @pytest.hookimpl(hookwrapper=True,tryfirst=True)
            def pytest_runtest_setup(self,item):
                self.observer.start();self.observer.emit('setup.begin');yield;self.observer.emit('setup.end')
            @pytest.hookimpl(hookwrapper=True,tryfirst=True)
            def pytest_runtest_call(self,item):
                self.observer.emit('call.begin');yield;self.observer.emit('call.end')
            @pytest.hookimpl(hookwrapper=True,tryfirst=True)
            def pytest_runtest_teardown(self,item):
                self.observer.emit('teardown.begin');yield;self.observer.emit('teardown.end')
            def pytest_unconfigure(self,config):self.observer.stop()
        n.base.old.Phases=Phases
        return result
    n.base.install_callback_observer=installed
