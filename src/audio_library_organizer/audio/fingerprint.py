from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys

from audio_library_organizer.audio.probe import probe_audio


@dataclass(frozen=True, slots=True)
class FingerprintResult:
    fingerprint: str
    duration_seconds: int


def parse_fpcalc_output(text: str) -> FingerprintResult:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip().upper()] = value.strip()
    fingerprint = values.get('FINGERPRINT', '')
    if not fingerprint:
        raise RuntimeError('fpcalc nie zwrócił fingerprintu Chromaprint.')
    try:
        duration = int(round(float(values.get('DURATION', '0'))))
    except ValueError as exc:
        raise RuntimeError('fpcalc zwrócił nieprawidłową długość nagrania.') from exc
    return FingerprintResult(fingerprint, duration)


def find_fpcalc() -> Path | None:
    explicit = os.environ.get('ALO_FPCALC')
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))

    bundle_root = getattr(sys, '_MEIPASS', None)
    executable_dir = Path(sys.executable).resolve().parent
    names = ('fpcalc.exe', 'fpcalc')
    if bundle_root:
        for name in names:
            candidates.append(Path(bundle_root) / 'tools' / 'chromaprint' / name)
    for name in names:
        candidates.append(executable_dir / 'tools' / 'chromaprint' / name)
        candidates.append(Path.cwd() / 'tools' / 'chromaprint' / name)

    which = shutil.which('fpcalc')
    if which:
        candidates.append(Path(which))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _fingerprint_with_fpcalc(path: Path, fpcalc: Path) -> FingerprintResult:
    proc = subprocess.run(
        [str(fpcalc), str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return parse_fpcalc_output(proc.stdout)


def _fingerprint_with_ffmpeg(path: Path) -> FingerprintResult:
    proc = subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(path), '-f', 'chromaprint', '-'],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    fp = proc.stdout.strip()
    if not fp:
        raise RuntimeError('FFmpeg nie wygenerował fingerprintu Chromaprint.')
    info = probe_audio(path)
    duration = int(round(info.duration_seconds or 0))
    return FingerprintResult(fp, duration)


def fingerprint_audio(path: Path) -> FingerprintResult:
    path = Path(path)
    fpcalc = find_fpcalc()
    if fpcalc is not None:
        try:
            return _fingerprint_with_fpcalc(path, fpcalc)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            # A bundled fpcalc is preferred on Windows, but FFmpeg is a useful
            # fallback on development systems and machines that already have it.
            pass
    return _fingerprint_with_ffmpeg(path)
