"""Remaining N2 boundaries; real Windows/NTFS/SQLite/Qt, no system cursor.

Only DACL and queued mutations touch owned synthetic files. API fault cases
are explicitly fault injection, never evidence of an actual OS malfunction.
"""
from contextlib import ExitStack,closing
from pathlib import Path
from threading import Event,get_ident
from uuid import uuid4
import ctypes as C
import hashlib,json,os,sqlite3,subprocess,sys,time,weakref
import pytest,shiboken6
from PySide6.QtCore import QObject,Signal,Slot,Qt,QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication
from test_windows_output_native_v0427 import diagnostic_window,record
from test_output_session_ui_v0427 import adopted_window,library,mp3_samples,run_check,pump,presentation
from test_output_contract_windows_v0427 import pair,owners,native_write_probe
from audio_library_organizer.safety import windows_file_identity as native
from audio_library_organizer.safety import windows_output_lease as leases
from n2final_dacl import deny

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Actual Windows x64/NTFS required')

def drain(predicate,seconds=15):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        QApplication.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    assert predicate(),'Bounded observed Qt operation did not finish'

@pytest.mark.parametrize('mode',['valid','read-only','write-denied','locked','unavailable','replace',
    'binding','library-uuid','track-uuid','source-uuid','wal','metadata','read-denied'])
def test_sqlite_delivery_boundaries(diagnostic_window,monkeypatch,mode):
    window,lib,binding=diagnostic_window;repo,root,track,output=lib
    database=repo.database_path;actual=window._accept_output_delivery;observed=[]
    original_audio=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (track.path,output)]
    def accept(result):
        delivery=result.output_delivery
        assert delivery is not None and delivery.windows_lease.active
        lease=delivery.windows_lease;before=native.capture(database,mutable=True)
        undo=lambda:None
        with ExitStack() as stack:
            try:
                if mode=='read-only':
                    database.chmod(0o444);undo=lambda:database.chmod(0o666)
                    with closing(sqlite3.connect(database)) as c:
                        with pytest.raises(sqlite3.OperationalError):
                            c.execute('UPDATE library_metadata SET library_id=library_id');c.commit()
                elif mode in ('write-denied','read-denied'):
                    stack.enter_context(deny(database,0x116 if mode=='write-denied' else 1))
                    with pytest.raises(sqlite3.OperationalError):
                        with closing(sqlite3.connect(database)) as c:
                            c.execute('UPDATE library_metadata SET library_id=library_id' if mode=='write-denied' else 'SELECT * FROM library_metadata').fetchall()
                elif mode=='locked':
                    c=stack.enter_context(closing(sqlite3.connect(database)));c.execute('BEGIN EXCLUSIVE')
                    stack.callback(c.rollback)
                elif mode in ('unavailable','replace'):
                    held=database.with_suffix('.held');database.rename(held)
                    if mode=='replace':database.write_bytes(held.read_bytes())
                    def restore():
                        if database.exists():database.unlink()
                        held.rename(database)
                    undo=restore
                    if mode=='replace':assert not native.same_database(before,native.capture(database,mutable=True))
                elif mode in ('binding','library-uuid','track-uuid','source-uuid','metadata'):
                    table,column,where,arg={
                        'binding':('managed_bindings','binding_id','binding_id',binding.binding_id),
                        'library-uuid':('library_metadata','library_id','singleton',1),
                        'track-uuid':('tracks','track_id','track_id',track.track_id),
                        'source-uuid':('tracks','source_id','track_id',track.track_id),
                        'metadata':('tracks','title','track_id',track.track_id)}[mode]
                    with closing(sqlite3.connect(database)) as c:
                        value=c.execute(f'SELECT {column} FROM {table} WHERE {where}=?',(arg,)).fetchone()[0]
                        changed=str(uuid4());c.execute(f'UPDATE {table} SET {column}=? WHERE {where}=?',(changed,arg));c.commit()
                    def restore():
                        with closing(sqlite3.connect(database)) as c:
                            c.execute(f'UPDATE {table} SET {column}=? WHERE {column}=?',(value,changed));c.commit()
                    undo=restore
                elif mode=='wal':
                    with closing(sqlite3.connect(database)) as c:
                        assert c.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
                        c.execute('UPDATE library_metadata SET library_id=library_id');c.commit()
                        checkpoint=c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                        assert checkpoint[0]==0
                        record('real-wal-checkpoint',result=checkpoint)
                start=time.perf_counter();actual(result);elapsed=time.perf_counter()-start
                expected=mode in ('valid','read-only','write-denied','wal')
                assert lease.accepted is expected,(mode,lease.accepted)
                assert not window._output_session
                assert bool(window._output_history) is expected
                assert all(not h.evaluation.is_confirmed for h in window._output_history.values())
                observed.append(mode)
                record('sqlite-queued-boundary',mode=mode,accepted=lease.accepted,
                    expected=expected,gui_recheck_seconds=elapsed,database_same_path=True)
            finally:undo()
    monkeypatch.setattr(window,'_accept_output_delivery',accept)
    run_check(window)
    assert observed==[mode]
    assert original_audio==[hashlib.sha256(p.read_bytes()).hexdigest() for p in (track.path,output)]
    with closing(sqlite3.connect(database)) as c:
        assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]

