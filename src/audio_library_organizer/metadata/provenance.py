from __future__ import annotations

from difflib import SequenceMatcher
import re

from audio_library_organizer.domain.models import TrackRecord

SNAPSHOT_FIELDS = ('artist', 'title', 'album', 'year', 'genre', 'bpm')


def snapshot_pre_online(track: TrackRecord) -> dict[str, object]:
    """Capture local metadata once, immediately before first online recognition."""
    if track.pre_online_metadata:
        return track.pre_online_metadata
    track.pre_online_metadata = {name: getattr(track, name) for name in SNAPSHOT_FIELDS}
    return track.pre_online_metadata


def restore_pre_online(track: TrackRecord) -> None:
    """Restore the compact local baseline captured before online recognition."""
    for name, value in (track.pre_online_metadata or {}).items():
        if name in SNAPSHOT_FIELDS:
            setattr(track, name, value)
    for name in SNAPSHOT_FIELDS:
        if name in track.pre_online_metadata:
            track.locked_fields.add(name)
            track.field_sources[name] = 'Przywrócone'
    track.status = 'review'
    track.locked_fields.discard('__status__')
    marker = 'Przywrócono dane sprzed rozpoznania online — sprawdź i zatwierdź'
    if marker not in track.match_reasons:
        track.match_reasons.append(marker)


def _norm_identity(value: str | None) -> str:
    text = (value or '').casefold()
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'[^\w]+', ' ', text, flags=re.UNICODE)
    return ' '.join(text.split())


def identity_similarity(before: str | None, after: str | None) -> float:
    a, b = _norm_identity(before), _norm_identity(after)
    if not a or not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def suspicious_identity_change(track: TrackRecord, artist: str | None, title: str | None) -> bool:
    baseline = track.pre_online_metadata or {}
    old_artist = baseline.get('artist') or track.artist
    old_title = baseline.get('title') or track.title
    if not old_artist or not old_title or not artist or not title:
        return False
    artist_score = identity_similarity(str(old_artist), artist)
    title_score = identity_similarity(str(old_title), title)
    # Require a strong mismatch in both identity components. This avoids
    # flagging harmless punctuation/version edits while catching a completely
    # different song returned by an online provider.
    return artist_score < 0.45 and title_score < 0.45


def compact_snapshot_text(track: TrackRecord) -> str:
    data = track.pre_online_metadata or {}
    if not data:
        return 'Brak — rozpoznawanie online nie zmieniło jeszcze tego pliku.'
    artist = data.get('artist') or '—'
    title = data.get('title') or '—'
    year = data.get('year') or '—'
    bpm = data.get('bpm')
    bpm_text = '—' if bpm is None else str(int(round(float(bpm))))
    genre = data.get('genre') or '—'
    return f'{artist} • {title} • {year} • {bpm_text} BPM • {genre}'
