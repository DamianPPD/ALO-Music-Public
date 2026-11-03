"""Real approved SQLite bindings and synthetic MP3, no production collection."""
from contextlib import closing
from dataclasses import asdict, replace
import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import json
import subprocess
import time
from uuid import uuid4

import pytest
from mutagen.id3 import ID3, TIT2
from audio_adoption_fixtures import mp3_samples, copy_audio
from test_legacy_adoption_v0427 import library, inventory, adoption_api
from audio_library_organizer.domain.file_state import FileState
from audio_library_organizer.metadata.change_history import metadata_revision
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.domain.models import TrackRecord


def api():
    name='audio_library_organizer.jobs.adopted_output'
    assert importlib.util.find_spec(name), 'Missing guarded adopted MP3 assessment'
    return importlib.import_module(name)


def approve(library):
    repo,root,track,output=library
    proposal=inventory(library).proposals[0]
    binding=adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
    return binding


def request(m,repo,track,binding):
    return m.AssessmentRequest(repo.library_id,track.track_id,binding.binding_id,str(uuid4()),1,'policy-v1')


def assess(m,library,binding,**kwargs):
    repo,root,track,_=library;r=request(m,repo,track,binding)
    return m.assess_adopted_mp3(repo,root,r,current_request=lambda:r,**kwargs)


def test_real_difference_after_restart_has_guard_and_preserves_audio_and_database_identity(library):
    m=api();repo,root,track,output=library;binding=approve(library)
    before={str(p):p.read_bytes() for p in (track.path,output)}
    records=asdict(repo.get_track(track.track_id));bindings=repo.list_managed_bindings()
    reopened=LibraryRepository(repo.database_path)
    result=assess(m,(reopened,root,track,output),binding)
    assert result.evaluation.state==FileState.NEEDS_UPDATE and result.evaluation.is_confirmed
    assert {d.field for d in result.difference.fields}>={'artist','title'}
    assert result.guard.metadata_revision==metadata_revision(repo.get_track(track.track_id))
    assert result.guard.binding_revision and result.guard.material_identity
    assert {str(p):p.read_bytes() for p in (track.path,output)}==before
    assert asdict(repo.get_track(track.track_id))==records and repo.list_managed_bindings()==bindings
    with closing(sqlite3.connect(repo.database_path)) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_real_partial_equality_never_promotes_to_in_library(library):
    m=api();repo,_,track,_=library;binding=approve(library)
    t=repo.get_track(track.track_id)
    repo.save_metadata(t.track_id,{'artist':'Fixture artist','title':'Legacy title'},
                       expected_revision=metadata_revision(t),library_id=repo.library_id)
    result=assess(m,library,binding)
    assert result.difference is None and not result.evaluation.is_confirmed
    assert result.evaluation.state is None
    assert result.reason=='PARTIAL_MATCH_ONLY'


@pytest.mark.parametrize('kind',['tag','replace','missing','source','offline','incomplete'])
def test_changed_missing_and_incomplete_material_never_gives_needs_update(library,kind,mp3_samples):
    m=api();repo,_,track,output=library;binding=approve(library)
    if kind=='tag':
        tags=ID3(output);tags.add(TIT2(encoding=3,text=['Tampered']));tags.save(output)
    elif kind=='replace':
        output.unlink();output.write_bytes(mp3_samples['different_tail'].read_bytes())
    elif kind=='missing':output.unlink()
    elif kind=='source':
        t=repo.get_track(track.track_id);t.sha256='f'*64;repo.upsert_track(t)
    elif kind=='offline':track.path.unlink()
    else:
        with closing(sqlite3.connect(repo.database_path)) as conn,conn:
            conn.execute("UPDATE managed_bindings SET applied_snapshot_json='{}'")
    result=assess(m,library,binding)
    assert result.evaluation.state not in (FileState.NEEDS_UPDATE,FileState.IN_LIBRARY)
    assert result.reason and result.difference is None


@pytest.mark.parametrize('field',['library_id','track_id','binding_id'])
def test_foreign_request_identity_is_refused(library,field):
    m=api();repo,root,track,_=library;b=approve(library);r=replace(request(m,repo,track,b),**{field:str(uuid4())})
    result=m.assess_adopted_mp3(repo,root,r,current_request=lambda:r)
    assert not result.evaluation.is_confirmed and result.difference is None