def test_new_interpreter_reopens_without_restoring_authority(diagnostic_window):
    window,lib,_=diagnostic_window;repo,root,track,_=lib
    run_check(window);assert window._output_history and not presentation(window,track).confirmed
    window.close();QApplication.processEvents()
    run=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('n2final_restart.py')),str(root),track.track_id],
        capture_output=True,text=True,timeout=60)
    folder=Path(os.environ['ALO_62D_EVIDENCE'])
    (folder/'restart.stdout.log').write_text(run.stdout);(folder/'restart.stderr.log').write_text(run.stderr)
    (folder/'restart.exit.txt').write_text(str(run.returncode))
    assert run.returncode==0,run.stderr
    data=json.loads(run.stdout.strip().splitlines()[-1])
    assert data['status']=='PASS' and data['pid']!=os.getpid() and data['library_id']==repo.library_id
    assert data['historical_P_restored'] is False and data['initial_H_entries']==0
    record('new-process-restart',**data)

class Receiver(QObject):
    def __init__(self,window):super().__init__(window);self.window=weakref.ref(window)
    @Slot(object)
    def accept(self,result):
        self.window()._file_check_finished(result)

@pytest.mark.parametrize('mode',['success','cancel','close','receiver-destroy','switch','binding','timeout','exception','quit'])
def test_active_qthread_boundaries(diagnostic_window,monkeypatch,mode,tmp_path):
    from audio_library_organizer.ui import workers
    from audio_library_organizer.audio import identity
    window,lib,binding=diagnostic_window;repo,root,track,output=lib
    app=QApplication.instance();app.setQuitOnLastWindowClosed(mode=='quit')
    entered=Event();release=Event();calls=[];gui=get_ident();ownerlist=[];destroyed=[];thread_done=[];frames=[]
    actual_decode=identity._decode;acquire=leases.acquire_output_lease
    def observe_acquire(*a,**kw):
        owner=acquire(*a,**kw);ownerlist.append(owner);return owner
    def busy_decode(path,decoder,cancelled):
        assert get_ident()!=gui
        if not ownerlist:
            return actual_decode(path,decoder,cancelled)
        with Path(path).open('rb') as f:
            frames.append(f.read(16));entered.set()
            assert release.wait(10),'GUI failed to release controlled active read'
            if mode=='exception':raise RuntimeError('synthetic worker decoder exception')
            return actual_decode(path,decoder,cancelled)
    monkeypatch.setattr(leases,'acquire_output_lease',observe_acquire)
    monkeypatch.setattr(identity,'_decode',busy_decode)
    receiver=None
    if mode in ('receiver-destroy','timeout'):
        receiver=Receiver(window)
        monkeypatch.setattr(window,'_file_check_finished',receiver.accept if mode=='receiver-destroy' else lambda r:None)
    if mode=='exception':
        actual_check=workers.check_library
        def fault(*a,**kw):actual_check(*a,**kw);raise RuntimeError('synthetic worker exception after real work')
        monkeypatch.setattr(workers,'check_library',fault)
    start=time.perf_counter();window.review_btn.click();thread=window._thread;worker=window._worker
    worker_thread=thread
    worker.destroyed.connect(lambda *_:destroyed.append(get_ident()),Qt.ConnectionType.DirectConnection)
    thread.finished.connect(lambda:thread_done.append(get_ident()),Qt.ConnectionType.DirectConnection)
    try:
        drain(entered.is_set)
        assert ownerlist and ownerlist[0].active and frames and worker.thread() is worker_thread
        assert not window._output_history and not window._output_session
        # Observable event-loop progress while actual worker read remains held.
        class Pulse(QObject):
            tick=Signal()
            @Slot()
            def heard(self):calls.append(get_ident())
        pulse=Pulse();pulse.tick.connect(pulse.heard,Qt.ConnectionType.QueuedConnection)
        pulse.tick.emit();drain(lambda:bool(calls));assert calls==[gui] and not release.is_set()
        if mode=='cancel':worker.cancel()
        elif mode=='close':window.close();assert worker._cancelled.is_set()
        elif mode=='receiver-destroy':shiboken6.delete(receiver)
        elif mode=='binding':
            with closing(sqlite3.connect(repo.database_path)) as c:
                c.execute('UPDATE managed_bindings SET binding_id=?',(str(uuid4()),));c.commit()
        elif mode=='switch':
            profile=window.library_registry.add_library('Only synthetic second library',(),tmp_path/'other-library')
            window.library_registry.activate(profile.profile_id);window._rebind_active_profile(profile)
            assert window.repository.library_id!=repo.library_id and worker._cancelled.is_set()
        release.set()
        if mode=='quit':
            class Quitter(QObject):
                go=Signal()
                @Slot()
                def stop(self):app.quit()
            quitter=Quitter();quitter.go.connect(quitter.stop,Qt.ConnectionType.QueuedConnection)
            quitter.go.emit();assert app.exec()==0
        drain(lambda:window._thread is None)
        assert thread_done and destroyed and all(t!=gui for t in destroyed)
        assert all(not o.active and o.owned_count==0 for o in ownerlist)
        assert not window._output_session
        if mode=='success':assert window._output_history
        else:assert not window._output_history
        assert all(not h.evaluation.is_confirmed for h in window._output_history.values())
        record('active-qthread-complete',mode=mode,work_thread=destroyed[0],gui_thread=gui,
            real_read=True,gui_pulses=len(calls),elapsed_seconds=time.perf_counter()-start,
            owned=[o.owned_count for o in ownerlist],accepted=[o.accepted for o in ownerlist],
            reasons=[o.reason for o in ownerlist],thread_finished=True,native_worker_destroyed=True)
    finally:
        release.set()
        if window._thread is not None:
            worker.cancel();thread.quit();assert thread.wait(15000)
        app.setQuitOnLastWindowClosed(False)

