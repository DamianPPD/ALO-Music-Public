"""I1-R1 read-only observation, never an acceptance substitute.

Original n2_cases remains byte-identical. Reuses its exact MainWindow/workflow,
with 1/2/8 measured rounds after one warm window, no weak/close weakening.
Global inequality is recorded, not declared an accepted product PASS here.
"""
from pathlib import Path
from collections import Counter
from threading import get_ident
import os,sys,time,json,sqlite3,weakref,threading,traceback,inspect
import pytest,shiboken6
from PySide6.QtCore import QSettings,QThreadPool,QCoreApplication,QEvent,Qt
from PySide6.QtWidgets import QApplication
import n2_cases as original
from n2_cases import Receiver,record as original_record,observe_remaining_references
from n2_cases import library,mp3_samples,approve,assert_completed_observation,assert_no_output_confirmation
from n2_cases import handle_count,native,leases
from i1_post_refgraph import observe
from n1_cases import Monitor
_monitor=None

def record(kind,**data):
    if _monitor is not None and kind in ('r1-before-window','r1-window-created',
            'queued-receiver','mainwindow-slot','round-complete','equivalent-before','equivalent-after'):
        _monitor.take(kind,detail=data)
    original_record(kind,**data)

def active_threads():
    rows=[]
    for ident,t in dict(threading._active).items():
        started=getattr(t,'_started',None);cond=getattr(started,'_cond',None)
        lock=getattr(cond,'_lock',None)
        rows.append({'id':id(t),'ident':ident,'native_id':getattr(t,'_native_id',None),
            'type':type(t).__module__+'.'+type(t).__qualname__,
            'name':t.name,'started_event':id(started),'condition':id(cond),'lock':id(lock),
            'event_set':started.is_set() if started is not None else None})
    return rows

@pytest.fixture
def monitor(monkeypatch):
    # Load product Event aliases before the stdlib-only observation wrapper.
    from audio_library_organizer.ui import main_window
    m=Monitor();take=m.take;notes=[];constructing={}
    original_dummy=threading._DummyThread.__init__;original_event=threading.Event
    stdlib_source={name:inspect.getsource(obj) for name,obj in (
        ('_DummyThread',threading._DummyThread),('Thread.__init__',threading.Thread.__init__),
        ('current_thread',threading.current_thread),('Event',threading.Event))}
    def observed_take(phase,objects=(),**detail):
        event=take(phase,objects,**detail);event['python_threads']=active_threads();return event
    m.take=observed_take
    def event_factory(*args,**kwargs):
        tid=get_ident()
        if tid not in constructing:return original_event(*args,**kwargs)
        m.take('dummy-event-before',dummy=constructing[tid]['dummy'])
        event=original_event(*args,**kwargs)
        constructing[tid]['events'].append(weakref.ref(event))
        m.take('dummy-event-after',[('actual-stdlib-started-event',event)],
            dummy=constructing[tid]['dummy'],event=id(event),condition=id(event._cond),lock=id(event._cond._lock))
        return event
    def dummy_init(dummy,*args,**kwargs):
        tid=get_ident();assert tid not in constructing,'Recursive observer DummyThread construction'
        span={'dummy':id(dummy),'events':[]};constructing[tid]=span
        stack=[{'filename':x.filename,'line':x.lineno,'function':x.name,'code':x.line}
            for x in traceback.extract_stack()[:-1]]
        m.take('dummy-before',dummy=id(dummy),thread=tid)
        try:result=original_dummy(dummy,*args,**kwargs)
        finally:constructing.pop(tid)
        notes.append({'dummy':id(dummy),'thread':tid,'native_id':dummy.native_id,
            'event_ids':[id(x()) for x in span['events'] if x() is not None],
            'started_event':id(dummy._started),'condition':id(dummy._started._cond),
            'lock':id(dummy._started._cond._lock),'registered_in_active':threading._active.get(tid) is dummy,
            'event_is_exact_stdlib_class':type(dummy._started) is original_event,'stack':stack})
        m.take('dummy-after',[('actual-stdlib-DummyThread',dummy)],dummy=id(dummy),thread=tid)
        return result
    monkeypatch.setattr(threading,'Event',event_factory)
    monkeypatch.setattr(threading._DummyThread,'__init__',dummy_init)
    try:yield m
    finally:
        result={'scope':'I1-R1 self-process PSS + exact stdlib helper attribution; no arbitrary close',
            'pid':os.getpid(),'dll_sha256':m.dll_sha256,'events':m.events,
            'stdlib_source':stdlib_source,'dummy_constructions':notes,'final_python_threads':active_threads()}
        (m.folder/'r1-pss-observations.json').write_text(json.dumps(result,indent=2)+'\n')

