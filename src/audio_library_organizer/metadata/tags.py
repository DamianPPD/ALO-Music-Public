from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, ID3NoHeaderError


@dataclass(frozen=True, slots=True)
class TagInfo:
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: str | None = None
    genre: str | None = None
    bpm: float | None = None
    comment: str | None = None
    has_cover: bool = False
    raw: dict[str, Any] | None = None


def _first(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value) -> float | None:
    try:
        return float(_first(value))
    except (TypeError, ValueError):
        return None


def _read_id3(path: Path) -> TagInfo:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        return TagInfo(raw={})

    def text(frame_id: str):
        frame = tags.get(frame_id)
        return _first(getattr(frame, 'text', None)) if frame else None

    comments = tags.getall('COMM')
    comment = _first(comments[0].text) if comments else None
    raw = {key: str(frame) for key, frame in tags.items() if not key.startswith('APIC')}
    return TagInfo(
        artist=text('TPE1'), title=text('TIT2'), album=text('TALB'),
        year=text('TDRC') or text('TYER'), genre=text('TCON'), bpm=_float(text('TBPM')),
        comment=comment, has_cover=bool(tags.getall('APIC')), raw=raw,
    )


def read_tags(path: Path) -> TagInfo:
    path = Path(path)
    if path.suffix.lower() == '.mp3':
        base = _read_id3(path)
        if any((base.artist, base.title, base.album, base.genre, base.bpm, base.comment, base.has_cover)):
            return base
    try:
        audio = MutagenFile(path, easy=True)
        tags = getattr(audio, 'tags', None) or {}
        raw = {str(k): v for k, v in tags.items()}
        artist = _first(tags.get('artist'))
        title = _first(tags.get('title'))
        album = _first(tags.get('album'))
        year = _first(tags.get('date') or tags.get('year'))
        genre = _first(tags.get('genre'))
        bpm = _float(tags.get('bpm'))
        comment = _first(tags.get('comment') or tags.get('description'))
        has_cover = False
        try:
            full = MutagenFile(path, easy=False)
            f_tags = getattr(full, 'tags', None)
            if hasattr(f_tags, 'getall'):
                has_cover = bool(f_tags.getall('APIC'))
            elif hasattr(full, 'pictures'):
                has_cover = bool(full.pictures)
            elif f_tags:
                has_cover = any(str(k).lower().startswith(('covr', 'metadata_block_picture')) for k in f_tags.keys())
        except Exception:
            pass
        return TagInfo(artist, title, album, year, genre, bpm, comment, has_cover, raw)
    except Exception:
        return TagInfo(raw={})
