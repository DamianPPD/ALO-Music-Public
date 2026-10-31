"""Native Windows/NTFS contract tests. Only real synthetic MP3 and SQLite.

No system cursor, fake token, fake evaluator or production gate activation.
Pure fault injections are identified separately from actual OS refusals.
"""
from contextlib import contextmanager
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import ctypes as C
import hashlib
import os
import subprocess
import sys
import time
import pytest
import shiboken6
from PySide6.QtCore import Qt,QSettings,QObject,Slot
from PySide6.QtWidgets import QApplication
from audio_adoption_fixtures import mp3_samples,copy_audio
from test_legacy_adoption_v0427 import library
from test_adopted_output_spec_v0427 import approve
from test_output_session_ui_v0427 import adopted_window,run_check,pump,presentation,assert_completed_observation,assert_no_output_confirmation
from test_windows_output_native_v0427 import diagnostic_window,record
from audio_library_organizer.safety import windows_file_identity as native
from audio_library_organizer.safety import windows_output_lease as leases

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Real Windows x64/NTFS contract; no Linux native claim')


def handle_count():
    k=C.WinDLL('kernel32',use_last_error=True)
    k.GetCurrentProcess.argtypes=[];k.GetCurrentProcess.restype=C.c_void_p
    k.GetProcessHandleCount.argtypes=[C.c_void_p,C.POINTER(C.c_uint32)];k.GetProcessHandleCount.restype=C.c_int32
    n=C.c_uint32()
    if not k.GetProcessHandleCount(k.GetCurrentProcess(),C.byref(n)):raise C.WinError(C.get_last_error())
    return n.value


@pytest.fixture
def pair(tmp_path,mp3_samples,monkeypatch):
    assert native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    monkeypatch.setattr(native,'WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED',True)
    return (copy_audio(mp3_samples['original'],tmp_path/'source'/'Source.mp3'),
        copy_audio(mp3_samples['original'],tmp_path/'library'/'GOTOWE'/'Managed.mp3'))


@pytest.fixture
def owners(monkeypatch):
    actual=leases.acquire_output_lease;seen=[]
    def observe(*a,**kw):
        owner=actual(*a,**kw);seen.append(owner);return owner
    monkeypatch.setattr(leases,'acquire_output_lease',observe)
    yield seen
    assert all(not o.active and o.owned_count==0 for o in seen)
    record('actual-owner-teardown',owners=len(seen),owned_end=[o.owned_count for o in seen])


@pytest.mark.parametrize('which',[0,1])
@pytest.mark.parametrize('action',['write','same-size','restored-mtime','delete','rename','replace'])
def test_real_lease_blocks_content_and_namespace_mutation(pair,tmp_path,which,action):
    p=pair[which];before=p.read_bytes();stamp=p.stat();replacement=tmp_path/'replacement.mp3'
    if action=='replace':replacement.write_bytes(before)
    changed=bytearray(before);changed[-16]^=0x5a
    def perform():
        if action=='write':
            with p.open('r+b',buffering=0) as stream:assert stream.write(b'X')==1
        elif action in ('same-size','restored-mtime'):
            with p.open('r+b',buffering=0) as stream:assert stream.write(changed)==len(changed)
            if action=='restored-mtime':os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        elif action=='delete':p.unlink()
        elif action=='rename':p.rename(p.with_name('renamed.mp3'))
        else:os.replace(replacement,p)
    owner=leases.acquire_output_lease(*map(str,pair))
    try:
        assert owner.active and owner.active_for(tuple(map(str,pair)),owner.material)
        with pytest.raises(OSError) as denied:
            perform()
        assert denied.value.winerror in (5,32)
        assert p.read_bytes()==before
        assert owner.active
        record('protected-mutation-refused',which=which,action=action,winerror=denied.value.winerror,
            before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            material=[asdict(x) for x in owner.material])
    finally:owner.close()
    assert owner.owned_count==0 and not owner.active
    # The SAME operation succeeds without protection, isolating the cause.
    perform()
    if action in ('write','same-size','restored-mtime'):
        assert p.read_bytes()!=before
        if action!='write':assert p.stat().st_size==stamp.st_size
        if action=='restored-mtime':assert p.stat().st_mtime_ns==stamp.st_mtime_ns
        record('post-release-content-mutation',action=action,which=which,
            before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            size_before=stamp.st_size,size_after=p.stat().st_size,mtime_before=stamp.st_mtime_ns,
            mtime_after=p.stat().st_mtime_ns,proof_after=asdict(native.capture(p)))
    elif action=='delete':assert not p.exists()
    elif action=='rename':
        target=p.with_name('renamed.mp3')
        assert not p.exists() and target.read_bytes()==before
    else:
        old_id=owner.material[which].leaf.file_id
        assert not replacement.exists() and p.read_bytes()==before
        assert native.capture(p).leaf.file_id!=old_id
    record('same-mutation-succeeds-after-release',action=action,which=which,owned=0)


