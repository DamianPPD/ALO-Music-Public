from __future__ import annotations

import hashlib
from pathlib import Path

from audio_library_organizer.domain.models import DuplicateKind, TrackRecord


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _norm(value: str | None) -> str:
    return ' '.join((value or '').casefold().split())


def classify_pair(a: TrackRecord, b: TrackRecord) -> DuplicateKind:
    if a.sha256 and b.sha256 and a.sha256 == b.sha256:
        return DuplicateKind.IDENTICAL

    if a.duration_seconds and b.duration_seconds:
        delta = abs(a.duration_seconds - b.duration_seconds)
    else:
        delta = None

    if a.fingerprint and b.fingerprint and a.fingerprint == b.fingerprint:
        if delta is None or delta <= max(3.0, min(a.duration_seconds or 0, b.duration_seconds or 0) * 0.015):
            return DuplicateKind.SAME_AUDIO
        # Matching audio material but a materially different duration is kept
        # out of automatic duplicate handling. It may be an edit/extended mix.
        return DuplicateKind.SIMILAR

    if (a.musicbrainz_recording_id and b.musicbrainz_recording_id
            and a.musicbrainz_recording_id == b.musicbrainz_recording_id):
        if delta is not None and delta <= max(3.0, min(a.duration_seconds or 0, b.duration_seconds or 0) * 0.015):
            return DuplicateKind.SAME_AUDIO
        # Even a shared recording ID is not enough for automatic duplicate
        # routing when duration evidence is missing or materially different.
        return DuplicateKind.SIMILAR

    if delta is not None:
        # Large duration differences are a hard guard: same name is not enough.
        if delta > max(8.0, min(a.duration_seconds, b.duration_seconds) * 0.03):
            return DuplicateKind.NONE

    same_artist = bool(a.artist and b.artist and _norm(a.artist) == _norm(b.artist))
    same_title = bool(a.title and b.title and _norm(a.title) == _norm(b.title))
    if same_artist and same_title and (delta is None or delta <= 3.0):
        return DuplicateKind.SIMILAR
    return DuplicateKind.NONE
