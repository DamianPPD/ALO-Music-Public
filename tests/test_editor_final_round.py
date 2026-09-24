import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.player import CompactPlayerBar, PlayerBar
from audio_library_organizer.ui.theme import style_for_theme


def _app():
    return QApplication.instance() or QApplication([])


def _track(tmp_path: Path, **updates) -> TrackRecord:
    values = dict(
        path=tmp_path / ('A very long track filename with artist title extended remix name '
                         'and additional release information.mp3'),
        artist='Re:Locate',
        title='A very long track title with extended remix and release information ' * 3,
        year='2009',
        genre='Trance',
        bpm=138,
        duration_seconds=316,
        codec='MP3',
        status='review',
    )
    values.update(updates)
    return TrackRecord(**values)


def _close(dialog):
    dialog._force_closing = True
    dialog.close()


def test_three_editor_columns_keep_equal_height_at_multiple_widths(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        for width in (1180, 1540):
            dialog.resize(width, 920)
            dialog.show()
            app.processEvents()
            heights = (
                dialog.metadata_card.height(),
                dialog.status_recognition_column.height(),
                dialog.cover_gallery.height(),
            )
            assert max(heights) - min(heights) <= 2
            assert dialog.comment.mapTo(dialog.metadata_card, dialog.comment.rect().topLeft()).y() < dialog.metadata_card.height()
    finally:
        _close(dialog)


def test_source_table_reserves_four_rows_and_caps_growth(tmp_path: Path):
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        minimum_height = dialog.source_table.horizontalHeader().height() + 4 * 31
        assert dialog.source_table.height() >= minimum_height

        sources = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', 'Nazwa pliku', 'Ręcznie', 'Testowe')
        dialog._source_values['title'] = {source: f'Tytuł {index}' for index, source in enumerate(sources)}
        dialog._refresh_source_comparison()
        assert dialog.source_table.rowCount() == 7
        assert dialog.source_table.height() <= dialog.source_table.horizontalHeader().height() + 6 * 31 + 8
    finally:
        _close(dialog)


def test_source_names_use_provider_colors_and_actions_stay_inside_cells(tmp_path: Path):
    app = _app()
    previous_style = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    values = {
        'Tag': 'TAG title',
        'Discogs': 'Discogs title',
        'MusicBrainz': 'MusicBrainz title',
        'Apple / iTunes': 'Apple title',
    }
    dialog = MetadataEditorDialog(_track(tmp_path, field_source_values={'title': values}))
    try:
        dialog.resize(1420, 920)
        dialog.show()
        app.processEvents()
        expected = ('#5ca3ff', '#43d17d', '#b36cff', '#ff6670')
        for row, color in enumerate(expected):
            assert dialog.source_table.item(row, 0).foreground().color() == QColor(color)
            cell = dialog.source_table.cellWidget(row, 5)
            button = cell.findChild(QPushButton, 'UseSourceDataButton')
            assert button.geometry().left() >= 6
            assert button.geometry().right() <= cell.width() - 6
        assert not dialog.source_legend_button.icon().isNull()
        assert dialog.source_legend_button.text() == ''
    finally:
        _close(dialog)
        app.setStyleSheet(previous_style)


def test_long_track_names_elide_but_keep_full_tooltips(tmp_path: Path):
    app = _app()
    track = _track(tmp_path)
    dialog = MetadataEditorDialog(track)
    player = PlayerBar()
    compact = CompactPlayerBar(player, track)
    try:
        dialog.track_header_title.setFixedWidth(150)
        compact.track_title.setFixedWidth(130)
        dialog.show()
        compact.show()
        app.processEvents()
        assert dialog.track_header_title.displayedText().endswith('…')
        assert compact.track_title.text().endswith('…')
        assert dialog.track_header_title.toolTip() == track.path.name
        assert compact.track_title.toolTip() == track.title
    finally:
        _close(dialog)
        compact.close()
        player.close()


def test_online_lock_and_editor_actions_use_real_thin_icons(tmp_path: Path):
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        assert '🔒' not in dialog.online_lock.text()
        assert '🔓' not in dialog.online_lock.text()
        assert not dialog.online_lock.icon().isNull()
        for button in (
            dialog.scan_online_button,
            dialog.restore_pre_online_button,
            dialog.undo_button,
            dialog.status_button,
            dialog.save_button,
        ):
            assert not button.icon().isNull()
            assert button.property('iconStyle') == 'thin'
    finally:
        _close(dialog)


def test_warning_marker_belongs_to_value_shell_before_source_badge(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path, year=None))
    try:
        dialog.show()
        app.processEvents()
        marker = dialog._field_status_icons['year']
        shell = dialog._field_value_shells['year']
        badge = dialog._source_buttons['year']
        assert marker.parentWidget() is shell
        assert marker.geometry().right() <= shell.width()
        assert shell.mapTo(dialog, shell.rect().topRight()).x() < badge.mapTo(dialog, badge.rect().topLeft()).x()
        assert not marker.isHidden()
        dialog.year.setText('2009')
        assert marker.isHidden()
    finally:
        _close(dialog)


def test_selected_cover_proposal_has_small_check_badge(tmp_path: Path):
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        pixmap = QPixmap(40, 40)
        pixmap.fill(QColor('#345678'))
        dialog._cover_candidate_pixmaps['source'] = pixmap
        dialog._rebuild_cover_proposals()
        dialog._select_cover_choice('source', record_undo=False)
        card = dialog._cover_proposal_labels['source'].parentWidget()
        badge = card.findChild(QLabel, 'CoverProposalSelectedBadge')
        assert card.property('selected') is True
        assert badge is not None
        assert not badge.isHidden()
        assert badge.text() == ''
        assert badge.pixmap() is not None and not badge.pixmap().isNull()
    finally:
        _close(dialog)
