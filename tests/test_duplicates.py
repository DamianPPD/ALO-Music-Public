from pathlib import Path

from audio_library_organizer.domain.models import DuplicateKind, TrackRecord
from audio_library_organizer.duplicates.comparator import classify_pair, sha256_file
from audio_library_organizer.duplicates.grouper import group_exact_duplicates


def test_same_file_bytes_are_identical(tmp_path: Path):
    a = tmp_path/'a.mp3'; b = tmp_path/'b.mp3'
    a.write_bytes(b'abc123'); b.write_bytes(b'abc123')
    assert sha256_file(a) == sha256_file(b)
    ta = TrackRecord(path=a, sha256=sha256_file(a), duration_seconds=120)
    tb = TrackRecord(path=b, sha256=sha256_file(b), duration_seconds=120)
    assert classify_pair(ta, tb) == DuplicateKind.IDENTICAL


def test_same_title_with_large_duration_difference_is_not_auto_duplicate(tmp_path: Path):
    a = TrackRecord(path=tmp_path/'a.mp3', artist='X', title='Track (Original Mix)', duration_seconds=222)
    b = TrackRecord(path=tmp_path/'b.mp3', artist='X', title='Track (Original Mix)', duration_seconds=411)
    assert classify_pair(a, b) == DuplicateKind.NONE


def test_close_metadata_without_hash_is_only_similar(tmp_path: Path):
    a = TrackRecord(path=tmp_path/'a.mp3', artist='X', title='Track', duration_seconds=300)
    b = TrackRecord(path=tmp_path/'b.mp3', artist='X', title='Track', duration_seconds=301.2)
    assert classify_pair(a, b) == DuplicateKind.SIMILAR


def test_group_exact_duplicates_groups_by_hash_only(tmp_path: Path):
    tracks = [
        TrackRecord(path=tmp_path/'a.mp3', sha256='x'),
        TrackRecord(path=tmp_path/'b.mp3', sha256='x'),
        TrackRecord(path=tmp_path/'c.mp3', sha256='y'),
        TrackRecord(path=tmp_path/'d.mp3', sha256=None),
    ]
    groups = group_exact_duplicates(tracks)
    assert [[t.filename for t in g] for g in groups] == [['a.mp3','b.mp3']]

def test_same_fingerprint_and_close_duration_is_same_audio(tmp_path: Path):
    a = TrackRecord(path=tmp_path/'a.mp3', fingerprint='FP1', duration_seconds=300.0)
    b = TrackRecord(path=tmp_path/'b.mp3', fingerprint='FP1', duration_seconds=301.5)
    assert classify_pair(a, b) == DuplicateKind.SAME_AUDIO


def test_same_fingerprint_but_big_duration_difference_is_similar_not_duplicate(tmp_path: Path):
    a = TrackRecord(path=tmp_path/'a.mp3', fingerprint='FP1', duration_seconds=220.0)
    b = TrackRecord(path=tmp_path/'b.mp3', fingerprint='FP1', duration_seconds=390.0)
    assert classify_pair(a, b) == DuplicateKind.SIMILAR


def test_group_auto_duplicates_groups_same_audio_fingerprint_but_not_longer_edit(tmp_path: Path):
    from audio_library_organizer.duplicates.grouper import group_auto_duplicates

    tracks = [
        TrackRecord(path=tmp_path/'a.mp3', sha256='sha-a', fingerprint='FP-AUDIO', duration_seconds=300.0, bitrate_kbps=192, codec='mp3'),
        TrackRecord(path=tmp_path/'b.mp3', sha256='sha-b', fingerprint='FP-AUDIO', duration_seconds=301.0, bitrate_kbps=320, codec='mp3'),
        TrackRecord(path=tmp_path/'extended.mp3', sha256='sha-c', fingerprint='FP-AUDIO', duration_seconds=410.0, bitrate_kbps=320, codec='mp3'),
    ]

    groups = group_auto_duplicates(tracks)

    assert len(groups) == 1
    assert {t.filename for t in groups[0]} == {'a.mp3', 'b.mp3'}


