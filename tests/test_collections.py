from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths


def test_collection_plan_uses_custom_folder_and_only_available_tracks(tmp_path: Path):
    from audio_library_organizer.jobs.collections import build_collection_plan

    library = LibraryPaths(tmp_path / 'ALO')
    (tmp_path/'a.mp3').write_bytes(b'audio')
    a = TrackRecord(path=tmp_path/'a.mp3', proposed_filename='Artist - A.mp3', is_available=True)
    b = TrackRecord(path=tmp_path/'b.mp3', proposed_filename='Artist - B.mp3', is_available=False)

    plan = build_collection_plan(library, 'Trance Vocal', [a, b])

    assert len(plan.items) == 1
    assert plan.items[0].destination_dir == library.custom_folders / 'Trance Vocal'
    assert plan.items[0].filename == 'Artist - A.mp3'


def test_list_collections_reports_file_count_and_size(tmp_path: Path):
    from audio_library_organizer.jobs.collections import list_collections

    library = LibraryPaths(tmp_path / 'ALO'); library.ensure_created()
    folder = library.custom_folders / 'Disco 90'; folder.mkdir()
    (folder/'a.mp3').write_bytes(b'abc')
    (folder/'b.flac').write_bytes(b'12345')

    rows = list_collections(library)

    assert len(rows) == 1
    assert rows[0].name == 'Disco 90'
    assert rows[0].file_count == 2
    assert rows[0].size_bytes == 8
