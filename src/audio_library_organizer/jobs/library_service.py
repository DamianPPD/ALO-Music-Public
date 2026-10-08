from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import wave
from pathlib import Path
from collections.abc import Callable

from audio_library_organizer.audio.probe import probe_audio
from audio_library_organizer.audio.bpm import estimate_bpm
from audio_library_organizer.audio.fingerprint import fingerprint_audio
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import AppSettings
from audio_library_organizer.duplicates.comparator import sha256_file
from audio_library_organizer.jobs.scanner import SourceScanOutcome, SourceScanStatus, scan_audio_sources
from audio_library_organizer.metadata.naming import propose_filename, normalize_title_case
from audio_library_organizer.metadata.filename_hints import parse_filename_hint, parse_filename_bpm
from audio_library_organizer.metadata.tags import read_tags
from audio_library_organizer.metadata.genre import normalize_genre_list
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.storage.scan_merge import SCAN_AUDIO_KEY, SCAN_STAT_KEY, stat_observation


def _wav_audio_observation(path: Path) -> dict | None:
    # Hash PCM frames and their format, not tags/container bytes. Only attempted
    # for new/changed WAVs. Other formats and legacy observations remain
    # conservative when their whole-file SHA changes.
    if path.suffix.lower() != '.wav':
        return None
    try:
        with wave.open(str(path), 'rb') as stream:
            digest = hashlib.sha256()
            digest.update(str((stream.getnchannels(), stream.getsampwidth(),
                               stream.getframerate(), stream.getnframes())).encode('ascii'))
            while frames := stream.readframes(65536):
                digest.update(frames)
        return {'kind': 'wav-pcm-sha256', 'digest': digest.hexdigest()}
    except (OSError, EOFError, wave.Error):
        return None


@dataclass(frozen=True, slots=True)
class ScanResult:
    total_seen: int
    scanned: int
    skipped_unchanged: int
    errors: int
    cancelled: bool = False
    source_counts: tuple[tuple[str, int], ...] = ()
    source_outcomes: tuple[SourceScanOutcome, ...] = ()


