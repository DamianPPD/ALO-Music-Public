"""Restart/source contracts on disposable libraries, never user audio folders."""
import json
from pathlib import Path
import sqlite3
from uuid import UUID

import pytest

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.storage.library_profiles import LibraryProfile, LibraryRegistry
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.ui.state import load_app_settings, save_app_settings
from test_library_migration_v0427 import LEGACY_COLUMNS, legacy_database, raw_rows


class Store:
    def __init__(self):
        self.data = {}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value


def repository(tmp_path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    return repo


def frozen_v1_database(path):
    """Build the published UUID layout independently of the v2 migrator."""
    legacy_database(path).close()
    columns = dict(LEGACY_COLUMNS)
    columns['path'] = 'TEXT NOT NULL UNIQUE'
    with sqlite3.connect(path) as conn:
        conn.execute('ALTER TABLE tracks RENAME TO old_tracks')
        conn.execute('CREATE TABLE tracks (track_id TEXT NOT NULL PRIMARY KEY,' +
                     ','.join(f'"{key}" {value}' for key, value in columns.items()) + ')')
        names = ','.join(f'"{key}"' for key in columns)
        rows = conn.execute(f'SELECT {names} FROM old_tracks ORDER BY path').fetchall()
        for i, row in enumerate(rows, 1):
            conn.execute(f'INSERT INTO tracks (track_id,{names}) VALUES (' +
                         ','.join('?' for _ in range(len(columns) + 1)) + ')',
                         (str(UUID(int=i)), *row))
        conn.execute('DROP TABLE old_tracks')
        conn.execute('PRAGMA user_version=1')


def test_empty_sources_reopens_existing_library(tmp_path):
    settings = AppSettings((), LibraryPaths(tmp_path / 'output'))
    repo = LibraryRepository(settings.library.database)
    repo.initialize()
    track = TrackRecord(tmp_path / 'unavailable.mp3', title='Ręczna edycja',
                        locked_fields={'title'}, audio_recognition={'recording': 'saved'})
    repo.upsert_track(track)
    store = Store()
    save_app_settings(store, settings)
    restored = load_app_settings(store)
    assert restored is not None
    assert restored.source_dirs == ()
    registry = LibraryRegistry.from_store(store, restored)
    reopened = LibraryRepository(registry.settings_for().library.database)
    reopened.initialize()
    assert reopened.get_track(track.track_id).title == 'Ręczna edycja'
    assert reopened.get_track(track.track_id).locked_fields == {'title'}
    assert reopened.get_track(track.track_id).audio_recognition == {'recording': 'saved'}
    assert len(reopened.list_tracks()) == 1


def test_existing_library_root_without_sources_key_reopens(tmp_path):
    store = Store()
    store.setValue('library_root', str(tmp_path / 'output'))
    restored = load_app_settings(store)
    assert restored is not None
    assert restored.source_dirs == ()
    assert restored.library.root == (tmp_path / 'output').resolve()


def test_profiles_do_not_share_source_or_managed_owners(tmp_path):
    # library_id is the isolation boundary for future managed owners, not a
    # request to introduce managed binding in this stage.
    source = tmp_path / 'shared-source'
    main = AppSettings((source,), LibraryPaths(tmp_path / 'main'))
    registry = LibraryRegistry(main)
    registry.add_library('Second', (source,), tmp_path / 'second', profile_id='second')
    repos = [LibraryRepository(registry.settings_for(registry.find(pid)).library.database)
             for pid in ('main', 'second')]
    assert hasattr(repos[0], 'library_id'), 'Missing durable library identity'
    assert repos[0].library_id != repos[1].library_id
    sources = [repo.list_sources()[0] for repo in repos]
    assert sources[0].source_id != sources[1].source_id
    for repo, registered in zip(repos, sources):
        assert registered.library_id == repo.library_id
        track = TrackRecord(source / 'song.mp3', title='Independent')
        repo.upsert_track(track)
        assert repo.get_track(track.track_id).source_id == registered.source_id
    assert repos[0].list_tracks()[0].track_id != repos[1].list_tracks()[0].track_id
    assert repos[0].get_track(repos[1].list_tracks()[0].track_id) is None


def test_source_ids_survive_profile_restart(tmp_path):
    store = Store()
    source = tmp_path / 'music'
    main = AppSettings((), LibraryPaths(tmp_path / 'main'))
    registry = LibraryRegistry(main)
    profile = registry.add_library('Dance', (source,), tmp_path / 'dance', profile_id='dance')
    registry.activate('dance')
    repo = LibraryRepository(registry.settings_for(profile).library.database)
    assert hasattr(repo, 'list_sources'), 'Missing durable source registry'
    first = repo.list_sources()[0]
    track = TrackRecord(source / 'album' / 'song.mp3', title='Manual')
    repo.upsert_track(track)
    registry.save(store)
    restored = LibraryRegistry.from_store(store, main)
    assert restored.active.profile_id == 'dance'
    again = LibraryRepository(restored.settings_for().library.database)
    assert again.library_id == repo.library_id
    assert again.list_sources()[0].source_id == first.source_id
    assert again.get_track(track.track_id).source_id == first.source_id
    assert again.get_track(track.track_id).source_relative_path == 'album/song.mp3'
    assert len(again.list_tracks()) == 1


def test_reregister_source_does_not_duplicate_id_or_tracks(tmp_path):
    repo = repository(tmp_path)
    assert hasattr(repo, 'register_source'), 'Missing source registration'
    source = repo.register_source(tmp_path / 'music')
    track = TrackRecord(tmp_path / 'music' / 'song.mp3')
    repo.upsert_track(track)
    for _ in range(3):
        reopened = LibraryRepository(repo.database_path)
        reopened.initialize()
        assert reopened.register_source(tmp_path / 'music' / '.').source_id == source.source_id
        assert reopened.get_track(track.track_id).source_id == source.source_id
        assert len(reopened.list_tracks()) == len(reopened.list_sources()) == 1


@pytest.mark.parametrize('reverse', [False, True])
def test_overlapping_sources_choose_deepest_root_independent_of_order(tmp_path, reverse):
    repo = repository(tmp_path)
    assert hasattr(repo, 'register_source'), 'Missing source registration'
    parent, child = tmp_path / 'music', tmp_path / 'music' / 'Dance'
    track = TrackRecord(child / 'album' / 'song.mp3')
    repo.upsert_track(track)
    roots = [parent, child]
    if reverse:
        roots.reverse()
    registered = {root: repo.register_source(root) for root in roots}
    saved = repo.get_track(track.track_id)
    assert saved.source_id == registered[child].source_id
    assert saved.source_relative_path == 'album/song.mp3'
    assert saved.track_id == track.track_id
    outside = TrackRecord(tmp_path / 'music-other' / 'song.mp3')
    repo.upsert_track(outside)
    assert repo.get_track(outside.track_id).source_id is None


def test_windows_root_aliases_and_volume_boundaries(tmp_path):
    repo = repository(tmp_path)
    assert hasattr(repo, 'register_source'), 'Missing Windows source identity'
    source = repo.register_source(r'G:\Muzyka\Dance')
    assert repo.register_source('g:/muzyka/dance/').source_id == source.source_id
    other = repo.register_source(r'H:\Muzyka\Dance')
    assert other.source_id != source.source_id
    for locator, wanted_id, relative in [
        (r'g:\MUZYKA\Dance\Album\song.mp3', source.source_id, 'Album/song.mp3'),
        ('H:/Muzyka/Dance/song.mp3', other.source_id, 'song.mp3'),
        (r'G:\Muzyka\Dance2\song.mp3', None, None),
    ]:
        track = TrackRecord(Path(locator))
        repo.upsert_track(track)
        saved = repo.get_track(track.track_id)
        assert (saved.source_id, saved.source_relative_path) == (wanted_id, relative)
    alias = TrackRecord(Path('G:/muzyka/dance/album/SONG.mp3'))
    existing = next(t for t in repo.list_tracks() if t.source_relative_path == 'Album/song.mp3')
    repo.upsert_track(alias)
    assert alias.track_id == existing.track_id
    assert len(repo.list_tracks()) == 3


def test_unc_alias_and_symlink_sources_are_not_duplicated(tmp_path):
    repo = repository(tmp_path)
    assert hasattr(repo, 'register_source'), 'Missing source registration'
    unc = repo.register_source(r'\\SERVER\Share\Dance')
    assert repo.register_source('//server/share/dance/').source_id == unc.source_id
    real = tmp_path / 'real'; real.mkdir()
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip('Symlink creation unavailable')
    registered = repo.register_source(real)
    assert repo.register_source(alias).source_id == registered.source_id


def test_ambiguous_source_match_is_not_chosen_randomly(tmp_path):
    repo = repository(tmp_path)
    assert hasattr(repo, 'register_source'), 'Missing source resolver'
    from audio_library_organizer.storage.source_registry import SourceRoot, match_source
    roots = [SourceRoot('a', 'library', '/music', 'posix:/music', True),
             SourceRoot('b', 'library', '/music', 'posix:/music', True)]
    assert match_source('/music/song.mp3', roots) == (None, None)
    assert match_source('/music/song.mp3', list(reversed(roots))) == (None, None)


def test_sqlite_sources_override_stale_qsettings_after_first_import(tmp_path):
    source, stale = tmp_path / 'music', tmp_path / 'stale'
    main = AppSettings((source,), LibraryPaths(tmp_path / 'output'))
    registry = LibraryRegistry(main)
    store = Store()
    save_app_settings(store, main)
    registry.save(store)
    store.setValue('sources', json.dumps([str(stale)]))
    restored = load_app_settings(store)
    assert restored.source_dirs == (source.resolve(),)
    again = LibraryRegistry.from_store(store, AppSettings((stale,), main.library))
    assert again.find('main').source_dirs == (source.resolve(),)


@pytest.mark.parametrize('cached', ['broken json', 'null', '["{root}"]'])
def test_invalid_presentation_cache_does_not_force_import_or_override_sqlite(tmp_path, cached):
    source = tmp_path / 'source'
    main = AppSettings((source,), LibraryPaths(tmp_path / 'output'))
    store = Store(); save_app_settings(store, main)
    store.setValue('sources', cached.replace('{root}', str(main.library.root)))
    restored = load_app_settings(store)
    assert restored is not None
    assert restored.source_dirs == (source.resolve(),)


def test_profiles_cannot_claim_same_library_database(tmp_path):
    settings = AppSettings((), LibraryPaths(tmp_path / 'output'))
    registry = LibraryRegistry(settings)
    with pytest.raises(ValueError, match='(?i)library|bibliotek'):
        registry.add_library('Alias', (tmp_path / 'new-source',), settings.library.root)
    assert len(registry.profiles) == 1
    assert LibraryRepository(settings.library.database).list_sources() == []


def test_ambiguous_windows_track_alias_is_rejected_without_new_uuid(tmp_path):
    repo = repository(tmp_path)
    first = TrackRecord(Path(r'G:\Music\song.mp3'), track_id=str(UUID(int=10)))
    second = TrackRecord(Path(r'g:\music\SONG.mp3'), track_id=str(UUID(int=11)))
    repo.upsert_track(first); repo.upsert_track(second)
    unresolved = TrackRecord(Path(r'G:\Music\song.mp3'), title='Must not overwrite')
    with pytest.raises(ValueError, match='(?i)ambiguous'):
        repo.upsert_track(unresolved)
    assert unresolved.track_id is None
    assert len(repo.list_tracks()) == 2
    assert repo.get_track(first.track_id).title is None


def test_switching_main_root_uses_destination_source_registry(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    first = AppSettings((tmp_path / 'old-source',), LibraryPaths(tmp_path / 'first'))
    destination = AppSettings((tmp_path / 'destination-source',), LibraryPaths(tmp_path / 'destination'))
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat)
    destination_repo = LibraryRepository(destination.library.database)
    destination_repo.initialize(); destination_repo.replace_sources(destination.source_dirs)
    original_id = destination_repo.list_sources()[0].source_id
    app = QApplication.instance() or QApplication([])
    # Only the interactive directory picker and confirmation are replaced.
    from unittest.mock import patch
    with patch.object(main_window, 'DashboardPage', DashboardPage), \
         patch.object(QFileDialog, 'getExistingDirectory', return_value=str(destination.library.root)), \
         patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
        window = main_window.MainWindow(first, store)
        try:
            window._change_main_library_location()
            assert window.app_settings.source_dirs == destination.source_dirs
            assert window.main_settings.source_dirs == destination.source_dirs
            assert load_app_settings(store).source_dirs == destination.source_dirs
            assert destination_repo.list_sources()[0].source_id == original_id
            assert destination_repo.list_sources(active_only=True)[0].root_path == str(destination.source_dirs[0])
        finally:
            window.close()


def test_posix_case_sensitive_roots_do_not_merge(tmp_path):
    import os
    if os.name == 'nt':
        pytest.skip('POSIX case-sensitive path contract')
    repo = repository(tmp_path)
    upper = repo.register_source(tmp_path / 'Music')
    lower = repo.register_source(tmp_path / 'music')
    assert upper.source_id != lower.source_id
    for directory, owner in [('Music', upper), ('music', lower)]:
        track = TrackRecord(tmp_path / directory / 'song.mp3')
        repo.upsert_track(track)
        assert repo.get_track(track.track_id).source_id == owner.source_id


def test_clearing_scan_roots_retains_source_ids_tracks_and_metadata(tmp_path):
    source = tmp_path / 'music'
    main = AppSettings((source,), LibraryPaths(tmp_path / 'output'))
    registry = LibraryRegistry(main)
    repo = LibraryRepository(main.library.database)
    assert hasattr(repo, 'list_sources'), 'Missing durable source registry'
    original = repo.list_sources()[0]
    track = TrackRecord(source / 'missing.mp3', title='Manual', locked_fields={'title'})
    repo.upsert_track(track)
    registry.clear_source_dirs('main')
    store = Store(); registry.save(store)
    restored = LibraryRegistry.from_store(store, main)
    assert restored.settings_for().source_dirs == ()
    assert repo.list_sources(active_only=True) == []
    assert repo.list_sources()[0].source_id == original.source_id
    assert repo.get_track(track.track_id).source_id == original.source_id
    assert repo.get_track(track.track_id).title == 'Manual'
    assert registry.add_source_dir('main', source).source_dirs == (source.resolve(),)
    assert repo.list_sources()[0].source_id == original.source_id


def test_schema_v1_migration_preserves_every_value_uuid_and_backup(tmp_path):
    db = tmp_path / 'library.sqlite3'
    frozen_v1_database(db)
    before = raw_rows(db)
    repo = LibraryRepository(db); repo.initialize()
    assert raw_rows(db, before[0].keys()) == before
    assert len({r['track_id'] for r in raw_rows(db)}) == 3
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    backups = list((tmp_path / 'migration-backups').glob('*.sqlite3'))
    assert len(backups) == 1
    assert raw_rows(backups[0]) == before
    first = repo.library_id
    for _ in range(2):
        repo.initialize()
        assert repo.library_id == first
        assert raw_rows(db, before[0].keys()) == before
    assert len(list((tmp_path / 'migration-backups').glob('*.sqlite3'))) == 1


def test_failed_v2_migration_rolls_back_all_ddl_and_can_retry(tmp_path, monkeypatch):
    from audio_library_organizer.storage import repository as module
    db = tmp_path / 'library.sqlite3'; frozen_v1_database(db)
    before = raw_rows(db)
    with sqlite3.connect(db) as conn:
        schema = conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
    real_connect = module.connect
    def denied(path):
        conn = real_connect(path)
        conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY
                            if action == sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK)
        return conn
    monkeypatch.setattr(module, 'connect', denied)
    with pytest.raises(Exception, match='(?i)migrat'):
        LibraryRepository(db).initialize()
    assert raw_rows(db) == before
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 1
        assert conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall() == schema
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    backup = next((tmp_path / 'migration-backups').glob('*.sqlite3'))
    assert raw_rows(backup) == before
    monkeypatch.setattr(module, 'connect', real_connect)
    LibraryRepository(db).initialize()
    assert raw_rows(db, before[0].keys()) == before


