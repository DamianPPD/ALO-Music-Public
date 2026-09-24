import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from audio_library_organizer.ui import player as player_module
from audio_library_organizer.domain.models import TrackRecord


def test_waveform_uses_file_amplitude_instead_of_decoration(tmp_path: Path):
    assert hasattr(player_module, 'read_waveform')
    path = tmp_path / 'levels.wav'
    sf.write(path, np.repeat([0.0, 0.25, -0.5, 1.0], 100), 8000, subtype='FLOAT')
    assert player_module.read_waveform(path, bins=4) == [0.0, 0.25, 0.5, 1.0]
    assert player_module.read_waveform(tmp_path / 'missing.mp3') == []


def test_waveform_seeking_follows_click_position():
    app = QApplication.instance() or QApplication([])
    bar = player_module.PlayerBar()
    try:
        bar.resize(1100, 150)
        bar.show()
        bar.seek.setRange(0, 100000)
        app.processEvents()
        moved = []
        bar.seek.sliderMoved.connect(moved.append)
        QTest.mouseClick(bar.seek, Qt.MouseButton.LeftButton,
                         pos=QPoint(bar.seek.width() * 3 // 4, bar.seek.height() // 2))
        assert moved and 70000 < moved[-1] < 80000
    finally:
        bar.close()


def test_stale_waveform_cannot_replace_current_track():
    app = QApplication.instance() or QApplication([])
    bar = player_module.PlayerBar()
    try:
        bar._waveform_generation = 2
        bar._waveform_ready(2, [0.25])
        bar._waveform_ready(1, [1.0])
        assert bar.seek.peaks == [0.25]
    finally:
        bar.close()


def test_mini_player_identifies_edited_track_and_shares_volume(tmp_path):
    app = QApplication.instance() or QApplication([])
    bar = player_module.PlayerBar()
    track = TrackRecord(path=tmp_path/'a.mp3', artist='Re:Locate', title='Built To Last')
    mini = player_module.CompactPlayerBar(bar, track)
    try:
        assert hasattr(mini, 'track_title')
        assert mini.track_title.text() == 'Built To Last'
        assert mini.track_artist.text() == 'Re:Locate'
        mini.volume.setValue(42)
        assert bar.audio.volume() == pytest.approx(0.42)
        bar.volume.setValue(61)
        assert mini.volume.value() == 61
    finally:
        mini.close()
        bar.close()


def test_cover_spans_transport_and_timeline():
    app = QApplication.instance() or QApplication([])
    bar = player_module.PlayerBar()
    try:
        bar.resize(1100, 150)
        bar.show()
        app.processEvents()
        cover = bar.cover.mapTo(bar, QPoint(0, 0))
        seek = bar.seek.mapTo(bar, QPoint(0, 0))
        assert seek.x() >= cover.x() + bar.cover.width()
        assert cover.y() <= seek.y() < cover.y() + bar.cover.height()
    finally:
        bar.close()


def test_long_title_does_not_push_player_beyond_window():
    app = QApplication.instance() or QApplication([])
    bar = player_module.PlayerBar()
    try:
        bar.title.setText('A long track title and remix name ' * 12)
        bar.resize(1000, 150)
        bar.show()
        app.processEvents()
        assert bar.width() == 1000
    finally:
        bar.close()


def test_missing_audio_device_does_not_offer_a_fake_output(monkeypatch):
    from PySide6.QtMultimedia import QMediaDevices
    monkeypatch.setattr(QMediaDevices, 'audioOutputs', lambda: [])
    app = QApplication.instance() or QApplication([])
    bar = player_module.PlayerBar()
    try:
        assert hasattr(bar, 'output_device')
        assert not bar.output_device.isEnabled()
        assert bar.output_device.count() == 1
        assert bar.output_device.currentData() is None
    finally:
        bar.close()