@pytest.mark.parametrize('which',[0,1])
def test_real_existing_writer_refuses_entire_pair(pair,which):
    with pair[which].open('r+b'):
        with pytest.raises(OSError) as denied:leases.acquire_output_lease(*map(str,pair))
        assert denied.value.winerror==32
    owner=leases.acquire_output_lease(*map(str,pair));owner.close()
    assert owner.owned_count==0
    record('existing-writer-pair-refusal',which=which,error=32,accepted_after_writer_closed=True)


@contextmanager
def writable_section(path,kind):
    api=native._WinAPI();k=api.k;ptr=C.c_void_p;u32=C.c_uint32
    mapping=k.CreateFileMappingW;mapping.argtypes=[ptr,ptr,u32,u32,u32,C.c_wchar_p];mapping.restype=ptr
    view=k.MapViewOfFile;view.argtypes=[ptr,u32,u32,u32,C.c_size_t];view.restype=ptr
    unmap=k.UnmapViewOfFile;unmap.argtypes=[ptr];unmap.restype=C.c_int32
    h=api.create(str(path),0xC0000000,7,None,3,0x00200000,None);section=None;address=None
    if h in (None,C.c_void_p(-1).value):raise C.WinError(C.get_last_error())
    try:
        section=mapping(h,None,4,0,0,None)
        if not section:raise C.WinError(C.get_last_error())
        if kind!='section-only':
            address=view(section,6,0,0,0)
            if not address:raise C.WinError(C.get_last_error())
        api.close(h);h=None
        if kind=='view-only':api.close(section);section=None
        yield
    finally:
        if address and not unmap(address):raise C.WinError(C.get_last_error())
        if section:api.close(section)
        if h:api.close(h)


@pytest.mark.parametrize('which',[0,1])
@pytest.mark.parametrize('kind',['section-only','view-and-section','view-only'])
def test_real_writable_mapping_refuses_entire_pair(pair,which,kind):
    before=pair[which].read_bytes()
    with writable_section(pair[which],kind):
        with pytest.raises(OSError) as denied:leases.acquire_output_lease(*map(str,pair))
        assert denied.value.winerror==32
    assert pair[which].read_bytes()==before
    owner=leases.acquire_output_lease(*map(str,pair));owner.close()
    assert owner.owned_count==0
    record('writable-mapping-pair-refusal',which=which,kind=kind,writer_file_handle_closed=True,error=32)


def test_real_hardlink_is_refused_without_modifying_either_alias(pair,tmp_path):
    other=tmp_path/'alias.mp3';os.link(pair[1],other);before=pair[1].read_bytes()
    with pytest.raises(ValueError):leases.acquire_output_lease(*map(str,pair))
    assert pair[1].read_bytes()==other.read_bytes()==before
    record('hardlink-pair-refusal',links=pair[1].stat().st_nlink)


