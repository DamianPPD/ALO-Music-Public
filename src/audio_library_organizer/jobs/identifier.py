from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from copy import deepcopy

from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.duplicates.grouper import mark_duplicate_statuses
from audio_library_organizer.metadata.provenance import snapshot_pre_online
from audio_library_organizer.metadata.online_lock import is_online_locked
from audio_library_organizer.metadata.change_history import metadata_changes, metadata_revision
from audio_library_organizer.jobs.managed_files import track_identity, source_material_revision


@dataclass(frozen=True, slots=True)
class IdentificationRunResult:
    processed: int
    certain: int
    probable: int
    uncertain: int
    errors: int
    cancelled: bool = False
    skipped_locked: int = 0
    skipped_stale: int = 0


class IdentificationJob:
    def __init__(self, repository: LibraryRepository, identifier, progress: Callable[[int,int,str], None] | None = None, tracks=None, *, force: bool = False):
        self.repository = repository
        self.identifier = identifier
        self.progress = progress
        self.tracks = (deepcopy(list(tracks)) if isinstance(repository, LibraryRepository)
                       else list(tracks)) if tracks is not None else None
        self.library_id = repository.library_id if isinstance(repository, LibraryRepository) else ''
        self.force = bool(force)
        self.cancelled: Callable[[], bool] | None = None

    def _save(self, before, after) -> bool:
        if isinstance(self.repository, LibraryRepository):
            if self.cancelled and self.cancelled():
                return False
            try:
                self.repository.save_metadata(before.track_id, metadata_changes(before, after),
                    expected_revision=metadata_revision(before), library_id=self.library_id,
                    expected_source=(str(before.path), before.source_id, before.source_relative_path),
                    expected_material_revision=source_material_revision(before))
                return True
            except ValueError:
                # Concurrent edits/deletion/context changes are stale requests,
                # never provider errors and never a reason to overwrite storage.
                return False
        # Compatibility with in-memory repository adapters; durable libraries
        # always use the field-only conditional writer above.
        self.repository.upsert_track(after)
        return True

    def run(self) -> IdentificationRunResult:
        if self.cancelled and self.cancelled():
            return IdentificationRunResult(0, 0, 0, 0, 0, cancelled=True)
        requested_tracks = self.tracks if self.tracks is not None else self.repository.list_tracks()
        requested_tracks = deepcopy(requested_tracks) if isinstance(self.repository, LibraryRepository) else list(requested_tracks)
        skipped_locked = sum(1 for track in requested_tracks if is_online_locked(track))
        tracks = [track for track in requested_tracks if not is_online_locked(track)]
        active_ids = {track_identity(t, self.library_id) for t in tracks}
        revisions = {}
        skipped_stale = 0
        # Capture a local baseline for every active track before any online data is
        # applied. Even exact duplicates skipped as provider representatives need
        # their own pre-online snapshot for later manual comparison/restoration.
        prepared = []
        for track in tracks:
            before = deepcopy(track)
            snapshot_pre_online(track)
            if self._save(before, track):
                prepared.append(track)
                revisions[track_identity(track, self.library_id)] = metadata_revision(track)
            else:
                skipped_stale += 1
        tracks = prepared
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
            before = deepcopy(track)
            try:
                outcome = self.identifier.identify(track)
                if outcome.candidate is None and not outcome.track.match_reasons:
                    outcome.track.match_reasons = ['Nie znaleziono pewnego dopasowania online']
                processed += 1
                if self._save(before, outcome.track):
                    revisions[track_identity(before, self.library_id)] = metadata_revision(outcome.track)
                    if outcome.decision == 'certain': certain += 1
                    elif outcome.decision == 'probable': probable += 1
                    else: uncertain += 1
                else:
                    skipped_stale += 1
            except Exception as exc:
                detail = str(exc).strip()
                message = 'Błąd rozpoznawania online'
                if detail:
                    message += f' — {detail}'
                else:
                    message += ' — spróbuj ponownie lub sprawdź połączenie/klucze'
                diagnostic = deepcopy(before) if isinstance(self.repository, LibraryRepository) else track
                diagnostic.match_reasons = [message]
                if self._save(before, diagnostic):
                    revisions[track_identity(before, self.library_id)] = metadata_revision(diagnostic)
                processed += 1
                errors += 1

        # Propagate resolved metadata to exact duplicates without altering their
        # technical fields/path. They remain in the duplicate review bucket.
        current_tracks = [t for t in self.repository.list_tracks()
                          if track_identity(t, self.library_id) in active_ids
                          and revisions.get(track_identity(t, self.library_id)) == metadata_revision(t)]
        by_hash = {t.sha256: t for t in current_tracks if t.sha256 and t.status != 'duplicate'}
        for track in [t for t in current_tracks if t.status == 'duplicate']:
            before = deepcopy(track)
            primary = by_hash.get(track.sha256)
            if not primary:
                continue
            protected = set(track.locked_fields) | {name for name, source in track.field_sources.items() if source == 'Ręcznie'}
            for name in ('artist','title','album','year','genre','comment','confidence','discogs_release_id','discogs_url','musicbrainz_recording_id','musicbrainz_release_id','cover_art_url','proposed_filename'):
                if name not in protected:
                    setattr(track, name, deepcopy(getattr(primary, name)))
            for name, source in primary.field_sources.items():
                if name not in protected:
                    track.field_sources[name] = deepcopy(source)
            for name, values in primary.field_source_values.items():
                if name not in protected:
                    track.field_source_values.setdefault(name, {}).update(deepcopy(values))
            track.match_reasons = list(primary.match_reasons)
            if self._save(before, track):
                revisions[track_identity(track, self.library_id)] = metadata_revision(track)

        # Online matching can reveal same-audio copies that have different file
        # hashes/bitrates. Re-evaluate duplicate groups using confirmed
        # MusicBrainz recording IDs plus duration, while still keeping edits
        # with materially different durations separate.
        tracks = [t for t in self.repository.list_tracks()
                  if track_identity(t, self.library_id) in active_ids
                  and revisions.get(track_identity(t, self.library_id)) == metadata_revision(t)]
        before_duplicates = {track_identity(t, self.library_id): deepcopy(t) for t in tracks}
        mark_duplicate_statuses(tracks)
        for track in tracks:
            self._save(before_duplicates[track_identity(track, self.library_id)], track)

        was_cancelled = was_cancelled or bool(self.cancelled and self.cancelled())
        return IdentificationRunResult(processed, certain, probable, uncertain, errors, was_cancelled, skipped_locked, skipped_stale)