@pytest.mark.parametrize('which',[0,1])
def test_actual_dacl_refuses_pair_and_restores_access(pair,which):
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in pair]
    with deny(pair[which],1) as proof:
        with pytest.raises(PermissionError):pair[which].read_bytes()
        with pytest.raises(OSError) as error:leases.acquire_output_lease(*map(str,pair))
        assert error.value.winerror==5
        record('actual-DACL-pair-refusal',which=which,winerror=error.value.winerror,proof=proof)
    owner=leases.acquire_output_lease(*map(str,pair));owner.close()
    assert owner.owned_count==0 and before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in pair]

def test_sqlite_connection_lifetimes_and_timings(diagnostic_window,monkeypatch):
    window,lib,_=diagnostic_window;gui=get_ident();connect=sqlite3.connect
    opened=[];closed=[];live={};decode_threads=[];acquires=[];holds=[];queued=[]
    class Connection(sqlite3.Connection):
        def close(self):
            token=live.pop(id(self));closed.append(token)
            record('sqlite-close',token=token,thread=get_ident())
            return super().close()
    def observed(*a,**kw):
        kw['factory']=Connection;start=time.perf_counter();conn=connect(*a,**kw)
        token=len(opened);live[id(conn)]=token;opened.append(token)
        record('sqlite-open',token=token,thread=get_ident(),connect_seconds=time.perf_counter()-start)
        return conn
    monkeypatch.setattr(sqlite3,'connect',observed)
    from audio_library_organizer.audio import identity
    original=identity._decode
    def decode(*a,**kw):decode_threads.append(get_ident());return original(*a,**kw)
    monkeypatch.setattr(identity,'_decode',decode)
    original_acquire=leases.acquire_output_lease;original_close=leases.WindowsOutputLease.close
    def acquire(*a,**kw):
        start=time.perf_counter();owner=original_acquire(*a,**kw);acquires.append((id(owner),time.perf_counter(),time.perf_counter()-start));return owner
    def close(owner):
        if owner.owned_count:holds.append(time.perf_counter()-next(t for oid,t,_ in acquires if oid==id(owner)))
        return original_close(owner)
    monkeypatch.setattr(leases,'acquire_output_lease',acquire);monkeypatch.setattr(leases.WindowsOutputLease,'close',close)
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    init=FileReconciliationWorker.__init__;emitted=[]
    def observe_init(w,*a,**kw):
        init(w,*a,**kw)
        w.finished.connect(lambda _:emitted.append(time.perf_counter()),Qt.ConnectionType.DirectConnection)
    monkeypatch.setattr(FileReconciliationWorker,'__init__',observe_init)
    accept=window._accept_output_delivery
    def observed_accept(result):queued.append(time.perf_counter()-emitted[-1]);return accept(result)
    monkeypatch.setattr(window,'_accept_output_delivery',observed_accept)
    run_check(window)
    assert not live and opened and sorted(opened)==sorted(closed)
    assert decode_threads and all(t!=gui for t in decode_threads)
    assert holds and queued and window._output_history
    record('resource-performance',sqlite_open=len(opened),sqlite_close=len(closed),sqlite_live=0,
        acquire_seconds=[x[2] for x in acquires],hold_seconds=holds,qt_queue_seconds=queued,
        decode_off_gui=True,scope='One real selected operation; timings reported, no fabricated timing threshold')

