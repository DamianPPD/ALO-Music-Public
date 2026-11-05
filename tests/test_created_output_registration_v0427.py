"""Producer ownership uses real MP3/SQLite, never adoption by matching a name."""
from dataclasses import replace
import hashlib
import sqlite3
import pytest
from audio_adoption_fixtures import mp3_samples
from test_export_preflight_v0427 import preflight, no_unhandled_qt_errors
from audio_library_organizer.ui.workers import ExportWorker
from audio_library_organizer.jobs import exporter


def test_worker_registers_verified_outputs_and_repeat_does_not_duplicate(preflight):
    _,repo,paths,worker,results,errors,_=preflight
    ids={t.track_id for t in repo.list_tracks()}
    worker.run()
    assert not errors and results[0].created==2
    bindings=repo.list_managed_bindings()
    assert {b.track_id for b in bindings}==ids
    assert all(b.evidence['producer']=='alo-export/v1' for b in bindings)
    first={p:hashlib.sha256(p.read_bytes()).hexdigest()for p in results[0].copied}
    again=ExportWorker(worker.plan,adoption_repository=repo,library_root=paths.root)
    done=[];again.finished.connect(done.append);again.failed.connect(errors.append);again.run()
    assert not errors and done[0].created==0 and done[0].skipped==2
    assert repo.list_managed_bindings()==bindings
    assert set(paths.root.rglob('*.mp3'))==set(first)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==v for p,v in first.items())


@pytest.mark.parametrize('fault',['metadata','source_binding','track_id','library','plan','manual_cover','source_swap','output_swap','locked','transaction','cancel_registration'])
def test_registration_refuses_changed_context_and_preserves_published_file(preflight,monkeypatch,fault):
    _,repo,paths,worker,results,errors,_=preflight
    # Use a single real item; inject at publication, before the ownership transaction.
    worker.plan=replace(worker.plan,items=worker.plan.items[:1])
    track=worker.plan.items[0].track
    if fault=='manual_cover':
        from PIL import Image
        cover=paths.root/'manual.png';Image.new('RGB',(8,8),'red').save(cover)
        track.manual_cover_path=str(cover);track.cover_choice='manual';repo.upsert_track(track)
    blocker=None;attack_denied=False
    def inject(event):
        nonlocal blocker,attack_denied
        if event.phase!='registering':return
        if fault=='metadata':
            current=repo.get_track(track.track_id);current.title='Changed';repo.upsert_track(current)
        elif fault=='manual_cover':
            from PIL import Image
            Image.new('RGB',(8,8),'blue').save(track.manual_cover_path)
        elif fault=='track_id':
            from uuid import uuid4
            replacement=str(uuid4())
            with sqlite3.connect(repo.database_path)as conn:
                conn.execute('UPDATE tracks SET track_id=? WHERE track_id=?',(replacement,track.track_id))
                # A coherent synthetic external rebind, rather than orphaned FK
                # rows that would make the runner's integrity audit fail.
                for table in ('source_audio_references','file_state_cache','legacy_adoption_proposals'):
                    conn.execute(f'UPDATE {table} SET track_id=? WHERE track_id=?',(replacement,track.track_id))
        elif fault=='source_binding':
            with sqlite3.connect(repo.database_path)as conn:conn.execute('UPDATE tracks SET source_id=NULL, source_relative_path=NULL WHERE track_id=?',(track.track_id,))
        elif fault=='library':
            from uuid import uuid4
            replacement=str(uuid4())
            with sqlite3.connect(repo.database_path)as conn:
                conn.execute('UPDATE library_metadata SET library_id=?',(replacement,))
                for table in ('sources','source_audio_references','legacy_adoption_runs','managed_bindings'):
                    conn.execute(f'UPDATE {table} SET library_id=?',(replacement,))
        elif fault=='plan':track.title='Changed plan'
        elif fault in ('source_swap','output_swap'):
            path=track.path if fault=='source_swap'else event.destination
            try:
                data=path.read_bytes();path.rename(path.with_suffix('.held'));path.write_bytes(data)
            except PermissionError:
                # Native deny-delete/write is itself the required refusal of the attack.
                attack_denied=True
        elif fault=='locked':
            blocker=sqlite3.connect(repo.database_path);blocker.execute('BEGIN EXCLUSIVE')
        elif fault=='transaction':
            with sqlite3.connect(repo.database_path)as conn:
                conn.execute("CREATE TRIGGER test_deny_binding BEFORE INSERT ON managed_bindings BEGIN SELECT RAISE(ABORT,'injected transaction failure'); END")
        elif fault=='cancel_registration':worker.cancel()
    worker.phase.connect(inject)
    try:worker.run()
    finally:
        if blocker:blocker.rollback();blocker.close()
    assert not errors and len(results)==1
    result=results[0]
    with sqlite3.connect(repo.database_path)as conn:
        assert conn.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    if fault=='cancel_registration' or attack_denied:
        assert result.created==1 and result.failed==0 and len(repo.list_managed_bindings())==1
        if fault=='cancel_registration':assert result.cancelled
        return
    assert result.failed==1 and result.outcomes[0].status=='registration_error'
    target=result.outcomes[0].destination
    assert target and target.is_file() and result.outcomes[0].error
    assert repo.list_managed_bindings()==()
    assert 'registration' in result.outcomes[0].error.lower()


