import os
import sys
from threading import Event
from time import monotonic

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui import waveform
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.player import PlayerBar
from audio_library_organizer.ui.theme import DARK_STYLE


@pytest.fixture(autouse=True)
def restore_application_style():
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    try:
        yield
    finally:
        app.setStyleSheet(previous)


def _host(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(DARK_STYLE)
    host = QWidget()
    layout = QVBoxLayout(host)
    page, bar = LibraryPage(), PlayerBar()
    layout.addWidget(page); layout.addWidget(bar)
    # This regression targets waveform extraction, independently of playback's decoder.
    monkeypatch.setattr(bar.player, 'setSource', lambda url: None)
    page.play_requested.connect(lambda track: bar.load_track(track, autoplay=False))
    bar.track_changed.connect(page.set_playing_track)
    cover = QPixmap(32, 32); cover.fill(QColor('#dc5588'))
    cover_path = tmp_path / 'cover.png'; cover.save(str(cover_path))
    tracks = [
        TrackRecord(path=tmp_path / 'A.wav', artist='Artist A', title='Song A', year='2001',
                    album='Album A', genre='House', bpm=120, channels=2, sample_rate_hz=44100,
                    duration_seconds=2, manual_cover_path=str(cover_path)),
        TrackRecord(path=tmp_path / 'problematic-B.mp3', artist='Artist B', title='Song B',
                    channels=1, sample_rate_hz=22050, duration_seconds=3),
        TrackRecord(path=tmp_path / 'C.flac', artist='Artist C', title='Song C', album='Album C',
                    channels=6, sample_rate_hz=96000, duration_seconds=4),
    ]
    sf.write(tracks[0].path, np.ones(400) * .25, 8000, subtype='FLOAT')
    tracks[1].path.write_bytes(b'ID3 damaged MP3')
    sf.write(tracks[2].path, np.ones(400) * .75, 8000)
    page.set_tracks(tracks)
    host.resize(1920, 1080); host.show(); app.processEvents()
    return app, host, page, bar, tracks


@pytest.mark.parametrize('sequence', [(0, 1), (0, 1, 2), (0, 1, 2, 0), (0, 1, 2, 0, 1, 2)])
def test_library_first_and_rapid_switch_survive_native_decoder_fault(tmp_path, monkeypatch, sequence):
    from test_waveform_process_safety import _native_crash_command
    original = waveform._waveform_command
    monkeypatch.setattr(waveform, '_waveform_command', lambda path, *args:
                        _native_crash_command() if path.name == 'problematic-B.mp3' else original(path, *args))
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *args: errors.append(args))
    app, host, page, bar, tracks = _host(tmp_path, monkeypatch)
    try:
        for index in sequence:
            page.select_track(tracks[index])
            page._play_selected()
            app.processEvents()
        assert QThreadPool.globalInstance().waitForDone(5000)
        app.processEvents()
        last = tracks[sequence[-1]]
        assert not errors
        assert host.isVisible()
        assert page._current_track() is last
        assert page.detail_labels['artist'].text() == last.artist
        assert page.detail_labels['title'].text() == last.title
        assert page.detail_labels['album'].text() == (last.album or '—')
        assert bar.current_track is last and bar.current_path == last.path
        assert bar.title.text() == last.title
        assert bar._waveform_generation == len(sequence)
        if last is tracks[1]:
            assert bar.seek.peaks == []
        else:
            assert max(bar.seek.peaks) == pytest.approx(.25 if last is tracks[0] else .75)
        # A late result from a preceding generation cannot overwrite the final view.
        expected = bar.seek.peaks.copy()
        bar._waveform_ready(bar._waveform_generation - 1, [1.0])
        assert bar.seek.peaks == expected
    finally:
        host.close()


def test_destroying_player_cancels_live_worker_without_deleted_qobject_access(tmp_path, monkeypatch):
    marker = tmp_path / 'decoder-started'
    monkeypatch.setattr(waveform, '_waveform_command', lambda *args: [
        sys.executable, '-c', 'from pathlib import Path; import sys,time; Path(sys.argv[1]).touch(); time.sleep(30)', str(marker)])
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *args: errors.append(args))
    app, host, page, bar, tracks = _host(tmp_path, monkeypatch)
    page.select_track(tracks[0]); page._play_selected()
    deadline = monotonic() + 3
    while not marker.exists() and monotonic() < deadline:
        app.processEvents(); Event().wait(.01)
    assert marker.exists()
    cancel = bar._waveform_cancel
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert cancel.is_set()
    assert QThreadPool.globalInstance().waitForDone(3000)
    app.processEvents()
    assert errors == []


def test_queued_waveform_result_is_removed_when_receiver_is_destroyed(tmp_path, monkeypatch):
    """The worker finishes and emits before deletion, with delivery still queued."""
    import shiboken6

    monkeypatch.setattr(waveform, 'read_waveform', lambda *args, **kwargs: [.25])
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *args: errors.append(args))
    app, host, page, bar, tracks = _host(tmp_path, monkeypatch)
    delivered = []
    bar.waveform_changed.connect(lambda peaks: delivered.append(list(peaks)))
    page.select_track(tracks[0]); page._play_selected()
    # No GUI event processing between emission and receiver destruction.
    assert QThreadPool.globalInstance().waitForDone(3000)
    assert delivered == [[]]
    cancel = bar._waveform_cancel
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(bar)
    assert cancel.is_set()
    app.processEvents()
    assert delivered == [[]]
    assert errors == []
