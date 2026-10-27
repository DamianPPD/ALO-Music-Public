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
    assert p.state==FileState.NEEDS_UPDATE and p.confirmed
    assert p.background=='#30251b'
    window.library.select_track(repo.get_track(other.track_id))
    assert presentation(window,track).state==FileState.NEEDS_UPDATE
    window.refresh_data()
    assert presentation(window,track).state==FileState.NEEDS_UPDATE
    combo=window.library.file_filter
    combo.setCurrentIndex(combo.findData(FileState.NEEDS_UPDATE))
    assert window.library.model.rowCount()==1
    window.library.table.sortByColumn(10,Qt.SortOrder.AscendingOrder)
    assert window.library.model.item(0,10).text()==('Needs update' if language=='en' else 'Do aktualizacji')
    if os.environ.get('STAGE62C_EVIDENCE'):
        target=Path(os.environ['STAGE62C_EVIDENCE'])
        window.library.table.horizontalScrollBar().setValue(window.library.table.horizontalScrollBar().maximum())
        QApplication.processEvents()
        assert presentation(window,track).confirmed
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
    assert window.library.model.item(0,0).data(Qt.ItemDataRole.UserRole).track_id==track.track_id
    assert window.library.model.item(1,0).data(Qt.ItemDataRole.UserRole).track_id==other.track_id
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
    run_check(window);assert presentation(window,track).confirmed
    from copy import deepcopy
    t=repo.get_track(track.track_id);before=deepcopy(t);setattr(t,field,value)
    window._commit_track_metadata(before,t)
    assert not presentation(window,track).confirmed
    window.refresh_data();assert not presentation(window,track).confirmed
    run_check(window)
    assert presentation(window,track).state==FileState.NEEDS_UPDATE


def test_manual_cover_and_same_path_replacement_remain_excluded(adopted_window,tmp_path):
    window,lib,_=adopted_window;repo,_,track,_=lib
    cover=tmp_path/'manual.png';cover.write_bytes(b'synthetic-one')
    t=repo.get_track(track.track_id)
    repo.save_metadata(t.track_id,{'manual_cover_path':str(cover),'cover_choice':'manual'},
        expected_revision=metadata_revision(t),library_id=repo.library_id)
    window.refresh_data();run_check(window)
    assert not presentation(window,track).confirmed
    cover.write_bytes(b'synthetic-two');run_check(window)
    assert not presentation(window,track).confirmed


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
    assert not presentation(window,track).confirmed


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
        assert held and not window._output_session
    finally:
        for c in held:c.rollback();c.close()


def test_unknown_filesystem_is_not_accepted(adopted_window,monkeypatch):
    from audio_library_organizer.jobs import output_session
    window,lib,_=adopted_window;_,_,track,_=lib
    monkeypatch.setattr(output_session,'local_filesystem',lambda p:None)
    run_check(window)
    assert not presentation(window,track).confirmed and not window._output_session


def test_state_is_not_restored_from_cache_after_restart(adopted_window):
    window,lib,_=adopted_window;repo,_,track,_=lib
    run_check(window);assert presentation(window,track).confirmed
    reopened=type(repo)(repo.database_path)
    assert not reopened.get_file_state(track.track_id).evaluation.is_confirmed
    window._invalidate_output_states();window.refresh_data()
    assert not presentation(window,track).confirmed


def test_late_result_cannot_replace_newer_actual_check(adopted_window):
    window,lib,_=adopted_window;repo,_,track,_=lib
    run_check(window);old=window.last_reconciliation_result
    run_check(window);new=window.last_reconciliation_result
    assert old.operation_id!=new.operation_id
    window._file_check_finished(old)
    assert window.last_reconciliation_result is new
    assert window._output_session[track.track_id].pending.request.operation_id==new.operation_id


def test_foreign_library_context_cannot_accept_existing_delivery(adopted_window):
    window,lib,_=adopted_window;_,_,track,_=lib
    run_check(window);old=window.last_reconciliation_result
    window._invalidate_output_states()
    window._file_check_context=(str(uuid4()),old.operation_id,window._file_check_generation)
    window._file_check_finished(old)
    assert not presentation(window,track).confirmed


def test_watch_event_invalidates_only_session_evidence(adopted_window):
    window,lib,_=adopted_window;_,_,track,output=lib
    run_check(window);assert presentation(window,track).confirmed
    with output.open('ab') as stream:stream.write(b'synthetic modification')
    pump(lambda:not presentation(window,track).confirmed)
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
    assert presentation(window,first).confirmed and not presentation(window,second).confirmed
    window.library.select_track(repo.get_track(second.track_id));assert presentation(window,first).confirmed
    run_check(window)
    assert presentation(window,second).state==FileState.NEEDS_UPDATE
    assert not presentation(window,first).confirmed
    assert set(window._output_session)=={second.track_id}


def test_wal_metadata_change_invalidates_accepted_state(adopted_window):
    window,lib,_=adopted_window;repo,_,track,_=lib
    conn=sqlite3.connect(repo.database_path)
    try:
        assert conn.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        run_check(window);assert presentation(window,track).confirmed
        conn.execute('UPDATE tracks SET album=? WHERE track_id=?',('External WAL metadata',track.track_id));conn.commit()
        pump(lambda:not presentation(window,track).confirmed)
    finally:conn.close()


def test_audio_source_save_revokes_session_proof(adopted_window):
    from copy import deepcopy
    window,lib,_=adopted_window;repo,_,track,_=lib
    run_check(window);assert presentation(window,track).confirmed
    before=repo.get_track(track.track_id);changed=deepcopy(before);changed.artist='Audio-source approval edit'
    window._save_audio_source(changed,before)
    assert not presentation(window,track).confirmed


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
    assert not presentation(window,track).confirmed
    assert (root/'.alo-held/library.sqlite3').is_file()
