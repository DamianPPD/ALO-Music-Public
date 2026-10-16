"""Regressions from the independent Stage 3 safety review."""
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest
from mutagen.id3 import ID3, TXXX

from audio_adoption_fixtures import mp3_samples, copy_audio
from test_legacy_adoption_v0427 import library, inventory, adoption_api
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.storage.repository import LibraryRepository


def test_adoption_entry_module_imports_in_fresh_process():
    result=subprocess.run([sys.executable,'-c','import audio_library_organizer.jobs.legacy_adoption'],
        env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'src'),'PYTHONDONTWRITEBYTECODE':'1'},
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0, result.stderr


def test_no_xing_stream_cannot_prove_complete_frame_aligned_tail(tmp_path,mp3_samples):
    from audio_library_organizer.audio.identity import inspect_audio
    full=tmp_path/'no-count.mp3'
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(mp3_samples['original']),
                    '-c:a','libmp3lame','-b:a','128k','-write_xing','0',str(full)],
                   capture_output=True,check=True,timeout=15)
    data=full.read_bytes(); begin=10+sum(x << (7*(3-i)) for i,x in enumerate(data[6:10]))
    # First MPEG-1/128kbps/44.1kHz frame: retaining whole frames is not a
    # decode error, so the missing declaration must explicitly be unsupported.
    pos=begin
    for _ in range(39):
        header=int.from_bytes(data[pos:pos+4],'big')
        pos+=144*128000//44100+((header>>9)&1)
    truncated=tmp_path/'aligned-truncation.mp3'; truncated.write_bytes(data[:pos])
    for path in (full,truncated):
        proof=inspect_audio(path)
        assert proof.status=='UNSUPPORTED' and proof.audio_digest is None, 'No declared complete stream length'


def test_active_profile_uuid_is_not_discarded_by_descriptor_dedup(library):
    repo,root,_,_=library; api=adoption_api()
    wrong=api.KnownLibrary(str(root),str(repo.database_path),str(uuid4()))
    result=inventory(library,known_libraries=(wrong,))
    assert not any(p.can_adopt for p in result.proposals)


def test_weak_foreign_marker_cannot_remove_a_matching_copy_from_ambiguity(library):
    repo,root,_,output=library
    second=copy_audio(output,root/'NIE_WYBRANE'/'copy (2).mp3')
    tags=ID3(second); tags.add(TXXX(encoding=3,desc='ALO_TRACK_ID',text=[str(uuid4())])); tags.save(second)
    result=inventory(library)
    assert not any(p.can_adopt for p in result.proposals), 'A weak marker selected an owner among matching outputs'
    assert repo.list_managed_bindings()==()


def another_library(tmp_path, sample):
    root=tmp_path/'foreign'; root.mkdir()
    repo=LibraryRepository(root/'.alo'/'library.sqlite3'); repo.initialize()
    source=copy_audio(sample,tmp_path/'foreign-source'/'song.mp3')
    repo.bootstrap_sources([source.parent]); st=source.stat()
    track=TrackRecord(source,size_bytes=st.st_size,mtime_ns=st.st_mtime_ns,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    repo.upsert_track(track)
    output=copy_audio(source,root/'GOTOWE'/'owned.mp3')
    api=adoption_api(); p=api.inventory_legacy_outputs(repo,library_root=root).proposals[0]
    api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root)
    return repo,root,output


def test_current_foreign_owner_alias_blocks_adoption(library,tmp_path,mp3_samples):
    repo,root,_,output=library; api=adoption_api()
    foreign,foreign_root,owned=another_library(tmp_path,mp3_samples['original'])
    owned.unlink(); owned.symlink_to(output)
    known=api.KnownLibrary(str(foreign_root),str(foreign.database_path),foreign.library_id)
    result=inventory(library,known_libraries=(known,))
    assert not any(p.can_adopt for p in result.proposals), 'Stored inode missed current cross-library owner alias'
    assert repo.list_managed_bindings()==()


