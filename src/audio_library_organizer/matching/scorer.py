from __future__ import annotations

from difflib import SequenceMatcher
import re

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.candidates import MetadataCandidate


def _norm(value: str | None) -> str:
    return ' '.join((value or '').casefold().replace('–','-').split())


def _norm_artist(value: str | None) -> str:
    text = (value or '').casefold().replace('–', '-').replace('*', ' ')
    text = re.sub(r'\b(?:feat(?:uring)?|ft)\.?\b', '&', text)
    text = re.sub(r'\s+(?:and|x)\s+', ' & ', text)
    text = text.replace('&', ' & ')
    parts = []
    for part in text.split('&'):
        cleaned = re.sub(r'[^\w]+', ' ', part, flags=re.UNICODE)
        cleaned = ' '.join(cleaned.split())
        if cleaned:
            parts.append(cleaned)
    return ' & '.join(parts)


def _ratio(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _artist_ratio(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _norm_artist(a), _norm_artist(b)).ratio()


def score_candidate(track: TrackRecord, candidate: MetadataCandidate) -> MetadataCandidate:
    score = 0.0
    reasons: list[str] = []
    artist_ratio = _artist_ratio(track.artist, candidate.artist)
    title_ratio = _ratio(track.title, candidate.title)
    album_ratio = _ratio(track.album, candidate.album)

    if track.artist and candidate.artist:
        if artist_ratio >= 0.97:
            score += 0.22; reasons.append('wykonawca zgodny')
        elif artist_ratio >= 0.80:
            score += 0.12; reasons.append('wykonawca podobny')
    if track.title and candidate.title:
        if title_ratio >= 0.97:
            score += 0.40; reasons.append('dokładny tytuł/wersja')
        elif title_ratio >= 0.82:
            score += 0.24; reasons.append('tytuł/wersja podobna')
    if track.duration_seconds and candidate.duration_seconds:
        delta = abs(track.duration_seconds - candidate.duration_seconds)
        if delta <= 3.0:
            score += 0.24; reasons.append('długość zgodna')
        elif delta <= 8.0:
            score += 0.12; reasons.append('długość zbliżona')
        elif delta > max(12.0, track.duration_seconds * 0.04):
            score -= 0.20; reasons.append('długość różna')
    if track.album and candidate.album:
        if album_ratio >= 0.90:
            score += 0.12; reasons.append('album zgodny')
        elif album_ratio >= 0.70:
            score += 0.06; reasons.append('album podobny')
    if track.year and candidate.year and str(track.year)[:4] == str(candidate.year)[:4]:
        score += 0.05; reasons.append('rok zgodny')
    # Strong title+artist match can reach a useful confidence even without album/year.
    if artist_ratio >= 0.97 and title_ratio >= 0.97:
        score += 0.05
    return candidate.with_score(max(0.0, min(1.0, score)), tuple(reasons))