@pytest.mark.parametrize('cycles',[1,2,8])
def test_readonly_mainwindow_pss(library,monkeypatch,tmp_path,cycles,monitor):
    mode='success'
    global _monitor
    _monitor=monitor
    monkeypatch.setattr(original,'record',record)
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
    i1_refs={name:[] for name in ('page','worker','thread','receiver')}
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
        record('r1-before-window',index=index)
        store=QSettings(str(tmp_path/f'round-{index}.ini'),QSettings.Format.IniFormat)
        AppPreferences(language='pl',theme='dark').save(store)
        window=main_window.MainWindow(AppSettings((),LibraryPaths(root)),store)
        record('r1-window-created',index=index,window=id(window),page=id(window.library))
        window_refs.append(weakref.ref(window))
        i1_refs['page'].append(weakref.ref(window.library))
        window.resize(1500,960);window.show();app.processEvents()
        receiver=Receiver(window,mode,events,repo);destroyed=[];threads=[];emitted=[]
        i1_refs['receiver'].append(weakref.ref(receiver))
        # Test-owned instance only. A MonkeyPatch undo list would retain the
        # original bound method/window across the cross-round weakref check.
        window._file_check_finished=receiver.accept
        def init(worker,*a,**kw):
            original_init(worker,*a,**kw);wid=id(worker)
            i1_refs['worker'].append(weakref.ref(worker))
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
            i1_refs['thread'].append(weakref.ref(thread))
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
    monitor.take('r1-before-first-window')
    roundtrip(0)
    observe(i1_refs,record,'after-normal-scope-0')
    observe_remaining_references(owner_refs,window_refs)
    assert owner_refs and all(ref() is None for ref in owner_refs)
    assert not live and Counter(opened)==Counter(closed)
    state=(pool.activeThreadCount(),pool.expiryTimeout(),pool.maxThreadCount())
    before=handle_count();record('equivalent-before',count=before,pool_state=state)
    counts=[]
    for index in range(1,cycles+1):
        roundtrip(index)
        observe(i1_refs,record,'after-normal-scope-'+str(index))
        assert all(ref() is None for ref in owner_refs)
        assert not live and Counter(opened)==Counter(closed)
        assert state==(pool.activeThreadCount(),pool.expiryTimeout(),pool.maxThreadCount())
        after=handle_count();counts.append(after)
        record('equivalent-after',count=after,pool_state=state,index=index,
            opened=len(opened),closed=len(closed),owners=len(owner_refs))
    steady=[e for e in monitor.events if e['phase'] in ('equivalent-before','equivalent-after')]
    assert len(steady)==cycles+1 and all(e['collector_delta']==0 for e in steady)
    summary={'status':'DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE','cycles_measured':cycles,
        'warm_windows':1,'before':before,'after_each':counts,
        'strict_global_equality':all(n==before for n in counts),
        'opened':len(opened),'closed':len(closed),'file_live':len(live),
        'owners':len(owner_refs),'owners_dead':all(x() is None for x in owner_refs),
        'gate_test_only':True,'forced_gc':False,'acceptance':False}
    (Path(os.environ['ALO_62D_EVIDENCE'])/'r1-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
