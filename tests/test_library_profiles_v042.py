from pathlib import Path

import pytest

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.storage.library_profiles import LibraryProfile, LibraryRegistry


class Store:
    def __init__(self):
        self.data = {}
    def value(self, key, default=None):
        return self.data.get(key, default)
    def setValue(self, key, value):
        self.data[key] = value


def make_main(tmp_path):
    src = tmp_path / 'main-src'; src.mkdir()
    return AppSettings((src,), LibraryPaths(tmp_path / 'main-library'))


def test_registry_supports_only_main_and_persistent_libraries(tmp_path):
    main = make_main(tmp_path)
    registry = LibraryRegistry.from_store(Store(), main)
    assert not hasattr(registry, 'open_temporary_session')
    with pytest.raises(ValueError):
        LibraryProfile('tmp', 'Tmp', 'temporary', (tmp_path,), tmp_path / 'x')


def test_add_library_can_generate_private_workspace_from_source_folder(tmp_path):
    main = make_main(tmp_path)
    source = tmp_path / 'House 2000'; source.mkdir()
    registry = LibraryRegistry.from_store(Store(), main)
    profile = registry.add_library('House 2000', (source,), profile_id='house')
    assert profile.kind == 'library'
    assert profile.source_dirs == (source.resolve(),)
    assert profile.library_root == (main.library.app_data / 'profiles' / 'house').resolve()


def test_removed_library_does_not_return_after_restart(tmp_path):
    store = Store(); main = make_main(tmp_path)
    source = tmp_path / 'Trance'; source.mkdir()
    registry = LibraryRegistry.from_store(store, main)
    profile = registry.add_library('Trance', (source,), profile_id='trance')
    registry.save(store)
    assert registry.remove_library(profile.profile_id)
    registry.save(store)
    restored = LibraryRegistry.from_store(store, main)
    assert restored.find('trance') is None