class LibraryService:
    def __init__(self, settings: AppSettings, repository: LibraryRepository):
        self.settings = settings
        self.repository = repository

    def scan(
        self,
        *,
        source_dirs: tuple[Path, ...] | None = None,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        track_ready: Callable[[int, int, TrackRecord], None] | None = None,
    ) -> ScanResult:
        requested = self.settings.source_dirs if source_dirs is None else source_dirs
        # Normalization failures are optional source errors, not startup failures.
        inventory = scan_audio_sources(requested, cancelled=cancelled)
        files = inventory.files
        outcomes = list(inventory.outcomes)
        file_roots = dict(inventory.file_roots)
        scanned = skipped = 0
        errors = sum(item.status == SourceScanStatus.ERROR for item in outcomes)
        was_cancelled = any(item.status == SourceScanStatus.CANCELLED for item in outcomes)
        excluded_ids = set()

        def mark_roots(path: Path, status: SourceScanStatus, reason: str):
            for index in file_roots.get(path, ()):
                outcome = outcomes[index]
                if outcome.status == SourceScanStatus.SUCCESS:
                    outcomes[index] = replace(outcome, status=status, reason=reason)

        for index, path in enumerate(files, 1):
            if was_cancelled or (cancelled and cancelled()):
                was_cancelled = True
                break
            if progress:
                progress(index, len(files), path.name)
            baseline = None
            try:
                snapshot = self.repository.scan_snapshot(path)
                baseline = snapshot.track
                stat = path.stat()
                same_size_time = baseline is not None and (baseline.size_bytes, baseline.mtime_ns) == (stat.st_size, stat.st_mtime_ns)
                if same_size_time and baseline.original_tags.get(SCAN_STAT_KEY) == stat_observation(stat):
                    skipped += 1
                    continue
                if same_size_time and SCAN_STAT_KEY not in baseline.original_tags:
                    # Legacy rows have no inode/ctime observation. Compare their
                    # saved exact SHA once before seeding a trusted stat/PCM
                    # observation; later unchanged scans need neither hash nor tags.
                    observed = deepcopy(baseline)
                    observed.sha256 = sha256_file(path)
                    observed.original_tags = {SCAN_STAT_KEY: stat_observation(stat)}
                    audio = _wav_audio_observation(path)
                    if audio is not None:
                        observed.original_tags[SCAN_AUDIO_KEY] = audio
                    if cancelled and cancelled():
                        was_cancelled = True
                        break
                    merged = self.repository.merge_scan_track(observed, snapshot, observations_only=True)
                    if merged is None:
                        raise ValueError('Legacy audio differs from its saved exact SHA; work was retained.')
                    skipped += 1
                    continue
                tags = read_tags(path)
                info = probe_audio(path)
                if not any(value is not None and value > 0 for value in (
                        info.duration_seconds, info.bitrate_kbps, info.sample_rate_hz, info.channels)):
                    raise ValueError('No readable audio stream was confirmed by the probe.')
                # Trust explicit BPM metadata first, then an explicit [139bpm]
                # filename hint. Only estimate from audio when neither exists.
                bpm_value = tags.bpm if tags.bpm is not None else parse_filename_bpm(path.stem)
                bpm_raw = None
                bpm_confidence = None
                if bpm_value is None and (info.duration_seconds or 0) >= 10:
                    bpm_result = estimate_bpm(path)
                    bpm_value = bpm_result.normalized_bpm
                    bpm_raw = bpm_result.raw_bpm
                    bpm_confidence = bpm_result.confidence

                fingerprint = None
                fingerprint_duration = None
                if (info.duration_seconds or 0) >= 5:
                    try:
                        fp = fingerprint_audio(path)
                        fingerprint = fp.fingerprint
                        fingerprint_duration = fp.duration_seconds
                    except Exception:
                        pass

                tag_identity = bool(tags.artist and tags.title)
                hint_artist, hint_title = parse_filename_hint(path.stem)
                track = TrackRecord(
                    path=path,
                    size_bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    duration_seconds=info.duration_seconds,
                    bitrate_kbps=info.bitrate_kbps,
                    sample_rate_hz=info.sample_rate_hz,
                    channels=info.channels,
                    codec=info.codec,
                    artist=tags.artist or hint_artist,
                    title=normalize_title_case(tags.title or hint_title),
                    album=tags.album,
                    year=tags.year,
                    genre=normalize_genre_list(tags.genre),
                    bpm=bpm_value,
                    bpm_raw=bpm_raw,
                    bpm_confidence=bpm_confidence,
                    fingerprint=fingerprint,
                    fingerprint_duration=fingerprint_duration,
                    comment=tags.comment,
                    has_cover=tags.has_cover,
                    sha256=sha256_file(path),
                    status='ready' if tag_identity else 'review',
                    original_tags=tags.raw or {},
                    field_sources={
                        'artist': 'Tag' if tags.artist else ('Nazwa pliku' if hint_artist else ''),
                        'title': 'Tag' if tags.title else ('Nazwa pliku' if hint_title else ''),
                        'album': 'Tag' if tags.album else '', 'year': 'Tag' if tags.year else '',
                        'genre': 'Tag' if tags.genre else '',
                        'bpm': 'Tag' if tags.bpm is not None else ('Nazwa pliku' if parse_filename_bpm(path.stem) is not None else 'Analiza audio'),
                    },
                    field_source_values={
                        'artist': ({'Tag': tags.artist} if tags.artist else ({'Nazwa pliku': hint_artist} if hint_artist else {})),
                        'title': ({'Tag': normalize_title_case(tags.title)} if tags.title else ({'Nazwa pliku': normalize_title_case(hint_title)} if hint_title else {})),
                        'album': ({'Tag': tags.album} if tags.album else {}),
                        'year': ({'Tag': tags.year} if tags.year else {}),
                        'genre': ({'Tag': normalize_genre_list(tags.genre)} if tags.genre else {}),
                        'bpm': ({'Tag': tags.bpm} if tags.bpm is not None else ({'Nazwa pliku': parse_filename_bpm(path.stem)} if parse_filename_bpm(path.stem) is not None else ({'Analiza audio': bpm_value} if bpm_value is not None else {}))),
                    },
                )
                track.proposed_filename = propose_filename(track)
                audio_observation = _wav_audio_observation(path)
                if audio_observation is not None:
                    track.original_tags[SCAN_AUDIO_KEY] = audio_observation
                track.original_tags[SCAN_STAT_KEY] = stat_observation(stat)
                after = path.stat()
                if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (
                        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError('File changed while scanner observations were being read.')
                if cancelled and cancelled():
                    was_cancelled = True
                    break
                merged = self.repository.merge_scan_track(track, snapshot)
                if merged is None:
                    raise ValueError('Audio continuity is ambiguous; saved work was retained.')
                scanned += 1
                if track_ready:
                    track_ready(index, len(files), merged)
            except Exception as exc:
                errors += 1
                if baseline is not None:
                    excluded_ids.add(baseline.track_id)
                mark_roots(path, SourceScanStatus.ERROR, str(exc))

        if cancelled and cancelled():
            was_cancelled = True
        if was_cancelled:
            outcomes = [replace(item, status=SourceScanStatus.CANCELLED, reason='Scan cancelled')
                        if item.status == SourceScanStatus.SUCCESS else item for item in outcomes]

        # Classification re-reads current decisions in one write transaction.
        # A no-op scan does not rewrite every record or recalculate statuses.
        if scanned and not was_cancelled:
            active_roots = []
            incomplete_context = any(item.status != SourceScanStatus.SUCCESS for item in outcomes)
            for root in (*self.settings.source_dirs, *requested):
                try:
                    resolved = Path(root).expanduser().resolve()
                    if resolved not in active_roots:
                        active_roots.append(resolved)
                    if not resolved.is_dir():
                        incomplete_context = True
                except (OSError, RuntimeError, ValueError):
                    incomplete_context = True
            self.repository.reconcile_scan_duplicates(active_roots, excluded_ids=excluded_ids,
                                                      incomplete_context=incomplete_context)
        counts = tuple((item.root, item.files) for item in outcomes if item.status == SourceScanStatus.SUCCESS)
        return ScanResult(len(files), scanned, skipped, errors, was_cancelled, counts, tuple(outcomes))
