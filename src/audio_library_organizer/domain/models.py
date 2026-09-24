from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class DuplicateKind(StrEnum):
    NONE = 'none'
    IDENTICAL = 'identical'
    SAME_AUDIO = 'same_audio'
    SIMILAR = 'similar'


@dataclass(slots=True)
class TrackRecord:
    path: Path
    size_bytes: int = 0
    mtime_ns: int = 0
    duration_seconds: float | None = None
    bitrate_kbps: int | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    codec: str | None = None
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: str | None = None
    genre: str | None = None
    bpm: float | None = None
    bpm_raw: float | None = None
    bpm_confidence: float | None = None
    fingerprint: str | None = None
    fingerprint_duration: int | None = None
    comment: str | None = None
    has_cover: bool = False
    sha256: str | None = None
    status: str = 'new'
    confidence: float | None = None
    proposed_filename: str | None = None
    filename_override: str | None = None
    original_tags: dict[str, Any] = field(default_factory=dict)
    discogs_release_id: str | None = None
    discogs_url: str | None = None
    musicbrainz_recording_id: str | None = None
    musicbrainz_release_id: str | None = None
    cover_art_url: str | None = None
    manual_cover_path: str | None = None
    cover_choice: str = 'auto'
    match_reasons: list[str] = field(default_factory=list)
    locked_fields: set[str] = field(default_factory=set)
    pre_online_metadata: dict[str, Any] = field(default_factory=dict)
    field_sources: dict[str, str] = field(default_factory=dict)
    field_source_values: dict[str, dict[str, Any]] = field(default_factory=dict)
    is_available: bool = True

    @property
    def filename(self) -> str:
        return self.path.name
