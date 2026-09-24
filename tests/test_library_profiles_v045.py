from datetime import datetime, timezone
from pathlib import Path

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.storage.library_profiles import LibraryRegistry


class Store:
    def __init__(self): self.data = {}
    def value(self, key, default=None): return self.data.get(key, default)
    def setValue(self, key, value): self.data[key] = value


def test_additional_library_can_exist_before_any_source_is_added(tmp_path):
    main_src = tmp_path/'main-src'; main_src.mkdir()
    main = AppSettings((main_src,), LibraryPaths(tmp_path/'main-out'))
    output = tmp_path/'House Library'
    registry = LibraryRegistry.from_store(Store(), main)
    profile = registry.add_library('House', (), library_root=output, profile_id='house')
    assert profile.source_dirs == ()
    assert profile.library_root == output.resolve()
    settings = registry.settings_for(profile)
    assert settings.source_dirs == ()
    assert settings.library.root == output.resolve()


def test_scan_history_is_persisted_per_library_and_updates_same_source(tmp_path):
    store = Store()
    main_src = tmp_path/'main-src'; main_src.mkdir()
    main = AppSettings((main_src,), LibraryPaths(tmp_path/'main-out'))
    output = tmp_path/'House Library'
    source = tmp_path/'incoming'; source.mkdir()
    registry = LibraryRegistry.from_store(store, main)
    registry.add_library('House', (), library_root=output, profile_id='house')
    registry.record_scan('house', source, 42, scanned_at=datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc))
    registry.record_scan('house', source, 47, scanned_at=datetime(2026, 9, 13, 3, 0, tzinfo=timezone.utc))
    registry.save(store)

    restored = LibraryRegistry.from_store(store, main)
    history = restored.scan_history('house')
    assert len(history) == 1
    assert history[0].source_dir == source.resolve()
    assert history[0].file_count == 47
    assert history[0].scanned_at.startswith('2026-09-13T03:00:00')


def test_add_source_dir_is_scoped_to_selected_library(tmp_path):
    main_src = tmp_path/'main-src'; main_src.mkdir()
    main = AppSettings((main_src,), LibraryPaths(tmp_path/'main-out'))
    output = tmp_path/'House Library'
    source = tmp_path/'new-source'; source.mkdir()
    registry = LibraryRegistry.from_store(Store(), main)
    registry.add_library('House', (), library_root=output, profile_id='house')
    registry.add_source_dir('house', source)
    assert registry.find('house').source_dirs == (source.resolve(),)
    assert registry.find('main').source_dirs == (main_src.resolve(),)


def test_scan_result_reports_file_count_per_explicit_source(monkeypatch, tmp_path):
    from audio_library_organizer.jobs.library_service import LibraryService

    a = tmp_path/'A'; b = tmp_path/'B'; a.mkdir(); b.mkdir()
    files = [a/'one.mp3', b/'two.mp3', b/'three.mp3']
    for path in files: path.write_bytes(b'x')

    class Repo:
        def scan_needed(self, *_): return False
        def list_tracks(self): return []
        def upsert_track(self, _track): pass

    settings = AppSettings((a, b), LibraryPaths(tmp_path/'out'))
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.iter_audio_files', lambda roots: iter(files))
    result = LibraryService(settings, Repo()).scan(source_dirs=(a, b))
    assert dict(result.source_counts) == {str(a.resolve()): 1, str(b.resolve()): 2}


def test_scan_history_can_be_cleared_for_one_library_only(tmp_path):
    store = Store()
    main_src = tmp_path/'main-src'; main_src.mkdir()
    main = AppSettings((main_src,), LibraryPaths(tmp_path/'main-out'))
    house_out = tmp_path/'house-out'
    a = tmp_path/'a'; b = tmp_path/'b'; a.mkdir(); b.mkdir()
    registry = LibraryRegistry.from_store(store, main)
    registry.add_library('House', (), library_root=house_out, profile_id='house')
    registry.record_scan('main', a, 2)
    registry.record_scan('house', b, 3)

    removed = registry.clear_scan_history('house')

    assert removed == 1
    assert registry.scan_history('house') == ()
    assert len(registry.scan_history('main')) == 1


def test_library_can_be_renamed_without_changing_output_folder(tmp_path):
    main_src = tmp_path/'main-src'; main_src.mkdir()
    main = AppSettings((main_src,), LibraryPaths(tmp_path/'main-out'))
    output = tmp_path/'House Library'
    registry = LibraryRegistry.from_store(Store(), main)
    registry.add_library('House', (), library_root=output, profile_id='house')

    renamed = registry.rename_library('house', 'House Classics')

    assert renamed.name == 'House Classics'
    assert renamed.library_root == output.resolve()


def test_library_sources_can_be_cleared_without_touching_output_folder(tmp_path):
    main_src = tmp_path/'main-src'; main_src.mkdir()
    main = AppSettings((main_src,), LibraryPaths(tmp_path/'main-out'))
    output = tmp_path/'House Library'
    source = tmp_path/'incoming'; source.mkdir()
    registry = LibraryRegistry.from_store(Store(), main)
    registry.add_library('House', (source,), library_root=output, profile_id='house')

    cleared = registry.clear_source_dirs('house')

    assert cleared.source_dirs == ()
    assert cleared.library_root == output.resolve()
