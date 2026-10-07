from pathlib import Path
from dataclasses import asdict
import sqlite3
from uuid import UUID, uuid4

import pytest

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.storage.repository import LibraryRepository


def make_track(path: Path, *, size=100, mtime=10, title='Track') -> TrackRecord:
    return TrackRecord(path=path, size_bytes=size, mtime_ns=mtime, title=title)


def test_repository_persists_and_updates_track(tmp_path: Path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    path = tmp_path / 'a.mp3'
    repo.upsert_track(make_track(path, title='Old'))
    repo.upsert_track(make_track(path, title='New'))
    rows = repo.list_tracks()
    assert len(rows) == 1
    assert rows[0].title == 'New'


def test_scan_needed_uses_size_and_mtime(tmp_path: Path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    path = tmp_path / 'a.mp3'
    assert repo.scan_needed(path, 100, 10) is True
    repo.upsert_track(make_track(path, size=100, mtime=10))
    assert repo.scan_needed(path, 100, 10) is False
    assert repo.scan_needed(path, 101, 10) is True
    assert repo.scan_needed(path, 100, 11) is True

def test_repository_persists_analysis_fields(tmp_path: Path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    track = TrackRecord(path=tmp_path/'x.mp3', bpm=128.0, bpm_raw=64.0, bpm_confidence=0.8, fingerprint='ABC', fingerprint_duration=300)
    repo.upsert_track(track)
    loaded = repo.list_tracks()[0]
    assert loaded.bpm == 128.0
    assert loaded.bpm_raw == 64.0
    assert loaded.bpm_confidence == 0.8
    assert loaded.fingerprint == 'ABC'
    assert loaded.fingerprint_duration == 300


def test_repository_persists_filename_override(tmp_path: Path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    track = TrackRecord(path=tmp_path/'x.mp3', filename_override='Specjalna nazwa')
    repo.upsert_track(track)
    assert repo.list_tracks()[0].filename_override == 'Specjalna nazwa'


def test_repository_persists_field_source_values(tmp_path: Path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    track = TrackRecord(
        path=tmp_path/'source-values.mp3',
        artist='Online Artist',
        field_source_values={
            'artist': {'Tag': 'Local Artist', 'Discogs': 'Online Artist'},
            'bpm': {'Analiza audio': 127.4},
        },
    )
    repo.upsert_track(track)

    loaded = repo.list_tracks()[0]

    assert loaded.field_source_values['artist']['Tag'] == 'Local Artist'
    assert loaded.field_source_values['artist']['Discogs'] == 'Online Artist'
    assert loaded.field_source_values['bpm']['Analiza audio'] == 127.4


def test_repository_tracks_availability_and_can_hide_missing(tmp_path: Path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    existing = tmp_path / 'exists.mp3'; existing.write_bytes(b'x')
    missing = tmp_path / 'missing.mp3'
    repo.upsert_track(TrackRecord(path=existing, title='Existing'))
    repo.upsert_track(TrackRecord(path=missing, title='Missing'))

    result = repo.sync_availability()

    assert result.total == 2
    assert result.available == 1
    assert result.missing == 1
    visible = repo.list_tracks(available_only=True)
    assert [row.title for row in visible] == ['Existing']
    all_rows = {row.title: row for row in repo.list_tracks()}
    assert all_rows['Existing'].is_available is True
    assert all_rows['Missing'].is_available is False


def test_library_paths_expose_persistent_database_and_custom_folders(tmp_path: Path):
    from audio_library_organizer.domain.settings import LibraryPaths

    library = LibraryPaths(tmp_path / 'ALO')
    assert library.database == library.root / '.alo' / 'library.sqlite3'
    assert library.custom_folders == library.root / 'MOJE_FOLDERY_MP3'
    library.ensure_created()
    assert library.database.parent.is_dir()
    assert library.custom_folders.is_dir()


def test_repository_can_purge_missing_records(tmp_path):
    db = tmp_path / 'lib.sqlite3'
    repo = LibraryRepository(db); repo.initialize()
    present_path = tmp_path / 'present.mp3'; present_path.write_bytes(b'x')
    missing_path = tmp_path / 'missing.mp3'
    present = TrackRecord(path=present_path, size_bytes=1, mtime_ns=1, is_available=True)
    missing = TrackRecord(path=missing_path, size_bytes=1, mtime_ns=1, is_available=False)
    repo.upsert_track(present); repo.upsert_track(missing)
    assert repo.purge_missing() == 1
    assert [t.path for t in repo.list_tracks()] == [present_path]


def test_uuid_survives_locator_change_and_reopen(tmp_path):
    db = tmp_path / 'library.sqlite3'
    repo = LibraryRepository(db)
    repo.initialize()
    track = make_track(tmp_path / 'old.mp3')
    repo.upsert_track(track)
    track_id = repo.list_tracks()[0].track_id
    assert UUID(track_id).version == 4
    assert track.track_id == track_id
    loaded = repo.get_track(track_id)
    loaded.path = tmp_path / 'new.mp3'
    repo.upsert_track(loaded)
    reopened = LibraryRepository(db)
    reopened.initialize()
    assert len(reopened.list_tracks()) == 1
    assert reopened.get_track(track_id).path == tmp_path / 'new.mp3'
    assert reopened.get_track(str(uuid4())) is None
    assert reopened.scan_needed(tmp_path / 'new.mp3', 100, 10) is False
    assert reopened.scan_needed(tmp_path / 'old.mp3', 100, 10) is True


def test_legacy_writer_reuses_existing_id_at_same_locator(tmp_path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    first = make_track(tmp_path / 'a.mp3', title='old')
    repo.upsert_track(first)
    second = make_track(first.path, title='manual edit')
    repo.upsert_track(second)
    assert second.track_id == first.track_id
    assert len(repo.list_tracks()) == 1
    assert repo.get_track(first.track_id).title == 'manual edit'


def test_explicit_id_cannot_overwrite_another_record_locator(tmp_path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    first = make_track(tmp_path / 'a.mp3', title='A')
    second = make_track(tmp_path / 'b.mp3', title='B')
    repo.upsert_track(first)
    repo.upsert_track(second)
    second.path = first.path
    second.title = 'must not be saved'
    with pytest.raises(sqlite3.IntegrityError):
        repo.upsert_track(second)
    assert [(t.path.name, t.title) for t in repo.list_tracks()] == [('a.mp3', 'A'), ('b.mp3', 'B')]
    assert repo.get_track(first.track_id).title == 'A'
    assert repo.get_track(second.track_id).title == 'B'


def test_all_model_fields_roundtrip_including_manual_json_and_empty_cover_choice(tmp_path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    track = TrackRecord(
        path=tmp_path / 'Ręczny.mp3', size_bytes=2**40, mtime_ns=2**55,
        duration_seconds=301.125, bitrate_kbps=320, sample_rate_hz=48000,
        channels=2, codec='MP3', artist='Źródło', title='Ręczny tytuł', album='Album',
        year='2008', genre='House / Disco', bpm=128.0, bpm_raw=64.0,
        bpm_confidence=0.75, fingerprint='FP', fingerprint_duration=301,
        comment='Moje uwagi', has_cover=True, sha256='a'*64, status='review',
        confidence=0.8, proposed_filename='Proposed', filename_override='Override',
        original_tags={'artist': ['Original'], 'nested': {'x': [None, 1, 'ą']}},
        discogs_release_id='1234', discogs_url='https://discogs.com/release/1234',
        musicbrainz_recording_id='recording-id', musicbrainz_release_id='release-id',
        cover_art_url='https://example.org/cover.jpg', manual_cover_path='manual/cover.png',
        cover_choice='', match_reasons=['Exact artist'], locked_fields={'title', 'album'},
        pre_online_metadata={'title': 'Before'}, field_sources={'title': 'RĘCZNIE'},
        field_source_values={'title': {'Tag': 'Original', 'RĘCZNIE': 'Ręczny tytuł'}},
        audio_recognition={'candidate': {'id': 'mb', 'score': 0.98}, 'selected': True},
        is_available=False,
    )
    repo.upsert_track(track)
    assert asdict(repo.list_tracks()[0]) == asdict(track)


@pytest.mark.parametrize('operation', ['upsert', 'sync', 'purge'])
def test_repository_writes_reject_schema_upgraded_after_initialize(tmp_path, operation):
    db = tmp_path / 'library.sqlite3'
    repo = LibraryRepository(db)
    repo.initialize()
    repo.upsert_track(make_track(tmp_path / 'missing.mp3'))
    with sqlite3.connect(db) as conn:
        conn.execute('PRAGMA user_version=99')
    original = db.read_bytes()
    with pytest.raises(Exception, match='(?i)(newer|unsupported|version)'):
        if operation == 'upsert':
            repo.upsert_track(make_track(tmp_path / 'new.mp3'))
        elif operation == 'sync':
            repo.sync_availability(purge_missing=True)
        else:
            repo.purge_missing()
    assert db.read_bytes() == original


def test_invalid_new_id_cannot_be_persisted(tmp_path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    track = make_track(tmp_path / 'a.mp3')
    track.track_id = 'broken'
    with pytest.raises(ValueError):
        repo.upsert_track(track)
    assert repo.list_tracks() == []


@pytest.mark.parametrize('purge', [False, True])
def test_stale_availability_observation_cannot_modify_or_delete_relocated_record(tmp_path, monkeypatch, purge):
    db = tmp_path / 'library.sqlite3'
    repo = LibraryRepository(db)
    repo.initialize()
    track = TrackRecord(path=tmp_path / 'missing.mp3', title='Manual title',
                        locked_fields={'title'}, field_sources={'title': 'RĘCZNIE'})
    repo.upsert_track(track)
    destination = tmp_path / 'available.mp3'
    destination.write_bytes(b'audio fixture')
    real_list = repo.list_tracks

    def list_then_relocate():
        observed = real_list()
        writer = LibraryRepository(db)
        moved = writer.get_track(track.track_id)
        moved.path = destination
        writer.upsert_track(moved)
        return observed

    monkeypatch.setattr(repo, 'list_tracks', list_then_relocate)
    result = repo.sync_availability(purge_missing=purge)
    current = repo.get_track(track.track_id)
    assert current is not None
    assert current.path == destination
    assert current.is_available is True
    assert current.title == 'Manual title'
    assert current.locked_fields == {'title'}
    assert current.field_sources == {'title': 'RĘCZNIE'}
    assert result.purged == 0