def test_resume_after_cancel_registers_only_remaining_item(preflight):
    _,repo,paths,worker,results,errors,_=preflight
    worker.phase.connect(lambda e:worker.cancel()if e.phase=='item_finished'and e.processed==1 else None)
    worker.run()
    assert not errors and results[0].created==1 and results[0].remaining==1
    first=results[0].copied[0];digest=hashlib.sha256(first.read_bytes()).hexdigest()
    again=ExportWorker(worker.plan,adoption_repository=repo,library_root=paths.root)
    done=[];again.finished.connect(done.append);again.failed.connect(errors.append);again.run()
    assert not errors and done[0].created==1 and done[0].skipped==1
    assert len(repo.list_managed_bindings())==2
    assert len(list(paths.root.rglob('*.mp3')))==2
    assert hashlib.sha256(first.read_bytes()).hexdigest()==digest


def test_same_bytes_handoff_replacement_never_gets_producer_ownership(preflight,monkeypatch):
    import os
    from audio_library_organizer.jobs import created_output as producer
    _,repo,paths,worker,results,errors,_=preflight
    worker.plan=replace(worker.plan,items=worker.plan.items[:1])
    original=producer._guard_file;swapped=False;denied=False
    def guard(path,root):
        nonlocal swapped,denied
        token=original(path,root)
        path=type(paths.root)(path)
        if not swapped and path.parent==paths.ready:
            swapped=True
            data=path.read_bytes()
            try:path.rename(path.with_suffix('.held'));path.write_bytes(data)
            except PermissionError:denied=True
        return token
    monkeypatch.setattr(producer,'_guard_file',guard)
    worker.run()
    assert swapped and not errors
    if os.name=='nt':
        assert denied and results[0].created==1
    else:
        assert results[0].failed==1 and not repo.list_managed_bindings()
        assert results[0].outcomes[0].destination.is_file()


def test_later_check_of_receipt_never_manufactures_current_positive_state(preflight):
    from audio_library_organizer.jobs.created_output import producer_check
    from audio_library_organizer.domain.file_state import evaluate_file_state,FileState
    import time
    _,repo,paths,worker,results,errors,_=preflight
    worker.run();assert not errors
    for binding in repo.list_managed_bindings():
        facts=producer_check(binding,repo.get_track(binding.track_id),paths.root,
            at=time.time_ns(),policy_revision='any-current-policy',cancelled=lambda:False)
        value=evaluate_file_state(facts)
        assert value.state==FileState.IN_LIBRARY and not value.is_confirmed
        assert facts.desired is None


