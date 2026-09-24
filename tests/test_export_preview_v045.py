from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs.exporter import ExportPlan


def _track(path: Path, proposed: str):
    return TrackRecord(path=path, artist='A', title='T', year='2000', genre='House', bpm=128, status='ready', proposed_filename=proposed)


def test_export_preview_reports_name_and_existing_target_conflicts_without_overwrite(tmp_path):
    library = LibraryPaths(tmp_path/'ALO')
    library.ensure_created()
    a = tmp_path/'a.mp3'; b = tmp_path/'b.mp3'; a.write_bytes(b'a'); b.write_bytes(b'b')
    existing = library.ready/'Same.mp3'; existing.write_bytes(b'existing')

    plan = ExportPlan.from_tracks([_track(a, 'Same.mp3'), _track(b, 'Same.mp3')], library)

    assert plan.preview_summary['name_conflicts'] == 1
    assert plan.preview_summary['existing_targets'] == 1
    assert plan.preview_summary['will_overwrite'] == 0
