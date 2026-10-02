"""Opt-out Windows crash capture; no Qt imports or playback synchronization.

The file stays open for the process lifetime so faulthandler's descriptor is
valid even after the GUI event loop ends. Rotate only before opening it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import atexit
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from threading import RLock, get_native_id
from time import monotonic
import warnings


_LOCK = RLock()
_stream = None
_path: Path | None = None
_write_failed = False
_decoder_failed = False
_MAX_PREVIOUS_SIZE = 5 * 1024 * 1024


def track_context(path) -> dict:
    """Path-derived ID: stable across selection/player/child, not an audio hash."""
    if path is None:
        return {'path': None, 'track_id': None}
    try:
        canonical = str(Path(path).resolve())
    except OSError:
        canonical = str(path)
    identity = os.path.normcase(canonical)
    return {'path': canonical, 'track_id': hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}


def _rotate(path: Path) -> None:
    if path.is_file() and path.stat().st_size >= _MAX_PREVIOUS_SIZE:
        path.replace(path.with_suffix('.previous.log'))


def initialize() -> Path | None:
    global _stream, _path
    flag = os.environ.get('ALO_CRASH_DEBUG', '').strip().lower()
    enabled = flag in {'1', 'true', 'yes'} or (sys.platform == 'win32' and flag not in {'0', 'false', 'no'})
    if not enabled:
        return None
    with _LOCK:
        if _stream is not None:
            return _path
        try:
            target = os.environ.get('ALO_CRASH_DEBUG_LOG')
            if target:
                path = Path(target).expanduser().resolve()
            else:
                root = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
                path = root / 'ALO Music' / 'alo_crash_debug.log'
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate(path)
            _rotate(path.with_name(path.stem + '.waveform.log'))
            stream = path.open('ab', buffering=0)
            try:
                faulthandler.enable(file=stream, all_threads=True)
            except (OSError, RuntimeError):
                stream.close()
                raise
        except (OSError, RuntimeError, ValueError) as error:
            warnings.warn(f'ALO crash diagnostics unavailable: {error}', RuntimeWarning)
            return None
        _stream, _path = stream, path
        atexit.register(_close_log)
        record('application.start', python=sys.version, platform=platform.platform(),
               log=str(path), waveform_log=str(decoder_trace()))
        return path


def decoder_trace() -> Path | None:
    global _decoder_failed
    if _stream is None or _decoder_failed:
        return None
    path = _path.with_name(_path.stem + '.waveform.log')
    try:
        # If the persistent trace is unwritable, preserve the normal temp trace.
        with path.open('ab'):
            pass
        return path
    except OSError as error:
        _decoder_failed = True
        record('diagnostics.decoder.unavailable', error=str(error))
        return None


def _close_log() -> None:
    global _stream
    with _LOCK:
        stream, _stream = _stream, None
        if stream is not None:
            faulthandler.disable()
            stream.close()


def record(event: str, **fields) -> None:
    global _write_failed
    if _stream is None or _write_failed:
        return
    row = {'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
           'time': monotonic(), 'pid': os.getpid(), 'thread': get_native_id(), 'event': event, **fields}
    data = (json.dumps(row, ensure_ascii=True, default=str) + '\n').encode('utf-8')
    # Only diagnostic writes use this lock. No Qt or decoder work occurs here.
    with _LOCK:
        if _stream is None or _write_failed:
            return
        try:
            _stream.write(data)
        except OSError as error:
            # A failed diagnostic disk must not interrupt audio or the GUI.
            _write_failed = True
            warnings.warn(f'ALO crash diagnostic write failed: {error}', RuntimeWarning)
