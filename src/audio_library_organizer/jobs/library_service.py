from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from audio_library_organizer.audio.probe import probe_audio
from audio_library_organizer.audio.bpm import estimate_bpm
from audio_library_organizer.audio.fingerprint import fingerprint_audio
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import AppSettings
from audio_library_organizer.duplicates.comparator import sha256_file
from audio_library_organizer.duplicates.grouper import mark_duplicate_statuses
from audio_library_organizer.jobs.scanner import iter_audio_files
from audio_library_organizer.metadata.naming import propose_filename, normalize_title_case
from audio_library_organizer.metadata.filename_hints import parse_filename_hint, parse_filename_bpm
from audio_library_organizer.metadata.tags import read_tags
from audio_library_organizer.metadata.genre import normalize_genre_list
from audio_library_organizer.storage.repository import LibraryRepository


@dataclass(frozen=True, slots=True)
class ScanResult:
    total_seen: int
    scanned: int
    skipped_unchanged: int
    errors: int
    cancelled: bool = False
    source_counts: tuple[tuple[str, int], ...] = ()


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
        scan_roots = tuple(Path(root).expanduser().resolve() for root in (source_dirs or self.settings.source_dirs))
        files = list(iter_audio_files(scan_roots))
        source_count_map = {str(root): 0 for root in scan_roots}
        for path in files:
            resolved = Path(path).resolve()
            for root in scan_roots:
                try:
                    inside = resolved.is_relative_to(root)
                except AttributeError:
                    inside = root == resolved or root in resolved.parents
                if inside:
                    source_count_map[str(root)] += 1
                    break
        scanned = skipped = errors = 0
        was_cancelled = False
        for index, path in enumerate(files, 1):
            if cancelled and cancelled():
                was_cancelled = True
                break
            if progress:
                progress(index, len(files), path.name)
            try:
                stat = path.stat()
                if not self.repository.scan_needed(path, stat.st_size, stat.st_mtime_ns):
                    skipped += 1
                    continue
                tags = read_tags(path)
                info = probe_audio(path)
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
                self.repository.upsert_track(track)
                scanned += 1
                if track_ready:
                    track_ready(index, len(files), track)
            except Exception:
                errors += 1

        # Re-evaluate duplicate relationships only inside sources currently
        # registered for this library (plus explicit roots from this scan).  This
        # keeps stale records from removed/old source folders from influencing a
        # new scan, while still comparing newly added files with the rest of the
        # active library.  Detection never chooses a winner; the user does.
        active_roots: list[Path] = []
        for root in (*self.settings.source_dirs, *scan_roots):
            resolved_root = Path(root).expanduser().resolve()
            if resolved_root not in active_roots:
                active_roots.append(resolved_root)

        def belongs_to_active_source(track: TrackRecord) -> bool:
            try:
                path = Path(track.path).resolve()
                return any(path == root or path.is_relative_to(root) for root in active_roots)
            except (OSError, ValueError):
                return False

        tracks = [
            track for track in self.repository.list_tracks()
            if getattr(track, 'is_available', True) and belongs_to_active_source(track)
        ]
        mark_duplicate_statuses(tracks)
        for track in tracks:
            self.repository.upsert_track(track)
        return ScanResult(len(files), scanned, skipped, errors, was_cancelled, tuple(source_count_map.items()))