def test_failed_source_save_does_not_leave_partial_registry_or_bindings(tmp_path):
    repo = repository(tmp_path)
    assert hasattr(repo, 'replace_sources'), 'Missing atomic source save'
    track = TrackRecord(tmp_path / 'one' / 'song.mp3', title='Unchanged')
    repo.upsert_track(track)
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute("CREATE TRIGGER fail_second BEFORE INSERT ON sources "
                     "WHEN NEW.root_path LIKE '%two' BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError, match='injected'):
        repo.replace_sources((tmp_path / 'one', tmp_path / 'two'))
    assert repo.list_sources() == []
    assert repo.get_track(track.track_id).source_id is None
    assert repo.get_track(track.track_id).title == 'Unchanged'
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_failed_profile_source_save_does_not_change_memory_or_qsettings(tmp_path):
    source = tmp_path / 'music'
    settings = AppSettings((source,), LibraryPaths(tmp_path / 'output'))
    registry = LibraryRegistry(settings)
    store = Store(); registry.save(store)
    before = dict(store.data)
    db = settings.library.database
    assert db.is_file(), 'Profile source registry was not saved'
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='sources'").fetchone()[0] == 1
        conn.execute("CREATE TRIGGER fail_source BEFORE INSERT ON sources BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError, match='injected'):
        registry.add_source_dir('main', tmp_path / 'new')
    assert registry.active.source_dirs == (source.resolve(),)
    assert store.data == before


def test_save_settings_commits_database_before_presentation(tmp_path):
    settings = AppSettings((tmp_path / 'source',), LibraryPaths(tmp_path / 'output'))
    class ObservingStore(Store):
        def setValue(self, key, value):
            if key == 'sources':
                assert settings.library.database.is_file(), 'Presentation written before DB'
                with sqlite3.connect(settings.library.database) as conn:
                    assert conn.execute('SELECT count(*) FROM sources WHERE active=1').fetchone()[0] == 1
            super().setValue(key, value)
    save_app_settings(ObservingStore(), settings)


def test_failed_settings_write_leaves_presentation_unchanged(tmp_path):
    store = Store()
    settings = AppSettings((), LibraryPaths(tmp_path / 'output'))
    save_app_settings(store, settings)
    before = dict(store.data)
    assert settings.library.database.is_file(), 'Settings source registry was not saved'
    with sqlite3.connect(settings.library.database) as conn:
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='sources'").fetchone()[0] == 1
        conn.execute("CREATE TRIGGER fail_source BEFORE INSERT ON sources BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError, match='injected'):
        save_app_settings(store, AppSettings((tmp_path / 'new',), settings.library))
    assert store.data == before


def test_startup_without_active_source_does_not_scan_or_purge(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    from audio_library_organizer.jobs.library_service import LibraryService
    settings = AppSettings((), LibraryPaths(tmp_path / 'output'))
    repo = LibraryRepository(settings.library.database); repo.initialize()
    track = TrackRecord(tmp_path / 'unavailable.mp3', title='Keep me')
    repo.upsert_track(track)
    def forbidden_scan(*args, **kwargs):
        pytest.fail('Startup must not scan')
    monkeypatch.setattr(LibraryService, 'scan', forbidden_scan)
    original_sync = LibraryRepository.sync_availability
    def checked_sync(self, *, purge_missing=False):
        assert purge_missing is False, 'Startup must not purge'
        return original_sync(self, purge_missing=purge_missing)
    monkeypatch.setattr(LibraryRepository, 'sync_availability', checked_sync)
    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    app = QApplication.instance() or QApplication([])
    window = main_window.MainWindow(settings, QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    try:
        app.processEvents()
        assert window.repository.get_track(track.track_id).title == 'Keep me'
        assert len(window.repository.list_tracks()) == 1
        assert window.app_settings.source_dirs == ()
    finally:
        window.close()


@pytest.mark.parametrize('operation', ['add', 'load', 'change_main'])
@pytest.mark.parametrize('alias_kind', ['directory', 'hardlink'])
def test_database_alias_profiles_rejected_before_any_write(tmp_path, operation, alias_kind):
    main = AppSettings((tmp_path / 'music',), LibraryPaths(tmp_path / 'main'))
    registry = LibraryRegistry(main)
    alias = tmp_path / 'alias'; alias.mkdir()
    if alias_kind == 'directory':
        (alias / '.alo').symlink_to(main.library.app_data, target_is_directory=True)
    else:
        import os
        (alias / '.alo').mkdir()
        os.link(main.library.database, LibraryPaths(alias).database)
    before = main.library.database.read_bytes()
    with pytest.raises(ValueError, match='(?i)already|registered'):
        if operation == 'add':
            registry.add_library('Alias', (tmp_path / 'new-source',), alias)
        elif operation == 'load':
            LibraryRegistry(main, [LibraryProfile('alias', 'Alias', 'library', (), alias)])
        else:
            second = registry.add_library('Second', (), tmp_path / 'second', profile_id='second')
            second_alias = tmp_path / 'second-alias'; second_alias.mkdir()
            (second_alias / '.alo').symlink_to(second.library_root / '.alo', target_is_directory=True)
            registry.update_main_settings(AppSettings((), LibraryPaths(second_alias)))
    assert registry.main_settings == main
    assert main.library.database.read_bytes() == before


@pytest.mark.parametrize('damage', ['blocked_root', 'missing', 'corrupt', 'newer_schema'])
def test_unavailable_inactive_profile_does_not_block_main_or_replace_database(tmp_path, damage):
    main = AppSettings((), LibraryPaths(tmp_path / 'main'))
    registry = LibraryRegistry(main)
    profile = registry.add_library('Second', (tmp_path / 'music',), tmp_path / 'second', profile_id='second')
    repo = LibraryRepository(LibraryPaths(profile.library_root).database)
    identity = repo.library_id
    store = Store(); registry.save(store)
    if damage in ('blocked_root', 'missing'):
        profile.library_root.rename(tmp_path / 'saved-second')
        if damage == 'blocked_root':
            profile.library_root.write_bytes(b'blocked')
    elif damage == 'corrupt':
        repo.database_path.write_bytes(b'corrupt')
    else:
        with sqlite3.connect(repo.database_path) as conn:
            conn.execute('PRAGMA user_version=999')
    restored = LibraryRegistry.from_store(store, main)
    assert restored.active.profile_id == 'main'
    assert restored.find('second') is not None
    restored.save(store)
    with pytest.raises(Exception):
        restored.activate('second')
    assert restored.active.profile_id == 'main'
    assert json.loads(store.data['libraries/profiles'])[0]['profile_id'] == 'second'
    if damage in ('blocked_root', 'missing'):
        assert not repo.database_path.exists()
        if damage == 'blocked_root':
            profile.library_root.unlink()
        (tmp_path / 'saved-second').rename(profile.library_root)
        restored.activate('second')
        assert restored.active.library_id == identity


@pytest.mark.parametrize('bad_cache', [12, 'wrong', {'wrong': 'value'}, [None]])
def test_invalid_profile_source_cache_cannot_discard_sqlite_library(tmp_path, bad_cache):
    main = AppSettings((), LibraryPaths(tmp_path / 'main'))
    registry = LibraryRegistry(main)
    first = registry.add_library('First', (tmp_path / 'music',), tmp_path / 'first', profile_id='first')
    registry.add_library('Second', (), tmp_path / 'second', profile_id='second')
    registry.activate('first')
    repo = LibraryRepository(LibraryPaths(first.library_root).database)
    source_id = repo.list_sources()[0].source_id
    store = Store(); registry.save(store)
    data = json.loads(store.data['libraries/profiles']); data[0]['source_dirs'] = bad_cache
    store.data['libraries/profiles'] = json.dumps(data)
    restored = LibraryRegistry.from_store(store, main)
    assert {p.profile_id for p in restored.profiles} == {'main', 'first', 'second'}
    assert restored.active.profile_id == 'first'
    assert restored.active.source_dirs == (tmp_path / 'music',)
    assert repo.list_sources()[0].source_id == source_id


def test_windows_locator_lookup_work_is_bounded_by_matches(tmp_path, monkeypatch):
    from audio_library_organizer.storage import repository as module
    repo = repository(tmp_path)
    for i in range(500):
        repo.upsert_track(TrackRecord(Path(f'G:/Music/song-{i}.mp3'), size_bytes=12, mtime_ns=34))
    steps = []
    real_connect = module.connect
    def measured_connect(path):
        conn = real_connect(path)
        conn.set_progress_handler(lambda: steps.append(1) and 0, 100)
        return conn
    monkeypatch.setattr(module, 'connect', measured_connect)
    assert not repo.scan_needed(Path('g:/MUSIC/SONG-499.mp3'), 12, 34)
    assert len(steps) < 50, 'Locator lookup must not read all 500 track payloads'


def test_migrated_windows_locator_alias_reuses_existing_track_id(tmp_path):
    db = tmp_path / 'library.sqlite3'; frozen_v1_database(db)
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE tracks SET path=? WHERE track_id=?', (r'G:\Music\song.mp3', str(UUID(int=1))))
    before = raw_rows(db)
    repo = LibraryRepository(db); repo.initialize()
    alias = TrackRecord(Path('g:/music/SONG.mp3'))
    repo.upsert_track(alias)
    assert alias.track_id == str(UUID(int=1))
    assert len(repo.list_tracks()) == len(before)


@pytest.mark.parametrize('action', ['change_main_alias', 'activate_unavailable'])
def test_profile_ui_failure_preserves_active_database_and_settings(tmp_path, monkeypatch, action):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    app = QApplication.instance() or QApplication([])
    settings = AppSettings((), LibraryPaths(tmp_path / 'main'))
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat)
    window = main_window.MainWindow(settings, store)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[2]))
    try:
        second = window.library_registry.add_library('Second', (), tmp_path / 'second', profile_id='second')
        window.library_registry.save(store)
        previous_repository = window.repository
        previous_store = {k: store.value(k) for k in store.allKeys()}
        second_db = LibraryPaths(second.library_root).database
        if action == 'change_main_alias':
            before = second_db.read_bytes()
            alias = tmp_path / 'alias'; alias.mkdir()
            (alias / '.alo').symlink_to(second.library_root / '.alo', target_is_directory=True)
            monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(alias))
            monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
            window._change_main_library_location()
            assert second_db.read_bytes() == before
            assert not (alias / 'GOTOWE').exists()
        else:
            second.library_root.rename(tmp_path / 'saved-second')
            window._activate_library_profile('second')
            assert not second_db.exists()
        assert warnings
        assert window.library_registry.active.profile_id == 'main'
        assert window.repository is previous_repository
        assert window.main_settings == settings
        assert {k: store.value(k) for k in store.allKeys()} == previous_store
    finally:
        window.close()


@pytest.mark.parametrize('recovery', ['reload', 'activate'])
def test_legacy_v1_sources_survive_unavailable_profile_saves(tmp_path, recovery):
    main = AppSettings((), LibraryPaths(tmp_path / 'main'))
    root = tmp_path / 'legacy'
    db = LibraryPaths(root).database
    db.parent.mkdir(parents=True)
    frozen_v1_database(db)
    source = tmp_path / 'legacy-music'
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE tracks SET path=? WHERE track_id=?',
                     (str(source / 'song.mp3'), str(UUID(int=1))))
    before = raw_rows(db)
    store = Store()
    store.data['libraries/profiles'] = json.dumps([dict(
        profile_id='legacy', name='Legacy', kind='library', library_root=str(root),
        source_dirs=[str(source)])])
    root.rename(tmp_path / 'hidden')
    for _ in range(2):
        unavailable = LibraryRegistry.from_store(store, main)
        assert unavailable.find('legacy').source_dirs == ()
        unavailable.save(store)
        assert json.loads(store.data['libraries/profiles'])[0]['source_dirs'] == [str(source)]
        assert not db.exists()
    (tmp_path / 'hidden').rename(root)
    if recovery == 'reload':
        restored = LibraryRegistry.from_store(store, main)
    else:
        unavailable.activate('legacy')
        restored = unavailable
    repo = LibraryRepository(db)
    first = repo.list_sources()[0]
    assert restored.find('legacy').source_dirs == (source,)
    assert repo.sources_initialized
    assert repo.get_track(str(UUID(int=1))).source_id == first.source_id
    assert raw_rows(db, columns=['track_id', *LEGACY_COLUMNS]) == before
    for _ in range(2):
        restored.save(store)
        restored = LibraryRegistry.from_store(store, main)
        assert repo.list_sources() == [first]
        assert raw_rows(db, columns=['track_id', *LEGACY_COLUMNS]) == before