def test_no_binding_or_live_guard_never_creates_ownership(library):
    m=api();repo,root,track,_=library
    r=m.AssessmentRequest(repo.library_id,track.track_id,str(uuid4()),str(uuid4()),1,'p1')
    assert not m.assess_adopted_mp3(repo,root,r,current_request=lambda:r).evaluation.is_confirmed
    b=approve(library)
    assert not m.assess_adopted_mp3(repo,root,request(m,repo,track,b),current_request=None).evaluation.is_confirmed


@pytest.mark.parametrize('kind',['metadata','generation','library','binding','policy','cancel'])
def test_changes_during_actual_read_discard_old_result(library,monkeypatch,kind):
    m=api();repo,root,track,_=library;b=approve(library);r=request(m,repo,track,b)
    live=[r];cancel=[False];original=m.recheck_read_path;done=[]
    def observed(*args,**kwargs):
        proof=original(*args,**kwargs)
        if not done:
            done.append(True)
            if kind=='metadata':
                t=repo.get_track(track.track_id)
                repo.save_metadata(t.track_id,{'artist':'Later edit'},expected_revision=metadata_revision(t),library_id=repo.library_id)
            elif kind=='binding':
                with closing(sqlite3.connect(repo.database_path)) as conn,conn:
                    conn.execute('UPDATE managed_bindings SET binding_id=?',(str(uuid4()),))
            elif kind=='cancel':cancel[0]=True
            else:
                key={'generation':'generation','library':'library_id','policy':'policy_revision'}[kind]
                live[0]=replace(r,**{key:2 if key=='generation' else str(uuid4())})
        return proof
    monkeypatch.setattr(m,'recheck_read_path',observed)
    result=m.assess_adopted_mp3(repo,root,r,current_request=lambda:live[0],cancelled=lambda:cancel[0])
    assert not result.evaluation.is_confirmed and result.difference is None


def test_staging_and_nested_placements_are_locally_unconfirmed_without_hiding_names(library):
    m=api();repo,root,track,output=library
    nested=output.parent/'.alo-copy-synthetic';nested.mkdir();output.rename(nested/output.name)
    b=approve((repo,root,track,nested/output.name))
    result=assess(m,(repo,root,track,nested/output.name),b)
    assert result.reason=='FINAL_PLACEMENT_UNCONFIRMED' and not result.evaluation.is_confirmed
    assert (nested/output.name).is_file()


def test_similar_filename_directly_in_final_root_is_not_globally_ignored(library):
    m=api();repo,root,track,output=library;p=output.with_name('.alo-copy-user-song.mp3');output.rename(p)
    lib=(repo,root,track,p);b=approve(lib)
    assert assess(m,lib,b).evaluation.state==FileState.NEEDS_UPDATE


@pytest.mark.parametrize('kind',['permission','symlink','hardlink','sql-error'])
def test_read_errors_and_aliases_fail_closed_without_removal(library,kind,monkeypatch):
    m=api();repo,root,track,output=library;b=approve(library)
    before=output.read_bytes()
    if kind=='permission':
        original=m._no_reparse
        def denied(path,root):
            if Path(path)==output:raise PermissionError('Synthetic access refusal')
            return original(path,root)
        monkeypatch.setattr(m,'_no_reparse',denied)
    elif kind=='symlink':
        held=output.with_suffix('.held');output.rename(held);output.symlink_to(held)
    elif kind=='hardlink':os.link(output,output.with_suffix('.alias'))
    else:
        def broken(*args):raise sqlite3.OperationalError('Synthetic SQLite read error')
        monkeypatch.setattr(repo,'adopted_assessment_snapshot',broken)
    result=assess(m,library,b)
    assert not result.evaluation.is_confirmed and result.difference is None
    assert output.read_bytes()==before


def test_sqlite_rejects_a_second_owner_for_the_same_native_object(library):
    m=api();repo,root,track,output=library;b=approve(library)
    second=TrackRecord(track.path.parent/'other.mp3');repo.upsert_track(second)
    with closing(sqlite3.connect(repo.database_path)) as conn,conn:
        conn.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('''INSERT INTO managed_bindings SELECT ?,library_id,?,
                'GOTOWE/alias.mp3',?,expected_sha256,audio_algorithm,audio_digest,
                device,inode,stat_json,source_binding_json,applied_snapshot_json,evidence_json,adopted_at
                FROM managed_bindings WHERE track_id=?''',
                (second.track_id,str(uuid4()),str(output)+'.alias',track.track_id))
    assert repo.list_managed_bindings()==(b,)


