from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.identifier import IdentificationJob
from audio_library_organizer.storage.repository import LibraryRepository


class CountingIdentifier:
    def __init__(self):
        self.calls = []

    def identify(self, track):
        self.calls.append(track.filename)
        class Outcome:
            candidate = None
            decision = 'uncertain'
            def __init__(self, current):
                self.track = current
        return Outcome(track)


def test_repository_persists_whole_track_online_lock(tmp_path: Path):
    from audio_library_organizer.metadata.online_lock import set_online_locked, is_online_locked

    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    track = TrackRecord(path=tmp_path / 'manual.mp3', artist='Manual Artist', title='Manual Title')
    set_online_locked(track, True)
    repo.upsert_track(track)

    loaded = repo.list_tracks()[0]
    assert is_online_locked(loaded) is True

    set_online_locked(loaded, False)
    repo.upsert_track(loaded)
    assert is_online_locked(repo.list_tracks()[0]) is False


def test_identification_job_skips_tracks_locked_against_online_recognition(tmp_path: Path):
    from audio_library_organizer.metadata.online_lock import set_online_locked

    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    locked = TrackRecord(path=tmp_path / 'locked.mp3', artist='Manual', title='Keep me', status='ready')
    pending = TrackRecord(path=tmp_path / 'pending.mp3', status='review')
    set_online_locked(locked, True)
    repo.upsert_track(locked)
    repo.upsert_track(pending)

    identifier = CountingIdentifier()
    result = IdentificationJob(repo, identifier, tracks=[locked, pending]).run()

    assert identifier.calls == ['pending.mp3']
    assert result.processed == 1
    assert result.skipped_locked == 1
    preserved = {track.filename: track for track in repo.list_tracks()}['locked.mp3']
    assert preserved.artist == 'Manual'
    assert preserved.title == 'Keep me'


def test_identification_job_with_only_locked_tracks_makes_no_provider_calls(tmp_path: Path):
    from audio_library_organizer.metadata.online_lock import set_online_locked

    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    locked = TrackRecord(path=tmp_path / 'locked.mp3', artist='Manual', title='Keep me')
    set_online_locked(locked, True)
    repo.upsert_track(locked)

    identifier = CountingIdentifier()
    result = IdentificationJob(repo, identifier, tracks=[locked]).run()

    assert identifier.calls == []
    assert result.processed == 0
    assert result.skipped_locked == 1


def test_unlocking_track_allows_online_identification_again(tmp_path: Path):
    from audio_library_organizer.metadata.online_lock import set_online_locked

    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    track = TrackRecord(path=tmp_path / 'track.mp3', artist='Manual', title='Editable')
    set_online_locked(track, True)
    set_online_locked(track, False)
    repo.upsert_track(track)

    identifier = CountingIdentifier()
    result = IdentificationJob(repo, identifier, tracks=[track]).run()

    assert identifier.calls == ['track.mp3']
    assert result.skipped_locked == 0
