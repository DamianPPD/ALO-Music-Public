"""Current content proofs, bounded adoption work, and real Qt cancellation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from audio_adoption_fixtures import mp3_samples, copy_audio
from test_legacy_adoption_v0427 import library, inventory, adoption_api
from audio_library_organizer.domain.models import TrackRecord


def test_large_library_approval_cost(tmp_path, mp3_samples, monkeypatch):
    """Regression: one approval must not decode all 300 sources and 40 outputs."""
    from audio_library_organizer.storage.repository import LibraryRepository
    root = tmp_path/'library'; root.mkdir()
    repo = LibraryRepository(root/'.alo'/'library.sqlite3'); repo.initialize()
    directory = tmp_path/'source'; directory.mkdir()
    repo.bootstrap_sources([directory])
    for i in range(300):
        path = copy_audio(mp3_samples['original' if i == 0 else 'different_tail'], directory/f'{i}.mp3')
        st = path.stat()
        repo.upsert_track(TrackRecord(path, size_bytes=st.st_size, mtime_ns=st.st_mtime_ns,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    output = copy_audio(mp3_samples['original'], root/'GOTOWE'/'selected.mp3')
    for i in range(39):
        subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i',f'sine=frequency={1000+i}:duration=0.2',
            '-c:a','libmp3lame','-b:a','128k',str(output.parent/f'unmatched-{i}.mp3')],
            check=True, capture_output=True, timeout=20)
    api = adoption_api()
    started = time.perf_counter()
    found = api.inventory_legacy_outputs(repo, library_root=root)
    initial_seconds = time.perf_counter()-started
    proposal = next(p for p in found.proposals if p.can_adopt)
    measured = {}
    for name in ('inventory_legacy_outputs','inspect_audio','_known_state','_context','_physical_inventory'):
        original = getattr(api, name)
        def measure(*args, _name=name, _original=original, **kwargs):
            start=time.perf_counter()
            try: return _original(*args, **kwargs)
            finally:
                entry=measured.setdefault(_name, {'calls':0,'seconds':0.0})
                entry['calls']+=1; entry['seconds']+=time.perf_counter()-start
        monkeypatch.setattr(api,name,measure)
    start=time.perf_counter()
    binding=api.adopt_legacy_output(repo, proposal.proposal_id, confirmed=True, library_root=root)
    measured.update(approval_seconds=time.perf_counter()-start, initial_inventory_seconds=initial_seconds,
                    records=300, outputs=40)
    if os.environ.get('ALO_ADOPTION_MEASURE'):
        Path(os.environ['ALO_ADOPTION_MEASURE']).write_text(json.dumps(measured,indent=2))
    assert len(repo.list_managed_bindings()) == 1 and binding.track_id == proposal.track_id
    assert measured['inspect_audio']['calls'] <= 4, measured
    assert measured.get('inventory_legacy_outputs',{}).get('calls',0) == 0, measured


def test_single_approval_emits_stages_and_can_cancel_before_commit(library):
    repo, root, _, _ = library
    p = inventory(library).proposals[0]
    stopped = False; stages=[]
    def progress(current, total, stage):
        nonlocal stopped
        stages.append((current,total,stage))
        if stage == 'saving': stopped=True
    with pytest.raises(InterruptedError):
        adoption_api().adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root,
            progress=progress,cancelled=lambda:stopped)
    assert repo.list_managed_bindings() == ()
    assert {'sources','outputs','source','output','owners','saving'} <= {s[2] for s in stages}

from test_adoption_integration_v0427 import app, make_window, wait


def test_dialog_finds_readable_candidate_and_keeps_all_statuses(library, app):
    from dataclasses import replace
    from audio_library_organizer.ui.adoption_dialog import LegacyAdoptionDialog
    repo,root,track,_=library
    found=inventory(library)
    other=replace(found.proposals[0],proposal_id='unresolved',status='UNRESOLVED',locator='')
    found=replace(found,proposals=(*found.proposals,other))
    dialog=LegacyAdoptionDialog(found,tracks=[track])
    try:
        assert track.artist in dialog.table.item(0,0).text()
        assert track.title in dialog.table.item(0,0).text()
        assert track.track_id not in dialog.table.item(0,0).text()
        assert not dialog.table.isRowHidden(0) and dialog.table.isRowHidden(1)
        assert dialog.table.currentRow()==-1 and not dialog.approve_button.isEnabled()
        dialog.status_filter.setCurrentIndex(0)
        assert not dialog.table.isRowHidden(1)
        dialog.search.setText(track.artist)
        assert not dialog.table.isRowHidden(0)
        dialog.search.setText('no such file')
        assert dialog.table.isRowHidden(0)
        assert '1' in dialog.counts.text()
    finally: dialog.close()


def test_mainwindow_progress_cancel_and_gui_heartbeat(library, app, tmp_path, monkeypatch):
    from threading import Event
    from PySide6.QtCore import QTimer
    api=adoption_api(); original=api._content_identity
    entered=Event(); release=Event()
    def blocked(*args,**kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args,**kwargs)
    window=make_window(library,tmp_path)
    heartbeats=[]; timer=QTimer(); timer.setInterval(1); timer.timeout.connect(lambda:heartbeats.append(1))
    try:
        window._check_library_clicked(); wait(app,lambda:window._thread is None)
        monkeypatch.setattr(api,'_content_identity',blocked)
        window.adoption_btn.click(); dialog=window._adoption_dialog
        dialog.table.selectRow(0); dialog.confirm_check.setChecked(True); dialog.approve_button.click()
        assert entered.wait(5)
        timer.start()
        wait(app,lambda:len(heartbeats)>=3 and dialog.operation_progress.maximum()>0)
        assert 'źród' in dialog.operation_label.text().lower()
        dialog.cancel_button.click()
        release.set(); wait(app,lambda:window._thread is None)
        assert library[0].list_managed_bindings()==()
        assert 'Anulowano' in dialog.details.toPlainText()
    finally:
        timer.stop(); release.set()
        if window._thread is not None: window._stop_file_check_on_quit(); app.processEvents()
        window.close()


def test_many_candidates_only_explicit_record_is_bound(library, mp3_samples):
    repo,root,_,_=library
    path=copy_audio(mp3_samples['different_tail'], library[2].path.parent/'second.mp3')
    st=path.stat(); second=TrackRecord(path,size_bytes=st.st_size,mtime_ns=st.st_mtime_ns,
                                      sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    repo.upsert_track(second); copy_audio(path,root/'GOTOWE'/'second.mp3')
    proposals=inventory(library).proposals
    assert len([p for p in proposals if p.can_adopt])==2
    p=next(p for p in proposals if p.track_id==second.track_id)
    adoption_api().adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root)
    assert [b.track_id for b in repo.list_managed_bindings()]==[second.track_id]


@pytest.mark.parametrize('stage,at',[('sources',0),('saving',0),('saving',1)])
def test_cancel_rolls_back_binding_proposal_and_cache(library,stage,at):
    import sqlite3
    repo,root,track,output=library; api=adoption_api(); p=inventory(library).proposals[0]
    original=(track.path.read_bytes(),output.read_bytes(),repo.get_track(track.track_id))
    stopped=False
    with sqlite3.connect(repo.database_path) as conn:
        cache=conn.execute('SELECT * FROM file_state_cache').fetchall()
    def progress(current,total,name):
        nonlocal stopped
        if name==stage and current==at: stopped=True
    with pytest.raises(InterruptedError):
        api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root,
                                progress=progress,cancelled=lambda:stopped)
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('SELECT status FROM legacy_adoption_proposals WHERE proposal_id=?',(p.proposal_id,)).fetchone()[0]=='CANDIDATE'
        assert conn.execute('SELECT * FROM file_state_cache').fetchall()==cache
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert repo.list_managed_bindings()==()
    assert (track.path.read_bytes(),output.read_bytes(),repo.get_track(track.track_id))==original


def test_cancel_after_actual_commit_reports_success(library,app,monkeypatch):
    import sqlite3
    from audio_library_organizer.ui.workers import LegacyAdoptionWorker
    repo,root,_,_=library; api=adoption_api(); p=inventory(library).proposals[0]
    worker=LegacyAdoptionWorker(repo,proposal_id=p.proposal_id,library_id=repo.library_id,
                               operation_id='after-commit',library_root=root)
    class CommitObserver(sqlite3.Connection):
        def __exit__(self,*args):
            result=super().__exit__(*args)
            if args[0] is None: worker.cancel()
            return result
    def connection(repository):
        conn=sqlite3.connect(repository.database_path,factory=CommitObserver)
        conn.row_factory=sqlite3.Row; conn.execute('PRAGMA foreign_keys=ON')
        return conn
    monkeypatch.setattr(api,'_rw',connection)
    finished=[]; errors=[]
    worker.finished.connect(finished.append); worker.failed.connect(lambda *args:errors.append(args))
    worker.run()
    assert worker._cancelled.is_set() and len(finished)==1 and errors==[]
    assert len(repo.list_managed_bindings())==1


def test_unselected_same_size_edit_with_restored_mtime_refuses(library,mp3_samples):
    repo,root,track,_=library; api=adoption_api()
    path=copy_audio(mp3_samples['different_tail'],track.path.parent/'other.mp3')
    st=path.stat(); repo.upsert_track(TrackRecord(path,size_bytes=st.st_size,mtime_ns=st.st_mtime_ns,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    p=next(p for p in inventory(library).proposals if p.can_adopt)
    st=path.stat(); data=bytearray(path.read_bytes()); data[-50]^=1; path.write_bytes(data)
    os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns))
    with pytest.raises(ValueError,match='Source.*changed'):
        api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings()==()


def test_reference_change_for_missing_unselected_source_refuses(library,mp3_samples):
    import sqlite3
    repo,root,track,_=library; api=adoption_api()
    path=copy_audio(mp3_samples['different_tail'],track.path.parent/'other.mp3')
    st=path.stat(); other=TrackRecord(path,size_bytes=st.st_size,mtime_ns=st.st_mtime_ns,
                                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    repo.upsert_track(other)
    p=next(p for p in inventory(library).proposals if p.can_adopt)
    path.unlink()
    # A later inventory can alter this table independently of _context().
    with sqlite3.connect(repo.database_path) as conn:
        row=conn.execute('SELECT evidence_json FROM source_audio_references WHERE track_id=?',(other.track_id,)).fetchone()
        ref=json.loads(row[0]); ref['audio_digest']=p.audio_digest
        conn.execute('UPDATE source_audio_references SET evidence_json=? WHERE track_id=?',(json.dumps(ref),other.track_id))
    with pytest.raises(ValueError,match='references changed'):
        api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings()==()


def test_old_inventory_falls_back_to_full_scan(library,monkeypatch):
    import sqlite3
    repo,root,_,_=library; api=adoption_api(); p=inventory(library).proposals[0]
    with sqlite3.connect(repo.database_path) as conn:
        ctx=json.loads(conn.execute('SELECT context_json FROM legacy_adoption_runs WHERE run_id=?',(p.run_id,)).fetchone()[0])
        ctx.pop('approval_snapshot')
        conn.execute('UPDATE legacy_adoption_runs SET context_json=? WHERE run_id=?',(json.dumps(ctx),p.run_id))
    original=api.inventory_legacy_outputs; calls=[]
    def count(*args,**kwargs): calls.append(1); return original(*args,**kwargs)
    monkeypatch.setattr(api,'inventory_legacy_outputs',count)
    api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root)
    assert calls==[1] and len(repo.list_managed_bindings())==1


def test_database_lock_reports_error_with_responsive_gui(library,app,tmp_path):
    import sqlite3
    from PySide6.QtCore import QTimer
    window=make_window(library,tmp_path); beats=[]; timer=QTimer(); timer.setInterval(1)
    timer.timeout.connect(lambda:beats.append(1))
    connection=None
    try:
        window._check_library_clicked(); wait(app,lambda:window._thread is None)
        window.adoption_btn.click(); dialog=window._adoption_dialog
        connection=sqlite3.connect(library[0].database_path); connection.execute('BEGIN IMMEDIATE')
        dialog.table.selectRow(0); dialog.confirm_check.setChecked(True); timer.start(); dialog.approve_button.click()
        wait(app,lambda:window._thread is None)
        assert len(beats)>3 and 'Błąd przypisywania' in dialog.details.toPlainText()
        assert library[0].list_managed_bindings()==()
    finally:
        timer.stop()
        if connection is not None: connection.rollback(); connection.close()
        if window._thread is not None:window._stop_file_check_on_quit();app.processEvents()
        window.close()


def test_duplicate_appearing_during_final_hash_sweep_rolls_back(library,monkeypatch):
    repo,root,_,output=library; api=adoption_api(); p=inventory(library).proposals[0]
    original=api._content_identity; calls=0
    def copy_during_final(path,*args,**kwargs):
        nonlocal calls
        value=original(path,*args,**kwargs)
        if Path(path)==output:
            calls+=1
            if calls==2:copy_audio(output,root/'NIE_WYBRANE'/'late.mp3')
        return value
    monkeypatch.setattr(api,'_content_identity',copy_during_final)
    with pytest.raises(ValueError,match='inventory changed'):
        api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings()==()


def test_cancelled_dialog_can_retry_without_deadlock(library,app,tmp_path):
    window=make_window(library,tmp_path)
    try:
        window._check_library_clicked();wait(app,lambda:window._thread is None)
        window.adoption_btn.click();dialog=window._adoption_dialog
        dialog.table.selectRow(0);dialog.confirm_check.setChecked(True);dialog.approve_button.click()
        window._worker.cancel();wait(app,lambda:window._thread is None)
        assert library[0].list_managed_bindings()==()
        dialog.confirm_check.setChecked(True);dialog.approve_button.click()
        assert window._thread is not None
        wait(app,lambda:window._thread is None)
        assert len(library[0].list_managed_bindings())==1
    finally:
        if window._thread is not None:window._stop_file_check_on_quit();app.processEvents()
        window.close()


def test_cancellation_in_final_membership_does_not_commit(library,monkeypatch):
    repo,root,_,_=library;api=adoption_api();p=inventory(library).proposals[0]
    original=api._output_membership;calls=0;stopped=False
    def membership(*args,**kwargs):
        nonlocal calls,stopped
        result=original(*args,**kwargs);calls+=1
        if calls==3:stopped=True
        return result
    monkeypatch.setattr(api,'_output_membership',membership)
    with pytest.raises(InterruptedError):
        api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root,cancelled=lambda:stopped)
    assert repo.list_managed_bindings()==()


def test_cancel_inside_selected_output_decoder_is_cancelled_not_refused(library,monkeypatch):
    repo,root,_,output=library;api=adoption_api();p=inventory(library).proposals[0]
    original=api.inspect_audio;calls=0;stopped=False
    def inspect(path,**kwargs):
        nonlocal calls,stopped
        if Path(path)==output:
            calls+=1
            if calls==2:stopped=True
        return original(path,**kwargs)
    monkeypatch.setattr(api,'inspect_audio',inspect)
    with pytest.raises(InterruptedError):
        api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root,cancelled=lambda:stopped)
    assert repo.list_managed_bindings()==()
