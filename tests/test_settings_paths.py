from audio_library_organizer.domain.settings import AppSettings, LibraryPaths


def test_custom_library_subfolders_cannot_be_sources(tmp_path):
    library = LibraryPaths(tmp_path / 'library')
    source_inside_library = library.custom_folders
    source_inside_library.mkdir(parents=True)
    import pytest
    with pytest.raises(ValueError):
        AppSettings((source_inside_library,), library)
