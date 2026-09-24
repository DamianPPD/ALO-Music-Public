from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.duplicates.grouper import mark_duplicate_statuses
from audio_library_organizer.metadata.provenance import snapshot_pre_online
from audio_library_organizer.metadata.online_lock import is_online_locked


@dataclass(frozen=True, slots=True)
class IdentificationRunResult:
    processed: int
    certain: int
    probable: int
    uncertain: int
    errors: int
    cancelled: bool = False
    skipped_locked: int = 0


class IdentificationJob:
    def __init__(self, repository: LibraryRepository, identifier, progress: Callable[[int,int,str], None] | None = None, tracks=None, *, force: bool = False):
        self.repository = repository
        self.identifier = identifier
        self.progress = progress
        self.tracks = list(tracks) if tracks is not None else None
        self.force = bool(force)
        self.cancelled: Callable[[], bool] | None = None

    def run(self) -> IdentificationRunResult:
        requested_tracks = list(self.tracks) if self.tracks is not None else self.repository.list_tracks()
        skipped_locked = sum(1 for track in requested_tracks if is_online_locked(track))
        tracks = [track for track in requested_tracks if not is_online_locked(track)]
        active_paths = {str(t.path.resolve()) for t in tracks}
        # Capture a local baseline for every active track before any online data is
        # applied. Even exact duplicates skipped as provider representatives need
        # their own pre-online snapshot for later manual comparison/restoration.
        for track in tracks:
            snapshot_pre_online(track)
            self.repository.upsert_track(track)
        # Process one representative per exact hash. Exact byte duplicates do not
        # need repeated provider requests; metadata can be propagated afterward.
        representatives = []
        seen_hashes: set[str] = set()
        for track in tracks:
            if track.status == 'duplicate' and track.sha256 in seen_hashes:
                continue
            if track.sha256:
                seen_hashes.add(track.sha256)
            already_checked = bool(track.discogs_release_id or track.musicbrainz_recording_id or track.musicbrainz_release_id)
            no_match_recorded = any('Nie znaleziono pewnego dopasowania online' in str(reason) for reason in (track.match_reasons or []))
            if not self.force and (already_checked or no_match_recorded):
                continue
            representatives.append(track)

        certain = probable = uncertain = errors = processed = 0
        was_cancelled = False
        for i, track in enumerate(representatives, 1):
            if self.cancelled and self.cancelled():
                was_cancelled = True
                break
            if self.progress:
                self.progress(i, len(representatives), track.filename)
            try:
                outcome = self.identifier.identify(track)
                if outcome.candidate is None and not outcome.track.match_reasons:
                    outcome.track.match_reasons = ['Nie znaleziono pewnego dopasowania online']
                self.repository.upsert_track(outcome.track)
                processed += 1
                if outcome.decision == 'certain': certain += 1
                elif outcome.decision == 'probable': probable += 1
                else: uncertain += 1
            except Exception as exc:
                detail = str(exc).strip()
                message = 'Błąd rozpoznawania online'
                if detail:
                    message += f' — {detail}'
                else:
                    message += ' — spróbuj ponownie lub sprawdź połączenie/klucze'
                track.match_reasons = [message]
                self.repository.upsert_track(track)
                processed += 1
                errors += 1

        # Propagate resolved metadata to exact duplicates without altering their
        # technical fields/path. They remain in the duplicate review bucket.
        current_tracks = [t for t in self.repository.list_tracks() if str(t.path.resolve()) in active_paths]
        by_hash = {t.sha256: t for t in current_tracks if t.sha256 and t.status != 'duplicate'}
        for track in [t for t in current_tracks if t.status == 'duplicate']:
            primary = by_hash.get(track.sha256)
            if not primary:
                continue
            for name in ('artist','title','album','year','genre','comment','confidence','discogs_release_id','discogs_url','musicbrainz_recording_id','musicbrainz_release_id','cover_art_url','proposed_filename','field_sources','field_source_values'):
                setattr(track, name, getattr(primary, name))
            track.match_reasons = list(primary.match_reasons)
            self.repository.upsert_track(track)

        # Online matching can reveal same-audio copies that have different file
        # hashes/bitrates. Re-evaluate duplicate groups using confirmed
        # MusicBrainz recording IDs plus duration, while still keeping edits
        # with materially different durations separate.
        tracks = [t for t in self.repository.list_tracks() if str(t.path.resolve()) in active_paths]
        mark_duplicate_statuses(tracks)
        for track in tracks:
            self.repository.upsert_track(track)

        return IdentificationRunResult(processed, certain, probable, uncertain, errors, was_cancelled, skipped_locked)
