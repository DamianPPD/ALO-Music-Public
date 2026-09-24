from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.candidates import MetadataCandidate
from audio_library_organizer.matching.resolver import IdentificationOutcome, apply_candidate
from audio_library_organizer.jobs.identifier import IdentificationJob
from audio_library_organizer.storage.repository import LibraryRepository


class FakeIdentifier:
    def identify(self, track):
        c = MetadataCandidate(source='discogs', artist='Abuna E', title='Watch Me (Double M & D. Bone Mix)', album='Abuna E – Watch Me', year='2000', genre='Hard House', release_id='123', source_url='https://www.discogs.com/release/123', score=0.96, reasons=('dokładny tytuł/wersja','długość zgodna'))
        apply_candidate(track, c, source_recording_id='mb123')
        return IdentificationOutcome(track, c, 'certain')


def test_identification_job_updates_repository(tmp_path: Path):
    repo = LibraryRepository(tmp_path/'db.sqlite3'); repo.initialize()
    repo.upsert_track(TrackRecord(path=tmp_path/'34.mp3', status='review', bpm=142))
    result = IdentificationJob(repo, FakeIdentifier()).run()
    assert result.processed == 1
    assert result.certain == 1
    loaded = repo.list_tracks()[0]
    assert loaded.artist == 'Abuna E'
    assert loaded.status == 'ready'
    assert loaded.discogs_release_id == '123'
    assert loaded.proposed_filename == 'Abuna E - Watch Me (Double M & D. Bone Mix) (2000) [142bpm].mp3'


def test_identification_job_rechecks_same_recording_duplicates_after_online_match(tmp_path: Path):
    repo = LibraryRepository(tmp_path/'db.sqlite3'); repo.initialize()
    repo.upsert_track(TrackRecord(path=tmp_path/'low.mp3', status='review', duration_seconds=300.0, bitrate_kbps=192, bpm=128, sha256='sha-low'))
    repo.upsert_track(TrackRecord(path=tmp_path/'high.mp3', status='review', duration_seconds=301.0, bitrate_kbps=320, bpm=128, sha256='sha-high'))

    IdentificationJob(repo, FakeIdentifier()).run()
    loaded = {t.filename: t for t in repo.list_tracks()}

    # ALO detects the group but deliberately does not choose the higher-bitrate
    # file for the user. Both remain unresolved DUPLIKAT candidates.
    assert loaded['high.mp3'].status == 'duplicate'
    assert loaded['low.mp3'].status == 'duplicate'
    assert loaded['high.mp3'].musicbrainz_recording_id == loaded['low.mp3'].musicbrainz_recording_id == 'mb123'


