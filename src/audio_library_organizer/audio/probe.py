from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
import wave

try:
    from mutagen import File as MutagenFile
except Exception:  # pragma: no cover
    MutagenFile = None


@dataclass(frozen=True, slots=True)
class AudioInfo:
    duration_seconds: float | None = None
    bitrate_kbps: int | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    codec: str | None = None


def _probe_wave(path: Path) -> AudioInfo:
    with wave.open(str(path), 'rb') as wf:
        rate = wf.getframerate()
        frames = wf.getnframes()
        channels = wf.getnchannels()
        bits = wf.getsampwidth() * 8
        duration = frames / rate if rate else None
        bitrate = int(rate * channels * bits / 1000) if rate else None
    return AudioInfo(duration, bitrate, rate, channels, 'WAVE')


def _probe_mutagen(path: Path) -> AudioInfo | None:
    if MutagenFile is None:
        return None
    try:
        audio = MutagenFile(path)
        info = getattr(audio, 'info', None)
        if info is None:
            return None
        length = float(getattr(info, 'length', 0) or 0) or None
        bitrate = getattr(info, 'bitrate', None)
        sample_rate = getattr(info, 'sample_rate', None)
        channels = getattr(info, 'channels', None)
        codec = path.suffix.lower().lstrip('.').upper() or None
        return AudioInfo(
            duration_seconds=length,
            bitrate_kbps=int(bitrate / 1000) if bitrate else None,
            sample_rate_hz=int(sample_rate) if sample_rate else None,
            channels=int(channels) if channels else None,
            codec=codec,
        )
    except Exception:
        return None


def _probe_ffprobe(path: Path) -> AudioInfo | None:
    try:
        proc = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
             'stream=codec_name,sample_rate,channels,bit_rate:format=duration,bit_rate',
             '-of', 'json', str(path)],
            capture_output=True, text=True, check=True, timeout=20,
        )
        data = json.loads(proc.stdout)
        stream = (data.get('streams') or [{}])[0]
        fmt = data.get('format') or {}
        raw_bitrate = stream.get('bit_rate') or fmt.get('bit_rate')
        duration = fmt.get('duration')
        return AudioInfo(
            duration_seconds=float(duration) if duration else None,
            bitrate_kbps=int(int(raw_bitrate) / 1000) if raw_bitrate else None,
            sample_rate_hz=int(stream['sample_rate']) if stream.get('sample_rate') else None,
            channels=int(stream['channels']) if stream.get('channels') else None,
            codec=(stream.get('codec_name') or '').upper() or None,
        )
    except Exception:
        return None


def probe_audio(path: Path) -> AudioInfo:
    path = Path(path)
    if path.suffix.lower() == '.wav':
        try:
            return _probe_wave(path)
        except Exception:
            pass
    return _probe_mutagen(path) or _probe_ffprobe(path) or AudioInfo(codec=path.suffix.lower().lstrip('.').upper() or None)