@pytest.mark.parametrize('mode',['success','cancel','receiver-destroy','reader-error'])
def test_actual_readtask_pool(diagnostic_window,mode):
    from audio_library_organizer.jobs.managed_files import resolve_read_path,ReadPurpose
    from audio_library_organizer.ui.workers import ReadTask
    window,lib,_=diagnostic_window;repo,root,track,output=lib
    plan=resolve_read_path(repo.get_track(track.track_id),repo.read_context(root),ReadPurpose.AUDIO_PROPERTIES,generation=77)
    assert plan.locator==str(output),plan
    entered=Event();release=Event();cancel=Event();received=[];destroyed=[];threads=[];gui=get_ident()
    def reader(path):
        assert path==output and get_ident()!=gui
        with path.open('rb') as stream:
            value=stream.read(16);entered.set()
            assert release.wait(10),'GUI did not release the test read'
            if mode=='reader-error':raise OSError('controlled reader I/O error')
            return value
    class Sink(QObject):
        @Slot(int,object)
        def ready(self,generation,result):received.append((generation,result,get_ident()))
    sink=Sink(window);task=ReadTask(plan,reader,cancel)
    signals=task.signals
    assert signals.thread()==QApplication.instance().thread()
    signals.destroyed.connect(lambda *_:destroyed.append(get_ident()),Qt.ConnectionType.DirectConnection)
    signals.ready.connect(sink.ready,Qt.ConnectionType.QueuedConnection)
    pool=QThreadPool.globalInstance();pool.start(task)
    try:
        drain(entered.is_set);assert pool.activeThreadCount()>=1
        if mode=='cancel':cancel.set()
        elif mode=='receiver-destroy':shiboken6.delete(sink)
    finally:release.set()
    assert pool.waitForDone(15000)
    drain(lambda:bool(destroyed))
    assert not shiboken6.isValid(task),'Native autoDelete QRunnable must actually be destroyed'
    assert destroyed==[gui] and not shiboken6.isValid(signals)
    if mode in ('cancel','receiver-destroy'):assert not received
    else:
        assert len(received)==1 and received[0][0]==77 and received[0][2]==gui
        result=received[0][1]
        assert result.resolution.is_verified is (mode=='success')
    record('actual-QRunnable-teardown',mode=mode,native_QRunnable_destroyed=True,
        native_QObject_destroyed=True,QObject_destroy_thread=destroyed[0],gui_thread=gui,
        queued_deliveries=len(received),pool_active_end=pool.activeThreadCount())

def test_actual_invalid_close_api_and_missing_file(pair,tmp_path):
    api=native._WinAPI()
    with pytest.raises(OSError) as error:api.close(0)
    assert error.value.winerror==6
    missing=tmp_path/'does-not-exist.mp3'
    with pytest.raises(OSError) as missing_error:leases.acquire_output_lease(str(pair[0]),str(missing))
    assert missing_error.value.winerror in (2,3)
    owner=leases.acquire_output_lease(*map(str,pair));owner.close();assert not owner.active and owner.owned_count==0
    record('actual-native-api-refusals',invalid_CloseHandle=6,missing_CreateFileW=missing_error.value.winerror,
        scope='Invalid null handle, not a forced uncertain close of an owned live handle')

def test_real_ffmpeg_stderr_and_bounded_sample_of_temp_disk(tmp_path,monkeypatch):
    from audio_library_organizer.audio import identity
    ffmpeg=identity._find_decoder();assert ffmpeg
    broken=tmp_path/'only-synthetic-broken.mp3';broken.write_bytes(b'not an MP3')
    with pytest.raises(ValueError):
        identity._decode_windows([ffmpeg,'-v','error','-nostdin','-f','mp3','-i',str(broken),'-f','null','-'],lambda:False)
    actual=identity.tempfile.TemporaryFile;paths=[];sizes=[]
    def tempfile(*a,**kw):
        stream=actual(*a,**kw);original_close=stream.close
        def close():
            sizes.append(os.fstat(stream.fileno()).st_size);return original_close()
        stream.close=close;return stream
    monkeypatch.setattr(identity.tempfile,'TemporaryFile',tempfile)
    with pytest.raises(ValueError):
        identity._decode_windows([sys.executable,'-I','-c','import os;os.write(2,b"E"*(2*1024*1024))'],lambda:False)
    assert sizes==[2*1024*1024]
    record('bounded-disk-risk-observation',producer='controlled CPython child, NOT FFmpeg proof',
        producer_bytes=2*1024*1024,temporary_bytes=sizes[0],rejected=True,
        limitation='Production transport has no byte quota; sample producer is bounded, output disk usage is not')
