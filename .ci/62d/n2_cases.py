"""Additional N2 native lifetime evidence; not a replacement for original83.

Fresh real MainWindows on the same QApplication. No system input, PSS, fake
lease/API, forced GC, timing tolerance or synthetic sleep.
"""
from collections import Counter
from pathlib import Path
from threading import get_ident
import json,os,sqlite3,sys,time,weakref
import pytest,shiboken6
from PySide6.QtCore import QObject,Slot,Qt,QSettings,QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication
from audio_adoption_fixtures import mp3_samples
from test_legacy_adoption_v0427 import library
from test_adopted_output_spec_v0427 import approve
from test_output_session_ui_v0427 import pump,assert_completed_observation,assert_no_output_confirmation
from test_output_contract_windows_v0427 import handle_count
from audio_library_organizer.safety import windows_file_identity as native
from audio_library_organizer.safety import windows_output_lease as leases

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Native Windows/NTFS N2 only')

def record(kind,**data):
    p=Path(os.environ['ALO_62D_EVIDENCE'])/'n2-observations.jsonl'
    with p.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'kind':kind,'time':time.perf_counter(),'thread':get_ident(),**data})+'\n')

class Receiver(QObject):
    def __init__(self,window,mode,events,repository):
        super().__init__(window);self.window=weakref.ref(window);self.mode=mode;self.events=events
        self.repository=repository;self.gui_thread=get_ident()
    @Slot(object)
    def receive(self,result):
        window=self.window();self.events.append(('queued',get_ident(),time.perf_counter()))
        record('queued-receiver',mode=self.mode,count=handle_count(),
            lease_active=result.output_delivery.windows_lease.active)
        if self.mode=='cancel':window._worker.cancel()
        elif self.mode=='close':window.close()
        elif self.mode=='destroy':shiboken6.delete(window)
        elif self.mode=='quit':QApplication.instance().quit()
    @Slot(object)
    def accept(self,result):
        # A real GUI-affine QObject receiver is required here. A plain Python
        # callback can inherit sender context while the worker waits for ACK.
        from audio_library_organizer.ui.main_window import MainWindow
        assert get_ident()==self.gui_thread
        record('mainwindow-slot',mode=self.mode,count=handle_count())
        if self.mode=='timeout':return
        window=self.window()
        if self.mode=='busy':
            connection=sqlite3.connect(self.repository.database_path)
            try:
                connection.execute('BEGIN EXCLUSIVE')
                MainWindow._file_check_finished(window,result)
            finally:connection.rollback();connection.close()
        else:MainWindow._file_check_finished(window,result)

def observe_remaining_references(owner_refs,window_refs):
    """Read-only provenance after a failed-liveness boundary; no GC or cleanup.

    Temporary inspection references disappear on this function's normal return.
    The original immediate-liveness assertion remains unchanged afterwards.
    A cycle is evidence of a reference path, not proof it is the only referrer.
    """
    import gc
    for owner_ref in owner_refs:
        owner=owner_ref()
        if owner is None:continue
        links=[]
        for window_ref in window_refs:
            window=window_ref()
            if window is None:continue
            result=getattr(window,'last_reconciliation_result',None)
            delivery=getattr(result,'output_delivery',None)
            page=getattr(window,'library',None)
            links.append({'window':id(window),'window_native_valid':shiboken6.isValid(window),
                'library_native_valid':shiboken6.isValid(page) if page is not None else None,
                'window_last_result_contains_owner':getattr(delivery,'windows_lease',None) is owner,
                'window_library_provider_back_to_window':getattr(getattr(page,'_context_provider',None),'__self__',None) is window,
                'window_library_reader_back_to_window':getattr(getattr(page,'_context_worker_reader',None),'__self__',None) is window,
                'window_gc_tracked':gc.is_tracked(window),
                'receiver_has_weak_window':isinstance(getattr(getattr(window._file_check_finished,'__self__',None),'window',None),weakref.ReferenceType)})
        record('retained-owner-reference-path',owner=id(owner),owned=owner.owned_count,
            active=owner.active,reason=owner.reason,links=links,gc_enabled=gc.isenabled(),
            gc_count=gc.get_count(),gc_threshold=gc.get_threshold(),
            forced_gc=False,exclusive_cause_proven=False)

