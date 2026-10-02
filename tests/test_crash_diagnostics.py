"""Persistent evidence must survive a fatal process exit, without a GUI loop."""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import soundfile as sf
import pytest

def _run(code, log, **environment):
    env = dict(os.environ, ALO_CRASH_DEBUG='1', ALO_CRASH_DEBUG_LOG=str(log))
    env.update(environment)
    return subprocess.run([sys.executable, '-c', code], env=env, capture_output=True,
                          text=True, timeout=15)


def _events(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
            if line.startswith('{')]


def test_diagnostics_flush_context_and_fatal_stack_without_gui(tmp_path):
    log = tmp_path / 'alo_crash_debug.log'
    result = _run("""
from audio_library_organizer import crash_debug
import ctypes, sys
crash_debug.initialize()
crash_debug.record('before.native.fault', path='A.wav', job_id='test:1', generation=1)
if sys.platform != 'win32':
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
ctypes.string_at(0)
""", log)
    assert log.is_file(), result.stderr
    assert result.returncode != 0
    events = _events(log)
    event = next(event for event in events if event['event'] == 'before.native.fault')
    assert event['path'] == 'A.wav' and event['job_id'] == 'test:1'
    assert event['timestamp'] and event['pid'] and event['thread']
    text = log.read_text(encoding='utf-8')
    assert 'Fatal Python error' in text or 'Windows fatal exception' in text


def test_disabled_diagnostics_creates_no_files(tmp_path):
    log = tmp_path / 'disabled.log'
    result = _run("""
from audio_library_organizer import crash_debug
crash_debug.initialize()
crash_debug.record('unused')
""", log, ALO_CRASH_DEBUG='0')
    assert result.returncode == 0, result.stderr
    assert not log.exists()


def test_unwritable_decoder_log_does_not_disable_waveform(tmp_path):
    wav = tmp_path / 'A.wav'; sf.write(wav, np.ones(400) * .5, 8000)
    log = tmp_path / 'alo_crash_debug.log'
    log.with_name('alo_crash_debug.waveform.log').mkdir()
    result = _run(f"""
from pathlib import Path
from audio_library_organizer import crash_debug
from audio_library_organizer.ui.waveform import read_waveform
crash_debug.initialize()
assert read_waveform(Path({str(wav)!r}), bins=4) == [.5] * 4
""", log)
    assert result.returncode == 0, result.stderr
    assert log.exists()


