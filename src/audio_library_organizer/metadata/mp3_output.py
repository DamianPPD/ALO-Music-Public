"""Shared deterministic MP3 write directives; no I/O, guessing or cover fetches."""
import hashlib
import re
from io import BytesIO
from mutagen.id3 import ID3, TPE1, TIT2, TALB, TDRC, TCON, TBPM, COMM, WXXX

from audio_library_organizer.domain.output_spec import (
    FieldAction, OutputField, OutputSpec, compare_specs,
)

_BPM_SUFFIX = re.compile(r'\s*\[\s*\d+(?:\.\d+)?\s*bpm\s*\]\s*$', re.IGNORECASE)
TEXT_FIELDS = ('artist','title','album','year','genre','bpm','comment')
REMOVED_NUMBER_FRAMES = {'track_number':'TRCK', 'disc_number':'TPOS'}
TEXT_FRAME_TYPES = {'artist':TPE1, 'title':TIT2, 'album':TALB, 'year':TDRC,
                    'genre':TCON, 'bpm':TBPM}


def build_title_tag(track):
    if not track.title:
        return None
    title = _BPM_SUFFIX.sub('', track.title).strip()
    if track.bpm is not None:
        title += f' [{int(round(track.bpm))}bpm]'
    return title


def mp3_tag_values(track):
    # This is the actual writer's set/preserve decision, including truthiness.
    return {'artist': track.artist, 'title': build_title_tag(track), 'album': track.album,
            'year': track.year, 'genre': track.genre,
            'bpm': str(int(round(track.bpm))) if track.bpm is not None else None,
            'comment': track.comment}


def mp3_text_frames(track):
    """Fresh actual frame objects, shared by materialization and expectation."""
    return {name:cls(encoding=3,text=str(value)) for name,cls in TEXT_FRAME_TYPES.items()
            if (value := mp3_tag_values(track)[name])}


def mp3_discogs_frame(track):
    return WXXX(encoding=3,desc='Discogs',url=track.discogs_url) if track.discogs_url else None


def _discogs_directive(track):
    frame=mp3_discogs_frame(track)
    if frame is None:
        return OutputField('discogs_url',FieldAction.REMOVE)
    try:
        tags=ID3();tags.add(frame);stream=BytesIO();tags.save(stream,v2_version=3);stream.seek(0)
        value=ID3(stream).getall('WXXX')[0].url
    except (UnicodeError,ValueError,IndexError):
        # The real writer may reject an unencodable URL. No invented resulting
        # string, no change to its error behaviour or the existing URL policy.
        return OutputField('discogs_url',FieldAction.UNKNOWN)
    return OutputField('discogs_url',FieldAction.SET,value)


def build_mp3_spec(track, *, cover_bytes=None, relative_path=None):
    # ID3v2.3 serializes genres/dates/multiple text values differently from raw
    # input. Use the writer's actual frames and Mutagen codec, in memory only.
    # This is not a second handwritten normalization implementation.
    tags=ID3()
    frames=mp3_text_frames(track)
    for frame in frames.values(): tags.add(frame)
    if track.comment: tags.add(COMM(encoding=3,lang='eng',desc='',text=track.comment))
    stream=BytesIO();tags.save(stream,v2_version=3);stream.seek(0);canonical=ID3(stream)
    fields=[]
    for name,value in mp3_tag_values(track).items():
        if not value:
            fields.append(OutputField(name,FieldAction.PRESERVE))
        elif name=='comment':
            comments=canonical.getall('COMM')
            fields.append(OutputField(name,FieldAction.SET,str(comments[0]) if comments else ''))
        else:
            frame=canonical.get(TEXT_FRAME_TYPES[name].__name__)
            fields.append(OutputField(name,FieldAction.SET,str(frame) if frame is not None else ''))
    fields += [OutputField(name, FieldAction.REMOVE) for name in REMOVED_NUMBER_FRAMES]
    fields.append(_discogs_directive(track))
    # Bytes must already be resolved/prepared by the caller; a path or URL is
    # never a cover digest. This stage's adopted adapter supplies neither.
    fields.append(OutputField('cover_sha256', FieldAction.SET, hashlib.sha256(cover_bytes).hexdigest())
                  if cover_bytes else OutputField('cover_sha256', FieldAction.UNKNOWN))
    fields.append(OutputField('relative_path', FieldAction.SET, relative_path)
                  if relative_path is not None else OutputField('relative_path', FieldAction.UNKNOWN))
    return OutputSpec(tuple(fields))


def observed_adoption_spec(snapshot):
    # v1 remains explicitly partial: no fabricated numbering, URL or full policy.
    names = (*TEXT_FIELDS, *REMOVED_NUMBER_FRAMES, 'discogs_url','cover_sha256','relative_path')
    tags = snapshot.get('tag_snapshot', {}) if snapshot.get('version') == 1 else {}
    fields = []
    for name in names:
        value = (snapshot.get('relative_path') if snapshot.get('version') == 1 else None) if name == 'relative_path' else (
            tags.get(name) if name in (*TEXT_FIELDS,'cover_sha256') else None)
        fields.append(OutputField(name, FieldAction.SET, value) if isinstance(value,str)
                      else OutputField(name, FieldAction.UNKNOWN))
    return OutputSpec(tuple(fields), provenance='legacy-adoption-v1-observed')