def test_identifier_marks_no_match_with_explanation(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.matching.resolver import IdentificationOutcome
    from audio_library_organizer.storage.repository import LibraryRepository
    from audio_library_organizer.jobs.identifier import IdentificationJob

    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    track = TrackRecord(path=tmp_path/'mystery.mp3', size_bytes=1, mtime_ns=1, status='review')
    repo.upsert_track(track)

    class NoMatchIdentifier:
        def identify(self, current):
            return IdentificationOutcome(current, None, 'uncertain')

    IdentificationJob(repo, NoMatchIdentifier()).run()
    stored = repo.list_tracks()[0]
    assert stored.match_reasons == ['Nie znaleziono pewnego dopasowania online']


def test_identifier_can_process_only_selected_active_tracks(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.matching.resolver import IdentificationOutcome
    from audio_library_organizer.storage.repository import LibraryRepository
    from audio_library_organizer.jobs.identifier import IdentificationJob

    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    a = TrackRecord(path=tmp_path/'a.mp3', size_bytes=1, mtime_ns=1, status='review')
    b = TrackRecord(path=tmp_path/'b.mp3', size_bytes=1, mtime_ns=1, status='review')
    repo.upsert_track(a); repo.upsert_track(b)
    seen = []

    class Identifier:
        def identify(self, current):
            seen.append(current.filename)
            return IdentificationOutcome(current, None, 'uncertain')

    IdentificationJob(repo, Identifier(), tracks=[a]).run()
    assert seen == ['a.mp3']


def test_identifier_marks_provider_error_with_explanation(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.storage.repository import LibraryRepository
    from audio_library_organizer.jobs.identifier import IdentificationJob

    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    track = TrackRecord(path=tmp_path/'error.mp3', size_bytes=1, mtime_ns=1, status='review')
    repo.upsert_track(track)

    class BrokenIdentifier:
        def identify(self, current):
            raise RuntimeError('network down')

    result = IdentificationJob(repo, BrokenIdentifier()).run()
    stored = repo.list_tracks()[0]
    assert result.errors == 1
    assert stored.match_reasons == ['Błąd rozpoznawania online — network down']


def test_pre_online_snapshot_is_captured_for_every_track_even_when_exact_duplicate_is_skipped(tmp_path: Path):
    repo = LibraryRepository(tmp_path/'db.sqlite3'); repo.initialize()
    first = TrackRecord(path=tmp_path/'a.mp3', artist='Old A', title='OLD TITLE A', year='1999', genre='House', bpm=128, status='review', sha256='same')
    second = TrackRecord(path=tmp_path/'b.mp3', artist='Old B', title='OLD TITLE B', year='2001', genre='Trance', bpm=130, status='duplicate', sha256='same')
    repo.upsert_track(first); repo.upsert_track(second)

    IdentificationJob(repo, FakeIdentifier()).run()
    loaded = {t.filename: t for t in repo.list_tracks()}

    assert loaded['a.mp3'].pre_online_metadata['artist'] == 'Old A'
    assert loaded['b.mp3'].pre_online_metadata['artist'] == 'Old B'
    assert loaded['b.mp3'].pre_online_metadata['title'] == 'OLD TITLE B'


def test_identification_job_can_cancel_after_current_track(tmp_path):
    from audio_library_organizer.jobs.identifier import IdentificationJob
    from audio_library_organizer.domain.models import TrackRecord

    tracks = [TrackRecord(path=tmp_path/f'{i}.mp3', sha256=str(i)) for i in range(3)]

    class Repo:
        def __init__(self): self.rows = tracks
        def upsert_track(self, track): pass
        def list_tracks(self): return list(self.rows)

    calls = []
    class Identifier:
        def identify(self, track):
            calls.append(track.filename)
            class Outcome:
                candidate = None
                decision = 'uncertain'
                def __init__(self, t): self.track = t
            return Outcome(track)

    job = IdentificationJob(Repo(), Identifier(), tracks=tracks)
    job.cancelled = lambda: len(calls) >= 1
    result = job.run()

    assert calls == ['0.mp3']
    assert result.cancelled is True
    assert result.processed == 1


def test_resume_skips_tracks_already_checked_online(tmp_path):
    repo = LibraryRepository(tmp_path/'db.sqlite3'); repo.initialize()
    done = TrackRecord(path=tmp_path/'done.mp3', size_bytes=1, mtime_ns=1, musicbrainz_recording_id='mb1', confidence=.7)
    pending = TrackRecord(path=tmp_path/'pending.mp3', size_bytes=1, mtime_ns=1)
    repo.upsert_track(done); repo.upsert_track(pending)
    calls=[]
    class Identifier:
        def identify(self, track):
            calls.append(track.path.name)
            class O:
                candidate = None; decision = 'uncertain'
                def __init__(self, t): self.track=t
            return O(track)
    result = IdentificationJob(repo, Identifier(), tracks=[done,pending]).run()
    assert calls == ['pending.mp3']
    assert result.processed == 1


def test_force_identification_rechecks_one_track_even_if_it_was_checked_before(tmp_path):
    repo = LibraryRepository(tmp_path/'db.sqlite3'); repo.initialize()
    done = TrackRecord(
        path=tmp_path/'done.mp3', size_bytes=1, mtime_ns=1,
        musicbrainz_recording_id='old-mb', confidence=.7, status='review',
    )
    repo.upsert_track(done)
    calls = []

    class Identifier:
        def identify(self, track):
            calls.append(track.path.name)
            return IdentificationOutcome(track, None, 'uncertain')

    result = IdentificationJob(repo, Identifier(), tracks=[done], force=True).run()
    assert calls == ['done.mp3']
    assert result.processed == 1