def test_windows_default_and_opt_out_use_local_app_data(tmp_path):
    result = _run("""
import os
from pathlib import Path
from audio_library_organizer import crash_debug
os.environ.pop('ALO_CRASH_DEBUG', None)
os.environ.pop('ALO_CRASH_DEBUG_LOG', None)
crash_debug.sys.platform = 'win32'
expected = Path(os.environ['LOCALAPPDATA']) / 'ALO Music' / 'alo_crash_debug.log'
assert crash_debug.initialize() == expected
assert expected.exists()
""", tmp_path / 'unused.log', LOCALAPPDATA=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_diagnostic_write_failure_warns_once_without_interrupting_caller(tmp_path):
    result = _run("""
from audio_library_organizer import crash_debug
import warnings
crash_debug.initialize()
class FullDisk:
    def write(self, data):
        raise OSError('disk full')
with warnings.catch_warnings(record=True) as seen:
    warnings.simplefilter('always')
    real_stream = crash_debug._stream
    crash_debug._stream = FullDisk()
    try:
        for i in range(10):
            crash_debug.record('test.write.failure')
    finally:
        crash_debug._stream = real_stream
    assert len(seen) == 1
""", tmp_path / 'log.log')
    assert result.returncode == 0, result.stderr


def test_worker_trace_write_failure_after_open_keeps_native_decode_working(tmp_path):
    if not Path('/dev/full').exists():
        pytest.skip('Requires a real ENOSPC diagnostic sink')
    wav = tmp_path / 'A.wav'; sf.write(wav, np.ones(400) * .5, 8000)
    result = _run(f"""
from pathlib import Path
from audio_library_organizer import crash_debug
from audio_library_organizer.ui.waveform import read_waveform
crash_debug.initialize()
crash_debug.decoder_trace = lambda: Path('/dev/full')
assert read_waveform(Path({str(wav)!r}), bins=4) == [.5] * 4
""", tmp_path / 'log.log')
    assert result.returncode == 0, result.stderr


def test_shutdown_disconnects_diagnostic_sink_before_late_callbacks(tmp_path):
    result = _run("""
from audio_library_organizer import crash_debug
crash_debug.initialize()
crash_debug._close_log()
crash_debug.record('late.destroyed.callback')
crash_debug._close_log()
""", tmp_path / 'log.log')
    assert result.returncode == 0, result.stderr


def test_windowed_worker_without_stderr_or_fault_handler_keeps_decode_working(tmp_path):
    wav = tmp_path / 'A.wav'; sf.write(wav, np.ones(400) * .5, 8000)
    bad_trace = tmp_path / 'trace-directory'; bad_trace.mkdir()
    output = tmp_path / 'peaks.json'
    fallback = tmp_path / 'stderr.log'
    result = _run(f"""
from pathlib import Path
from audio_library_organizer.audio import waveform_worker
waveform_worker.sys.stderr = None
def unavailable(*args, **kwargs):
    raise RuntimeError('fault handler unavailable')
waveform_worker.faulthandler.enable = unavailable
assert waveform_worker.main([{str(wav)!r}, '4', {str(output)!r}, {str(bad_trace)!r}, '1']) == 0
""", tmp_path / 'log.log', ALO_WAVEFORM_FALLBACK_TRACE=str(fallback))
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text()) == [.5] * 4
    assert 'Waveform trace open failed' in fallback.read_text()


def test_windowed_worker_with_both_trace_sinks_full_keeps_decode_working(tmp_path):
    if not Path('/dev/full').exists():
        pytest.skip('Requires a real ENOSPC diagnostic sink')
    wav = tmp_path / 'A.wav'; sf.write(wav, np.ones(400) * .5, 8000)
    output = tmp_path / 'peaks.json'
    result = _run(f"""
from audio_library_organizer.audio import waveform_worker
waveform_worker.sys.stderr = None
assert waveform_worker.main([{str(wav)!r}, '4', {str(output)!r}, '/dev/full', '1']) == 0
""", tmp_path / 'log.log', ALO_WAVEFORM_FALLBACK_TRACE='/dev/full')
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(output.read_text()) == [.5] * 4


def test_invalid_diagnostic_path_does_not_block_startup(tmp_path):
    result = _run("""
from audio_library_organizer import crash_debug
def unavailable_home(self):
    raise RuntimeError('Could not determine home directory')
crash_debug.Path.expanduser = unavailable_home
assert crash_debug.initialize() is None
""", tmp_path / 'log.log')
    assert result.returncode == 0, result.stderr


def test_decoder_phases_and_identity_persist_after_temporary_files_removed(tmp_path):
    wav = tmp_path / 'long.wav'
    # Many read bins must produce a summary, not one log line per read chunk.
    sf.write(wav, np.ones(400000) * .5, 8000, subtype='FLOAT')
    log = tmp_path / 'alo_crash_debug.log'
    code = f"""
from pathlib import Path
from audio_library_organizer import crash_debug
from audio_library_organizer.ui.waveform import read_waveform
crash_debug.initialize()
assert len(read_waveform(Path({str(wav)!r}), bins=240, generation=7, job_id='test:7')) == 240
"""
    result = _run(code, log)
    assert result.returncode == 0, result.stderr
    child_log = log.with_name('alo_crash_debug.waveform.log')
    events = _events(child_log)
    phases = [event['phase'] for event in events]
    assert phases.index('SoundFile.enter') < phases.index('SoundFile.opened')
    assert phases.index('audio.read.enter') < phases.index('audio.read.leave')
    assert phases.index('audio.read.leave') < phases.index('SoundFile.close.enter')
    assert phases.index('SoundFile.close.enter') < phases.index('SoundFile.closed')
    assert len(events) < 20
    assert all(event['job_id'] == 'test:7' and event['generation'] == 7 for event in events)
    assert len({event['track_id'] for event in events}) == 1
    parent = _events(log)
    request = next(event for event in parent if event['event'] == 'decoder.start')
    assert request['track_id'] == events[0]['track_id']
    assert any(event['event'] == 'decoder.reaped' for event in parent)


