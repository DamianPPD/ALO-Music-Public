from pathlib import Path

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
