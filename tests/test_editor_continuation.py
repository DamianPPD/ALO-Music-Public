import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.player import PlayerBar, CompactPlayerBar
from audio_library_organizer.ui.waveform import WaveformSlider


def test_online_lock_is_above_metadata_and_disables_scan(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = MetadataEditorDialog(TrackRecord(path=tmp_path/'a.mp3'))
    try:
        dialog.show()
        app.processEvents()
        assert dialog.online_lock.mapTo(dialog, QPoint()).y() < dialog.artist.mapTo(dialog, QPoint()).y()
        dialog.online_lock.click()
        assert not dialog.scan_online_button.isEnabled()
    finally:
        dialog._force_closing = True
        dialog.close()


def test_field_markers_follow_status_and_sources(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = MetadataEditorDialog(TrackRecord(path=tmp_path/'a.mp3', artist='Artist', field_sources={'artist':'Tag'}))
    try:
        assert dialog._field_status_icons['artist'].property('statusKind') == dialog.status_icons['artist'].property('statusKind') == 'ok'
        assert dialog._field_status_icons['artist'].isHidden()
        assert dialog._field_status_icons['year'].property('statusKind') == 'warning'
        assert not dialog._field_status_icons['year'].isHidden()
        assert not dialog._source_buttons['artist'].icon().isNull()
        dialog.year.setText('2009')
        assert dialog._field_status_icons['year'].property('statusKind') == 'ok'
        assert dialog._field_status_icons['year'].isHidden()
        dialog.artist.clear()
        assert dialog._field_status_icons['artist'].property('statusKind') == 'critical'
    finally:
        dialog._force_closing = True
        dialog.close()


def test_mini_seek_is_disabled_for_other_track_and_shares_waveform(tmp_path):
    app = QApplication.instance() or QApplication([])
    bar = PlayerBar()
    track = TrackRecord(path=tmp_path/'a.mp3')
    mini = CompactPlayerBar(bar, track)
    try:
        bar.current_path = tmp_path/'other.mp3'
        mini._position_changed(9000)
        assert mini.elapsed.text() == '00:00'
        assert not mini.seek.isEnabled()
        assert isinstance(mini.seek, WaveformSlider)
        bar.current_path = track.path
        bar.track_changed.emit(track)
        bar._waveform_ready(bar._waveform_generation, [0.2, 0.8])
        assert mini.seek.isEnabled()
        assert mini.seek.peaks == [0.2, 0.8]
        bar.current_path = tmp_path/'other.mp3'
        bar.track_changed.emit(TrackRecord(path=bar.current_path))
        assert not mini.seek.peaks
    finally:
        mini.close()
        bar.close()


def test_main_player_duration_updates_seek_range():
    app = QApplication.instance() or QApplication([])
    bar = PlayerBar()
    try:
        bar._duration_changed(65000)
        assert bar.seek.maximum() == 65000
        assert bar.total.text() == '01:05'
    finally:
        bar.close()


def test_editor_keeps_player_and_actions_visible_in_short_window(tmp_path):
    from audio_library_organizer.ui.theme import style_for_theme
    from audio_library_organizer.ui.v0411_theme import style_for_v0411
    app = QApplication.instance() or QApplication([])
    bar = PlayerBar()
    dialog = MetadataEditorDialog(TrackRecord(path=tmp_path/'a.mp3'), player_bar=bar)
    dialog.setStyleSheet(style_for_theme('dark') + style_for_v0411('dark'))
    try:
        dialog.resize(1420, 760)
        dialog.show()
        app.processEvents()
        assert dialog.height() == 760
        assert dialog.status_button.mapTo(dialog, QPoint()).y() + dialog.status_button.height() < 760
        assert dialog.compact_player.mapTo(dialog, QPoint()).y() + dialog.compact_player.height() < 760
        assert dialog.content_scroll.verticalScrollBar().maximum() > 0
    finally:
        dialog._force_closing = True
        dialog.close()
        bar.close()
