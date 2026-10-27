"""6.2B partial integration: pending evidence is NOT accepted display state."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Event
import time
from uuid import uuid4

import pytest
from audio_adoption_fixtures import mp3_samples
from test_legacy_adoption_v0427 import library
from test_adopted_output_spec_v0427 import approve, request
from audio_library_organizer.jobs import adopted_output as ao
from audio_library_organizer.jobs.file_reconciliation import check_library
from audio_library_organizer.metadata.change_history import metadata_revision
from audio_library_organizer.domain.file_state import FileState


def check(library, binding, *, live=None, **kwargs):
    repo, root, track, _ = library
    req = request(ao, repo, track, binding)
    return check_library(repo, library_root=root, library_id=repo.library_id,
        operation_id=req.operation_id, output_request=req,
        current_output_request=live or (lambda: req), **kwargs)


def protected(library):
    repo, _, track, output = library
    with sqlite3.connect(repo.database_path) as conn:
        rows = {name: conn.execute('SELECT * FROM '+name+' ORDER BY 1').fetchall()
                for name in ('tracks','sources','managed_bindings')}
    return rows, tuple((str(p), hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode)
                       for p in (track.path, output))


@pytest.mark.parametrize('field,value', [('artist','Changed artist'),('album','Changed album')])
def test_real_check_produces_pending_difference_without_cache_promotion(library, field, value):
    repo, root, track, _ = library
    binding = approve(library)
    t = repo.get_track(track.track_id)
    repo.save_metadata(t.track_id, {field:value}, expected_revision=metadata_revision(t), library_id=repo.library_id)
    before = protected(library)
    result = check(library, binding)
    pending = result.pending_output_assessment
    assert pending.assessment.guard and pending.assessment.difference
    assert field in {d.field for d in pending.assessment.difference.fields}
    assert pending.evaluation.state == FileState.NEEDS_UPDATE and pending.evaluation.is_confirmed
    # The ordinary cache and main results have NOT acquired incomplete OutputSpec evidence.
    assert result.files[0].evaluation.state is None
    assert repo.get_file_state(track.track_id).evaluation.state is None
    assert not repo.get_file_state(track.track_id).evaluation.is_confirmed
    assert protected(library) == before
    again = type(repo)(repo.database_path).get_file_state(track.track_id)
    assert again.evaluation.state is None and not again.evaluation.is_confirmed


def test_partial_match_keeps_pending_and_cached_state_unconfirmed(library):
    repo, _, track, _ = library; binding = approve(library)
    t = repo.get_track(track.track_id)
    repo.save_metadata(t.track_id, {'artist':'Fixture artist','title':'Legacy title'},
        expected_revision=metadata_revision(t), library_id=repo.library_id)
    result = check(library, binding)
    assert result.pending_output_assessment.assessment.reason == 'PARTIAL_MATCH_ONLY'
    assert result.pending_output_assessment.evaluation.state is None
    assert not result.pending_output_assessment.evaluation.is_confirmed


@pytest.mark.parametrize('change', ['artist','title','album','bpm','cover_choice','source','binding','generation','policy','cancel'])
def test_changes_during_read_never_produce_positive_pending_evidence(library, monkeypatch, change):
    repo, root, track, _ = library; binding = approve(library)
    req = request(ao, repo, track, binding); live = [req]; cancelled = Event()
    original = ao.recheck_read_path; once = []
    def observed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not once:
            once.append(True)
            if change in ('artist','title','album','bpm','cover_choice'):
                t = repo.get_track(track.track_id)
                repo.save_metadata(t.track_id, {change:129.0 if change=='bpm' else 'new'},
                    expected_revision=metadata_revision(t), library_id=repo.library_id)
            elif change in ('source','binding'):
                with sqlite3.connect(repo.database_path) as conn:
                    if change=='source': conn.execute("UPDATE tracks SET sha256=? WHERE track_id=?",('f'*64,track.track_id))
                    else: conn.execute('UPDATE managed_bindings SET binding_id=?',(str(uuid4()),))
            elif change=='cancel': cancelled.set()
            else: live[0]=replace(req, **({'generation':2} if change=='generation' else {'policy_revision':'new'}))
        return result
    monkeypatch.setattr(ao, 'recheck_read_path', observed)
    result=check_library(repo, library_root=root, library_id=repo.library_id, operation_id=req.operation_id,
        output_request=req,current_output_request=lambda:live[0],cancelled=cancelled.is_set)
    assert once
    pending=result.pending_output_assessment
    assert pending is None or (pending.assessment.difference is None and not pending.evaluation.is_confirmed)
    assert all(f.evaluation.state != FileState.NEEDS_UPDATE for f in result.files)
    if change=='cancel':
        assert result.cancelled and 'CANCELLED' in result.reason_codes


def test_unbound_regular_check_has_no_new_producer(library):
    repo,root,_,_=library
    result=check_library(repo,library_root=root)
    assert result.pending_output_assessment is None
    assert repo.list_managed_bindings()==()


@pytest.mark.parametrize('kind',['tag','missing','incomplete','foreign'])
def test_unverified_or_foreign_material_never_gets_positive_pending(library,kind):
    repo,root,track,output=library;binding=approve(library)
    if kind=='tag':
        from mutagen.id3 import ID3,TIT2
        tags=ID3(output);tags.add(TIT2(encoding=3,text=['Changed']));tags.save(output)
    elif kind=='missing': output.unlink()
    elif kind=='incomplete':
        with sqlite3.connect(repo.database_path) as conn:conn.execute("UPDATE managed_bindings SET applied_snapshot_json='{}'")
    else: binding=replace(binding,binding_id=str(uuid4()))
    result=check(library,binding)
    p=result.pending_output_assessment
    assert p is None or p.evaluation.state != FileState.NEEDS_UPDATE
    assert all(f.evaluation.state != FileState.NEEDS_UPDATE for f in result.files)


def test_manual_cover_at_same_path_remains_explicitly_unsupported(library,tmp_path):
    repo,_,track,_=library;binding=approve(library)
    cover=tmp_path/'manual.png';cover.write_bytes(b'first synthetic content')
    t=repo.get_track(track.track_id)
    repo.save_metadata(t.track_id,{'manual_cover_path':str(cover),'cover_choice':'manual'},
        expected_revision=metadata_revision(t),library_id=repo.library_id)
    for content in (b'first synthetic content',b'changed synthetic content'):
        cover.write_bytes(content)
        result=check(library,binding)
        p=result.pending_output_assessment
        assert p.assessment.reason=='COVER_CONTENT_CONTEXT_REQUIRED'
        assert not p.evaluation.is_confirmed and p.assessment.difference is None
    assert cover.read_bytes()==b'changed synthetic content'


@pytest.mark.parametrize('field',['library_id','operation_id'])
def test_mismatched_envelope_is_rejected_before_cache_write(library,field):
    repo,root,track,_=library;binding=approve(library)
    # Adoption itself seeds a historical cache row. Check no change to it,
    # not absence of a row which the fixture deliberately created.
    before=repo.get_file_state(track.track_id)
    original=request(ao,repo,track,binding)
    req=replace(original,**{field:str(uuid4())})
    with pytest.raises(ValueError,match='Output assessment context'):
        check_library(repo,library_root=root,library_id=repo.library_id,operation_id=original.operation_id,
            output_request=req,current_output_request=lambda:req)
    assert repo.get_file_state(track.track_id) == before


def test_actual_qthread_delivers_pending_evidence_without_promoting_it(library):
    from PySide6.QtCore import QThread,QObject,Slot,Qt
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    app=QApplication.instance() or QApplication([])
    repo,root,track,_=library;binding=approve(library);req=request(ao,repo,track,binding)
    thread=QThread();worker=FileReconciliationWorker(repo,library_id=repo.library_id,
        operation_id=req.operation_id,library_root=root,output_request=req,current_output_request=lambda:req)
    got=[];errors=[]
    class Receiver(QObject):
        @Slot(object)
        def receive(self,result):
            assert QThread.currentThread()==app.thread()
            got.append(result)
    receiver=Receiver();worker.moveToThread(thread)
    worker.finished.connect(receiver.receive,Qt.ConnectionType.QueuedConnection)
    worker.finished.connect(thread.quit,Qt.ConnectionType.DirectConnection)
    worker.failed.connect(lambda *args:errors.append(args))
    worker.failed.connect(thread.quit,Qt.ConnectionType.DirectConnection)
    thread.finished.connect(worker.deleteLater);thread.started.connect(worker.run)
    thread.start()
    try:
        deadline=time.monotonic()+15
        while not got and not errors and time.monotonic()<deadline:app.processEvents()
        assert thread.wait(15000)
        app.processEvents()
        assert not errors and len(got)==1
        assert got[0].pending_output_assessment.evaluation.state==FileState.NEEDS_UPDATE
        assert repo.get_file_state(track.track_id).evaluation.state is None
    finally:
        worker.cancel() if thread.isRunning() else None
        thread.quit();assert thread.wait(15000)


@pytest.mark.parametrize('value',[None,'',42,[],{}])
def test_incomplete_applied_value_has_no_invented_token_or_authority(library,value):
    repo,root,track,_=library;binding=approve(library)
    payload=dict(binding.applied_snapshot);payload['value']=value
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('UPDATE managed_bindings SET applied_snapshot_json=?',(json.dumps(payload),))
    binding=repo.list_managed_bindings()[0]
    before=protected(library)
    result=check(library,binding)
    item=result.files[0]
    assert item.facts.applied is None
    assert item.facts.owner_track_id==track.track_id
    assert result.pending_output_assessment.assessment.difference is None
    assert not result.pending_output_assessment.evaluation.is_confirmed
    assert protected(library)==before


def test_pending_packet_is_not_delivery_authority_after_later_metadata_edit(library):
    repo,_,track,_=library;binding=approve(library)
    result=check(library,binding);pending=result.pending_output_assessment
    assert pending.evaluation.state==FileState.NEEDS_UPDATE
    t=repo.get_track(track.track_id)
    repo.save_metadata(t.track_id,{'artist':'Later edit after worker return'},
        expected_revision=metadata_revision(t),library_id=repo.library_id)
    assert pending.assessment.guard.metadata_revision != metadata_revision(repo.get_track(track.track_id))
    # No consumer is authorized by this packet: cache remains unconfirmed.
    assert repo.get_file_state(track.track_id).evaluation.state is None


def test_one_requested_record_does_not_fan_out_extra_assessments(library,monkeypatch):
    from audio_library_organizer.domain.models import TrackRecord
    repo,_,track,_=library;binding=approve(library)
    for i in range(40):repo.upsert_track(TrackRecord(track.path.parent/f'missing-{i}.mp3'))
    original=ao.assess_adopted_mp3;calls=[]
    def observe(*args,**kwargs):
        calls.append(args[2].track_id)
        return original(*args,**kwargs)
    monkeypatch.setattr(ao,'assess_adopted_mp3',observe)
    result=check(library,binding)
    assert len(result.files)==41 and calls==[track.track_id]
    assert result.pending_output_assessment.evaluation.state==FileState.NEEDS_UPDATE


def test_cancelled_check_has_no_pending_positive(library):
    repo,root,track,_=library;binding=approve(library)
    result=check(library,binding,cancelled=lambda:True)
    assert result.cancelled and result.pending_output_assessment is None
