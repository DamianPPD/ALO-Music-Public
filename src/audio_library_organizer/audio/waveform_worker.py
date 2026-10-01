"""Private decoder entry point. Run only in a disposable OS process."""
from __future__ import annotations

import faulthandler
import json
import os
from pathlib import Path
import sys
from threading import get_native_id
from time import monotonic


def decode(path: Path, bins: int, trace) -> list[float]:
    def mark(phase):
        trace.write(json.dumps({'phase': phase, 'path': str(path), 'pid': os.getpid(),
                                'thread': get_native_id(), 'time': monotonic()}) + '\n')
        trace.flush()

    try:
        import numpy as np
        import soundfile as sf
        mark('SoundFile.enter')
        with sf.SoundFile(str(path)) as audio:
            mark('SoundFile.opened')
            count = min(bins, len(audio))
            peaks = []
            for i in range(count):
                remaining = (i + 1) * len(audio) // count - audio.tell()
                peak = 0.0
                while remaining > 0:
                    mark('audio.read.enter')
                    samples = audio.read(min(65536, remaining), dtype='float32', always_2d=True)
                    mark('audio.read.leave')
                    if not len(samples):
                        return []
                    peak = max(peak, float(np.max(np.abs(np.nan_to_num(samples)))))
                    remaining -= len(samples)
                peaks.append(min(1.0, peak))
            return peaks
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        # Ordinary unsupported-file errors are different from a native crash.
        trace.write(f'decode unavailable: {error}\n')
        return []


def main(argv=None) -> int:
    path, bins, output, trace_path, generation = sys.argv[1:] if argv is None else argv
    with Path(trace_path).open('w', encoding='utf-8', buffering=1) as trace:
        faulthandler.enable(file=trace, all_threads=True)
        trace.write(f'generation={generation} pid={os.getpid()} thread={get_native_id()}\n')
        peaks = decode(Path(path), int(bins), trace)
        Path(output).write_text(json.dumps(peaks, allow_nan=False), encoding='utf-8')
        faulthandler.disable()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
