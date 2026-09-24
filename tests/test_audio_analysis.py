from pathlib import Path
import wave
import numpy as np

from audio_library_organizer.audio.bpm import normalize_club_bpm, estimate_bpm
from audio_library_organizer.audio.fingerprint import fingerprint_audio


def write_click_track(path: Path, bpm: float = 120.0, seconds: float = 20.0, rate: int = 22050):
    samples = np.zeros(int(seconds * rate), dtype=np.float32)
    beat = int(rate * 60.0 / bpm)
    click_len = int(rate * 0.015)
    pulse = np.hanning(click_len) * 0.9
    for pos in range(0, len(samples)-click_len, beat):
        samples[pos:pos+click_len] += pulse
    pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate); f.writeframes(pcm.tobytes())


def test_normalize_club_bpm_corrects_half_time_candidate():
    assert normalize_club_bpm(69.8) == 139.6
    assert normalize_club_bpm(128.2) == 128.2


def test_estimate_bpm_finds_simple_click_track(tmp_path: Path):
    path = tmp_path/'click.wav'; write_click_track(path, 120.0)
    result = estimate_bpm(path)
    assert result.raw_bpm is not None
    assert 116 <= result.normalized_bpm <= 124


def test_fingerprint_audio_returns_chromaprint(tmp_path: Path):
    path = tmp_path/'click.wav'; write_click_track(path, 120.0, 6.0)
    result = fingerprint_audio(path)
    assert result.duration_seconds >= 5
    assert len(result.fingerprint) > 8


def test_parse_fpcalc_output_reads_duration_and_fingerprint():
    from audio_library_organizer.audio.fingerprint import parse_fpcalc_output

    result = parse_fpcalc_output('DURATION=123\nFINGERPRINT=AQAAABbb_cc\n')

    assert result.duration_seconds == 123
    assert result.fingerprint == 'AQAAABbb_cc'


def test_find_fpcalc_checks_pyinstaller_bundle(monkeypatch, tmp_path: Path):
    import sys
    from audio_library_organizer.audio.fingerprint import find_fpcalc

    bundled = tmp_path / 'bundle' / 'tools' / 'chromaprint'
    bundled.mkdir(parents=True)
    exe = bundled / ('fpcalc.exe' if sys.platform.startswith('win') else 'fpcalc')
    exe.write_bytes(b'x')
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path / 'bundle'), raising=False)
    monkeypatch.delenv('ALO_FPCALC', raising=False)
    monkeypatch.setattr('audio_library_organizer.audio.fingerprint.shutil.which', lambda _: None)

    assert find_fpcalc() == exe


def test_estimate_bpm_is_close_for_140_club_click(tmp_path: Path):
    path = tmp_path/'click140.wav'; write_click_track(path, 140.0, 60.0)
    result = estimate_bpm(path)
    assert result.normalized_bpm is not None
    assert 139.0 <= result.normalized_bpm <= 141.0
