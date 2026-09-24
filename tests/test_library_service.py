from pathlib import Path
import csv
import wave
import struct

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.jobs.library_service import LibraryService
from audio_library_organizer.jobs.reporting import build_operation_summary, export_csv
from audio_library_organizer.storage.repository import LibraryRepository


def write_wav(path: Path, seconds: float = 0.1):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(struct.pack('<h', 0) * int(8000*seconds))


def test_scan_persists_files_and_marks_exact_duplicate(tmp_path: Path):
    source = tmp_path/'source'; source.mkdir()
    write_wav(source/'a.wav')
    (source/'b.wav').write_bytes((source/'a.wav').read_bytes())
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    service = LibraryService(settings, repo)
    result = service.scan()
    assert result.total_seen == 2
    tracks = repo.list_tracks()
    assert len(tracks) == 2
    # Detection classifies the unresolved group but does not auto-pick a primary.
    assert sum(t.status == 'duplicate' for t in tracks) == 2
    assert sum(t.status == 'review' for t in tracks) == 0
    assert all(t.sha256 for t in tracks)


def test_scan_resume_skips_unchanged_file(tmp_path: Path):
    source = tmp_path/'source'; source.mkdir(); write_wav(source/'a.wav')
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    service = LibraryService(settings, repo)
    first = service.scan(); second = service.scan()
    assert first.scanned == 1
    assert second.scanned == 0
    assert second.skipped_unchanged == 1


def test_summary_and_csv_report(tmp_path: Path):
    source = tmp_path/'source'; source.mkdir(); write_wav(source/'a.wav')
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    service = LibraryService(settings, repo); service.scan()
    tracks = repo.list_tracks()
    summary = build_operation_summary(tracks)
    assert summary['total'] == 1
    assert summary['review'] == 1
    out = export_csv(tracks, tmp_path/'report.csv')
    with out.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]['status'] == 'review'


