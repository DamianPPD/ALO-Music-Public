from pathlib import Path

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.storage.library_profiles import LibraryRegistry
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.domain.models import TrackRecord


class Store:
    def __init__(self, data=None):
        self.data = dict(data or {})
    def value(self, key, default=None):
        return self.data.get(key, default)
    def setValue(self, key, value):
        self.data[key] = value
    def remove(self, key):
        self.data.pop(key, None)
    def clear(self):
        self.data.clear()


def test_sync_availability_can_purge_missing_records(tmp_path: Path):
    db = tmp_path / 'library.sqlite3'
    repo = LibraryRepository(db); repo.initialize()
    existing = tmp_path / 'keep.mp3'; existing.write_bytes(b'audio')
    missing = tmp_path / 'gone.mp3'; missing.write_bytes(b'audio')
    repo.upsert_track(TrackRecord(path=existing, size_bytes=5, mtime_ns=1, artist='A', title='Keep'))
    repo.upsert_track(TrackRecord(path=missing, size_bytes=5, mtime_ns=1, artist='B', title='Gone'))
    missing.unlink()

    summary = repo.sync_availability(purge_missing=True)

    assert summary.available == 1
    assert summary.missing == 1
    assert summary.purged == 1
    assert [track.path for track in repo.list_tracks()] == [existing.resolve()]


def test_full_reset_clears_alo_state_and_databases_but_keeps_music(tmp_path: Path):
    from audio_library_organizer.jobs.reset import reset_alo_state

    source = tmp_path / 'source'; source.mkdir()
    song = source / 'keep.mp3'; song.write_bytes(b'music')
    main = AppSettings((source,), LibraryPaths(tmp_path / 'main-library'))
    main.library.ensure_created(); main.library.database.write_bytes(b'main-db')

    store = Store({'sources': '["old"]', 'library_root': 'old', 'ui/language': 'en', 'ui/language_selected': True})
    registry = LibraryRegistry(main)
    extra_source = tmp_path / 'extra-source'; extra_source.mkdir()
    extra = registry.add_library('Extra', (extra_source,), profile_id='extra')
    extra_settings = registry.settings_for(extra)
    extra_settings.library.database.write_bytes(b'extra-db')
    registry.save(store)

    result = reset_alo_state(store, main, registry)

    assert result.databases_removed == 2
    assert store.data == {}
    assert not main.library.database.exists()
    assert not extra_settings.library.database.exists()
    assert song.read_bytes() == b'music'
    assert source.exists()


def test_language_selection_marker_is_explicit_and_resettable():
    from audio_library_organizer.domain.preferences import language_selection_done, save_language_selection

    store = Store()
    assert language_selection_done(store) is False
    save_language_selection(store, 'en')
    assert language_selection_done(store) is True
    assert store.data['ui/language'] == 'en'
    assert store.data['ui/language_selected'] is True


def test_reset_one_library_index_removes_only_alo_database_files(tmp_path):
    from audio_library_organizer.jobs.reset import reset_library_index
    root = tmp_path / 'library'
    music = root / 'GOTOWE' / 'song.mp3'
    music.parent.mkdir(parents=True)
    music.write_bytes(b'music')
    db = root / '.alo' / 'library.sqlite3'
    db.parent.mkdir(parents=True)
    db.write_bytes(b'db')
    Path(str(db) + '-wal').write_bytes(b'wal')

    removed = reset_library_index(root)

    assert removed == 1
    assert not db.exists()
    assert not Path(str(db) + '-wal').exists()
    assert music.read_bytes() == b'music'
