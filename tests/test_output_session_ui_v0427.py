"""Real MainWindow, SQLite, MP3 and QThread; no native mouse automation."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4
import pytest
from PySide6.QtCore import Qt,QSettings
from PySide6.QtWidgets import QApplication
from audio_adoption_fixtures import mp3_samples,copy_audio
from test_legacy_adoption_v0427 import library
from test_adopted_output_spec_v0427 import approve
from audio_library_organizer.domain.file_state import FileState
from audio_library_organizer.domain.settings import AppSettings,LibraryPaths
from audio_library_organizer.domain.preferences import AppPreferences
from audio_library_organizer.metadata.change_history import metadata_revision


def pump(predicate,seconds=15):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:QApplication.processEvents()
    assert predicate(),'Qt operation did not complete'


@pytest.fixture
def adopted_window(library,tmp_path,monkeypatch):
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    repo,root,track,output=library;binding=approve(library)
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window,'DashboardPage',DashboardPage)
    store=QSettings(str(tmp_path/'isolated.ini'),QSettings.Format.IniFormat)
    AppPreferences(language='pl',theme='dark').save(store)
    window=main_window.MainWindow(AppSettings((),LibraryPaths(root)),store)
    window.resize(1500,960);window.show();app.processEvents()
    yield window,library,binding
    window.close();app.processEvents()


def run_check(window):
    window.review_btn.click()
    pump(lambda:window._thread is None)
    assert window.last_reconciliation_result is not None


def presentation(window,track):
    return window.library._file_presentation(window.repository.get_track(track.track_id))


def assert_completed_observation(window,track):
    """Windows has useful H after release; Linux retains its original contract."""
    from audio_library_organizer.safety import windows_file_identity as native
    p=presentation(window,track)
    if not native.on_windows():
        assert p.confirmed
        return
    delivery=window.last_reconciliation_result.output_delivery
    assert delivery is not None and delivery.windows_lease is not None
    lease=delivery.windows_lease
    assert lease.accepted and not lease.active and lease.owned_count==0
    assert not p.confirmed and not window._output_session
    history=window._output_history[track.track_id]
    assert not history.evaluation.is_confirmed
    assert history.operation_id==delivery.pending.request.operation_id


def assert_no_output_confirmation(window,track):
    assert not presentation(window,track).confirmed
    assert track.track_id not in window._output_history
    assert track.track_id not in window._output_session


@pytest.mark.parametrize('language',['pl','en'])
def test_real_check_reaches_column_filter_sort_and_survives_selection_refresh(adopted_window,language):
    from audio_library_organizer.ui.i18n import apply_static_language
    window,lib,binding=adopted_window;repo,root,track,output=lib
    from audio_library_organizer.domain.models import TrackRecord
    other_path=copy_audio(track.path,track.path.with_name('Other synthetic.mp3'))
    st=other_path.stat()
    other=TrackRecord(other_path,size_bytes=st.st_size,mtime_ns=st.st_mtime_ns,
        sha256=hashlib.sha256(other_path.read_bytes()).hexdigest(),title='Other synthetic')
    repo.upsert_track(other);window.refresh_data();window.library.select_track(repo.get_track(track.track_id))
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (track.path,output)]
    window.preferences=replace(window.preferences,language=language)
    apply_static_language(window.library,language)
    run_check(window)
    p=presentation(window,track)
    assert p.state==FileState.NEEDS_UPDATE
    assert_completed_observation(window,track)
    assert p.background=='#30251b'
    window.library.select_track(repo.get_track(other.track_id))
    assert presentation(window,track).state==FileState.NEEDS_UPDATE
    window.refresh_data()
    assert presentation(window,track).state==FileState.NEEDS_UPDATE
    combo=window.library.file_filter
    combo.setCurrentIndex(combo.findData(FileState.NEEDS_UPDATE))
    assert window.library.model.rowCount()==1
    window.library.table.sortByColumn(10,Qt.SortOrder.AscendingOrder)
    from audio_library_organizer.safety import windows_file_identity as native
    expected='Needs update' if language=='en' else 'Do aktualizacji'
    if native.on_windows():expected+=' · '+('Unconfirmed' if language=='en' else 'Niepotwierdzony')
    assert window.library.model.item(0,10).text()==expected
    if os.environ.get('STAGE62C_EVIDENCE'):
        target=Path(os.environ['STAGE62C_EVIDENCE'])
        window.library.table.horizontalScrollBar().setValue(window.library.table.horizontalScrollBar().maximum())
        QApplication.processEvents()
        assert_completed_observation(window,track)
        window.library.grab().save(str(target/f'library-needs-update-{language}.png'))
        (target/f'ui-difference-{language}.json').write_text(json.dumps({
            'library_id':repo.library_id,'track_id':track.track_id,'binding_id':binding.binding_id,
            'state':p.state,'confirmed':p.confirmed,'background':p.background,
            'cell_text':window.library.model.item(0,10).text(),
            'filtered_rows':window.library.model.rowCount(),
            'session_entries':len(window._output_session),
            'cached_confirmed':repo.get_file_state(track.track_id).evaluation.is_confirmed,
            'worker_operation':window.last_reconciliation_result.operation_id},ensure_ascii=False,indent=2))
    combo.setCurrentIndex(0)
    window.library.table.sortByColumn(10,Qt.SortOrder.AscendingOrder)
    assert window.library.model.rowCount()==2
    # The ordinary unbound row now has SOURCE_ONLY, not unknown. Its existing
    # rank precedes NEEDS_UPDATE; retain an exact identity/order assertion.
    assert window.library.model.item(0,0).data(Qt.ItemDataRole.UserRole).track_id==other.track_id
    assert window.library.model.item(1,0).data(Qt.ItemDataRole.UserRole).track_id==track.track_id
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in (track.path,output)]==before
    assert repo.list_managed_bindings()==(binding,)
    assert not repo.get_file_state(track.track_id).evaluation.is_confirmed


def test_partial_match_never_becomes_in_library(adopted_window):
    window,lib,_=adopted_window;repo,_,track,_=lib
    t=repo.get_track(track.track_id)
    repo.save_metadata(t.track_id,{'artist':'Fixture artist','title':'Legacy title'},
        expected_revision=metadata_revision(t),library_id=repo.library_id)
    window.refresh_data();run_check(window)
    assert presentation(window,track).state is None


@pytest.mark.parametrize('field,value',[('artist','New artist'),('title','New title'),('album','New album'),('bpm',129.),('cover_choice','none')])
def test_edit_after_acceptance_invalidates_state_before_next_check(adopted_window,field,value):
    window,lib,_=adopted_window;repo,_,track,_=lib
    run_check(window);assert_completed_observation(window,track)
    from copy import deepcopy
    t=repo.get_track(track.track_id);before=deepcopy(t);setattr(t,field,value)
    window._commit_track_metadata(before,t)
    assert_no_output_confirmation(window,track)
    window.refresh_data();assert_no_output_confirmation(window,track)
    run_check(window)
    assert presentation(window,track).state==FileState.NEEDS_UPDATE
    assert_completed_observation(window,track)


def test_manual_cover_and_same_path_replacement_remain_excluded(adopted_window,tmp_path):
    window,lib,_=adopted_window;repo,_,track,_=lib
    cover=tmp_path/'manual.png';cover.write_bytes(b'synthetic-one')
    t=repo.get_track(track.track_id)
    repo.save_metadata(t.track_id,{'manual_cover_path':str(cover),'cover_choice':'manual'},
        expected_revision=metadata_revision(t),library_id=repo.library_id)
    window.refresh_data();run_check(window)
    assert_no_output_confirmation(window,track)
    cover.write_bytes(b'synthetic-two');run_check(window)
    assert_no_output_confirmation(window,track)


@pytest.mark.parametrize('kind',['artist','title','album','bpm','cover','binding','source','policy','generation','cancel','output-bytes'])
def test_change_between_worker_and_gui_delivery_is_rejected(adopted_window,monkeypatch,kind):
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    window,lib,_=adopted_window;repo,_,track,output=lib
    original=FileReconciliationWorker.__init__;events=[]
    def init(worker,*args,**kwargs):
        original(worker,*args,**kwargs)
        def mutate(result):
            events.append('worker_finished_before_gui_delivery')
            if kind in ('artist','title','album','bpm','cover'):
                t=repo.get_track(track.track_id)
                key='cover_choice' if kind=='cover' else kind
                repo.save_metadata(t.track_id,{key:131. if key=='bpm' else 'Queued edit'},
                    expected_revision=metadata_revision(t),library_id=repo.library_id)
            elif kind in ('binding','source'):
                with sqlite3.connect(repo.database_path) as conn:
                    if kind=='binding':conn.execute('UPDATE managed_bindings SET binding_id=?',(str(uuid4()),))
                    else:conn.execute('UPDATE tracks SET sha256=? WHERE track_id=?',('f'*64,track.track_id))
            elif kind=='output-bytes':
                from audio_library_organizer.safety import windows_file_identity as native
                if native.on_windows():
                    with pytest.raises(OSError):
                        with output.open('ab') as stream:stream.write(b'Controlled synthetic change')
                    worker.cancel()  # Write was blocked; cancellation is a separate refusal.
                else:
                    with output.open('ab') as stream:stream.write(b'Controlled synthetic change')
            elif kind=='cancel':worker.cancel()
        # Direct callback registered BEFORE MainWindow's queued connection.
        worker.finished.connect(mutate,Qt.ConnectionType.DirectConnection)
    monkeypatch.setattr(FileReconciliationWorker,'__init__',init)
    if kind in ('policy','generation'):
        # Mutate on GUI delivery, before the original acceptance slot executes.
        original_slot=window._file_check_finished
        def deliver(result):
            events.append('gui_delivery_context_changed')
            if kind=='policy':window.qt_settings.setValue('ui/filename_template','{Title}')
            else:window._file_check_generation+=1
            original_slot(result)
        monkeypatch.setattr(window,'_file_check_finished',deliver)
    window.review_btn.click();pump(lambda:window._thread is None)
    assert events
    assert_no_output_confirmation(window,track)


def test_worker_only_classifies_local_scope_and_cannot_be_used_as_watcher_only_proof():
    from audio_library_organizer.jobs.output_session import local_filesystem
    assert local_filesystem('/definitely/not/a/known/physical/path') is None


def test_database_locked_at_gui_acceptance_refuses_without_waiting(adopted_window,monkeypatch):
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    window,lib,_=adopted_window;repo,_,track,_=lib
    original=FileReconciliationWorker.__init__;held=[]
    def init(worker,*args,**kwargs):
        original(worker,*args,**kwargs)
        def lock(result):
            c=sqlite3.connect(repo.database_path,check_same_thread=False)
            c.execute('BEGIN EXCLUSIVE');held.append(c)
        worker.finished.connect(lock,Qt.ConnectionType.DirectConnection)
    monkeypatch.setattr(FileReconciliationWorker,'__init__',init)
    try:
        window.review_btn.click();pump(lambda:window._thread is None)
        assert held and not window._output_session and not window._output_history
    finally:
        for c in held:c.rollback();c.close()


def test_unknown_filesystem_is_not_accepted(adopted_window,monkeypatch):
    from audio_library_organizer.jobs import output_session
    window,lib,_=adopted_window;_,_,track,_=lib
    monkeypatch.setattr(output_session,'local_filesystem',lambda p:None)
    run_check(window)
    assert_no_output_confirmation(window,track)
    assert not window._output_session


def test_state_is_not_restored_from_cache_after_restart(adopted_window):
    window,lib,_=adopted_window;repo,_,track,_=lib
    run_check(window);assert_completed_observation(window,track)
    reopened=type(repo)(repo.database_path)
    assert not reopened.get_file_state(track.track_id).evaluation.is_confirmed
    window._invalidate_output_states();window.refresh_data()
    assert_no_output_confirmation(window,track)


def test_late_result_cannot_replace_newer_actual_check(adopted_window):
    window,lib,_=adopted_window;repo,_,track,_=lib
    run_check(window);old=window.last_reconciliation_result
    run_check(window);new=window.last_reconciliation_result
    assert old.operation_id!=new.operation_id
    window._file_check_finished(old)
    assert window.last_reconciliation_result is new
    from audio_library_organizer.safety import windows_file_identity as native
    if native.on_windows():assert window._output_history[track.track_id].operation_id==new.operation_id
    else:assert window._output_session[track.track_id].pending.request.operation_id==new.operation_id


def test_foreign_library_context_cannot_accept_existing_delivery(adopted_window):
    window,lib,_=adopted_window;_,_,track,_=lib
    run_check(window);old=window.last_reconciliation_result
    window._invalidate_output_states()
    window._file_check_context=(str(uuid4()),old.operation_id,window._file_check_generation)
    window._file_check_finished(old)
    assert_no_output_confirmation(window,track)


def test_watch_event_invalidates_only_session_evidence(adopted_window):
    window,lib,_=adopted_window;_,_,track,output=lib
    run_check(window);assert_completed_observation(window,track)
    with output.open('ab') as stream:stream.write(b'synthetic modification')
    pump(lambda:not presentation(window,track).confirmed and track.track_id not in window._output_history)
    assert output.exists()


def test_two_real_approved_bindings_are_checked_by_selection_without_mixing(adopted_window,mp3_samples):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.jobs.legacy_adoption import inventory_legacy_outputs,adopt_legacy_output
    window,lib,_=adopted_window;repo,root,first,_=lib
    source=copy_audio(mp3_samples['different_tail'],first.path.with_name('Second.mp3'))
    st=source.stat();second=TrackRecord(source,size_bytes=st.st_size,mtime_ns=st.st_mtime_ns,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),artist='Second desired',title='Second title')
    repo.upsert_track(second);copy_audio(source,root/'GOTOWE'/'Second.mp3',title='Second applied')
    inventory=inventory_legacy_outputs(repo,library_root=root)
    proposal=next(p for p in inventory.proposals if p.track_id==second.track_id and p.can_adopt)
    adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    assert len(repo.list_managed_bindings())==2
    window.refresh_data();window.library.select_track(repo.get_track(first.track_id));run_check(window)
    assert_completed_observation(window,first)
    assert_no_output_confirmation(window,second)
    window.library.select_track(repo.get_track(second.track_id));assert_completed_observation(window,first)
    run_check(window)
    assert presentation(window,second).state==FileState.NEEDS_UPDATE
    assert_completed_observation(window,second)
    assert not presentation(window,first).confirmed
    from audio_library_organizer.safety import windows_file_identity as native
    if native.on_windows():assert set(window._output_history)=={second.track_id} and not window._output_session
    else:assert set(window._output_session)=={second.track_id}


def test_wal_metadata_change_invalidates_accepted_state(adopted_window):
    window,lib,_=adopted_window;repo,_,track,_=lib
    conn=sqlite3.connect(repo.database_path)
    try:
        assert conn.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        run_check(window);assert_completed_observation(window,track)
        conn.execute('UPDATE tracks SET album=? WHERE track_id=?',('External WAL metadata',track.track_id));conn.commit()
        pump(lambda:not presentation(window,track).confirmed and track.track_id not in window._output_history)
    finally:conn.close()


def test_audio_source_save_revokes_session_proof(adopted_window):
    from copy import deepcopy
    window,lib,_=adopted_window;repo,_,track,_=lib
    run_check(window);assert_completed_observation(window,track)
    before=repo.get_track(track.track_id);changed=deepcopy(before);changed.artist='Audio-source approval edit'
    window._save_audio_source(changed,before)
    assert_no_output_confirmation(window,track)


def test_windows_scope_gate_is_explicitly_closed_without_native_change_token(tmp_path,monkeypatch):
    from audio_library_organizer.jobs import output_session
    monkeypatch.setattr(output_session.sys,'platform','win32')
    assert output_session.local_filesystem(tmp_path) is None


@pytest.mark.parametrize('when',['before-check','queued-delivery'])
def test_symlinked_database_directory_cannot_supply_new_ui_confirmation(adopted_window,monkeypatch,when):
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    window,lib,_=adopted_window;repo,root,track,_=lib
    def swap():
        directory=root/'.alo';held=root/'.alo-held'
        directory.rename(held);directory.symlink_to(held,target_is_directory=True)
    if when=='before-check':swap()
    else:
        original=FileReconciliationWorker.__init__
        def init(worker,*args,**kwargs):
            original(worker,*args,**kwargs)
            worker.finished.connect(lambda result:swap(),Qt.ConnectionType.DirectConnection)
        monkeypatch.setattr(FileReconciliationWorker,'__init__',init)
    run_check(window)
    assert_no_output_confirmation(window,track)
    assert (root/'.alo-held/library.sqlite3').is_file()


@pytest.fixture
def scanned_integration_window(tmp_path,mp3_samples,monkeypatch):
    """Ordinary application, real scanner/SQLite/audio; no prepared file facts."""
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    source=tmp_path/'integration-source';source.mkdir()
    paths=[copy_audio(mp3_samples['original'],source/f'Synthetic-{i}.mp3',title=f'Synthetic {i}')for i in range(10)]
    app=QApplication.instance()or QApplication([])
    monkeypatch.setattr(main_window,'DashboardPage',DashboardPage)
    store=QSettings(str(tmp_path/'integration-only.ini'),QSettings.Format.IniFormat)
    AppPreferences(language='pl',theme='dark').save(store)
    store.setValue('providers/auto_identify',False)
    window=main_window.MainWindow(AppSettings((source,),LibraryPaths(tmp_path/'integration-library')),store)
    window.show();app.processEvents()
    window.start_scan();pump(lambda:window._thread is None)
    assert len(window.repository.list_tracks())==10
    yield window,paths,store
    window.close();app.processEvents()


def _integration_cells(window):
    return {window.library.model.item(row,0).data(Qt.ItemDataRole.UserRole).track_id:
            window.library.model.item(row,10)for row in range(window.library.model.rowCount())}


def test_normal_source_check_has_explicit_assignment_absence(scanned_integration_window,tmp_path):
    from audio_library_organizer.jobs.file_reconciliation import check_library
    window,paths,_=scanned_integration_window
    paths[0].rename(tmp_path/'held-source.mp3')
    result=check_library(window.repository,library_root=window.app_settings.library.root)
    states={Path(item.source.locator).name:item.evaluation.state for item in result.files}
    assert states['Synthetic-0.mp3']==FileState.SOURCE_UNAVAILABLE
    assert all(s==FileState.SOURCE_ONLY for n,s in states.items()if n!='Synthetic-0.mp3')
    assert window.repository.list_managed_bindings()==()


def test_cache_refresh_is_read_only_and_refuses_locked_database(scanned_integration_window,monkeypatch):
    window,_,_=scanned_integration_window
    repo=window.repository
    with sqlite3.connect(repo.database_path) as conn:
        before=conn.execute('SELECT * FROM tracks ORDER BY track_id').fetchall()
    def forbidden(*a,**kw):raise AssertionError('Cache refresh must not rewrite metadata')
    monkeypatch.setattr(window,'_commit_track_metadata',forbidden)
    run_check(window)
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('SELECT * FROM tracks ORDER BY track_id').fetchall()==before
    cells={tid:item.text()for tid,item in _integration_cells(window).items()}
    original=repo.file_check_snapshot;timeouts=[]
    def snapshot(**kw):
        timeouts.append(kw['timeout'])
        return original(**kw)
    monkeypatch.setattr(repo,'file_check_snapshot',snapshot)
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('BEGIN EXCLUSIVE')
        try:window._refresh_file_check_rows()
        finally:conn.rollback()
    assert timeouts==[0.0]
    assert {tid:item.text()for tid,item in _integration_cells(window).items()}==cells
    assert 'nie można odświeżyć' in window.operation_status.text()


def test_invalid_managed_context_refuses_refresh_without_callback_exception(adopted_window,tmp_path):
    from audio_library_organizer.jobs.managed_files import lexical_locator
    window,lib,binding=adopted_window;repo,_,track,_=lib
    before=window._read_context
    cells={tid:item.text()for tid,item in _integration_cells(window).items()}
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('UPDATE managed_bindings SET locator_key=? WHERE track_id=?',
                     (lexical_locator(str(tmp_path/'other-library/alien.mp3')),track.track_id))
    assert repo.file_check_snapshot().managed_bindings[0].binding_id==binding.binding_id
    window._refresh_file_check_rows()
    assert window._read_context is before
    assert {tid:item.text()for tid,item in _integration_cells(window).items()}==cells
    assert 'nie można odświeżyć' in window.operation_status.text()


@pytest.mark.parametrize('language',['pl','en'])
def test_normal_check_reaches_all_rows_colors_filter_and_sort(scanned_integration_window,tmp_path,language):
    from audio_library_organizer.ui.i18n import apply_static_language
    from audio_library_organizer.ui.library_file_state import FILE_STATE_COLORS,FILE_STATE_SORT_ORDER
    from audio_library_organizer.ui.library_page import LIBRARY_SORT_ROLE
    window,paths,_=scanned_integration_window
    paths[0].rename(tmp_path/'held-source.mp3')
    window.preferences=replace(window.preferences,language=language);apply_static_language(window.library,language)
    run_check(window)
    tracks=window.repository.list_tracks();cells=_integration_cells(window)
    assert len(cells)==len(tracks)==10
    for track in tracks:
        state=FileState.SOURCE_UNAVAILABLE if track.path==paths[0]else FileState.SOURCE_ONLY
        text=('Source unavailable'if state==FileState.SOURCE_UNAVAILABLE else'Source only')if language=='en'else FILE_STATE_COLORS[state].label
        item=cells[track.track_id]
        assert item.text().startswith(text),(track.path,item.text())
        assert item.foreground().color().name()==FILE_STATE_COLORS[state].accent
        assert item.background().color().name()==FILE_STATE_COLORS[state].background
        assert not presentation(window,track).confirmed
    for state,count in [(FileState.SOURCE_ONLY,9),(FileState.SOURCE_UNAVAILABLE,1)]:
        window.library.file_filter.setCurrentIndex(window.library.file_filter.findData(state.value))
        assert window.library.model.rowCount()==count
    window.library.file_filter.setCurrentIndex(0)
    window.library.table.sortByColumn(10,Qt.SortOrder.AscendingOrder)
    QApplication.processEvents()
    ranks=[window.library.model.item(i,10).data(LIBRARY_SORT_ROLE)for i in range(10)]
    assert ranks==sorted(ranks)and set(ranks)=={FILE_STATE_SORT_ORDER[FileState.SOURCE_ONLY],FILE_STATE_SORT_ORDER[FileState.SOURCE_UNAVAILABLE]}


def test_created_outputs_survive_cancel_and_restart_with_real_owners(scanned_integration_window,tmp_path,monkeypatch):
    """Acceptance test: deliberately stays FAIL while producer ownership is absent."""
    import subprocess,sys,textwrap
    from audio_library_organizer.ui import main_window,export_dialogs,workers
    window,paths,store=scanned_integration_window
    run_check(window)
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}
    for i,track in enumerate(window.repository.list_tracks()):
        track.artist='Synthetic artist';track.title=f'Synthetic title {i}';track.album='Synthetic album'
        track.year='2000';track.genre='House';track.bpm=128;track.status='ready'
        track.locked_fields.add('__status__');track.cover_choice='none'
        window.repository.upsert_track(track)
    window.refresh_data()
    monkeypatch.setattr(main_window,'confirm_bulk_copy',lambda *a,**kw:True)
    monkeypatch.setattr(export_dialogs.ExportSummaryDialog,'exec',lambda dialog:0)
    actual_init=workers.ExportWorker.__init__
    def init(worker,*a,**kw):
        actual_init(worker,*a,**kw)
        def stop(event):
            if event.phase=='item_finished'and event.processed==3:worker.cancel()
        worker.phase.connect(stop,Qt.ConnectionType.DirectConnection)
    monkeypatch.setattr(workers.ExportWorker,'__init__',init)
    window.export_library();pump(lambda:window._thread is None,seconds=45)
    result=window._export_result
    assert result.cancelled and result.created==3 and result.remaining==7 and result.failed==0
    outputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in result.copied}
    assert all(o.status=='verified'and o.raw_verified and o.final_sha256==outputs[str(o.destination)]for o in result.outcomes)
    completed_source=result.outcomes[0].source
    unprocessed=next(p for p in paths if p not in {o.source for o in result.outcomes})
    held={str(completed_source):tmp_path/'completed-source-held.mp3',str(unprocessed):tmp_path/'unprocessed-source-held.mp3'}
    for old,new in held.items():Path(old).rename(new)
    run_check(window)
    window.library.table.sortByColumn(10,Qt.SortOrder.AscendingOrder);QApplication.processEvents()
    observed={tid:item.text()for tid,item in _integration_cells(window).items()}
    assert len(observed)==10
    # Repeat the real GUI operation: the existing legacy guard must refuse it,
    # rather than suffix-copying around unassigned already-existing outputs.
    window.export_library();pump(lambda:window._thread is None,seconds=45)
    assert window._export_result.created==0 and window._export_result.fatal_error
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in outputs.items())
    for p,digest in before.items():assert hashlib.sha256(held.get(p,Path(p)).read_bytes()).hexdigest()==digest
    library_root=window.app_settings.library.root
    window.close();QApplication.processEvents()
    code=textwrap.dedent('''
        import sys,json
        from pathlib import Path
        sys.path.insert(0,sys.argv[1])
        from PySide6.QtCore import QSettings,QCoreApplication,QEvent,QThreadPool
        from PySide6.QtWidgets import QApplication
        from audio_library_organizer.domain.settings import AppSettings,LibraryPaths
        from audio_library_organizer.ui import main_window
        from audio_library_organizer.ui.dashboard_page import DashboardPage
        main_window.DashboardPage=DashboardPage
        app=QApplication([]);errors=[]
        sys.excepthook=lambda kind,value,tb:errors.append(str(value))
        w=main_window.MainWindow(AppSettings((),LibraryPaths(Path(sys.argv[2]))),QSettings(sys.argv[3],QSettings.Format.IniFormat))
        w.show();app.processEvents()
        cells={w.library.model.item(i,0).data(256).track_id:w.library.model.item(i,10).text()for i in range(w.library.model.rowCount())}
        bindings=[b.track_id for b in w.repository.list_managed_bindings()]
        w.close();app.processEvents();QThreadPool.globalInstance().waitForDone(5000)
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        Path(sys.argv[4]).write_text(json.dumps({'cells':cells,'bindings':bindings,'callback_errors':errors}))
    ''')
    output=tmp_path/'restarted-window.json'
    child=subprocess.run([sys.executable,'-I','-B','-c',code,str(Path(__file__).resolve().parents[1]/'src'),str(library_root),store.fileName(),str(output)],capture_output=True,text=True,timeout=45)
    (tmp_path/'restart.stdout.log').write_text(child.stdout);(tmp_path/'restart.stderr.log').write_text(child.stderr)
    assert child.returncode==0,child.stderr
    restarted=json.loads(output.read_text());assert len(restarted['cells'])==10 and not restarted['callback_errors']
    evidence={'workflow':'scan/check/create/cancel/recheck/sort/close/new-process-reopen','created':3,'remaining':7,
        'output_hashes':outputs,'table_before_close':observed,'table_after_restart':restarted['cells'],
        'registered_owners':restarted['bindings'],'sources_unchanged':True,'outputs_not_overwritten':True,'restart_exit':child.returncode}
    target=Path(os.environ.get('ALO_62D_EVIDENCE',str(tmp_path)))
    (target/'integration-full-flow.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))
    assert len(restarted['bindings'])==3,'3 verified new outputs have no persistent producer-owned binding after restart'