def test_automatic_duplicate_detection_never_chooses_a_quality_winner(tmp_path: Path):
    from audio_library_organizer.duplicates.grouper import mark_duplicate_statuses

    low = TrackRecord(path=tmp_path/'low.mp3', fingerprint='FP', duration_seconds=300, bitrate_kbps=192, codec='mp3', artist='X', title='T', year='2000', genre='House', bpm=128, status='ready')
    high = TrackRecord(path=tmp_path/'high.mp3', fingerprint='FP', duration_seconds=300, bitrate_kbps=320, codec='mp3', artist='X', title='T', year='2000', genre='House', bpm=128, status='ready')

    groups = mark_duplicate_statuses([low, high])

    assert len(groups) == 1
    assert low.status == 'duplicate'
    assert high.status == 'duplicate'
    assert 'duplicate_primary' not in low.locked_fields
    assert 'duplicate_primary' not in high.locked_fields


def test_same_musicbrainz_recording_and_close_duration_is_same_audio(tmp_path: Path):
    a = TrackRecord(path=tmp_path/'a.mp3', musicbrainz_recording_id='mb-rec-1', duration_seconds=300.0, bitrate_kbps=192)
    b = TrackRecord(path=tmp_path/'b.mp3', musicbrainz_recording_id='mb-rec-1', duration_seconds=301.0, bitrate_kbps=320)
    assert classify_pair(a, b) == DuplicateKind.SAME_AUDIO


def test_apply_manual_primary_overrides_automatic_quality_choice(tmp_path: Path):
    from audio_library_organizer.duplicates.grouper import apply_manual_primary

    low = TrackRecord(path=tmp_path/'low.mp3', artist='A', title='T', year='2000', genre='House', bpm=128, status='duplicate', bitrate_kbps=192)
    high = TrackRecord(path=tmp_path/'high.mp3', artist='A', title='T', year='2000', genre='House', bpm=128, status='ready', bitrate_kbps=320)

    apply_manual_primary([low, high], low)

    assert low.status == 'ready'
    assert high.status == 'duplicate'


def test_manual_primary_choice_survives_future_duplicate_recalculation(tmp_path: Path):
    from audio_library_organizer.duplicates.grouper import apply_manual_primary, mark_duplicate_statuses

    low = TrackRecord(path=tmp_path/'low.mp3', fingerprint='FP', duration_seconds=300, bitrate_kbps=192, codec='mp3', artist='X', title='T', year='2000', genre='House', bpm=128, status='duplicate')
    high = TrackRecord(path=tmp_path/'high.mp3', fingerprint='FP', duration_seconds=300, bitrate_kbps=320, codec='mp3', artist='X', title='T', year='2000', genre='House', bpm=128, status='ready')

    apply_manual_primary([low, high], low)
    mark_duplicate_statuses([low, high])

    assert low.status == 'ready'
    assert high.status == 'duplicate'
    assert 'duplicate_primary' in low.locked_fields


def test_duplicate_group_edit_applies_metadata_once_and_approves_selected_primary(tmp_path: Path):
    from audio_library_organizer.metadata.manual_edits import apply_duplicate_group_edits

    selected = TrackRecord(path=tmp_path/'selected.mp3', artist='Old', title='Track', status='duplicate')
    other = TrackRecord(path=tmp_path/'other.mp3', artist='Old', title='Track', status='ready')

    apply_duplicate_group_edits(
        [selected, other], selected,
        {'artist': 'Artist', 'title': 'Track (Club Mix)', 'year': '2001', 'genre': 'House', 'bpm': 128.0},
        manual_cover_path='C:/covers/track.jpg', approve=True,
    )

    assert selected.status == 'ready'
    assert other.status == 'duplicate'
    assert 'duplicate_primary' in selected.locked_fields
    assert selected.year == other.year == '2001'
    assert selected.genre == other.genre == 'House'
    assert selected.bpm == other.bpm == 128.0
    assert selected.manual_cover_path == other.manual_cover_path == 'C:/covers/track.jpg'
    assert selected.has_cover is True and other.has_cover is True