@pytest.mark.parametrize('damage', ['symlink_loop', 'unknown_user'])
@pytest.mark.parametrize('initialized', [True, False])
def test_unresolvable_optional_cache_does_not_block_or_bootstrap(tmp_path, damage, initialized):
    main = AppSettings((), LibraryPaths(tmp_path / 'main'))
    registry = LibraryRegistry(main)
    root = tmp_path / 'first'
    source = tmp_path / 'music'
    if initialized:
        profile = registry.add_library('First', (source,), root, profile_id='first')
        repo = LibraryRepository(LibraryPaths(root).database)
        original = repo.list_sources()
        library_id = repo.library_id
    else:
        db = LibraryPaths(root).database
        db.parent.mkdir(parents=True)
        frozen_v1_database(db)
        repo = LibraryRepository(db)
    if damage == 'symlink_loop':
        loop = tmp_path / 'loop'
        loop.symlink_to(loop)
        bad = str(loop)
    else:
        bad = '~alo_test_nonexistent_user_783491/music'
    store = Store()
    store.data['libraries/profiles'] = json.dumps([dict(
        profile_id='first', name='First', kind='library', library_root=str(root),
        source_dirs=[bad])])
    store.data['libraries/active'] = 'first'
    restored = LibraryRegistry.from_store(store, main)
    assert restored.active.profile_id == 'first'
    restored.save(store)
    if initialized:
        assert restored.active.source_dirs == (source,)
        assert repo.list_sources() == original
        assert repo.library_id == library_id
    else:
        assert not repo.sources_initialized
        assert repo.list_sources() == []
        assert json.loads(store.data['libraries/profiles'])[0]['source_dirs'] == [bad]
    again = LibraryRegistry.from_store(store, main)
    assert again.active.library_id == restored.active.library_id
    assert repo.sources_initialized == initialized


