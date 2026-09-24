from pathlib import Path
import pytest

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths


def test_destination_creation_creates_default_subfolders(tmp_path: Path):
    root = tmp_path / 'Moja biblioteka'
    paths = LibraryPaths(root=root)
    paths.ensure_created()
    assert paths.ready == root / 'GOTOWE'
    assert paths.duplicates == root / 'NIE_WYBRANE'
    assert paths.not_selected == root / 'NIE_WYBRANE'
    assert paths.review == root / 'DO_SPRAWDZENIA'
    assert paths.reports == root / 'raporty'
    for p in (paths.root, paths.ready, paths.duplicates, paths.review, paths.reports):
        assert p.is_dir()


def test_destination_rejects_same_or_nested_in_source(tmp_path: Path):
    source = tmp_path / 'source'
    source.mkdir()
    with pytest.raises(ValueError):
        AppSettings(source_dirs=(source,), library=LibraryPaths(source))
    with pytest.raises(ValueError):
        AppSettings(source_dirs=(source,), library=LibraryPaths(source / 'output'))


def test_multiple_source_directories_are_normalized_and_unique(tmp_path: Path):
    a = tmp_path / 'A'; b = tmp_path / 'B'
    a.mkdir(); b.mkdir()
    settings = AppSettings(source_dirs=(a, a, b), library=LibraryPaths(tmp_path / 'out'))
    assert settings.source_dirs == (a.resolve(), b.resolve())