@pytest.mark.parametrize('mode',['success','cancel','timeout','busy','close','destroy','quit'])
def test_real_mainwindow_strict_lifetime(library,monkeypatch,tmp_path,mode):
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    from audio_library_organizer.domain.settings import AppSettings,LibraryPaths
    from audio_library_organizer.domain.preferences import AppPreferences
    assert native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    monkeypatch.setattr(native,'WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED',True)
    monkeypatch.setattr(main_window,'DashboardPage',DashboardPage)
    repo,root,track,_=library;approve(library)
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    pool=QThreadPool.globalInstance();gui_thread=get_ident()
    opened=[];closed=[];live={};owner_refs=[];window_refs=[];events=[];db_opens=[]
    original_open=native._WinAPI.open;original_close=native._WinAPI.close
    original_acquire=leases.acquire_output_lease;original_init=FileReconciliationWorker.__init__
    def observe_open(api,*a,**kw):
        h=original_open(api,*a,**kw);key=(id(api),h)
        assert key not in live;token=len(opened);live[key]=token;opened.append(token)
        record('file-open',token=token,handle=h,count=handle_count());return h
    def observe_close(api,h):
        key=(id(api),h);assert key in live,'Attempt to close an unobserved/already closed native handle'
        token=live[key];result=original_close(api,h)
        closed.append(token);del live[key];record('file-close',token=token,count=handle_count())
        return result
    def acquire(*a,**kw):
        start=time.perf_counter();owner=original_acquire(*a,**kw)
        assert get_ident()!=gui_thread
        owner_refs.append(weakref.ref(owner))
        record('acquired-pair',owner=id(owner),count=handle_count(),owned=owner.owned_count,
            acquire_seconds=time.perf_counter()-start)
        return owner
    def audit(name,args):
        if name=='sqlite3.connect/handle':db_opens.append(id(args[0]))
    sys.addaudithook(audit)
    monkeypatch.setattr(native._WinAPI,'open',observe_open)
    monkeypatch.setattr(native._WinAPI,'close',observe_close)
    monkeypatch.setattr(leases,'acquire_output_lease',acquire)
    def drain_until(predicate):
        end=time.monotonic()+15
        while not predicate() and time.monotonic()<end:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert predicate(),'Observed Qt teardown did not complete'
    # Round-local QObject references never enter the cross-round records.
    def roundtrip(index):
        store=QSettings(str(tmp_path/f'round-{index}.ini'),QSettings.Format.IniFormat)
        AppPreferences(language='pl',theme='dark').save(store)
        window=main_window.MainWindow(AppSettings((),LibraryPaths(root)),store)
        window_refs.append(weakref.ref(window))
        window.resize(1500,960);window.show();app.processEvents()
        receiver=Receiver(window,mode,events,repo);destroyed=[];threads=[];emitted=[]
        # Test-owned instance only. A MonkeyPatch undo list would retain the
        # original bound method/window across the cross-round weakref check.
        window._file_check_finished=receiver.accept
        def init(worker,*a,**kw):
            original_init(worker,*a,**kw);wid=id(worker)
            worker.destroyed.connect(lambda *_:destroyed.append(('worker',wid,get_ident())),Qt.ConnectionType.DirectConnection)
            def emit(result):
                emitted.append(get_ident());record('worker-emission',count=handle_count(),
                    active=result.output_delivery.windows_lease.active)
            worker.finished.connect(emit,Qt.ConnectionType.DirectConnection)
            worker.finished.connect(receiver.receive,Qt.ConnectionType.QueuedConnection)
        start=time.perf_counter();before_db=len(db_opens);before_queued=len(events)
        # Restore per-round worker constructor before the next window is made.
        with monkeypatch.context() as patch:
            patch.setattr(FileReconciliationWorker,'__init__',init)
            window.review_btn.click();thread=window._thread
            thread.destroyed.connect(lambda *_:threads.append(get_ident()),Qt.ConnectionType.DirectConnection)
            if mode=='quit':assert app.exec()==0
            drain_until(lambda:bool(threads))
        app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert emitted and all(t!=gui_thread for t in emitted)
        assert destroyed and all(t!=gui_thread for _,_,t in destroyed) and threads
        assert all(t==gui_thread for t in threads)
        assert len(events)==before_queued+1 and all(t==gui_thread for _,t,_ in events[before_queued:])
        if shiboken6.isValid(window):
            if mode=='success':assert_completed_observation(window,track)
            else:assert_no_output_confirmation(window,track)
            window.close();window.deleteLater()
        assert pool.waitForDone(5000)
        app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert not shiboken6.isValid(window) and pool.activeThreadCount()==0
        record('round-complete',index=index,mode=mode,duration=time.perf_counter()-start,
            sqlite_connections_opened=len(db_opens)-before_db,worker_destroyed=destroyed,
            pool_active=pool.activeThreadCount(),pool_expiry=pool.expiryTimeout(),
            pool_max=pool.maxThreadCount(),file_live=len(live),count=handle_count())
        # Return no owner, packet, QObject or bound method.
    roundtrip(0)
    observe_remaining_references(owner_refs,window_refs)
    # End of normal Python scope, not a destructor forced for the measurement.
    assert owner_refs and all(ref() is None for ref in owner_refs)
    assert not live and Counter(opened)==Counter(closed)
    state=(pool.activeThreadCount(),pool.expiryTimeout(),pool.maxThreadCount())
    before=handle_count();record('equivalent-before',count=before,pool_state=state)
    roundtrip(1)
    assert all(ref() is None for ref in owner_refs)
    assert not live and Counter(opened)==Counter(closed)
    assert state==(pool.activeThreadCount(),pool.expiryTimeout(),pool.maxThreadCount())
    after=handle_count();record('equivalent-after',count=after,pool_state=state,
        opened=len(opened),closed=len(closed),owners=len(owner_refs))
    assert before==after,'N2 equivalent MainWindow rounds did not preserve process HANDLE count'
