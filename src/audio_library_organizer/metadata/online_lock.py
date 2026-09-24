from __future__ import annotations

from audio_library_organizer.domain.models import TrackRecord

ONLINE_LOCK_MARKER = '__online_lock__'


def is_online_locked(track: TrackRecord) -> bool:
    """Return whether online identification must leave this track untouched."""
    return ONLINE_LOCK_MARKER in (track.locked_fields or set())


def set_online_locked(track: TrackRecord, locked: bool) -> None:
    """Enable/disable the whole-track online-identification lock."""
    if locked:
        track.locked_fields.add(ONLINE_LOCK_MARKER)
    else:
        track.locked_fields.discard(ONLINE_LOCK_MARKER)