def test_csv_report_includes_identification_and_duplicate_evidence(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord

    track = TrackRecord(
        path=tmp_path/'x.mp3', status='ready', confidence=0.96,
        discogs_release_id='123', discogs_url='https://www.discogs.com/release/123',
        musicbrainz_recording_id='mb-rec', musicbrainz_release_id='mb-rel',
        match_reasons=['fingerprint', 'czas zgodny'], fingerprint='FP', fingerprint_duration=300,
    )
    out = export_csv([track], tmp_path/'extended.csv')
    with out.open(encoding='utf-8-sig', newline='') as f:
        row = next(csv.DictReader(f))

    assert row['confidence'] == '0.96'
    assert row['discogs_release_id'] == '123'
    assert row['musicbrainz_recording_id'] == 'mb-rec'
    assert 'fingerprint' in row['match_reasons']


def test_scan_uses_filename_as_untrusted_hint_but_keeps_review_status(tmp_path: Path):
    source = tmp_path/'source'; source.mkdir()
    write_wav(source/'Abuna E - Watch Me (Double M & D. Bone Mix) - EKWADOR MANIECZKI.wav')
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()

    LibraryService(settings, repo).scan()
    track = repo.list_tracks()[0]

    assert track.artist == 'Abuna E'
    assert track.title == 'Watch Me (Double M & D. Bone Mix) - Ekwador Manieczki'
    assert track.status == 'review'


def test_scan_can_be_cancelled_between_files(tmp_path: Path):
    source = tmp_path/'source'; source.mkdir()
    for i in range(4):
        write_wav(source/f'{i}.wav')
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    service = LibraryService(settings, repo)
    calls = {'n': 0}

    def cancelled():
        calls['n'] += 1
        return calls['n'] >= 3

    result = service.scan(cancelled=cancelled)
    assert result.cancelled is True
    assert result.scanned < 4


def test_scan_reports_progress_for_each_processed_file(tmp_path: Path):
    source = tmp_path/'source'; source.mkdir()
    for i in range(3):
        write_wav(source/f'{i}.wav')
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    service = LibraryService(settings, repo)
    events = []

    result = service.scan(progress=lambda current, total, name: events.append((current, total, name)))
    assert result.cancelled is False
    assert len(events) == 3
    assert events[-1][0] == 3
    assert events[-1][1] == 3


def test_scan_duplicate_detection_ignores_cached_tracks_outside_active_sources(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    source = tmp_path/'new_source'; source.mkdir()
    write_wav(source/'current.wav')
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    old_path = tmp_path/'old_source'/'old.wav'; old_path.parent.mkdir(); old_path.write_bytes((source/'current.wav').read_bytes())
    old_stat = old_path.stat()
    from audio_library_organizer.duplicates.comparator import sha256_file
    repo.upsert_track(TrackRecord(path=old_path, size_bytes=old_stat.st_size, mtime_ns=old_stat.st_mtime_ns, sha256=sha256_file(old_path), status='review'))

    LibraryService(settings, repo).scan()
    current = next(t for t in repo.list_tracks() if t.path.name == 'current.wav')
    assert current.status != 'duplicate'


def test_scan_notifies_after_each_track_is_saved_for_live_ui(tmp_path: Path):
    source = tmp_path/'source'; source.mkdir()
    for i in range(3):
        write_wav(source/f'{i}.wav')
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()
    service = LibraryService(settings, repo)
    ready_events = []

    service.scan(track_ready=lambda current, total, track: ready_events.append((current, total, track.path.name)))

    assert len(ready_events) == 3
    assert ready_events[0][0] == 1
    assert ready_events[-1][:2] == (3, 3)
    assert len(repo.list_tracks()) == 3


def test_scan_prefers_bpm_from_filename_over_uncertain_local_analysis(monkeypatch, tmp_path: Path):
    from audio_library_organizer.audio.bpm import BPMResult

    source = tmp_path/'source'; source.mkdir()
    write_wav(source/'Artist - Track (Original Mix) [139bpm].wav', seconds=12.0)
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()

    monkeypatch.setattr(
        'audio_library_organizer.jobs.library_service.estimate_bpm',
        lambda _path: BPMResult(raw_bpm=126.1, normalized_bpm=126.1, confidence=0.12),
    )
    monkeypatch.setattr(
        'audio_library_organizer.jobs.library_service.fingerprint_audio',
        lambda _path: (_ for _ in ()).throw(RuntimeError('skip fingerprint in unit test')),
    )

    LibraryService(settings, repo).scan()
    track = repo.list_tracks()[0]

    assert track.bpm == 139.0
    assert track.bpm_raw is None
    assert track.proposed_filename.endswith('[139bpm].wav')


def test_scan_records_local_source_candidates(monkeypatch, tmp_path: Path):
    from audio_library_organizer.metadata.tags import TagInfo
    from audio_library_organizer.audio.probe import AudioInfo
    from audio_library_organizer.audio.bpm import BPMResult

    source = tmp_path/'source'; source.mkdir()
    path = source/'Artist Hint - Title Hint [139bpm].wav'
    write_wav(path, seconds=12.0)
    settings = AppSettings((source,), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(tmp_path/'state.sqlite3'); repo.initialize()

    monkeypatch.setattr(
        'audio_library_organizer.jobs.library_service.read_tags',
        lambda _path: TagInfo(artist='Tag Artist', title='Tag Title', year='2001', genre='House', raw={'artist': ['Tag Artist']}),
    )
    monkeypatch.setattr(
        'audio_library_organizer.jobs.library_service.probe_audio',
        lambda _path: AudioInfo(duration_seconds=12.0, bitrate_kbps=1411, sample_rate_hz=44100, channels=2, codec='WAV'),
    )
    monkeypatch.setattr(
        'audio_library_organizer.jobs.library_service.estimate_bpm',
        lambda _path: BPMResult(raw_bpm=127.4, normalized_bpm=127.4, confidence=0.8),
    )
    monkeypatch.setattr(
        'audio_library_organizer.jobs.library_service.fingerprint_audio',
        lambda _path: (_ for _ in ()).throw(RuntimeError('skip')),
    )

    LibraryService(settings, repo).scan()
    track = repo.list_tracks()[0]

    assert track.field_source_values['artist']['Tag'] == 'Tag Artist'
    assert track.field_source_values['title']['Tag'] == 'Tag Title'
    assert track.field_source_values['year']['Tag'] == '2001'
    assert track.field_source_values['genre']['Tag'] == 'House'
    # The explicit filename BPM wins, so the source candidate mirrors the value actually available from the filename.
    assert track.field_source_values['bpm']['Nazwa pliku'] == 139.0


def test_scan_can_be_limited_to_new_source_dirs(monkeypatch, tmp_path):
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.jobs.library_service import LibraryService

    source_a = tmp_path/'a'; source_b = tmp_path/'b'; source_a.mkdir(); source_b.mkdir()
    picked = source_b/'new.mp3'; picked.write_bytes(b'x')
    settings = AppSettings((source_a,), LibraryPaths(tmp_path/'out'))

    class Repo:
        def scan_needed(self, path, size, mtime): return False
        def list_tracks(self): return []
        def upsert_track(self, track): pass

    seen = {}
    def fake_iter(dirs):
        seen['dirs'] = tuple(dirs)
        return iter([picked])

    monkeypatch.setattr('audio_library_organizer.jobs.library_service.iter_audio_files', fake_iter)
    service = LibraryService(settings, Repo())
    result = service.scan(source_dirs=(source_b,))

    assert seen['dirs'] == (source_b,)
    assert result.total_seen == 1
    assert result.skipped_unchanged == 1


def test_limited_new_file_scan_rechecks_duplicates_against_existing_library(monkeypatch, tmp_path):
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.jobs.library_service import LibraryService
    from audio_library_organizer.domain.models import TrackRecord

    source_a = tmp_path/'a'; source_b = tmp_path/'b'; source_a.mkdir(); source_b.mkdir()
    settings = AppSettings((source_a,), LibraryPaths(tmp_path/'out'))
    existing = TrackRecord(path=source_a/'old.mp3', size_bytes=1, mtime_ns=1, sha256='same')
    new = TrackRecord(path=source_b/'new.mp3', size_bytes=1, mtime_ns=1, sha256='same')

    class Repo:
        def scan_needed(self, path, size, mtime): return False
        def list_tracks(self, **kwargs): return [existing, new]
        def upsert_track(self, track): pass

    monkeypatch.setattr('audio_library_organizer.jobs.library_service.iter_audio_files', lambda dirs: iter(()))
    captured = {}
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.mark_duplicate_statuses', lambda tracks: captured.setdefault('tracks', list(tracks)) or [])
    LibraryService(settings, Repo()).scan(source_dirs=(source_b,))
    assert captured['tracks'] == [existing, new]