def test_malformed_known_library_does_not_count_as_complete_ownership_context(library,tmp_path):
    root=tmp_path/'bad-profile'; root.mkdir(); db=root/'bad.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE library_metadata(singleton INTEGER,library_id TEXT)')
        conn.execute('INSERT INTO library_metadata VALUES(1,?)',(str(uuid4()),))
        conn.execute('PRAGMA user_version=3')
    api=adoption_api(); result=inventory(library,known_libraries=(api.KnownLibrary(str(root),str(db)),))
    assert not any(p.can_adopt for p in result.proposals), 'Malformed profile was treated as an owner-complete library'


def test_second_matching_output_appearing_during_commit_invalidates_approval(library,monkeypatch):
    repo,root,_,output=library; api=adoption_api(); p=inventory(library).proposals[0]
    original=api.inspect_audio; calls=0
    def late_copy(path,**kwargs):
        nonlocal calls
        result=original(path,**kwargs)
        if Path(path)==output:
            calls+=1
            if calls==2: copy_audio(output,root/'NIE_WYBRANE'/'late (2).mp3')
        return result
    monkeypatch.setattr(api,'inspect_audio',late_copy)
    with pytest.raises(ValueError,match='changed|inventory|Inventory|copy'):
        api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings()==()


def test_offline_source_reappearing_changed_during_commit_rejects_approval(library,mp3_samples,monkeypatch):
    repo,root,track,output=library; api=adoption_api(); p=inventory(library).proposals[0]
    track.path.unlink(); original=api.inspect_audio; calls=0
    def reappears(path,**kwargs):
        nonlocal calls
        result=original(path,**kwargs)
        if Path(path)==output:
            calls+=1
            if calls==2: track.path.write_bytes(mp3_samples['different_tail'].read_bytes())
        return result
    monkeypatch.setattr(api,'inspect_audio',reappears)
    with pytest.raises(ValueError,match='Source|source|changed'):
        api.adopt_legacy_output(repo,p.proposal_id,confirmed=True,library_root=root)
    assert repo.list_managed_bindings()==()


def test_partial_tag_snapshot_cannot_confirm_clean_output_policy(library):
    from audio_library_organizer.domain.file_state import FileState, evaluate_file_state
    from audio_library_organizer.domain.settings import LibraryPaths
    from audio_library_organizer.jobs.exporter import ExportPlan
    from audio_library_organizer.jobs.managed_files import ReadPurpose, resolve_read_path, read_material
    repo,root,track,output=library; api=adoption_api()
    output.unlink(); output=copy_audio(track.path,root/'GOTOWE'/track.filename)
    track.artist=''; track.title=''; track.field_sources={}; track.locked_fields=set()
    track.proposed_filename=track.filename; track.status='review'; repo.upsert_track(track)
    proposal=inventory((repo,root,track,output)).proposals[0]
    binding=api.adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    expected=ExportPlan.from_tracks([track],LibraryPaths(root)).items[0].destination_dir
    assert expected!=output.parent
    evaluation=evaluate_file_state(api.binding_facts(binding,track,root,current=True))
    assert not (evaluation.is_confirmed and evaluation.state==FileState.IN_LIBRARY), 'Partial snapshot pretended full policy was applied'
    track.path.unlink()
    context=repo.read_context(root)
    result=read_material(resolve_read_path(track,context,ReadPurpose.PLAYBACK),lambda path:path.read_bytes())
    assert result.resolution.is_verified and result.value==output.read_bytes()


def test_known_binding_cannot_be_reinterpreted_under_a_different_profile_root(library,tmp_path,mp3_samples):
    repo,root,_,output=library; api=adoption_api()
    foreign,foreign_root,owned=another_library(tmp_path,mp3_samples['original'])
    owned.unlink(); owned.symlink_to(output)
    declared=tmp_path/'moved-profile'; (declared/'.alo').mkdir(parents=True)
    copied=declared/'.alo'/'library.sqlite3'
    with sqlite3.connect(foreign.database_path) as source, sqlite3.connect(copied) as target:
        source.backup(target)
    known=api.KnownLibrary(str(declared),str(copied),foreign.library_id)
    result=inventory(library,known_libraries=(known,))
    assert not any(p.can_adopt for p in result.proposals), 'Foreign binding was silently reinterpreted under a new root'