def test_failed_decoder_evidence_is_retained(tmp_path):
    broken = tmp_path / 'broken.mp3'; broken.write_bytes(b'ID3 broken')
    log = tmp_path / 'alo_crash_debug.log'
    result = _run(f"""
from pathlib import Path
from audio_library_organizer import crash_debug
from audio_library_organizer.ui import waveform
crash_debug.initialize()
waveform._waveform_command = lambda *args: [__import__('sys').executable, '-X', 'faulthandler', '-c', 'import ctypes; ctypes.string_at(0)']
import sys
if sys.platform != 'win32':
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
assert waveform.read_waveform(Path({str(broken)!r}), job_id='fault:1') == []
""", log)
    assert result.returncode == 0, result.stderr
    events = _events(log)
    failed = next(event for event in events if event['event'] == 'decoder.failed')
    assert failed['job_id'] == 'fault:1' and failed['exit_code'] != 0
    assert 'Fatal Python error' in failed['stderr'] or 'Windows fatal exception' in failed['stderr']


def test_library_player_log_distinguishes_selection_play_cancel_and_stale_result(tmp_path):
    wav = tmp_path / 'A.wav'; sf.write(wav, np.ones(400) * .5, 8000)
    second = tmp_path / 'B.wav'; sf.write(second, np.ones(400) * .25, 8000)
    log = tmp_path / 'alo_crash_debug.log'
    result = _run(f"""
from pathlib import Path
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtCore import QThreadPool, QCoreApplication, QEvent
from audio_library_organizer import crash_debug
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.player import PlayerBar
crash_debug.initialize()
app = QApplication([])
host = QWidget(); layout = QVBoxLayout(host)
page, bar = LibraryPage(), PlayerBar()
layout.addWidget(page); layout.addWidget(bar)
page.play_requested.connect(lambda track: bar.load_track(track, autoplay=False))
tracks = [TrackRecord(path=Path({str(wav)!r})), TrackRecord(path=Path({str(second)!r}))]
page.set_tracks(tracks)
page.select_track(tracks[0])
assert bar.current_path is None
page._play_selected()
page.select_track(tracks[1]); page._play_selected()
assert QThreadPool.globalInstance().waitForDone(5000)
app.processEvents()
expected = bar.seek.peaks.copy()
bar._waveform_ready(1, [1.0])
assert bar.seek.peaks == expected
host.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
assert QThreadPool.globalInstance().waitForDone(3000)
app.processEvents()
""", log, QT_QPA_PLATFORM='offscreen')
    assert result.returncode == 0, result.stderr
    events = _events(log)
    names = [event['event'] for event in events]
    assert names.index('library.selection.enter') < names.index('library.selection.done')
    assert names.index('library.selection.done') < names.index('library.play.request')
    assert names.index('player.source.enter') < names.index('player.source.done')
    assert 'player.waveform.cancel.request' in names
    assert 'player.waveform.discard.stale' in names
    assert 'player.destroyed' in names
    starts = [event for event in events if event['event'] == 'job.start']
    finished = [event for event in events if event['event'] == 'job.finished']
    assert {event['job_id'] for event in starts} == {event['job_id'] for event in finished}
    assert finished[-1]['active_jobs'] == 0
