"""Versioned MP3 material evidence, never evidence of ownership.

v1 hashes every complete MPEG Layer III frame, including the stream's Info/Xing
frame. Parsed ID3v2, APEv2 and ID3v1 envelopes are excluded.
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
import struct
import subprocess
import sys
import time

from mutagen import MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError

ALGORITHM = 'mp3-layer3-frames-sha256/v1'
MAX_ID3_BYTES = 64 * 1024 * 1024
MAX_APEV2_BYTES = 16 * 1024 * 1024
MAX_APEV2_ITEMS = 4096
_APE_DESCRIPTOR = struct.Struct('<8s4I8s')
_APE_ITEM = struct.Struct('<II')
_APE_MAGIC = b'APETAGEX'
_APE_HAS_HEADER = 1 << 31
_APE_IS_HEADER = 1 << 29
DECODE_SECONDS = 120
MAX_DECODE_STDERR_BYTES = 64 * 1024


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
    ape_at_eof: bool = False


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


def _ape_footer(stream, begin, end):
    if end - begin < _APE_DESCRIPTOR.size:
        return None
    stream.seek(end - _APE_DESCRIPTOR.size)
    raw = stream.read(_APE_DESCRIPTOR.size)
    return raw if raw.startswith(_APE_MAGIC) else None


def _ape_start(stream, begin, end, footer, cancelled):
    _cancel(cancelled)
    if len(footer) != _APE_DESCRIPTOR.size:
        raise ValueError('Invalid APEv2 footer length.')
    magic, version, size, count, flags, reserved = _APE_DESCRIPTOR.unpack(footer)
    if version != 2000:
        raise ValueError('Invalid APEv2 version.')
    if flags & ~(_APE_HAS_HEADER | 1) or any(reserved):
        raise ValueError('Invalid APEv2 footer flags or reserved bytes.')
    header_size = _APE_DESCRIPTOR.size if flags & _APE_HAS_HEADER else 0
    start = end - size - header_size
    if (size < _APE_DESCRIPTOR.size or size + header_size > MAX_APEV2_BYTES
            or start < begin):
        raise ValueError('Invalid APEv2 size or position.')
    remaining = size - _APE_DESCRIPTOR.size
    if count > min(MAX_APEV2_ITEMS, remaining // 11):
        raise ValueError('Invalid APEv2 item count.')
    stream.seek(start)
    if header_size:
        expected = _APE_DESCRIPTOR.pack(magic, version, size, count, flags | _APE_IS_HEADER, reserved)
        if stream.read(header_size) != expected:
            raise ValueError('Invalid APEv2 header/footer pair.')
    keys = {b'id3', b'tag', b'oggs', b'mp+'}
    for _ in range(count):
        _cancel(cancelled)
        if remaining < 11:
            raise ValueError('Invalid APEv2 item length.')
        raw = stream.read(_APE_ITEM.size)
        if len(raw) != _APE_ITEM.size:
            raise ValueError('Invalid APEv2 item header.')
        value_size, item_flags = _APE_ITEM.unpack(raw)
        if item_flags > 5:
            raise ValueError('Invalid APEv2 item flags.')
        remaining -= _APE_ITEM.size
        key_start = stream.tell()
        key_data = stream.read(min(remaining, 256))
        key_size = key_data.find(b'\0')
        if key_size < 2 or any(not 0x20 <= byte <= 0x7e for byte in key_data[:key_size]):
            raise ValueError('Invalid APEv2 item key.')
        key = key_data[:key_size].lower()
        if key in keys:
            raise ValueError('Invalid APEv2 reserved or duplicate item key.')
        keys.add(key)
        remaining -= key_size + 1
        if value_size > remaining:
            raise ValueError('Invalid APEv2 item value length.')
        stream.seek(key_start + key_size + 1)
        value = stream.read(value_size)
        if len(value) != value_size:
            raise ValueError('Invalid APEv2 truncated item value.')
        if (item_flags & 6) != 2:  # Text and external locators are UTF-8.
            try:
                value.decode('utf-8')
            except UnicodeDecodeError as exc:
                raise ValueError('Invalid APEv2 item UTF-8.') from exc
        remaining -= value_size
    if remaining:
        raise ValueError('Invalid APEv2 unaccounted item bytes.')
    return start


def _mp3_tails(stream, begin, length):
    end = length
    if length - begin >= 128:
        stream.seek(length - 128)
        if stream.read(3) == b'TAG':
            end -= 128
    footer = _ape_footer(stream, begin, end)
    if footer is not None:
        yield end, footer
    if end != length:
        # A binary APEv2 item can also contain TAG 128 bytes from EOF.
        footer = _ape_footer(stream, begin, length)
        if footer is not None:
            yield length, footer
    yield end, None


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
    first_error = None
    for tail_end, footer in _mp3_tails(stream, begin, end):
        try:
            frame_end = tail_end if footer is None else _ape_start(stream, begin, tail_end, footer, cancelled)
            digest, count = _mpeg_frame_digest(stream, begin, frame_end, cancelled)
        except ValueError as exc:
            if first_error is None:
                first_error = exc
        else:
            # Only the boundary of the declared, complete stream can succeed.
            # Magic bytes inside a frame or a metadata value do not set that boundary.
            return digest, count, frame_end if footer is not None else None, footer is not None and tail_end == length
    raise first_error


def _mpeg_frame_digest(stream, begin, end, cancelled):
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



def _windows_stderr_probe(stream):
    """Borrow the sole-consumer anonymous pipe handle; never close it here."""
    import ctypes as C
    import msvcrt

    peek = C.WinDLL('kernel32', use_last_error=True).PeekNamedPipe
    peek.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p,
                     C.POINTER(C.c_uint32), C.c_void_p]
    peek.restype = C.c_int
    handle = msvcrt.get_osfhandle(stream.fileno())

    def available():
        count = C.c_uint32()
        if not peek(handle, None, 0, None, C.byref(count), None):
            error = C.get_last_error()
            if error == 109:  # ERROR_BROKEN_PIPE: writer closed, no more bytes
                return 0
            raise C.WinError(error)
        return count.value
    return available


def _decode_windows(command, cancelled):
    """Bound stderr while decoding, without disk spooling or reader Threads.

    communicate() on CPython Windows creates reader Threads with inherited
    daemon state, retaining a DummyThread/Event for each native Qt worker.
    Peek/read use one worker and one pipe consumer, with no concurrent reads
    on its synchronous handle. Retain only the diagnostic prefix, count every
    byte, and refuse at quota+1. Kernel pipe buffering is finite; no temp file.
    """
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, bufsize=0)
    try:
        deadline = time.monotonic() + DECODE_SECONDS
        prefix = bytearray()
        consumed = 0
        try:
            available = _windows_stderr_probe(process.stderr)
            while True:
                _cancel(cancelled)
                if time.monotonic() > deadline:
                    raise TimeoutError('Complete audio decoding exceeded its limit.')
                count = available()
                if count:
                    chunk = os.read(process.stderr.fileno(),
                                    min(count, 4096, MAX_DECODE_STDERR_BYTES + 1 - consumed))
                    if not chunk:
                        raise OSError('Unexpected EOF in decoder stderr pipe.')
                    consumed += len(chunk)
                    if consumed > MAX_DECODE_STDERR_BYTES:
                        raise ValueError('Decoder stderr exceeded 65536-byte transport limit.')
                    prefix.extend(chunk[:4096 - len(prefix)])
                    continue  # stop/deadline checks also apply to continuous output
                if process.poll() is not None:
                    # The child may have written and exited since the empty
                    # peek. Recheck after observing exit before accepting EOF.
                    if available():
                        continue
                    break
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
        except (InterruptedError, TimeoutError):
            raise
        except OSError as exc:
            raise OSError('Decoder stderr transport failed: ' + str(exc)) from exc
        if process.returncode or consumed:
            raise ValueError('Full MP3 decoding failed: ' + prefix.decode(errors='replace'))
    finally:
        try:
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    if process.poll() is None:
                        raise
        finally:
            try:
                process.wait()
            finally:
                process.stderr.close()


def _decode(path, decoder, cancelled, frame_end=None):
    input_args = ['-protocol_whitelist', 'file,pipe', '-f', 'mp3', '-i', str(path)]
    if frame_end is not None:
        # Some FFmpeg versions feed footer-only APE items to the MP3 decoder.
        # Use a seekable view ending at the validated last frame on the same file.
        input_args = ['-protocol_whitelist', 'file,pipe,subfile', '-f', 'mp3',
                      '-start', '0', '-end', str(frame_end), '-i', 'subfile:file:' + str(path)]
    command = [str(decoder), '-hide_banner', '-v', 'error', '-nostdin', '-xerror',
               '-err_detect', 'explode', *input_args, '-map', '0:a:0',
               '-vn', '-sn', '-dn', '-threads', '1', '-f', 'null', '-']
    if os.name == 'nt':
        return _decode_windows(command, cancelled)
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


def _tags(path, *, ape_at_eof=False):
    try:
        tags = ID3(path, load_v1=not ape_at_eof)
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
            digest, count, frame_end, ape_at_eof = _frame_identity(stream, before.st_size, cancelled)
        executable = decoder if decoder is not None else _find_decoder()
        if not executable:
            return replace(result, status='UNAVAILABLE', reason='Complete MP3 decoder is unavailable.')
        _decode(path, executable, cancelled, frame_end)
        snapshot = _tags(path, ape_at_eof=ape_at_eof)
        _cancel(cancelled)
        if stat_identity(path.stat()) != token:
            raise ValueError('Audio file changed during identity validation.')
        return replace(result, status='VALID', audio_digest=digest, frame_count=count,
                       tag_snapshot=snapshot, ape_at_eof=ape_at_eof)
    except InterruptedError as exc:
        return replace(result, status='CANCELLED', reason=str(exc))
    except UnsupportedMP3 as exc:
        return replace(result, status='UNSUPPORTED', reason=str(exc))
    except FileNotFoundError as exc:
        return replace(result, status='UNAVAILABLE', reason=str(exc))
    except (OSError, ValueError, MutagenError, TimeoutError, subprocess.SubprocessError) as exc:
        return replace(result, status='ERROR', reason=str(exc))