def test_pending_invalid_legacy_cache_retries_after_path_repair(tmp_path):
    main = AppSettings((), LibraryPaths(tmp_path / 'main'))
    root = tmp_path / 'legacy'
    db = LibraryPaths(root).database
    db.parent.mkdir(parents=True)
    frozen_v1_database(db)
    source = tmp_path / 'music'; source.mkdir()
    loop = tmp_path / 'loop'; loop.symlink_to(loop)
    store = Store()
    store.data['libraries/profiles'] = json.dumps([dict(
        profile_id='legacy', name='Legacy', kind='library', library_root=str(root),
        source_dirs=[str(source), str(loop)])])
    root.rename(tmp_path / 'hidden')
    unavailable = LibraryRegistry.from_store(store, main)
    unavailable.save(store)
    assert json.loads(store.data['libraries/profiles'])[0]['source_dirs'] == [str(source), str(loop)]
    (tmp_path / 'hidden').rename(root)
    restored = LibraryRegistry.from_store(store, main)
    repo = LibraryRepository(db)
    assert not repo.sources_initialized
    assert repo.list_sources() == []  # No partial seeding from mixed-validity input.
    restored.save(store)
    loop.unlink(); loop.symlink_to(source, target_is_directory=True)
    restored.activate('legacy')
    assert repo.sources_initialized
    roots = repo.list_sources()
    assert len(roots) == 1
    restored.save(store)
    again = LibraryRegistry.from_store(store, main)
    assert again.find('legacy').source_dirs == (source,)
    assert repo.list_sources() == roots


def test_optional_cache_guard_does_not_swallow_essential_root_error(tmp_path):
    main = AppSettings((), LibraryPaths(tmp_path / 'main'))
    loop = tmp_path / 'root-loop'; loop.symlink_to(loop)
    store = Store()
    store.data['libraries/profiles'] = json.dumps([dict(
        profile_id='broken', name='Broken', kind='library', library_root=str(loop),
        source_dirs=['~alo_test_nonexistent_user_783491/music'])])
    with pytest.raises(RuntimeError, match='Symlink loop'):
        LibraryRegistry.from_store(store, main)


def test_essential_root_normalization_error_does_not_silently_delete_profile(tmp_path):
    main = AppSettings((), LibraryPaths(tmp_path / 'main'))
    store = Store()
    payload = json.dumps([dict(profile_id='bad', name='Bad', kind='library',
        library_root=str(tmp_path / 'bad') + '\x00', source_dirs=[])])
    store.data['libraries/profiles'] = payload
    with pytest.raises(RuntimeError, match='root'):
        LibraryRegistry.from_store(store, main)
    assert store.data['libraries/profiles'] == payload