def test_library_status_text_marks_primary_chosen_from_duplicates(tmp_path: Path):
    from audio_library_organizer.ui.state import library_status_text

    track = TrackRecord(path=tmp_path/'x.mp3', artist='A', title='T', year='2000', genre='House', bpm=128, status='ready', locked_fields={'duplicate_primary'})
    assert library_status_text(track) == 'GOTOWE'


def test_promoted_duplicate_version_stays_independent_from_existing_primary(tmp_path: Path):
    from audio_library_organizer.metadata.manual_edits import promote_duplicate_as_version
    from audio_library_organizer.duplicates.grouper import mark_duplicate_statuses, group_auto_duplicates

    primary = TrackRecord(
        path=tmp_path/'primary.mp3', fingerprint='FP', duration_seconds=300, bitrate_kbps=320,
        codec='mp3', artist='Artist', title='Track (Original Mix)', year='2000', genre='House', bpm=128, status='ready',
        locked_fields={'duplicate_primary'},
    )
    alternate = TrackRecord(
        path=tmp_path/'alternate.mp3', fingerprint='FP', duration_seconds=301, bitrate_kbps=192,
        codec='mp3', artist='Artist', title='Track (Radio Edit)', year='2000', genre='House', bpm=128, status='duplicate',
    )

    promote_duplicate_as_version(alternate, approve=True)
    mark_duplicate_statuses([primary, alternate])

    assert primary.status == 'ready'
    assert 'duplicate_primary' in primary.locked_fields
    assert alternate.status == 'ready'
    assert 'separate_version' in alternate.locked_fields
    assert group_auto_duplicates([primary, alternate]) == []


def test_duplicate_group_filename_override_applies_only_to_selected_primary(tmp_path: Path):
    from audio_library_organizer.metadata.manual_edits import apply_duplicate_group_edits

    selected = TrackRecord(path=tmp_path/'selected.mp3', artist='Artist', title='Track', status='duplicate')
    other = TrackRecord(path=tmp_path/'other.mp3', artist='Artist', title='Track', status='ready')

    apply_duplicate_group_edits(
        [selected, other], selected,
        {'artist': 'Artist', 'title': 'Track (Club Mix)', 'filename_override': 'Artist - Track (Club Mix) [128bpm]'},
        approve=False,
    )

    assert selected.filename_override == 'Artist - Track (Club Mix) [128bpm]'
    assert 'filename_override' in selected.locked_fields
    assert other.filename_override is None
    assert 'filename_override' not in other.locked_fields


def test_manual_primary_selection_moves_previous_primary_back_to_duplicate(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.duplicates.grouper import apply_manual_primary

    first = TrackRecord(path=tmp_path/'a.mp3', artist='A', title='T', year='2000', genre='House', bpm=128, status='ready')
    second = TrackRecord(path=tmp_path/'b.mp3', artist='A', title='T', year='2000', genre='House', bpm=128, status='duplicate')
    first.locked_fields.add('duplicate_primary')
    apply_manual_primary([first, second], second)
    assert first.status == 'duplicate'
    assert 'duplicate_primary' not in first.locked_fields
    assert second.status == 'ready'
    assert 'duplicate_primary' in second.locked_fields


def test_duration_delta_label_marks_possible_long_or_short_version(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.duplicates.grouper import duration_delta_label

    reference = TrackRecord(path=tmp_path/'a.mp3', duration_seconds=220)
    long = TrackRecord(path=tmp_path/'b.mp3', duration_seconds=381)
    short = TrackRecord(path=tmp_path/'c.mp3', duration_seconds=185)
    assert duration_delta_label(reference, reference) == '0:00'
    assert duration_delta_label(long, reference) == '+2:41'
    assert duration_delta_label(short, reference) == '-0:35'
