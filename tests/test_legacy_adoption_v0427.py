import csv
import hashlib
import importlib
import importlib.util
from pathlib import Path

import pytest

from audio_adoption_fixtures import mp3_samples, copy_audio
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.storage.repository import LibraryRepository


def adoption_api():
    name = 'audio_library_organizer.jobs.legacy_adoption'
    assert importlib.util.find_spec(name) is not None, 'Missing explicit legacy adoption contract'
    return importlib.import_module(name)


@pytest.fixture
def library(tmp_path, mp3_samples):
    root = tmp_path/'library'; root.mkdir()
    source = copy_audio(mp3_samples['original'], tmp_path/'source'/'Artist - Title.mp3')
    repo = LibraryRepository(root/'.alo'/'library.sqlite3'); repo.initialize()
    repo.bootstrap_sources([source.parent])
    st = source.stat()
    track = TrackRecord(path=source, size_bytes=st.st_size, mtime_ns=st.st_mtime_ns,
                        sha256=hashlib.sha256(source.read_bytes()).hexdigest(), artist='Manual artist',
                        title='Manual title', status='duplicate', locked_fields={'title'},
                        field_sources={'title':'manual'}, original_tags={'fixture':True})
    repo.upsert_track(track)
    output = copy_audio(source, root/'GOTOWE'/'Artist - Title (Extended Mix).mp3', title='Legacy title', cover=True)
    return repo, root, track, output


def inventory(library, **kwargs):
    repo, root, _, _ = library
    return adoption_api().inventory_legacy_outputs(repo, library_root=root, **kwargs)


def test_legacy_report_mapping_is_only_candidate_evidence(library):
    repo, root, track, output = library
    reports = root/'raporty'; reports.mkdir()
    with (reports/'old.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['source_path','destination_path','verified'])
        writer.writeheader(); writer.writerow({'source_path':str(track.path),'destination_path':str(output),'verified':True})
    result = inventory(library)
    assert len(result.proposals) == 1 and result.proposals[0].status == 'CANDIDATE'
    assert any('CSV' in value for value in result.proposals[0].evidence_sources)
    assert repo.list_managed_bindings() == ()


def test_multiple_legacy_outputs_block_automatic_creation(library):
    repo, root, track, output = library
    copy_audio(output, root/'DO_SPRAWDZENIA'/'Artist - Title (2).mp3')
    result = inventory(library)
    assert len(result.proposals) == 2
    assert all(p.status == 'CONFLICT' and not p.can_adopt for p in result.proposals)
    assert track.track_id in result.blocked_track_ids
    assert repo.list_managed_bindings() == ()
    guard=getattr(adoption_api(),'assert_legacy_export_allowed',None)
    assert callable(guard), 'Missing actual export barrier for unresolved legacy outputs'
    with pytest.raises(ValueError,match='adoption|Adoption|historical'):
        guard(result,repo.list_tracks())


def test_same_filename_or_fingerprint_never_authorizes_adoption(library, mp3_samples):
    repo, root, track, output = library
    output.write_bytes(mp3_samples['different_tail'].read_bytes())
    track.fingerprint = 'same-weak-fingerprint'; repo.upsert_track(track)
    result = inventory(library)
    assert all(p.status != 'CANDIDATE' for p in result.proposals)
    assert repo.list_managed_bindings() == ()


def test_adoption_requires_explicit_confirmation(library):
    repo, root, _, _ = library
    proposal=inventory(library).proposals[0]
    with pytest.raises(ValueError,match='confirmation'):
        adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=False,library_root=root)
    assert repo.list_managed_bindings() == ()


def test_adoption_survives_restart_without_changing_manual_work(library):
    repo, root, track, output = library
    before=repo.get_track(track.track_id); audio_bytes=output.read_bytes(); source_bytes=track.path.read_bytes()
    proposal=inventory(library).proposals[0]
    adopted=adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    reopened=LibraryRepository(repo.database_path); reopened.initialize()
    binding=reopened.list_managed_bindings()[0]
    assert adopted.track_id == binding.track_id == track.track_id
    assert binding.library_id == reopened.library_id
    assert reopened.get_track(track.track_id) == before
    assert output.read_bytes() == audio_bytes and track.path.read_bytes() == source_bytes


