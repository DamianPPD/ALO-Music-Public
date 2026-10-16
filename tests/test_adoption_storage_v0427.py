import hashlib
import sqlite3

import pytest

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.storage.database import SCHEMA_VERSION
import audio_library_organizer.storage.migrations as migrations

TABLES = ('legacy_adoption_proposals','legacy_adoption_runs','source_audio_references','managed_bindings')


def v3_database(tmp_path):
    repo=LibraryRepository(tmp_path/'library.sqlite3'); repo.initialize()
    track=TrackRecord(path=tmp_path/'offline.mp3',size_bytes=123,mtime_ns=456,
                      title='Manual',locked_fields={'title'},field_sources={'title':'manual'},
                      status='duplicate',audio_recognition={'chosen':'preserve'})
    repo.upsert_track(track)
    with sqlite3.connect(repo.database_path) as conn:
        for table in TABLES:
            conn.execute(f'DROP TABLE IF EXISTS {table}')
        conn.execute('PRAGMA user_version=3')
    return repo,track


def test_schema_v4_adds_separate_authoritative_bindings(tmp_path):
    repo,track=v3_database(tmp_path); before=repo.get_track(track.track_id)
    repo.initialize()
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 4, 'Missing v3→v4 adoption migration'
        names={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert set(TABLES) <= names
        assert conn.execute('SELECT COUNT(*) FROM managed_bindings').fetchone()[0]==0
    assert repo.get_track(track.track_id)==before


def test_v4_retry_preserves_ids_and_does_not_adopt_old_tracks(tmp_path):
    repo,track=v3_database(tmp_path)
    assert callable(getattr(repo,'list_managed_bindings',None)), 'Missing authoritative binding reader'
    repo.initialize(); before=repo.get_track(track.track_id)
    for _ in range(3):
        repo.initialize()
        assert repo.get_track(track.track_id)==before and repo.list_managed_bindings()==()
    backups=list((tmp_path/'migration-backups').glob('pre-v4-*.sqlite3'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==3
        assert conn.execute('SELECT title FROM tracks').fetchone()[0]=='Manual'


def test_failed_v4_migration_retains_usable_v3_database(tmp_path,monkeypatch):
    repo,track=v3_database(tmp_path)
    assert hasattr(migrations,'create_managed_schema'), 'Missing atomic adoption schema step'
    original=migrations.create_managed_schema
    def failing(conn):
        original(conn)
        raise RuntimeError('injected adoption schema fault')
    before=repo.get_track(track.track_id)
    monkeypatch.setattr(migrations,'create_managed_schema',failing)
    with pytest.raises(migrations.MigrationError,match='injected adoption schema fault'):
        repo.initialize()
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==3
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='managed_bindings'").fetchall()
    assert repo.get_track(track.track_id)==before


def test_newer_adoption_schema_is_rejected_without_changes(tmp_path):
    repo=LibraryRepository(tmp_path/'library.sqlite3'); repo.initialize()
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('PRAGMA user_version=99')
    before=hashlib.sha256(repo.database_path.read_bytes()).hexdigest()
    with pytest.raises(migrations.MigrationError,match='newer'):
        repo.initialize()
    assert hashlib.sha256(repo.database_path.read_bytes()).hexdigest()==before
