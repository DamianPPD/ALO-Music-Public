"""Native traceback watchdog with no Python monitoring or application wrappers."""

import atexit
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

_handles = []


def install():
    directory = Path(os.environ['ALO_RESTART_TRACE_DIR'])
    directory.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    log = (directory / f'child-{pid}.jsonl').open('a', encoding='utf-8', buffering=1)
    faults = (directory / f'child-{pid}.faulthandler.log').open('a', encoding='utf-8', buffering=1)
    _handles.extend((log, faults))

    def record(stage, event, **fields):
        log.write(json.dumps({'stage': stage, 'event': event, 'pid': pid,
                              'python_thread_id': threading.get_ident(),
                              'native_thread_id': threading.get_native_id(),
                              'monotonic_ns': time.monotonic_ns(), **fields}) + '\n')
        log.flush()
        os.fsync(log.fileno())

    script = Path(os.environ['ALO_RESTART_CHILD_SCRIPT']).read_text(encoding='utf-8')
    position = sys.orig_argv.index('-c')
    record('START', 'observer_installed', mode='native-faulthandler-only',
           child_source_matches_command=script == sys.orig_argv[position + 1],
           child_source_sha256=hashlib.sha256(script.encode()).hexdigest(),
           python_version=sys.version.split()[0])

    def exit_marker():
        record('START', 'natural_atexit')
        faulthandler.dump_traceback(file=faults, all_threads=True)
        faults.flush()
        os.fsync(faults.fileno())
        record('END', 'natural_atexit')

    faulthandler.enable(file=faults, all_threads=True)
    faulthandler.dump_traceback_later(10, repeat=True, file=faults)
    atexit.register(exit_marker)