def test_stale_output_approval_is_rejected(library, mp3_samples):
    repo, root, _, output = library
    proposal=inventory(library).proposals[0]
    output.write_bytes(mp3_samples['different_tail'].read_bytes())
    with pytest.raises(ValueError,match='changed|stale'):
        adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings() == ()


def test_stale_record_approval_preserves_new_manual_edit(library):
    repo,root,track,_=library
    proposal=inventory(library).proposals[0]
    current=repo.get_track(track.track_id); current.title='New manual edit'; repo.upsert_track(current)
    with pytest.raises(ValueError,match='changed|stale'):
        adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    assert repo.get_track(track.track_id).title=='New manual edit' and repo.list_managed_bindings()==()


def test_source_offline_uses_only_previously_verified_source_identity(library):
    repo,root,track,_=library
    inventory(library)  # Captures a verified, UUID-scoped source reference.
    track.path.unlink()
    proposal=next(p for p in inventory(library).proposals if p.track_id==track.track_id)
    assert proposal.status=='CANDIDATE'
    binding=adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    assert binding.track_id==track.track_id and not track.path.exists()


def test_first_inventory_with_offline_source_cannot_trust_csv_or_fingerprint(library):
    repo,root,track,_=library; track.path.unlink()
    result=inventory(library)
    assert all(not p.can_adopt for p in result.proposals) and repo.list_managed_bindings()==()


@pytest.mark.parametrize('kind',['symlink','hardlink'])
def test_alias_is_not_adoptable(library,kind):
    import os
    repo,root,track,output=library
    extra=root/'GOTOWE'/'alias.mp3'
    if kind=='symlink': extra.symlink_to(output)
    else: os.link(output,extra)
    result=inventory(library)
    assert any(p.status=='CONFLICT' for p in result.proposals)
    # Any alias makes this output inventory unsuitable for ownership approval.
    assert all(not p.can_adopt for p in result.proposals)


def test_copied_foreign_uuid_marker_is_not_ownership(library):
    from mutagen.id3 import ID3,TXXX
    from uuid import uuid4
    repo,root,_,output=library
    tags=ID3(output); tags.add(TXXX(encoding=3,desc='ALO_TRACK_ID',text=[str(uuid4())])); tags.save(output)
    result=inventory(library)
    assert any('FOREIGN_UUID_MARKER' in p.reason_codes for p in result.proposals)
    assert all(not p.can_adopt for p in result.proposals)


def test_two_records_with_same_audio_do_not_choose_owner_by_report(library):
    repo,root,track,output=library
    second=copy_audio(track.path,track.path.parent/'another.mp3'); st=second.stat()
    other=TrackRecord(path=second,size_bytes=st.st_size,mtime_ns=st.st_mtime_ns,
                      sha256=hashlib.sha256(second.read_bytes()).hexdigest())
    repo.upsert_track(other)
    result=inventory(library)
    assert all(not p.can_adopt for p in result.proposals)
    assert any('MULTIPLE_RECORD_OWNERS' in p.reason_codes for p in result.proposals)


def test_another_output_appearing_after_inventory_invalidates_approval(library):
    repo,root,_,output=library; proposal=inventory(library).proposals[0]
    copy_audio(output,root/'NIE_WYBRANE'/'copy (2).mp3')
    with pytest.raises(ValueError,match='changed|stale'):
        adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings()==()


def test_existing_binding_is_never_silently_replaced(library):
    repo,root,track,_=library; proposal=inventory(library).proposals[0]
    binding=adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    with pytest.raises(ValueError,match='bound|binding'):
        adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings()==(binding,)
    assert any(p.status=='ALREADY_BOUND' for p in inventory(library).proposals)


def test_wrong_library_root_is_rejected(library,tmp_path):
    repo,_,_,_=library; proposal=inventory(library).proposals[0]
    with pytest.raises(ValueError,match='context'):
        adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=tmp_path)
    assert repo.list_managed_bindings()==()


