"""Private decoder entry point. Run only in a disposable OS process."""
from __future__ import annotations

import faulthandler
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import get_native_id
from time import monotonic


def _warn(message, error_stream) -> None:
    try:
        print(message, file=error_stream)
    except (OSError, ValueError):
        pass  # Even both diagnostic sinks failing must not change decode output.


def _enable_fault_handler(trace, error_stream) -> None:
    try:
        faulthandler.enable(file=trace, all_threads=True)
    except (OSError, RuntimeError, ValueError) as error:
        _warn(f'Waveform faulthandler unavailable: {error}', error_stream)


def decode(path: Path, bins: int, trace, *, generation: int = 0, error_stream=None) -> list[float]:
    error_stream = error_stream or sys.stderr
    identity = os.path.normcase(str(path.resolve()))
    context = {'generation': generation, 'job_id': os.environ.get('ALO_WAVEFORM_JOB_ID'),
               'track_id': hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}
    trace_failed = False

    def mark(phase, **fields):
        nonlocal trace_failed
        if trace_failed:
            return
        try:
            trace.write(json.dumps({'phase': phase, 'path': str(path), 'pid': os.getpid(),
                                'thread': get_native_id(), 'time': monotonic(),
                                'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                                **context, **fields}) + '\n')
            trace.flush()
        except OSError as error:
            trace_failed = True
            _warn(f'Waveform trace write failed: {error}', error_stream)
            _enable_fault_handler(error_stream, error_stream)

    try:
        mark('decoder.enter')
        import numpy as np
        import soundfile as sf
        mark('SoundFile.enter')
        audio = sf.SoundFile(str(path))
        try:
            mark('SoundFile.opened', frames=len(audio), sample_rate=audio.samplerate, channels=audio.channels,
                 soundfile_version=sf.__version__, libsndfile_version=sf.__libsndfile_version__)
            count = min(bins, len(audio))
            peaks = []
            reads = 0
            mark('audio.read.enter')
            for i in range(count):
                remaining = (i + 1) * len(audio) // count - audio.tell()
                peak = 0.0
                while remaining > 0:
                    samples = audio.read(min(65536, remaining), dtype='float32', always_2d=True)
                    reads += 1
                    if not len(samples):
                        return []
                    peak = max(peak, float(np.max(np.abs(np.nan_to_num(samples)))))
                    remaining -= len(samples)
                peaks.append(min(1.0, peak))
            mark('audio.read.leave', read_count=reads, peaks=len(peaks))
            return peaks
        finally:
            mark('SoundFile.close.enter')
            audio.close()
            mark('SoundFile.closed')
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        # Ordinary unsupported-file errors are different from a native crash.
        mark('decode.unavailable', error=str(error))
        return []


def main(argv=None) -> int:
    path, bins, output, trace_path, generation = sys.argv[1:] if argv is None else argv
    # Windowed frozen builds may have no Python stderr despite redirected OS handles.
    error_stream = sys.stderr
    if error_stream is None:
        fallback = os.environ.get('ALO_WAVEFORM_FALLBACK_TRACE', os.devnull)
        try:
            error_stream = Path(fallback).open('a', encoding='utf-8', buffering=1)
        except OSError:
            error_stream = Path(os.devnull).open('a', encoding='utf-8', buffering=1)
    try:
        trace = Path(trace_path).open('a', encoding='utf-8', buffering=1)
    except OSError as error:
        _warn(f'Waveform trace open failed: {error}', error_stream)
        trace = error_stream
    try:
        _enable_fault_handler(trace, error_stream)
        peaks = decode(Path(path), int(bins), trace, generation=int(generation), error_stream=error_stream)
        Path(output).write_text(json.dumps(peaks, allow_nan=False), encoding='utf-8')
    finally:
        faulthandler.disable()
        if trace is not error_stream:
            try:
                trace.close()
            except OSError as error:
                _warn(f'Waveform trace close failed: {error}', error_stream)
        if error_stream is not sys.stderr:
            try:
                error_stream.close()
            except OSError:
                pass  # The optional trace must not make a successful decode fail.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
