"""Remaining I1 real Qt lifecycle. Reuses established n2/PSS harness only.

No GUI layout change, forced GC, sleeps, timers, registry cleanup or tolerance.
D/E/F/G/H each use one warm and one measured real window in a fresh process.
Test-only gate fixture restores False; source gate is unchanged.
"""
from pathlib import Path
from collections import Counter
from threading import get_ident
import os,sys,time,json,weakref
import pytest,shiboken6
from PySide6.QtCore import QObject,Slot,QSettings,QThreadPool,QCoreApplication,QEvent,Qt
from PySide6.QtWidgets import QApplication
import n2_cases as original
import i1final_pss as i1base
from i1final_pss import monitor,record
from n2_cases import Receiver,observe_remaining_references
from n2_cases import library,mp3_samples,approve,assert_completed_observation,assert_no_output_confirmation
from n2_cases import handle_count,native,leases
from i1_post_refgraph import observe
pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Native Windows/NTFS I1 only')

class ScenarioReceiver(QObject):
    def __init__(self,window,mode,events,repository):
        super().__init__(window)
        self.window=weakref.ref(window);self.mode=mode;self.events=events
        self.repository=repository;self.gui_thread=get_ident()

    @Slot(object)
    def receive(self,result):
        window=self.window();lease=result.output_delivery.windows_lease
        assert get_ident()==self.gui_thread and shiboken6.isValid(window)
        assert lease.active and not lease.accepted
        assert not window._output_history and not window._output_session
        self.events.append(('queued',get_ident(),time.perf_counter()))
        record('queued-receiver',mode=self.mode,count=handle_count(),lease_active=lease.active)
        if self.mode=='destroy':
            record('destroy-before-accept',window=id(window),accepted=lease.accepted)
            shiboken6.delete(window)
        elif self.mode=='cancel-destroy':
            window._worker.cancel()
            assert not lease.active and not window._output_history and not window._output_session
            record('destroy-after-cancel',reason=lease.reason,accepted=lease.accepted)
            shiboken6.delete(window)
        elif self.mode=='quit':
            record('quit-before-positive-delivery',accepted=lease.accepted)
            QApplication.instance().quit()

    @Slot(object)
    def accept(self,result):
        assert get_ident()==self.gui_thread
        window=self.window()
        assert window is not None and shiboken6.isValid(window)
        if self.mode in ('destroy','cancel-destroy'):
            raise AssertionError('Dead receiver must not accept a queued result')
        if self.mode in ('timeout','quit'):
            assert not window._output_history and not window._output_session
            record('positive-delivery-not-consumed',mode=self.mode,accepted=result.output_delivery.windows_lease.accepted)
            return
        assert self.mode=='after-delivery'
        Receiver.accept(self,result)
        lease=result.output_delivery.windows_lease
        assert lease.accepted and not lease.active
        assert window._output_history and not window._output_session
        assert all(not h.evaluation.is_confirmed for h in window._output_history.values())
        record('destroy-after-real-accept',accepted=lease.accepted,history_confirmed=False)
        shiboken6.delete(window)

