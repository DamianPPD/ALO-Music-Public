from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class AcoustIDHit:
    recording_id: str
    score: float
    title: str | None = None
    artist: str | None = None


@dataclass(frozen=True, slots=True)
class MusicBrainzRecording:
    recording_id: str
    artist: str | None
    title: str | None
    duration_seconds: float | None
    release_ids: tuple[str, ...] = ()
    release_titles: tuple[str, ...] = ()
    years: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetadataCandidate:
    source: str
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: str | None = None
    genre: str | None = None
    comment: str | None = None
    duration_seconds: float | None = None
    release_id: str | None = None
    source_url: str | None = None
    musicbrainz_release_id: str | None = None
    cover_art_url: str | None = None
    score: float = 0.0
    reasons: tuple[str, ...] = ()

    def with_score(self, score: float, reasons: tuple[str, ...]) -> 'MetadataCandidate':
        return replace(self, score=score, reasons=reasons)
