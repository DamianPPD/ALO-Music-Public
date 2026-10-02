"""Exercise real Qt playback and native waveform processes in a bounded child."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_100_settled_and_100_rapid_track_changes_release_jobs_and_decoders(tmp_path):
    script = r'''
import gc, json, shutil, subprocess, sys, weakref
from pathlib import Path
import numpy as np
import soundfile as sf
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, QPersistentModelIndex, Qt, qInstallMessageHandler
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from PySide6.QtTest import QSignalSpy, QTest
from audio_library_organizer import crash_debug
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui import waveform
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.player import PlayerBar

root = Path(sys.argv[1])
crash_debug.initialize()
app = QApplication([])
errors = []
sys.excepthook = lambda *args: errors.append(args)
paths = []
for name, frames, rate, channels in [
    ('short.wav', 8000, 8000, 1), ('short.flac', 16000, 8000, 2),
    ('short.mp3', 44100, 44100, 1), ('long.wav', 120 * 44100, 44100, 1),
    ('large.wav', 8 * 96000, 96000, 6),
]:
    path = root / name
    samples = np.sin(np.arange(frames, dtype=np.float32) * .1) * .5
    sf.write(path, np.repeat(samples[:, None], channels, axis=1), rate)
    paths.append(path)
ffmpeg = shutil.which('ffmpeg')
if ffmpeg:
    m4a = root / 'short.m4a'
    subprocess.run([ffmpeg, '-v', 'error', '-i', str(paths[0]), '-c:a', 'aac', str(m4a)],
                   check=True, timeout=10)
    paths.append(m4a)

processes, active_at_spawn, references = [], [], []
original_popen = waveform.subprocess.Popen
def observed_popen(*args, **kwargs):
    active_at_spawn.append(sum(process.poll() is None for process in processes))
    process = original_popen(*args, **kwargs)
    processes.append(process)
    return process
waveform.subprocess.Popen = observed_popen
original_init = waveform.WaveformJob.__init__
def observed_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    references.append((weakref.ref(self), weakref.ref(self.signals)))
waveform.WaveformJob.__init__ = observed_init

host = QWidget(); layout = QVBoxLayout(host)
page, bar = LibraryPage(), PlayerBar()
layout.addWidget(page); layout.addWidget(bar)
tracks = [TrackRecord(path=path, title=path.name) for path in paths]
page.set_tracks(tracks)
page.play_requested.connect(lambda track: bar.load_track(track, autoplay=True))
bar.track_changed.connect(page.set_playing_track)
states = []
bar.player.playbackStateChanged.connect(states.append)
pool = QThreadPool.globalInstance()
host.resize(1600, 1000); host.show(); app.processEvents()
page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
indexes = [QPersistentModelIndex(page.model.index(row, 3)) for row in range(page.model.rowCount())]
removed, inserted, reset = (QSignalSpy(page.model.rowsRemoved), QSignalSpy(page.model.rowsInserted),
                            QSignalSpy(page.model.modelReset))
plays = QSignalSpy(page.play_requested)
qt_messages = []
previous_handler = qInstallMessageHandler(lambda kind, context, message: qt_messages.append(message))

def double_click(track):
    row = next(row for row in range(page.model.rowCount())
               if page.model.item(row, 0).data(Qt.ItemDataRole.UserRole) is track)
    center = page.table.visualRect(page.model.index(row, 3)).center()
    before = plays.count()
    QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=center, delay=0)
    assert plays.count() == before
    QTest.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=center, delay=0)
    QTest.mouseRelease(page.table.viewport(), Qt.MouseButton.LeftButton, pos=center, delay=0)
    assert plays.count() == before + 1
    assert all(index.isValid() for index in indexes)
    assert removed.count() == inserted.count() == reset.count() == 0

# Single selections alone must not start either decoder, even over 100 clicks.
for i in range(100):
    page.select_track(tracks[i % len(tracks)])
    app.processEvents()
assert bar.current_path is None and not processes

# Every settled switch performs a real child decode; QMediaPlayer is not mocked.
for i in range(100):
    track = tracks[i % len(tracks)]
    double_click(track)
    assert pool.waitForDone(10000)
    app.processEvents()
    assert pool.activeThreadCount() == 0 and not waveform._ACTIVE_JOBS
    assert bar.current_path == track.path
    if track.path.suffix != '.m4a':
        assert len(bar.seek.peaks) == 240 and max(bar.seek.peaks) > .3
    if i % 3 == 0:
        bar.player.stop(); app.processEvents()
    if i % 10 == 9:
        gc.collect()
        assert all(job() is None and signals() is None for job, signals in references)
assert len(processes) == 100

# A->B->C->D->E and longer rapid bursts replace in-flight waveform/playback.
for i in range(100):
    track = tracks[(i + 1) % len(tracks)]
    double_click(track)
    app.processEvents()
assert pool.waitForDone(10000)
app.processEvents()
assert bar.current_path == track.path
assert len(bar.seek.peaks) == 240
assert pool.activeThreadCount() == 0 and not waveform._ACTIVE_JOBS
assert all(count == 0 for count in active_at_spawn)
assert all(process.poll() is not None for process in processes)
assert QMediaPlayer.PlaybackState.PlayingState in states
assert not [message for message in qt_messages if 'index' in message.lower() or 'model' in message.lower()]
qInstallMessageHandler(previous_handler)

# Also destroy the receiver with a fresh request; cancellation must finish.
bar.load(paths[0], autoplay=True)
cancel = bar._waveform_cancel
host.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
assert cancel.is_set() and pool.waitForDone(10000)
app.processEvents(); gc.collect()
assert not errors and not waveform._ACTIVE_JOBS
assert all(job() is None and signals() is None for job, signals in references)
assert all(process.poll() is not None for process in processes)
print(json.dumps({'selections': 100, 'settled': 100, 'rapid': 100, 'jobs': len(references),
                  'decoders': len(processes), 'formats': [path.suffix for path in paths],
                  'jobs_remaining': 0, 'decoders_remaining': 0}))
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', ALO_CRASH_DEBUG='1',
               ALO_CRASH_DEBUG_LOG=str(tmp_path / 'alo_crash_debug.log'),
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], env=env,
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr[-12000:]
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary['jobs'] == 201
    assert summary['decoders'] >= 100
    assert summary['jobs_remaining'] == summary['decoders_remaining'] == 0
    events = [json.loads(line) for line in (tmp_path / 'alo_crash_debug.log').read_text().splitlines()]
    started = [event for event in events if event['event'] == 'job.start']
    finished = [event for event in events if event['event'] == 'job.finished']
    assert {event['job_id'] for event in started} == {event['job_id'] for event in finished}
    assert len(finished) == 201 and finished[-1]['active_jobs'] == 0
    accepted = [event for event in events if event['event'] == 'player.waveform.accept']
    assert all(event['generation'] == event['current_generation'] for event in accepted)