def test_published_locator_survives_publication_context_cleanup_failure(tmp_path):
    from contextlib import contextmanager
    from audio_library_organizer.safety.copy_pipeline import copy_without_overwrite,PublishedCopyError
    source=tmp_path/'source.mp3';source.write_bytes(b'synthetic copy bytes')
    @contextmanager
    def publication(staged):
        yield lambda target:None
        raise OSError('injected producer cleanup failure')
    with pytest.raises(PublishedCopyError)as error:
        copy_without_overwrite(source,tmp_path/'output',publication=publication)
    assert error.value.destination.is_file()
    assert error.value.destination.read_bytes()==source.read_bytes()


def test_changed_producer_output_uses_existing_conflict_state(preflight,mp3_samples):
    from audio_library_organizer.jobs.file_reconciliation import check_library
    from audio_library_organizer.domain.file_state import FileState
    import shutil
    _,repo,paths,worker,results,errors,_=preflight
    worker.run();assert not errors
    binding=repo.list_managed_bindings()[0]
    target=type(paths.root)(binding.locator(paths.root))
    shutil.copyfile(mp3_samples['different_tail'],target)
    result=check_library(repo,library_root=paths.root)
    item=next(i for i in result.files if i.track_id==binding.track_id)
    assert item.evaluation.state==FileState.CONFLICT
    assert repo.get_file_state(binding.track_id).evaluation.state==FileState.CONFLICT
    assert not repo.get_file_state(binding.track_id).evaluation.is_confirmed


def test_touch_is_history_not_an_ownership_conflict(preflight):
    import os,time
    from audio_library_organizer.jobs.created_output import producer_check
    from audio_library_organizer.domain.file_state import evaluate_file_state,FileState
    _,repo,paths,worker,results,errors,_=preflight
    worker.run();assert not errors
    binding=repo.list_managed_bindings()[0];target=type(paths.root)(binding.locator(paths.root))
    st=target.stat();os.utime(target,ns=(st.st_atime_ns,st.st_mtime_ns+10000000))
    facts=producer_check(binding,repo.get_track(binding.track_id),paths.root,at=time.time_ns(),
        policy_revision='',cancelled=lambda:False)
    assert evaluate_file_state(facts).state==FileState.IN_LIBRARY
    assert not evaluate_file_state(facts).is_confirmed and facts.conflict is None


def test_missing_producer_output_uses_existing_missing_state(preflight):
    from audio_library_organizer.jobs.file_reconciliation import check_library
    from audio_library_organizer.domain.file_state import FileState
    _,repo,paths,worker,results,errors,_=preflight
    worker.run();assert not errors
    binding=repo.list_managed_bindings()[0];type(paths.root)(binding.locator(paths.root)).unlink()
    result=check_library(repo,library_root=paths.root)
    item=next(i for i in result.files if i.track_id==binding.track_id)
    assert item.evaluation.state==FileState.MANAGED_FILE_MISSING
    assert repo.get_file_state(binding.track_id).evaluation.state==FileState.MANAGED_FILE_MISSING
    assert len(repo.list_managed_bindings())==2


def test_automatic_check_follows_receipt_at_same_clock_tick(preflight,mp3_samples,monkeypatch):
    import shutil
    from audio_library_organizer.jobs import file_reconciliation as reconciliation
    from audio_library_organizer.domain.file_state import FileState
    _,repo,paths,worker,results,errors,_=preflight
    worker.run();assert not errors
    bindings=repo.list_managed_bindings();at=max(b.adopted_at for b in bindings)
    binding=bindings[0]
    shutil.copyfile(mp3_samples['different_tail'],binding.locator(paths.root))
    monkeypatch.setattr(reconciliation.time,'time_ns',lambda:at)
    result=reconciliation.check_library(repo,library_root=paths.root)
    assert result.checked_at>at and result.cache_saved==2,(result.reason_codes,result.cache_saved)
    assert repo.get_file_state(binding.track_id).evaluation.state==FileState.CONFLICT
    explicit=reconciliation.check_library(repo,library_root=paths.root,checked_at=at)
    assert explicit.checked_at==at and explicit.cache_saved==0
    assert 'CACHE_WRITE_REJECTED'in explicit.reason_codes