@pytest.mark.parametrize('scenario',['D','E','F','G','H'])
def test_lifecycle_matrix(library,monkeypatch,tmp_path,scenario,monitor):
    mode={'D':'after-delivery','E':'destroy','F':'cancel-destroy','G':'timeout','H':'quit'}[scenario]
    cycles=1
    i1base._monitor=monitor
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
    original_lease_close=leases.WindowsOutputLease.close;owner_closes=[]
    def observe_owner_close(owner):
        result=original_lease_close(owner)
        state={'owner':id(owner),'reason':owner.reason,'accepted':owner.accepted,'owned':owner.owned_count,'thread':get_ident()}
        owner_closes.append(state);record('owner-closed',**state)
        return result
    monkeypatch.setattr(leases.WindowsOutputLease,'close',observe_owner_close)
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
        receiver=ScenarioReceiver(window,mode,events,repo);destroyed=[];threads=[];emitted=[]
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
        start=time.perf_counter();before_db=len(db_opens);before_queued=len(events);before_owner_closes=len(owner_closes)
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
            if mode=='after-delivery':assert_completed_observation(window,track)
            else:assert_no_output_confirmation(window,track)
            if mode=='timeout':
                timeout_closes=[x for x in owner_closes[before_owner_closes:] if x['reason']=='DELIVERY_TIMEOUT' and x['owned']==0 and not x['accepted']]
                assert timeout_closes,'Current round did not close its owner after the actual delivery timeout'
                record('delivery-timeout-proved',reason='DELIVERY_TIMEOUT',owned=0)
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
    assert all(ref() is None for ref in window_refs)
    assert all(ref() is None for refs in i1_refs.values() for ref in refs)
    assert not live and Counter(opened)==Counter(closed)
    state=(pool.activeThreadCount(),pool.expiryTimeout(),pool.maxThreadCount())
    before=handle_count();record('equivalent-before',count=before,pool_state=state)
    counts=[]
    for index in range(1,cycles+1):
        roundtrip(index)
        observe(i1_refs,record,'after-normal-scope-'+str(index))
        assert all(ref() is None for ref in owner_refs)
        assert all(ref() is None for ref in window_refs)
        assert all(ref() is None for refs in i1_refs.values() for ref in refs)
        assert not live and Counter(opened)==Counter(closed)
        assert state==(pool.activeThreadCount(),pool.expiryTimeout(),pool.maxThreadCount())
        after=handle_count();counts.append(after)
        record('equivalent-after',count=after,pool_state=state,index=index,
            opened=len(opened),closed=len(closed),owners=len(owner_refs))
    steady=[e for e in monitor.events if e['phase'] in ('equivalent-before','equivalent-after')]
    assert len(steady)==cycles+1 and all(e['collector_delta']==0 for e in steady)
    for after in counts:i1base.strict_global_equal(before,after)
    inventory=[[(x['id'],x['type'],x['started_event'],x['lock']) for x in e['python_threads']] for e in steady]
    assert all(row==inventory[0] for row in inventory)
    summary={'status':'R2_SCENARIO_PASS_NOT_FULL_N2','scenario':scenario,'cycles_measured':cycles,
        'warm_windows':1,'before':before,'after_each':counts,
        'strict_global_equality':all(n==before for n in counts),
        'opened':len(opened),'closed':len(closed),'file_live':len(live),
        'owners':len(owner_refs),'owners_dead':all(x() is None for x in owner_refs),
        'gate_test_only':True,'forced_gc':False,'acceptance':True}
    (Path(os.environ['ALO_62D_EVIDENCE'])/'r2-summary.json').write_text(json.dumps(summary,indent=2)+'\n')



