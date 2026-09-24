from pathlib import Path
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.storage.library_profiles import LibraryRegistry, LibraryProfile


class Store:
    def __init__(self): self.data = {}
    def value(self, key, default=None): return self.data.get(key, default)
    def setValue(self, key, value): self.data[key] = value


def make_main(tmp_path):
    src = tmp_path / 'main-src'; src.mkdir()
    return AppSettings((src,), LibraryPaths(tmp_path / 'main-library'))


def test_registry_keeps_main_profile_and_persists_additional_libraries(tmp_path):
    store = Store(); main = make_main(tmp_path)
    registry = LibraryRegistry.from_store(store, main)
    assert registry.active.kind == 'main'
    alt_src = tmp_path / 'alt-src'; alt_src.mkdir()
    alt_root = tmp_path / 'alt-library'
    profile = registry.add_library('House 90s', (alt_src,), alt_root, profile_id='house')
    registry.activate('house')
    registry.save(store)

    restored = LibraryRegistry.from_store(store, main)
    assert restored.active.profile_id == 'house'
    assert restored.active.source_dirs == (alt_src.resolve(),)
    assert restored.active.library_root == alt_root.resolve()


def test_additional_library_is_isolated_and_persisted(tmp_path):
    store = Store(); main = make_main(tmp_path)
    source = tmp_path / 'incoming'; source.mkdir()
    registry = LibraryRegistry.from_store(store, main)
    library = registry.add_library('Folder DJ', (source,), profile_id='dj')
    registry.activate('dj')
    assert library.kind == 'library'
    assert registry.settings_for(library).source_dirs == (source.resolve(),)
    assert registry.settings_for(library).library.root != main.library.root
    registry.save(store)

    restored = LibraryRegistry.from_store(store, main)
    assert restored.active.profile_id == 'dj'
    assert restored.find('dj') is not None


def test_removing_active_additional_library_returns_to_main(tmp_path):
    registry = LibraryRegistry.from_store(Store(), make_main(tmp_path))
    source = tmp_path / 'extra'; source.mkdir()
    registry.add_library('Extra', (source,), profile_id='extra')
    registry.activate('extra')
    assert registry.remove_library('extra')
    assert registry.active.kind == 'main'


def test_main_profile_can_be_refreshed_when_main_sources_change(tmp_path):
    store = Store(); main = make_main(tmp_path)
    registry = LibraryRegistry.from_store(store, main)
    extra = tmp_path / 'extra'; extra.mkdir()
    updated = AppSettings(main.source_dirs + (extra,), main.library)
    registry.update_main_settings(updated)
    registry.activate('main')
    assert extra.resolve() in registry.active.source_dirs
    assert extra.resolve() in registry.settings_for().source_dirs


