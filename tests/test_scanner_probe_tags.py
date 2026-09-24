from pathlib import Path
import math
import wave
import struct

from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TDRC, TBPM, COMM, APIC

from audio_library_organizer.jobs.scanner import iter_audio_files
from audio_library_organizer.audio.probe import probe_audio
from audio_library_organizer.metadata.tags import read_tags


def write_silent_wav(path: Path, seconds: float = 1.0, rate: int = 44100):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(rate)
        frame = struct.pack('<hh', 0, 0)
        f.writeframes(frame * int(seconds * rate))


def test_scanner_recurses_supported_audio_only(tmp_path: Path):
    (tmp_path/'nested').mkdir()
    for name in ('a.mp3','b.flac','c.wav','d.m4a','e.ogg','ignore.txt'):
        (tmp_path/'nested'/name).write_bytes(b'x')
    names = [p.name for p in iter_audio_files((tmp_path,))]
    assert names == ['a.mp3','b.flac','c.wav','d.m4a','e.ogg']


def test_probe_reads_wav_duration_and_audio_properties(tmp_path: Path):
    path = tmp_path/'tone.wav'
    write_silent_wav(path, seconds=1.25)
    info = probe_audio(path)
    assert math.isclose(info.duration_seconds, 1.25, abs_tol=0.03)
    assert info.sample_rate_hz == 44100
    assert info.channels == 2
    assert info.codec in {'PCM', 'WAVE'}


def test_read_tags_from_id3_file(tmp_path: Path):
    path = tmp_path/'tagged.mp3'
    tags = ID3()
    tags.add(TPE1(encoding=3, text='Armani & Ghost'))
    tags.add(TIT2(encoding=3, text='Airport (Original Mix) [139bpm]'))
    tags.add(TALB(encoding=3, text='Armani & Ghost – Airport'))
    tags.add(TDRC(encoding=3, text='2003'))
    tags.add(TCON(encoding=3, text='Hard House, Jumpstyle'))
    tags.add(TBPM(encoding=3, text='139'))
    tags.add(COMM(encoding=3, lang='eng', desc='', text='Discogs release data'))
    tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=b'fakejpeg'))
    tags.save(path)
    result = read_tags(path)
    assert result.artist == 'Armani & Ghost'
    assert result.title == 'Airport (Original Mix) [139bpm]'
    assert result.album == 'Armani & Ghost – Airport'
    assert result.year == '2003'
    assert result.genre == 'Hard House, Jumpstyle'
    assert result.bpm == 139
    assert result.comment == 'Discogs release data'
    assert result.has_cover is True
