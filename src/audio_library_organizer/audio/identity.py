"""Versioned MP3 material evidence, never evidence of ownership.

v1 hashes every complete MPEG Layer III frame, including the stream's Info/Xing
frame. Parsed ID3v2 and ID3v1 envelopes are excluded; no fixed prefix is skipped.
It deliberately does not equate a re-encoded recording with the original. A
strict, complete decoder pass is also required. Unsupported variants fail closed.
Call only in workers: this module reads and hashes the complete local file.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

from mutagen import MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError

ALGORITHM = 'mp3-layer3-frames-sha256/v1'
MAX_ID3_BYTES = 64 * 1024 * 1024
DECODE_SECONDS = 120


@dataclass(frozen=True, slots=True)
class AudioIdentity:
    status: str
    full_sha256: str | None = None
    audio_digest: str | None = None
    algorithm: str = ALGORITHM
    frame_count: int = 0
    stat_identity: tuple = ()
    tag_snapshot: dict = field(default_factory=dict)
    reason: str = ''


class UnsupportedMP3(ValueError):
    pass


def stat_identity(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, value.st_nlink)


def _opened_file_matches(before, opened):
    if os.name != 'nt':
        return stat_identity(opened) == stat_identity(before)
    # CPython 3.11 exposes CreationTime as integer ctime in both APIs.
    # Other Windows runtimes require explicit birthtime because fstat ctime
    # can mean metadata change time. Persisted and same-API tokens stay intact.
    creation_field = ('st_ctime_ns' if sys.implementation.name == 'cpython'
                      and sys.version_info[:2] == (3, 11) else 'st_birthtime_ns')
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_nlink', creation_field)
    tokens = [tuple(getattr(value, name, None) for name in fields)
              for value in (before, opened)]
    for token in tokens:
        if (any(type(value) is not int for value in token) or token[0] < 0
                or token[1] <= 0 or token[2] < 0 or token[4] <= 0):
            raise ValueError('Insufficient Windows file identity evidence.')
    return tokens[0] == tokens[1]


def _cancel(cancelled):
    if cancelled():
        raise InterruptedError('Audio identity cancelled.')


def _frame_identity(stream, length, cancelled):
    """Strict envelope/frame traversal: no sync-search through unknown bytes."""
    stream.seek(0)
    header = stream.read(10)
    begin, end = 0, length
    if header.startswith(b'ID3'):
        if len(header) != 10 or any(x & 128 for x in header[6:10]):
            raise ValueError('Invalid ID3 length.')
        if header[3] not in (2, 3, 4) or header[4] == 255 or header[5] & 0x10:
            raise UnsupportedMP3('Unsupported ID3 version/footer.')
        allowed = {2: 0xc0, 3: 0xe0, 4: 0xe0}[header[3]]
        if header[5] & ~allowed:
            raise ValueError('Invalid ID3 flags.')
        tag_length = sum(x << (7 * (3-i)) for i, x in enumerate(header[6:10]))
        if tag_length > MAX_ID3_BYTES:
            raise UnsupportedMP3('ID3 envelope exceeds supported limit.')
        begin = 10 + tag_length
        if begin > end:
            raise ValueError('Truncated ID3 envelope.')
    if end >= 128:
        stream.seek(end-128)
        if stream.read(3) == b'TAG':
            end -= 128
    stream.seek(begin)
    digest = hashlib.sha256()
    count, configuration, declared = 0, None, None
    position = begin
    while position < end:
        _cancel(cancelled)
        raw_header = stream.read(4)
        if len(raw_header) != 4:
            raise ValueError('Truncated MPEG header.')
        header = int.from_bytes(raw_header, 'big')
        version, layer = (header >> 19) & 3, (header >> 17) & 3
        bitrate_index, rate_index = (header >> 12) & 15, (header >> 10) & 3
        if header >> 21 != 0x7ff or version == 1 or rate_index == 3 or bitrate_index == 15:
            raise ValueError('Invalid MPEG frame boundary/header.')
        if layer != 1 or bitrate_index == 0:
            raise UnsupportedMP3('Only non-free-format MPEG Layer III is supported.')
        rate = (44100, 48000, 32000)[rate_index] // (1 if version == 3 else 2 if version == 2 else 4)
        table = ((0,32,40,48,56,64,80,96,112,128,160,192,224,256,320,0) if version == 3
                 else (0,8,16,24,32,40,48,56,64,80,96,112,128,144,160,0))
        bitrate = table[bitrate_index] * 1000
        channels = 1 if ((header >> 6) & 3) == 3 else 2
        current = (version, rate, channels)
        if configuration is not None and current != configuration:
            raise UnsupportedMP3('Changing audio stream configuration is unsupported.')
        configuration = current
        size = (144 if version == 3 else 72) * bitrate // rate + ((header >> 9) & 1)
        if position + size > end:
            raise ValueError('Truncated MPEG frame.')
        payload = stream.read(size-4)
        if len(payload) != size-4:
            raise ValueError('Truncated MPEG payload.')
        frame = raw_header + payload
        if count == 0:
            crc = 0 if ((header >> 16) & 1) else 2
            side = (17 if channels == 1 else 32) if version == 3 else (9 if channels == 1 else 17)
            offset = 4 + crc + side
            if frame[offset:offset+4] in (b'Info', b'Xing'):
                flags = int.from_bytes(frame[offset+4:offset+8], 'big')
                if flags & 1:
                    declared = int.from_bytes(frame[offset+8:offset+12], 'big')
        digest.update(frame)
        count += 1
        position += size
    if count < 2:
        raise ValueError('No complete MPEG audio stream.')
    if declared is None:
        raise UnsupportedMP3('A declared Xing/Info frame count is required to prove stream completeness.')
    if declared + 1 != count:
        raise ValueError('Truncated or inconsistent Xing/Info frame count.')
    return digest.hexdigest(), count


def _find_decoder():
    name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    roots = [Path(sys.executable).parent, Path.cwd()]
    if getattr(sys, '_MEIPASS', None):
        roots.insert(0, Path(sys._MEIPASS))
    for root in roots:
        for relative in (Path('tools')/'ffmpeg'/name, Path('tools')/'ffmpeg'/'bin'/name):
            candidate = root / relative
            if candidate.is_file():
                return str(candidate)
    return shutil.which('ffmpeg')


def _decode(path, decoder, cancelled):
    command = [str(decoder), '-hide_banner', '-v', 'error', '-nostdin', '-xerror',
               '-err_detect', 'explode', '-protocol_whitelist', 'file,pipe', '-f', 'mp3',
               '-i', str(path), '-map', '0:a:0', '-vn', '-sn', '-dn', '-threads', '1', '-f', 'null', '-']
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.monotonic() + DECODE_SECONDS
    try:
        while True:
            _cancel(cancelled)
            if time.monotonic() > deadline:
                raise TimeoutError('Complete audio decoding exceeded its limit.')
            try:
                _, error = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode or error:
            raise ValueError('Full MP3 decoding failed: ' + error[:4096].decode(errors='replace'))
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def _tags(path):
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = {}
    def text(key):
        value = tags.get(key)
        return str(value) if value is not None else ''
    covers = tags.getall('APIC') if hasattr(tags, 'getall') else []
    primary = next((c for c in covers if c.type == 3), covers[0] if covers else None)
    markers = {str(t.desc): [str(v) for v in t.text] for t in tags.getall('TXXX')
               if str(t.desc).upper().startswith('ALO_')} if hasattr(tags, 'getall') else {}
    comments = tags.getall('COMM') if hasattr(tags, 'getall') else []
    return {'artist': text('TPE1'), 'title': text('TIT2'), 'album': text('TALB'),
            'year': text('TDRC') or text('TYER'), 'genre': text('TCON'), 'bpm': text('TBPM'),
            'comment': str(comments[0]) if comments else '',
            'cover_sha256': hashlib.sha256(primary.data).hexdigest() if primary else '',
            'markers': markers}


def inspect_audio(path: Path, *, decoder=None, cancelled=None) -> AudioIdentity:
    """Return evidence or an explicit failure; never write/tag a music file."""
    cancelled = cancelled or (lambda: False)
    result = AudioIdentity('ERROR')
    try:
        _cancel(cancelled)
        path = Path(path).absolute()
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('Audio locator is not a regular file.')
        token = stat_identity(before)
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            if not _opened_file_matches(before, opened):
                raise ValueError('Audio file changed before opening.')
            full = hashlib.sha256()
            while chunk := stream.read(1024*1024):
                _cancel(cancelled)
                full.update(chunk)
            result = replace(result, full_sha256=full.hexdigest(), stat_identity=token)
            if path.suffix.lower() != '.mp3':
                return replace(result, status='UNSUPPORTED', reason='Only MP3 identity is supported.')
            digest, count = _frame_identity(stream, before.st_size, cancelled)
        executable = decoder if decoder is not None else _find_decoder()
        if not executable:
            return replace(result, status='UNAVAILABLE', reason='Complete MP3 decoder is unavailable.')
        _decode(path, executable, cancelled)
        snapshot = _tags(path)
        _cancel(cancelled)
        if stat_identity(path.stat()) != token:
            raise ValueError('Audio file changed during identity validation.')
        return replace(result, status='VALID', audio_digest=digest, frame_count=count, tag_snapshot=snapshot)
    except InterruptedError as exc:
        return replace(result, status='CANCELLED', reason=str(exc))
    except UnsupportedMP3 as exc:
        return replace(result, status='UNSUPPORTED', reason=str(exc))
    except FileNotFoundError as exc:
        return replace(result, status='UNAVAILABLE', reason=str(exc))
    except (OSError, ValueError, MutagenError, TimeoutError, subprocess.SubprocessError) as exc:
        return replace(result, status='ERROR', reason=str(exc))
