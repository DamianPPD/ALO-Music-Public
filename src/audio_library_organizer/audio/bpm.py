from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BPMResult:
    raw_bpm: float | None
    normalized_bpm: float | None
    confidence: float | None = None


def normalize_club_bpm(value: float | None) -> float | None:
    if value is None:
        return None
    bpm = float(value)
    # Conservative half/double-time correction for dance music. Do not force
    # every tempo into a narrow window; only correct common obvious halves.
    if 45 <= bpm < 85:
        bpm *= 2.0
    elif 210 < bpm <= 300:
        bpm /= 2.0
    return round(bpm, 1)


def estimate_bpm(path: Path, *, analysis_seconds: float = 180.0) -> BPMResult:
    try:
        import librosa
        import numpy as np
        y, sr = librosa.load(str(path), sr=22050, mono=True, duration=analysis_seconds)
        if y.size < sr * 8:
            return BPMResult(None, None, None)
        onset = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = librosa.feature.tempo(onset_envelope=onset, sr=sr, aggregate=np.median)
        raw = float(np.ravel(tempo)[0]) if np.size(tempo) else None

        # Librosa's tempo grid is quantized to analysis frames and can be a few
        # BPM off around common club tempos (e.g. 140 can land near 143.55).
        # Once a stable beat sequence exists, the average beat interval gives a
        # much more precise estimate. Trim the outer 10% to ignore occasional
        # missed/double detections at transitions.
        _beat_tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr)
        if len(beat_frames) >= 8:
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
            intervals = np.diff(beat_times)
            if intervals.size >= 7:
                low, high = np.quantile(intervals, [0.10, 0.90])
                trimmed = intervals[(intervals >= low) & (intervals <= high)]
                if trimmed.size:
                    refined = 60.0 / float(np.mean(trimmed))
                    if 35.0 <= refined <= 320.0:
                        raw = refined

        normalized = normalize_club_bpm(raw)
        # A deliberately simple confidence proxy: regular onset autocorrelation
        # yields a stronger peak relative to the median background.
        ac = librosa.autocorrelate(onset, max_size=min(len(onset), 256))
        if len(ac) > 4:
            body = ac[1:]
            peak = float(body.max())
            med = float(np.median(body)) or 1.0
            confidence = max(0.0, min(1.0, (peak / med - 1.0) / 8.0))
        else:
            confidence = None
        return BPMResult(round(raw, 2) if raw else None, normalized, confidence)
    except Exception:
        return BPMResult(None, None, None)
