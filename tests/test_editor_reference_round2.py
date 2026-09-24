import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.player import PlayerBar


def _app():
    return QApplication.instance() or QApplication([])


def _complete_track(tmp_path: Path, **updates) -> TrackRecord:
    values = dict(
        path=tmp_path / '12-07-56 - ReLocate - Built To Last (Ferry Tayle Remix).mp3',
        artist='Re:Locate',
        title='Built To Last (Ferry Tayle Remix)',
        year='2009',
        genre='Trance',
        bpm=138,
        duration_seconds=316,
        codec='MP3',
        status='review',
    )
    values.update(updates)
    return TrackRecord(**values)


def test_editor_initial_size_fills_screen_without_exceeding_available_geometry(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_complete_track(tmp_path))
    try:
        dialog.show()
        app.processEvents()
        available = dialog.screen().availableGeometry()
        assert dialog.width() <= available.width()
        assert dialog.height() <= available.height()
        assert dialog.width() >= min(1680, int(available.width() * 0.96))
        assert dialog.height() >= min(1040, int(available.height() * 0.90))
    finally:
        dialog._force_closing = True
        dialog.close()


def test_top_track_strip_shows_filename_bpm_duration_and_format(tmp_path: Path):
    _app()
    dialog = MetadataEditorDialog(_complete_track(tmp_path))
    try:
        assert dialog.track_header_title.text() == '12-07-56 - ReLocate - Built To Last (Ferry Tayle Remix).mp3'
        assert dialog.track_header_bpm.text() == '138 BPM'
        assert dialog.track_header_duration.text() == '05:16'
        assert dialog.track_header_format.text() == 'MP3'
        assert dialog.track_header_icon.pixmap() is not None
        assert not dialog.track_header_icon.pixmap().isNull()
        refreshed = _complete_track(tmp_path)
        refreshed.path = tmp_path / 'Updated long filename after online recognition.mp3'
        refreshed.bpm = 140
        refreshed.duration_seconds = 301
        refreshed.codec = 'FLAC'
        dialog.apply_online_result(refreshed)
        assert dialog.track_header_title.fullText() == refreshed.path.name
        assert dialog.track_header_title.toolTip() == refreshed.path.name
        assert dialog.track_header_bpm.text() == '140 BPM'
        assert dialog.track_header_duration.text() == '05:01'
        assert dialog.track_header_format.text() == 'FLAC'
    finally:
        dialog._force_closing = True
        dialog.close()


def test_valid_fields_have_no_extra_icon_and_missing_fields_show_warning(tmp_path: Path):
    dialog = MetadataEditorDialog(_complete_track(tmp_path, year=None))
    try:
        assert dialog._field_status_icons['artist'].isHidden()
        assert not dialog._field_status_icons['year'].isHidden()
        assert dialog._field_status_icons['year'].text() == ''
        assert not dialog._field_status_icons['year'].pixmap().isNull()
        assert dialog._field_status_icons['year'].property('statusKind') == 'warning'
        dialog.year.setText('2009')
        assert dialog._field_status_icons['year'].isHidden()
        dialog.artist.clear()
        assert not dialog._field_status_icons['artist'].isHidden()
        assert dialog._field_status_icons['artist'].text() == ''
        assert not dialog._field_status_icons['artist'].pixmap().isNull()
        assert dialog._field_status_icons['artist'].property('statusKind') == 'critical'
    finally:
        dialog._force_closing = True
        dialog.close()


def test_source_action_is_a_small_centered_button_inside_the_cell(tmp_path: Path):
    app = _app()
    track = _complete_track(
        tmp_path,
        field_source_values={
            'artist': {'Tag': 'Re:Locate'},
            'title': {'Tag': 'Built To Last (Ferry Tayle Remix)'},
            'year': {'Tag': '2009'},
            'genre': {'Tag': 'Trance'},
        },
    )
    dialog = MetadataEditorDialog(track)
    try:
        dialog.show()
        app.processEvents()
        cell = dialog.source_table.cellWidget(0, 5)
        button = cell.findChild(QPushButton, 'UseSourceDataButton')
        assert cell.objectName() == 'UseSourceDataCell'
        assert button is not None
        assert button.width() <= 108
        assert button.height() <= 24
        assert abs((button.x() + button.width() / 2) - cell.width() / 2) <= 2
    finally:
        dialog._force_closing = True
        dialog.close()


def test_cover_actions_are_below_art_and_proposals_without_duplicate_search(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_complete_track(tmp_path))
    try:
        dialog.show()
        app.processEvents()
        visible_texts = [button.text() for button in dialog.findChildren(QPushButton) if not button.isHidden()]
        assert 'Wyszukaj' not in visible_texts
        assert dialog.cover_proposal_count.height() <= 24
        proposals_bottom = dialog.cover_proposals_host.mapTo(dialog, QPoint()).y() + dialog.cover_proposals_host.height()
        assert dialog.choose_cover_button.mapTo(dialog, QPoint()).y() >= proposals_bottom
        assert dialog.search_cover_button.mapTo(dialog, QPoint()).y() >= proposals_bottom
        assert dialog.search_cover_button.text() == 'Szukaj okładki online'
        assert 'Więcej okładek online…' not in visible_texts
    finally:
        dialog._force_closing = True
        dialog.close()


def test_footer_has_only_undo_status_toggle_and_save(tmp_path: Path):
    track = _complete_track(tmp_path)
    dialog = MetadataEditorDialog(track)

    def update_status(_editor, desired):
        track.status = 'ready' if desired else 'review'

    dialog.ready_requested.connect(update_status)
    try:
        footer_texts = [button.text() for button in dialog.footer_buttons]
        assert footer_texts == ['Cofnij ostatnią zmianę', 'DO SPRAWDZENIA', 'Zapisz zmiany']
        dialog.status_button.click()
        assert dialog.status_button.text() == 'GOTOWE'
        assert dialog.status_button.property('currentStatusKind') == 'ready'
        dialog.status_button.click()
        assert dialog.status_button.text() == 'DO SPRAWDZENIA'
        assert dialog.status_button.property('currentStatusKind') == 'review'
    finally:
        dialog._force_closing = True
        dialog.close()