def test_cancel_before_commit_keeps_no_binding(library):
    repo,root,_,_=library; proposal=inventory(library).proposals[0]
    with pytest.raises(InterruptedError,match='cancelled'):
        adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root,cancelled=lambda:True)
    assert repo.list_managed_bindings()==()


def test_missing_known_library_blocks_ownership_instead_of_ignoring_it(library,tmp_path):
    api=adoption_api(); missing=api.KnownLibrary(str(tmp_path/'offline'),str(tmp_path/'offline'/'.alo'/'library.sqlite3'))
    result=inventory(library,known_libraries=(missing,))
    assert all(not p.can_adopt for p in result.proposals)


def test_two_profiles_for_same_database_are_one_ownership_context(library):
    repo,root,_,_=library; api=adoption_api()
    duplicate=api.KnownLibrary(str(root),str(repo.database_path),repo.library_id)
    result=inventory(library,known_libraries=(duplicate,duplicate))
    assert len(result.known_libraries)==1 and result.proposals[0].can_adopt


def test_symlink_output_alias_cannot_leave_original_as_adoptable(library):
    repo,root,_,output=library
    (root/'GOTOWE'/'alias.mp3').symlink_to(output)
    result=inventory(library)
    assert not any(p.can_adopt for p in result.proposals), 'Alias ambiguity did not block primary candidate'


def test_source_changed_after_fresh_inventory_is_rejected_at_commit(library,mp3_samples,monkeypatch):
    repo,root,track,_=library; api=adoption_api(); proposal=inventory(library).proposals[0]
    original=api._known_state
    def changed(descriptors,**kwargs):
        result=original(descriptors,**kwargs)
        if kwargs.get('conn') is not None:
            track.path.write_bytes(mp3_samples['different_tail'].read_bytes())
        return result
    monkeypatch.setattr(api,'_known_state',changed)
    with pytest.raises(ValueError,match='source|Source|changed'):
        api.adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings()==()


def test_cancellation_during_cache_write_rolls_back_binding_and_proposal(library,monkeypatch):
    from threading import Event
    import audio_library_organizer.storage.file_state_cache as cache
    repo,root,_,_=library; api=adoption_api(); proposal=inventory(library).proposals[0]
    cancelled=Event(); original=cache.write_file_facts
    def cancel_after_write(*args,**kwargs):
        result=original(*args,**kwargs); cancelled.set(); return result
    monkeypatch.setattr(cache,'write_file_facts',cancel_after_write)
    with pytest.raises(InterruptedError,match='cancelled'):
        api.adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root,cancelled=cancelled.is_set)
    assert repo.list_managed_bindings()==()
    import sqlite3
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('SELECT status FROM legacy_adoption_proposals WHERE proposal_id=?',(proposal.proposal_id,)).fetchone()[0]=='CANDIDATE'


def test_concurrent_same_approval_commits_only_one_owner(library):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    repo,root,_,_=library; api=adoption_api(); proposal=inventory(library).proposals[0]; start=Barrier(2)
    def run():
        start.wait(timeout=5)
        try:
            api.adopt_legacy_output(LibraryRepository(repo.database_path),proposal.proposal_id,confirmed=True,library_root=root)
            return 'COMMITTED'
        except (ValueError,sqlite3.OperationalError):
            return 'REJECTED'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run) for _ in range(2)]
        results=[f.result(timeout=15) for f in futures]
    assert sorted(results)==['COMMITTED','REJECTED'] and len(repo.list_managed_bindings())==1


def test_parent_library_scope_blocks_cross_library_adoption(library,tmp_path):
    repo,root,_,_=library; api=adoption_api()
    other=LibraryRepository(tmp_path/'.alo'/'library.sqlite3'); other.initialize()
    known=api.KnownLibrary(str(tmp_path),str(other.database_path),other.library_id)
    result=inventory(library,known_libraries=(known,))
    assert all(not p.can_adopt for p in result.proposals)
    assert any('FOREIGN_LIBRARY_ROOT' in p.reason_codes for p in result.proposals)


def test_cancelled_inventory_does_not_persist_observations(library):
    import sqlite3
    repo,_,_,_=library; result=inventory(library,cancelled=lambda:True)
    assert result.cancelled
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM legacy_adoption_runs').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM source_audio_references').fetchone()[0]==0