def test_real_junction_is_refused_without_opening_the_target_leaf(pair,tmp_path):
    target=pair[0].parent;junction=tmp_path/'junction'
    for p in (target,junction):assert not any(c in str(p) for c in '&|<>"%^!\r\n')
    result=subprocess.run([str(Path(os.environ['SystemRoot'])/'System32'/'cmd.exe'),'/d','/c',
        'mklink','/J',str(junction),str(target)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    before=pair[0].read_bytes()
    try:
        with pytest.raises((OSError,ValueError)):
            leases.acquire_output_lease(str(junction/pair[0].name),str(pair[1]))
        assert pair[0].read_bytes()==before
    finally:os.rmdir(junction)
    record('junction-pair-refusal',target_unchanged=True)


def test_native_owner_has_zero_process_handle_delta_after_complete_close(pair,monkeypatch):
    actual=native._WinAPI;seen=[]
    class ObservedAPI(actual):
        def __init__(self):super().__init__();self.opened=[];self.closed=[];seen.append(self)
        def open(self,*a,**kw):
            h=super().open(*a,**kw);self.opened.append(h);return h
        def close(self,h):super().close(h);self.closed.append(h)
    monkeypatch.setattr(native,'_WinAPI',ObservedAPI)
    warm=leases.acquire_output_lease(*map(str,pair));warm.close();handle_count()
    before=handle_count()
    for _ in range(8):
        owner=leases.acquire_output_lease(*map(str,pair));owner.close();assert owner.owned_count==0
    after=handle_count()
    assert all(Counter(a.opened)==Counter(a.closed) for a in seen)
    assert before==after,'Native owner handle count did not return after close'
    record('native-owner-no-leak',before=before,after=after,cycles=8,
        opened=sum(len(a.opened) for a in seen),closed=sum(len(a.closed) for a in seen))


def test_native_partial_acquire_query_fault_closes_every_actual_handle(pair,monkeypatch):
    actual=native._WinAPI;opened=[];closed=[]
    class FaultAPI(actual):
        def open(self,*a,**kw):
            h=super().open(*a,**kw);opened.append(h);return h
        def query(self,h):
            if len(opened)==3:raise OSError('controlled query fault after real CreateFile')
            return super().query(h)
        def close(self,h):super().close(h);closed.append(h)
    monkeypatch.setattr(native,'_WinAPI',FaultAPI)
    with pytest.raises(OSError,match='controlled query fault'):leases.acquire_output_lease(*map(str,pair))
    assert Counter(opened)==Counter(closed)
    record('native-handles-query-fault-injection',injected_query_error=True,opened=len(opened),closed=len(closed))


@pytest.mark.parametrize('language',['pl','en'])
def test_history_is_useful_non_authoritative_and_new_check_is_async(diagnostic_window,monkeypatch,owners,language):
    from dataclasses import replace,fields
    from audio_library_organizer.ui.i18n import apply_static_language
    window,lib,binding=diagnostic_window;repo,_,track,_=lib
    window.preferences=replace(window.preferences,language=language);apply_static_language(window.library,language)
    actual_accept=window._accept_output_delivery;claims=[]
    def observe(result):
        actual_accept(result)
        d=result.output_delivery
        claims.append({'active':d.windows_lease.active,'claimed':d.windows_lease.accepted,
            'history_confirmed':window._output_history[track.track_id].evaluation.is_confirmed,
            'session_entries':len(window._output_session)})
    monkeypatch.setattr(window,'_accept_output_delivery',observe)
    run_check(window);assert_completed_observation(window,track)
    first=window.last_reconciliation_result.operation_id
    h=window._output_history[track.track_id]
    assert not {'lease','delivery','windows_lease','pending','handles'} & {f.name for f in fields(h)}
    for _ in range(3):window.refresh_data()
    assert_completed_observation(window,track)
    window.library.file_filter.setCurrentIndex(window.library.file_filter.findData('NEEDS_UPDATE'))
    window.library.table.sortByColumn(10,Qt.SortOrder.AscendingOrder)
    assert window.library.model.rowCount()==1
    expected='Needs update · Unconfirmed' if language=='en' else 'Do aktualizacji · Niepotwierdzony'
    assert window.library.model.item(0,10).text()==expected
    assert ('rechecking required' if language=='en' else 'ponownej kontroli') in window.library.model.item(0,10).toolTip()
    assert len(owners)==1,'Pure refresh/filter/sort started a new assessment'
    run_check(window);assert_completed_observation(window,track)
    assert window.last_reconciliation_result.operation_id!=first and len(owners)==2
    assert claims and all(c=={'active':True,'claimed':True,'history_confirmed':False,'session_entries':0} for c in claims)
    assert repo.list_managed_bindings()==(binding,)
    record('persistent-history-and-fresh-check',language=language,claims=claims,
        cell_text=window.library.model.item(0,10).text(),operation_ids=[first,window.last_reconciliation_result.operation_id],
        own_counts=[o.owned_count for o in owners])
    target=os.environ.get('ALO_62D_EVIDENCE')
    if target:window.library.grab().save(str(Path(target)/('history-'+language+'.png')))


@pytest.mark.parametrize('which',['source','managed'])
def test_failed_recheck_removes_old_history_and_uses_fallback(diagnostic_window,owners,which):
    window,lib,_=diagnostic_window;_,_,track,managed=lib
    run_check(window);assert_completed_observation(window,track)
    p=track.path if which=='source' else managed
    with p.open('r+b'):
        window.review_btn.click();pump(lambda:window._thread is None)
    assert_no_output_confirmation(window,track)
    assert len(owners)==1,'Failed second acquisition must not return a partial owner'
    record('failed-recheck-fallback',which=which,history_entries=len(window._output_history),owners=len(owners))


@pytest.mark.parametrize('which',['source','managed'])
def test_true_postrelease_same_size_restored_mtime_never_renews_authority(diagnostic_window,owners,which):
    window,lib,_=diagnostic_window;_,_,track,managed=lib
    run_check(window);assert_completed_observation(window,track)
    d=window.last_reconciliation_result.output_delivery
    p=track.path if which=='source' else managed;before=p.read_bytes();stamp=p.stat()
    raw=bytearray(before);raw[-16]^=0x5a
    with p.open('r+b',buffering=0) as stream:assert stream.write(raw)==len(raw)
    os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert p.read_bytes()!=before and p.stat().st_size==stamp.st_size and p.stat().st_mtime_ns==stamp.st_mtime_ns
    fresh=native.capture(p)
    window.refresh_data()  # No event pump before the synchronous authority check.
    assert not presentation(window,track).confirmed and not window._output_session
    assert not d.windows_lease.active and d.windows_lease.owned_count==0
    pump(lambda:track.track_id not in window._output_history)
    assert_no_output_confirmation(window,track)
    record('true-postrelease-restored-mtime',which=which,sha_before=hashlib.sha256(before).hexdigest(),
        sha_after=hashlib.sha256(p.read_bytes()).hexdigest(),size=p.stat().st_size,mtime_restored=True,
        protected_proof=asdict(d.windows_material[0 if which=='source' else 1]),post_proof=asdict(fresh),
        native_token_equal=fresh==d.windows_material[0 if which=='source' else 1],
        current_confirmation=False,history_cleared_by_observed_change=True)


def test_two_bindings_only_assess_the_selected_record(diagnostic_window,mp3_samples,owners):
    from test_output_session_ui_v0427 import test_two_real_approved_bindings_are_checked_by_selection_without_mixing
    test_two_real_approved_bindings_are_checked_by_selection_without_mixing(diagnostic_window,mp3_samples)
    assert len(owners)==2 and all(o.owned_count==0 for o in owners)


def test_abandoned_receiver_times_out_then_rejects_late_packet(diagnostic_window,monkeypatch,owners):
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    window,lib,_=diagnostic_window;_,_,track,_=lib;packets=[];actual_init=FileReconciliationWorker.__init__
    def init(w,*a,**kw):
        actual_init(w,*a,**kw);w.finished.connect(packets.append,Qt.ConnectionType.DirectConnection)
    monkeypatch.setattr(FileReconciliationWorker,'__init__',init)
    actual_slot=window._file_check_finished
    monkeypatch.setattr(window,'_file_check_finished',lambda result:None)
    window.review_btn.click();pump(lambda:window._thread is None)
    assert len(packets)==len(owners)==1 and owners[0].reason=='DELIVERY_TIMEOUT'
    assert owners[0].owned_count==0 and not owners[0].active
    actual_slot(packets[0]);assert_no_output_confirmation(window,track)
    record('abandoned-and-late-delivery',reason=owners[0].reason,owned=0)


def test_worker_exception_closes_pair_and_never_publishes_history(diagnostic_window,monkeypatch,owners):
    from audio_library_organizer.ui import workers
    window,lib,_=diagnostic_window;_,_,track,_=lib
    actual=workers.check_library
    def fault(*a,**kw):
        boundary=kw.pop('before_output_check');assert boundary()
        raise RuntimeError('controlled selected worker error')
    monkeypatch.setattr(workers,'check_library',fault)
    window.review_btn.click();pump(lambda:window._thread is None)
    assert len(owners)==1 and owners[0].owned_count==0
    assert_no_output_confirmation(window,track)
    record('selected-worker-exception',injected=True,owned=0)


def test_close_while_delivery_is_active_revokes_and_finishes_thread(diagnostic_window,monkeypatch,owners):
    window,lib,_=diagnostic_window;_,_,track,_=lib;actual=window._file_check_finished
    def close_first(result):window.close();actual(result)
    monkeypatch.setattr(window,'_file_check_finished',close_first)
    window.review_btn.click();pump(lambda:window._thread is None)
    assert len(owners)==1 and owners[0].owned_count==0 and not owners[0].active
    assert_no_output_confirmation(window,track)
    record('close-active',owned=0,window_visible=window.isVisible())


@pytest.mark.parametrize('kind',['destroy','quit'])
def test_receiver_destruction_or_real_quit_releases_protection(library,monkeypatch,owners,kind,tmp_path):
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    monkeypatch.setattr(main_window,'DashboardPage',DashboardPage)
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    from audio_library_organizer.domain.settings import AppSettings,LibraryPaths
    from audio_library_organizer.domain.preferences import AppPreferences
    repo,root,track,_=library;approve(library)
    app=QApplication.instance() or QApplication([])
    store=QSettings(str(tmp_path/'contract-only.ini'),QSettings.Format.IniFormat);AppPreferences().save(store)
    assert native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    monkeypatch.setattr(native,'WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED',True)
    window=main_window.MainWindow(AppSettings((),LibraryPaths(root)),store);window.show();app.processEvents()
    actual_init=FileReconciliationWorker.__init__;packets=[];finished=[];quit_seen=[]
    app.aboutToQuit.connect(lambda:quit_seen.append(True))
    class Controller(QObject):
        @Slot(object)
        def receive(self,result):
            packets.append(result)
            if kind=='destroy':shiboken6.delete(window)
            else:app.quit()
    controller=Controller()
    def init(w,*a,**kw):
        actual_init(w,*a,**kw);w.finished.connect(controller.receive,Qt.ConnectionType.QueuedConnection)
    monkeypatch.setattr(FileReconciliationWorker,'__init__',init)
    try:
        window.review_btn.click();thread=window._thread
        thread.finished.connect(lambda:finished.append(True),Qt.ConnectionType.DirectConnection)
        if kind=='quit':assert app.exec()==0
        else:pump(lambda:bool(finished))
        app.processEvents()
        assert packets and finished and len(owners)==1
        assert not owners[0].active and owners[0].owned_count==0
        if kind=='destroy':assert not shiboken6.isValid(window)
        else:assert quit_seen
        record('receiver-lifetime',kind=kind,owned=0,thread_finished=True,about_to_quit=bool(quit_seen))
    finally:
        if shiboken6.isValid(window):window.close()
        app.processEvents()
