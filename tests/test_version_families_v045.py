from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.duplicates.families import base_version_title, group_version_families


def _track(tmp_path, name, title, *, artist='ATB', status='ready', duration=300):
    return TrackRecord(path=tmp_path/name, artist=artist, title=title, status=status, duration_seconds=duration)


def test_base_version_title_strips_common_mix_edit_suffixes():
    assert base_version_title('Back To Life (Jam El Mar Extended Mix)') == 'back to life'
    assert base_version_title('Back To Life (Jam El Mar Mix)') == 'back to life'
    assert base_version_title('Track (Radio Edit)') == 'track'
    assert base_version_title('Track (Club Mix)') == 'track'
    assert base_version_title('Track') == 'track'


def test_groups_related_versions_but_not_unrelated_titles(tmp_path):
    tracks = [
        _track(tmp_path, 'a.mp3', '9 PM (Original Mix)', duration=480),
        _track(tmp_path, 'b.mp3', '9 PM (Radio Edit)', duration=230),
        _track(tmp_path, 'c.mp3', '9 PM (Extended Mix)', duration=540),
        _track(tmp_path, 'd.mp3', '9 PM (Club Mix)', duration=510),
        _track(tmp_path, 'e.mp3', 'Ecstasy (Radio Edit)', duration=220),
    ]
    families = group_version_families(tracks)
    assert len(families) == 1
    assert {t.filename for t in families[0]} == {'a.mp3', 'b.mp3', 'c.mp3', 'd.mp3'}


def test_family_grouping_is_informational_and_does_not_change_statuses(tmp_path):
    a = _track(tmp_path, 'a.mp3', 'Track (Original Mix)', status='ready')
    b = _track(tmp_path, 'b.mp3', 'Track (Extended Mix)', status='review')
    before = (a.status, b.status)
    group_version_families([a, b])
    assert (a.status, b.status) == before


def test_fully_resolved_manual_duplicate_group_is_no_longer_pending_comparison(tmp_path):
    from audio_library_organizer.duplicates.grouper import group_potential_duplicates, apply_duplicate_decision
    a = TrackRecord(path=tmp_path/'a.mp3', artist='A', title='Track', duration_seconds=300, status='ready')
    b = TrackRecord(path=tmp_path/'b.mp3', artist='A', title='Track', duration_seconds=301, status='review')
    apply_duplicate_decision(a, 'keep')
    apply_duplicate_decision(b, 'not_selected')
    assert group_potential_duplicates([a, b]) == []


def test_named_version_family_with_materially_different_duration_is_not_duplicate_queue(tmp_path):
    from audio_library_organizer.duplicates.grouper import group_potential_duplicates
    radio = TrackRecord(
        path=tmp_path/'radio.mp3', artist='ATB', title='9 PM (Radio Edit)',
        fingerprint='SAME-MATERIAL', duration_seconds=230, status='review',
    )
    extended = TrackRecord(
        path=tmp_path/'extended.mp3', artist='ATB', title='9 PM (Extended Mix)',
        fingerprint='SAME-MATERIAL', duration_seconds=540, status='review',
    )
    assert len(group_version_families([radio, extended])) == 1
    assert group_potential_duplicates([radio, extended]) == []