def test_multiple_operations_one_window(library,monkeypatch,tmp_path,monitor):
    scenario='B'
    mode='success'
    cycles=1
    i1base._monitor=monitor
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
    original_lease_close=leases.WindowsOutputLease.close;owner_closes=[]
    def observe_owner_close(owner):
        result=original_lease_close(owner)
        state={'owner':id(owner),'reason':owner.reason,'accepted':owner.accepted,'owned':owner.owned_count,'thread':get_ident()}
        owner_closes.append(state);record('owner-closed',**state)
        return result
    monkeypatch.setattr(leases.WindowsOutputLease,'close',observe_owner_close)
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
        window_refs.append(weakref.ref(window));i1_refs['page'].append(weakref.ref(window.library))
        record('r1-window-created',index=index,window=id(window),page=id(window.library))
        window.resize(1500,960);window.show();app.processEvents()
        receiver=Receiver(window,mode,events,repo)
        i1_refs['receiver'].append(weakref.ref(receiver));window._file_check_finished=receiver.accept
        destroyed=[];threads=[];emitted=[];result_ids=[];operation_ids=[];counts_same_window=[]
        before_db=len(db_opens);start=time.perf_counter()
        def operation(number):
            before_thread=len(threads);before_worker=len(destroyed);before_emit=len(emitted);before_queue=len(events)
            def init(worker,*a,**kw):
                original_init(worker,*a,**kw);wid=id(worker)
                i1_refs['worker'].append(weakref.ref(worker))
                worker.destroyed.connect(lambda *_:destroyed.append(('worker',wid,get_ident())),Qt.ConnectionType.DirectConnection)
                def emit(result):
                    emitted.append(get_ident());record('worker-emission',count=handle_count(),active=result.output_delivery.windows_lease.active)
                worker.finished.connect(emit,Qt.ConnectionType.DirectConnection)
                worker.finished.connect(receiver.receive,Qt.ConnectionType.QueuedConnection)
            with monkeypatch.context() as patch:
                patch.setattr(FileReconciliationWorker,'__init__',init)
                window.review_btn.click();thread=window._thread
                assert thread is not None
                i1_refs['thread'].append(weakref.ref(thread))
                thread.destroyed.connect(lambda *_:threads.append(get_ident()),Qt.ConnectionType.DirectConnection)
                drain_until(lambda:len(threads)==before_thread+1)
            app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            assert len(destroyed)==before_worker+1 and len(emitted)==before_emit+1
            assert emitted[-1]!=gui_thread and destroyed[-1][2]!=gui_thread and threads[-1]==gui_thread
            assert len(events)==before_queue+1 and events[-1][1]==gui_thread
            assert window._thread is None and window._worker is None
            assert_completed_observation(window,track)
            result=window.last_reconciliation_result;owner=result.output_delivery.windows_lease
            assert owner is owner_refs[-1]() and not owner.active and owner.owned_count==0
            result_ids.append(id(result));operation_ids.append(result.operation_id)
            record('same-window-result',index=index,operation=number,result=id(result),owner=id(owner),
                operation_id=result.operation_id,closed=True,accepted=owner.accepted,history_confirmed=False)
        for number in range(4):
            operation(number)  # all round-local Thread/worker/result references end here
            assert all(ref() is None for name in ('worker','thread') for ref in i1_refs[name])
            assert all(ref() is None for ref in owner_refs[:-1]) and owner_refs[-1]() is not None
            assert not live and Counter(opened)==Counter(closed)
            counts_same_window.append(handle_count())
            snapshot=monitor.take('same-window-after-operation',index=index,operation=number)
            assert snapshot['collector_delta']==0
            record('same-window-equivalent',index=index,operation=number,count=counts_same_window[-1],
                old_owners_dead=True,current_closed_owner_alive=True,
                result_retention_proof='Frozen result/output_delivery contains its owner; dead older owners imply dead older results')
        assert len(set(operation_ids))==4
        assert len(set(counts_same_window))==1,'Same-window operations grew global HANDLE count'
        window.close();window.deleteLater();assert pool.waitForDone(5000)
        app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert not shiboken6.isValid(window) and pool.activeThreadCount()==0
        record('round-complete',index=index,mode='B',operations=4,duration=time.perf_counter()-start,
            sqlite_connections_opened=len(db_opens)-before_db,worker_destroyed=destroyed,
            pool_active=pool.activeThreadCount(),pool_expiry=pool.expiryTimeout(),pool_max=pool.maxThreadCount(),
            file_live=len(live),count=handle_count(),same_window_counts=counts_same_window)
    monitor.take('r1-before-first-window')
    roundtrip(0)
    observe(i1_refs,record,'after-normal-scope-0')
    observe_remaining_references(owner_refs,window_refs)
    assert owner_refs and all(ref() is None for ref in owner_refs)
    assert all(ref() is None for ref in window_refs)
    assert all(ref() is None for refs in i1_refs.values() for ref in refs)
    assert not live and Counter(opened)==Counter(closed)
    state=(pool.activeThreadCount(),pool.expiryTimeout(),pool.maxThreadCount())
    before=handle_count();record('equivalent-before',count=before,pool_state=state)
    counts=[]
    for index in range(1,cycles+1):
        roundtrip(index)
        observe(i1_refs,record,'after-normal-scope-'+str(index))
        assert all(ref() is None for ref in owner_refs)
        assert all(ref() is None for ref in window_refs)
        assert all(ref() is None for refs in i1_refs.values() for ref in refs)
        assert not live and Counter(opened)==Counter(closed)
        assert state==(pool.activeThreadCount(),pool.expiryTimeout(),pool.maxThreadCount())
        after=handle_count();counts.append(after)
        record('equivalent-after',count=after,pool_state=state,index=index,
            opened=len(opened),closed=len(closed),owners=len(owner_refs))
    steady=[e for e in monitor.events if e['phase'] in ('equivalent-before','equivalent-after')]
    assert len(steady)==cycles+1 and all(e['collector_delta']==0 for e in steady)
    for after in counts:i1base.strict_global_equal(before,after)
    inventory=[[(x['id'],x['type'],x['started_event'],x['lock']) for x in e['python_threads']] for e in steady]
    assert all(row==inventory[0] for row in inventory)
    summary={'status':'R2_SCENARIO_PASS_NOT_FULL_N2','scenario':scenario,'cycles_measured':cycles,
        'warm_windows':1,'before':before,'after_each':counts,
        'strict_global_equality':all(n==before for n in counts),
        'opened':len(opened),'closed':len(closed),'file_live':len(live),
        'owners':len(owner_refs),'owners_dead':all(x() is None for x in owner_refs),
        'gate_test_only':True,'forced_gc':False,'acceptance':True}
    (Path(os.environ['ALO_62D_EVIDENCE'])/'r2-summary.json').write_text(json.dumps(summary,indent=2)+'\n')


