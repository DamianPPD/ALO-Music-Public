from __future__ import annotations

import re
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, ID3NoHeaderError, APIC, TALB, TBPM, TCON, TDRC, TIT2, TPE1, COMM, WXXX
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

from audio_library_organizer.domain.models import TrackRecord

_BPM_SUFFIX = re.compile(r'\s*\[\s*\d+(?:\.\d+)?\s*bpm\s*\]\s*$', re.IGNORECASE)


def build_title_tag(track: TrackRecord) -> str | None:
    if not track.title:
        return None
    title = _BPM_SUFFIX.sub('', track.title).strip()
    if track.bpm is not None:
        title += f' [{int(round(track.bpm))}bpm]'
    return title


def _write_mp3(path: Path, track: TrackRecord, cover_bytes: bytes | None, cover_mime: str, replace_cover: bool) -> None:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    values = {
        'TPE1': (TPE1, track.artist),
        'TIT2': (TIT2, build_title_tag(track)),
        'TALB': (TALB, track.album),
        'TDRC': (TDRC, track.year),
        'TCON': (TCON, track.genre),
        'TBPM': (TBPM, str(int(round(track.bpm))) if track.bpm is not None else None),
    }
    # ALO output policy: album/disc sequencing is intentionally removed.
    # Numbers that are part of the actual title/version remain untouched.
    tags.delall('TRCK')
    tags.delall('TPOS')
    for frame_id, (cls, value) in values.items():
        if value:
            tags.delall(frame_id)
            tags.add(cls(encoding=3, text=str(value)))
    if track.comment:
        tags.delall('COMM')
        tags.add(COMM(encoding=3, lang='eng', desc='', text=track.comment))
    # Keep the Discogs link in the dedicated URL area instead of cluttering Comment.
    for key in list(tags.keys()):
        if key.startswith('WXXX:') and getattr(tags[key], 'desc', '').casefold() == 'discogs':
            del tags[key]
    if track.discogs_url:
        tags.add(WXXX(encoding=3, desc='Discogs', url=track.discogs_url))
    if replace_cover:
        tags.delall('APIC')
    if cover_bytes:
        if not replace_cover:
            tags.delall('APIC')
        tags.add(APIC(encoding=3, mime=cover_mime, type=3, desc='Cover', data=cover_bytes))
    tags.save(path, v2_version=3)



def _write_flac(path: Path, track: TrackRecord, cover_bytes: bytes | None, cover_mime: str, replace_cover: bool) -> None:
    audio = FLAC(path)
    values = {
        'artist': track.artist,
        'title': build_title_tag(track),
        'album': track.album,
        'date': track.year,
        'genre': track.genre,
        'bpm': str(int(round(track.bpm))) if track.bpm is not None else None,
        'comment': track.comment,
        'discogs_url': track.discogs_url,
    }
    for number_key in ('tracknumber', 'tracktotal', 'totaltracks', 'discnumber', 'disctotal', 'totaldiscs'):
        try:
            del audio[number_key]
        except KeyError:
            pass
    for key, value in values.items():
        if value:
            audio[key] = [str(value)]
    if replace_cover:
        audio.clear_pictures()
    if cover_bytes:
        picture = Picture()
        picture.type = 3
        picture.mime = cover_mime
        picture.desc = 'Cover'
        picture.data = cover_bytes
        if not replace_cover:
            audio.clear_pictures()
        audio.add_picture(picture)
    audio.save()


def _write_mp4(path: Path, track: TrackRecord, cover_bytes: bytes | None, cover_mime: str, replace_cover: bool) -> None:
    audio = MP4(path)
    tags = audio.tags
    if tags is None:
        audio.add_tags(); tags = audio.tags
    values = {
        '\xa9ART': track.artist,
        '\xa9nam': build_title_tag(track),
        '\xa9alb': track.album,
        '\xa9day': track.year,
        '\xa9gen': track.genre,
        'tmpo': int(round(track.bpm)) if track.bpm is not None else None,
        '\xa9cmt': track.comment,
    }
    tags.pop('trkn', None)
    tags.pop('disk', None)
    for key, value in values.items():
        if value is not None and value != '':
            tags[key] = [value] if key != 'tmpo' else [int(value)]
    if track.discogs_url:
        tags['----:com.apple.iTunes:DISCOGS_URL'] = [track.discogs_url.encode('utf-8')]
    if replace_cover:
        tags.pop('covr', None)
    if cover_bytes:
        imageformat = MP4Cover.FORMAT_PNG if cover_mime == 'image/png' else MP4Cover.FORMAT_JPEG
        tags['covr'] = [MP4Cover(cover_bytes, imageformat=imageformat)]
    audio.save()

def _write_generic(path: Path, track: TrackRecord) -> None:
    audio = MutagenFile(path, easy=True)
    if audio is None:
        return
    values = {
        'artist': track.artist,
        'title': build_title_tag(track),
        'album': track.album,
        'date': track.year,
        'genre': track.genre,
        'bpm': str(int(round(track.bpm))) if track.bpm is not None else None,
        'comment': track.comment,
    }
    for number_key in ('tracknumber', 'tracktotal', 'totaltracks', 'discnumber', 'disctotal', 'totaldiscs'):
        try:
            del audio[number_key]
        except Exception:
            pass
    for key, value in values.items():
        if value:
            try:
                audio[key] = [str(value)]
            except Exception:
                pass
    audio.save()


def write_resolved_tags(path: Path, track: TrackRecord, *, cover_bytes: bytes | None = None, cover_mime: str = 'image/jpeg', replace_cover: bool = False) -> None:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.mp3':
        _write_mp3(path, track, cover_bytes, cover_mime, replace_cover)
    elif suffix == '.flac':
        _write_flac(path, track, cover_bytes, cover_mime, replace_cover)
    elif suffix in {'.m4a', '.mp4'}:
        _write_mp4(path, track, cover_bytes, cover_mime, replace_cover)
    else:
        _write_generic(path, track)
