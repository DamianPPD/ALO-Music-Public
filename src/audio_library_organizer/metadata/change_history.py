from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from collections.abc import Iterable
import hashlib
import json

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.managed_files import track_identity


_SNAPSHOT_FIELDS = (
    'artist', 'title', 'album', 'year', 'genre', 'bpm', 'comment', 'discogs_url',
    'manual_cover_path', 'has_cover', 'status', 'proposed_filename', 'filename_override',
    'locked_fields', 'match_reasons', 'field_sources', 'field_source_values', 'audio_recognition', 'cover_choice',
)

# Complete metadata revision/write allowlist. Physical observations, source
# bindings, path, hashes/fingerprint and original_tags are deliberately absent.
METADATA_FIELDS = tuple(dict.fromkeys((*_SNAPSHOT_FIELDS,
    'confidence', 'discogs_release_id', 'musicbrainz_recording_id',
    'musicbrainz_release_id', 'cover_art_url', 'pre_online_metadata')))


def metadata_values(track: TrackRecord) -> dict:
    return {name: deepcopy(getattr(track, name)) for name in METADATA_FIELDS}


def metadata_revision(track: TrackRecord) -> str:
    values = metadata_values(track)
    values['locked_fields'] = sorted(values['locked_fields'])
    # SQLite REAL roundtrips 128 as 128.0; numerically equal metadata must have
    # one token regardless of whether the caller just saved or reloaded it.
    for name in ('bpm', 'confidence'):
        if values[name] is not None:
            values[name] = float(values[name])
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def metadata_changes(before: TrackRecord, after: TrackRecord) -> dict:
    return {name: deepcopy(getattr(after, name)) for name in METADATA_FIELDS
            if getattr(before, name) != getattr(after, name)}


@dataclass(frozen=True, slots=True)
class TrackSnapshot:
    path_key: str
    values: dict[str, object]

    @classmethod
    def capture(cls, track: TrackRecord, library_id: str = '') -> 'TrackSnapshot':
        return cls(
            path_key=track_identity(track, library_id),
            values={name: deepcopy(getattr(track, name)) for name in _SNAPSHOT_FIELDS},
        )

    def restore(self, track: TrackRecord) -> None:
        for name, value in self.values.items():
            setattr(track, name, deepcopy(value))


@dataclass(frozen=True, slots=True)
class ChangeAction:
    description: str
    snapshots: tuple[TrackSnapshot, ...]

    @property
    def path_keys(self) -> set[str]:
        return {snapshot.path_key for snapshot in self.snapshots}


class ChangeHistory:
    """Session-only undo/history for manual user decisions."""

    def __init__(self, *, limit: int = 200, library_id: str = ''):
        self.limit = max(1, int(limit))
        self.library_id = library_id
        self._actions: list[ChangeAction] = []

    def record(self, tracks: Iterable[TrackRecord], description: str) -> ChangeAction | None:
        snapshots: list[TrackSnapshot] = []
        seen: set[str] = set()
        for track in tracks:
            key = track_identity(track, self.library_id)
            if key in seen:
                continue
            seen.add(key)
            snapshots.append(TrackSnapshot.capture(track, self.library_id))
        if not snapshots:
            return None
        action = ChangeAction(description=description.strip() or 'Zmiana', snapshots=tuple(snapshots))
        self._actions.append(action)
        if len(self._actions) > self.limit:
            del self._actions[:-self.limit]
        return action

    def undo_last(self, tracks: Iterable[TrackRecord], *, library_id: str | None = None) -> ChangeAction | None:
        if library_id is not None and library_id != self.library_id:
            return None
        if not self._actions:
            return None
        action = self._actions.pop()
        by_path = {track_identity(track, self.library_id): track for track in tracks}
        for snapshot in action.snapshots:
            track = by_path.get(snapshot.path_key)
            if track is not None:
                snapshot.restore(track)
        return action

    def history_for(self, track: TrackRecord, *, limit: int = 6) -> list[str]:
        key = track_identity(track, self.library_id)
        result: list[str] = []
        for action in reversed(self._actions):
            if key in action.path_keys:
                result.append(action.description)
                if len(result) >= max(1, limit):
                    break
        return result

    def __len__(self) -> int:
        return len(self._actions)
