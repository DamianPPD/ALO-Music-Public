from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from collections.abc import Iterable

from audio_library_organizer.domain.models import TrackRecord


_SNAPSHOT_FIELDS = (
    'artist', 'title', 'album', 'year', 'genre', 'bpm', 'comment', 'discogs_url',
    'manual_cover_path', 'has_cover', 'status', 'proposed_filename', 'filename_override',
    'locked_fields', 'match_reasons', 'field_sources', 'field_source_values', 'cover_choice',
)


def _path_key(path: Path) -> str:
    return str(Path(path).resolve()).casefold()


@dataclass(frozen=True, slots=True)
class TrackSnapshot:
    path_key: str
    values: dict[str, object]

    @classmethod
    def capture(cls, track: TrackRecord) -> 'TrackSnapshot':
        return cls(
            path_key=_path_key(track.path),
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

    def __init__(self, *, limit: int = 200):
        self.limit = max(1, int(limit))
        self._actions: list[ChangeAction] = []

    def record(self, tracks: Iterable[TrackRecord], description: str) -> ChangeAction | None:
        snapshots: list[TrackSnapshot] = []
        seen: set[str] = set()
        for track in tracks:
            key = _path_key(track.path)
            if key in seen:
                continue
            seen.add(key)
            snapshots.append(TrackSnapshot.capture(track))
        if not snapshots:
            return None
        action = ChangeAction(description=description.strip() or 'Zmiana', snapshots=tuple(snapshots))
        self._actions.append(action)
        if len(self._actions) > self.limit:
            del self._actions[:-self.limit]
        return action

    def undo_last(self, tracks: Iterable[TrackRecord]) -> ChangeAction | None:
        if not self._actions:
            return None
        action = self._actions.pop()
        by_path = {_path_key(track.path): track for track in tracks}
        for snapshot in action.snapshots:
            track = by_path.get(snapshot.path_key)
            if track is not None:
                snapshot.restore(track)
        return action

    def history_for(self, track: TrackRecord, *, limit: int = 6) -> list[str]:
        key = _path_key(track.path)
        result: list[str] = []
        for action in reversed(self._actions):
            if key in action.path_keys:
                result.append(action.description)
                if len(result) >= max(1, limit):
                    break
        return result

    def __len__(self) -> int:
        return len(self._actions)
