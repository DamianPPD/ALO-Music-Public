from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.duplicates import grouper


def test_potential_duplicate_grouping_avoids_all_pairs_for_unrelated_library(tmp_path, monkeypatch):
    original = grouper.classify_pair
    calls = 0

    def counted(left, right):
        nonlocal calls
        calls += 1
        return original(left, right)

    monkeypatch.setattr(grouper, 'classify_pair', counted)
    tracks = [
        TrackRecord(
            path=tmp_path / f'{index:04d}.mp3',
            artist=f'Artist {index}',
            title=f'Track {index}',
            duration_seconds=180 + (index % 20),
            sha256=f'sha-{index}',
            fingerprint=f'fp-{index}',
            musicbrainz_recording_id=f'mb-{index}',
        )
        for index in range(300)
    ]

    assert grouper.group_potential_duplicates(tracks) == []
    assert calls < 20


def test_potential_duplicate_grouping_still_groups_same_named_tracks(tmp_path):
    first = TrackRecord(
        path=tmp_path / 'a.mp3', artist='Artist', title='Track', duration_seconds=220
    )
    second = TrackRecord(
        path=tmp_path / 'b.mp3', artist='Artist', title='Track', duration_seconds=390
    )

    groups = grouper.group_potential_duplicates([first, second])

    assert len(groups) == 1
    assert {track.filename for track in groups[0]} == {'a.mp3', 'b.mp3'}