def test_scale_with_eight_real_approved_mp3_and_fixed_query_count(tmp_path,monkeypatch):
    m=api();root=tmp_path/'library';source=tmp_path/'source';source.mkdir()
    repo=LibraryRepository(root/'.alo'/'library.sqlite3');repo.initialize();repo.bootstrap_sources([source])
    timings=[];query_counts=[]
    original_connect=sqlite3.connect
    for i in range(8):
        path=source/f'{i}.mp3'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i',
            f'sine=frequency={440+i*31}:duration=0.3','-ac','2','-c:a','libmp3lame','-b:a','128k',str(path)],
            check=True,capture_output=True,timeout=15)
        st=path.stat();t=TrackRecord(path,size_bytes=st.st_size,mtime_ns=st.st_mtime_ns,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),artist=f'Desired {i}',title=f'Title {i}')
        repo.upsert_track(t)
        output=copy_audio(path,root/'GOTOWE'/path.name,title=f'Applied {i}')
        inv=adoption_api().inventory_legacy_outputs(repo,library_root=root)
        proposal=next(p for p in inv.proposals if p.track_id==t.track_id and p.can_adopt)
        b=adoption_api().adopt_legacy_output(repo,proposal.proposal_id,confirmed=True,library_root=root)
        if i in (0,3,7):
            r=request(m,repo,t,b);queries=[]
            def connect(*args,**kwargs):
                c=original_connect(*args,**kwargs);c.set_trace_callback(queries.append);return c
            with monkeypatch.context() as patch:
                patch.setattr(sqlite3,'connect',connect)
                start=time.perf_counter();result=m.assess_adopted_mp3(repo,root,r,current_request=lambda:r)
                elapsed=time.perf_counter()-start
            assert result.evaluation.state==FileState.NEEDS_UPDATE
            assert not any('file_state_cache' in q for q in queries)
            query_counts.append(len(queries));timings.append({'real_approved_bindings':i+1,'one_selected_assessment_seconds':elapsed,'sql_statements':len(queries)})
    assert len(repo.list_managed_bindings())==8 and len(set(query_counts))==1
    if os.environ.get('STAGE62A_EVIDENCE'):
        Path(os.environ['STAGE62A_EVIDENCE'],'scale-real-bindings.json').write_text(json.dumps({
            'scope':'ONE_SELECTED_RECORD_AMONG_1_4_8_REAL_WORKFLOW_ADOPTIONS_NOT_BULK_OR_WINDOWS',
            'observations':timings,'full_library_batch':'NOT IMPLEMENTED'},indent=2)+'\n')


def test_snapshot_cost_with_one_thousand_schema_valid_synthetic_binding_rows(library,monkeypatch):
    """SQL scaling only; generated rows are NOT claimed to be real adopted files."""
    m=api();repo,root,track,output=library;b=approve(library)
    with closing(sqlite3.connect(repo.database_path)) as conn,conn:
        columns=[r[1] for r in conn.execute('PRAGMA table_info(managed_bindings)')]
        template=dict(zip(columns,conn.execute('SELECT * FROM managed_bindings').fetchone()))
        for i in range(999):
            tid=str(uuid4());conn.execute('INSERT INTO tracks(track_id,path,path_key) VALUES (?,?,?)',
                (tid,str(root/'synthetic'/f'{i}.mp3'),'model:'+str(i)))
            row=dict(template,track_id=tid,binding_id=str(uuid4()),relative_path=f'GOTOWE/model-{i}.mp3',
                locator_key='model:'+str(i),inode=10_000_000+i)
            stamp=json.loads(row['stat_json']);stamp[1]=row['inode'];row['stat_json']=json.dumps(stamp)
            conn.execute('INSERT INTO managed_bindings VALUES ('+','.join('?' for _ in columns)+')',
                         tuple(row[c] for c in columns))
    queries=[];original=sqlite3.connect
    def observed(*args,**kwargs):
        c=original(*args,**kwargs);c.set_trace_callback(queries.append);return c
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',observed);start=time.perf_counter()
        snapshot=repo.adopted_assessment_snapshot(track.track_id);elapsed=time.perf_counter()-start
    assert len(snapshot.managed_bindings)==1000 and len(queries)<15
    assert not any('file_state_cache' in q for q in queries)
    if os.environ.get('STAGE62A_EVIDENCE'):
        Path(os.environ['STAGE62A_EVIDENCE'],'scale-synthetic-binding-rows.json').write_text(json.dumps({
            'scope':'SCHEMA_VALID_SYNTHETIC_SQL_ROWS_ONLY_NOT_APPROVED_WORKFLOW_OR_FILE_PREFLIGHT',
            'rows':1000,'snapshot_seconds':elapsed,'sql_statements':len(queries)},indent=2)+'\n')
