from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.manual_edits import apply_manual_field


def test_apply_manual_field_updates_selected_tracks_and_locks_field(tmp_path: Path):
    tracks = [
        TrackRecord(path=tmp_path / 'a.mp3', genre='House'),
        TrackRecord(path=tmp_path / 'b.mp3', genre='Techno'),
    ]

    apply_manual_field(tracks, 'genre', 'Hard House', lock=True)

    assert [t.genre for t in tracks] == ['Hard House', 'Hard House']
    assert all('genre' in t.locked_fields for t in tracks)


def test_apply_manual_field_rejects_unknown_fields(tmp_path: Path):
    track = TrackRecord(path=tmp_path / 'a.mp3')

    try:
        apply_manual_field([track], 'sha256', 'nope')
    except ValueError as exc:
        assert 'Nie można ręcznie zmieniać pola' in str(exc)
    else:
        raise AssertionError('expected ValueError')


def test_manual_metadata_can_include_discogs_url_and_approve_track(tmp_path: Path):
    from audio_library_organizer.metadata.manual_edits import approve_as_ready

    track = TrackRecord(path=tmp_path / 'a.mp3', artist='A', title='T', bpm=128, status='review')
    apply_manual_field([track], 'year', '2000', lock=True)
    apply_manual_field([track], 'genre', 'House', lock=True)
    apply_manual_field([track], 'discogs_url', 'https://www.discogs.com/release/123', lock=True)
    approve_as_ready(track)

    assert track.year == '2000'
    assert track.genre == 'House'
    assert track.discogs_url.endswith('/123')
    assert track.status == 'ready'
    assert 'year' in track.locked_fields
    assert 'genre' in track.locked_fields
    assert any('ręcznie zatwierdz' in reason.casefold() for reason in track.match_reasons)


def test_promote_duplicate_as_version_marks_only_selected_track(tmp_path: Path):
    from audio_library_organizer.metadata.manual_edits import promote_duplicate_as_version

    selected = TrackRecord(path=tmp_path/'radio.mp3', artist='A', title='T (Radio Edit)', status='duplicate')
    promote_duplicate_as_version(selected, approve=False)

    assert selected.status == 'review'
    assert 'separate_version' in selected.locked_fields
    assert any('osobna wersja' in reason.casefold() for reason in selected.match_reasons)


def test_manual_filename_override_is_lockable_and_rebuilds_proposed_filename(tmp_path: Path):
    track = TrackRecord(path=tmp_path/'x.mp3', artist='A', title='Track', bpm=128)
    apply_manual_field([track], 'filename_override', 'Moja nazwa', lock=True)
    assert track.filename_override == 'Moja nazwa'
    assert track.proposed_filename == 'Moja nazwa.mp3'
    assert 'filename_override' in track.locked_fields


def test_apply_manual_field_can_preserve_selected_source_label(tmp_path: Path):
    track = TrackRecord(path=tmp_path/'a.mp3', artist='Old')
    apply_manual_field([track], 'artist', 'Discogs Artist', lock=True, source='Discogs')

    assert track.artist == 'Discogs Artist'
    assert track.field_sources['artist'] == 'Discogs'
    assert track.field_source_values['artist']['Discogs'] == 'Discogs Artist'


def test_apply_manual_field_records_manual_candidate_by_default(tmp_path: Path):
    track = TrackRecord(path=tmp_path/'a.mp3')
    apply_manual_field([track], 'year', '1999', lock=True)

    assert track.field_sources['year'] == 'Ręcznie'
    assert track.field_source_values['year']['Ręcznie'] == '1999'
