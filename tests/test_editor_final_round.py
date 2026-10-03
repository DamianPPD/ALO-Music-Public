import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QRect, QSettings
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


def test_metadata_and_cover_columns_align_at_top_without_stretching_comment(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        for width in (1180, 1540):
            dialog.resize(width, 920)
            dialog.show()
            app.processEvents()
            assert dialog.metadata_column.y() == dialog.cover_recognition_column.y()
            assert 60 <= dialog.comment.height() <= 82
            assert dialog.comment.mapTo(dialog.metadata_card, dialog.comment.rect().topLeft()).y() < dialog.metadata_card.height()
    finally:
        _close(dialog)


def test_source_table_fits_its_rows_and_grows_for_all_sources(tmp_path: Path):
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        initial_rows = dialog.source_table.rowCount()
        assert dialog.source_table.height() >= dialog.source_table.horizontalHeader().height() + initial_rows * 31
        assert dialog.source_table.height() <= dialog.source_table.horizontalHeader().height() + max(1, initial_rows) * 31 + 24

        sources = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', 'Nazwa pliku', 'Ręcznie', 'Testowe')
        dialog._source_values['title'] = {source: f'Tytuł {index}' for index, source in enumerate(sources)}
        dialog._refresh_source_comparison()
        assert dialog.source_table.rowCount() == 7
        assert dialog.source_table.height() >= dialog.source_table.horizontalHeader().height() + 7 * 31
        assert dialog.source_table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        dialog.show()
        _app().processEvents()
        assert not dialog.source_table.verticalScrollBar().isVisible()
        assert dialog.source_table.visualItemRect(dialog.source_table.item(6, 1)).bottom() <= dialog.source_table.viewport().height()
    finally:
        _close(dialog)


def test_audio_source_row_and_legend_use_the_same_a1_icon(tmp_path: Path):
    from audio_library_organizer.jobs.audio_identification import SOURCE
    from PySide6.QtWidgets import QWidgetAction

    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path, field_source_values={
        'title': {SOURCE: 'A Remix', 'Tag': 'A Remix'}, 'artist': {SOURCE: 'DJ', 'Tag': 'DJ'}
    }))
    try:
        dialog.show()
        app.processEvents()
        row = dialog._source_rows().index(SOURCE)
        source_item = dialog.source_table.item(row, 0)
        assert source_item.text() == 'ROZPOZNANIE AUDIO'
        assert not source_item.icon().isNull()
        assert dialog.source_table.cellWidget(row, 0) is None
        legend = [action.defaultWidget() for action in dialog.source_legend_button.menu().actions()
                  if isinstance(action, QWidgetAction) and action.defaultWidget()]
        audio_option = next(widget for widget in legend
                            if widget.findChild(QLabel, 'SourceMenuProvider').text() == 'ROZPOZNANIE AUDIO')
        assert audio_option.findChild(QLabel, 'SourceMenuDot').property('sourceKind') == 'audio_recognition'
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
            cell = dialog.source_table.cellWidget(row, 6)
            button = cell.findChild(QPushButton, 'UseSourceDataButton')
            assert button.geometry().left() >= 6
            assert button.geometry().right() <= cell.width() - 6
        assert not dialog.source_legend_button.icon().isNull()
        assert dialog.source_legend_button.text() == ''
    finally:
        _close(dialog)
        app.setStyleSheet(previous_style)


def test_source_comparison_reserves_readable_columns_and_scrolls_when_narrow(tmp_path: Path):
    from audio_library_organizer.jobs.audio_identification import SOURCE

    app = _app()
    previous_style = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    track = _track(tmp_path, field_source_values={
        'title': {'Tag': 'Stepping To The Beat (Dave Mcdonald Remix)',
                  SOURCE: 'Stepping To The Beat (Dave Mcdonald Remix)'},
        'artist': {'Tag': 'DJ Jose', SOURCE: 'DJ Jose'},
    })
    dialog = MetadataEditorDialog(track)
    try:
        dialog.resize(1180, 920)
        dialog.show()
        app.processEvents()
        table = dialog.source_table
        assert 190 <= table.columnWidth(0) < 220
        assert table.columnWidth(2) >= 250
        # The editor's vertical scrollbar can narrow the table viewport.
        # Keep readable columns and verify that actions remain fully reachable.
        if table.horizontalScrollBar().maximum() > 0:
            assert table.horizontalScrollBar().isVisible()
            table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
            app.processEvents()
        for row in range(table.rowCount()):
            source_item = table.item(row, 0)
            assert table.cellWidget(row, 0) is None
            assert table.columnWidth(0) >= table.fontMetrics().horizontalAdvance(source_item.text()) + 25
            title = table.item(row, 2)
            assert table.columnWidth(2) >= table.fontMetrics().horizontalAdvance(title.text()) + 16
            action = table.cellWidget(row, 6)
            assert action.geometry().left() >= 0
            assert action.geometry().right() <= table.viewport().width()
            assert table.columnViewportPosition(6) >= table.columnViewportPosition(1) + table.columnWidth(1)
        table.setFixedWidth(750)
        app.processEvents()
        assert table.horizontalScrollBar().maximum() > 0
        assert table.horizontalScrollBar().isVisible()
    finally:
        _close(dialog)
        app.setStyleSheet(previous_style)


def test_source_comparison_refresh_removes_stale_first_column_button(tmp_path: Path):
    from audio_library_organizer.jobs.audio_identification import SOURCE

    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path, field_source_values={
        'title': {'Tag': 'Original mix', 'MusicBrainz': 'Other mix', SOURCE: 'Audio mix'},
    }))
    try:
        dialog.resize(1180, 920)
        dialog.show()
        app.processEvents()
        table = dialog.source_table
        assert table.item(0, 0).text() == 'TAG'
        table.setCellWidget(0, 0, QPushButton('Użyj danych'))
        assert table.cellWidget(0, 0) is not None  # This masks the real source item.
        dialog._refresh_source_comparison()
        app.processEvents()
        assert table.horizontalHeaderItem(0).text() == 'Źródło'
        assert table.horizontalHeaderItem(6).text() == 'Akcja'
        assert [table.item(row, 0).text() for row in range(table.rowCount())] == [
            'TAG', 'MusicBrainz', 'ROZPOZNANIE AUDIO'
        ]
        for row in range(table.rowCount()):
            assert table.cellWidget(row, 0) is None
            assert not table.item(row, 0).icon().isNull()
            assert table.cellWidget(row, 6).findChild(QPushButton).text() == 'Użyj danych'
            assert table.columnViewportPosition(6) > table.columnViewportPosition(0) + table.columnWidth(0)
    finally:
        _close(dialog)


def test_editor_initial_geometry_fits_work_area_and_is_resizable(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    app = _app()
    for area, expected in (
        (QRect(0, 0, 2000, 1200), (1600, 1060)),
        (QRect(40, 20, 1280, 800), (1248, 736)),
        (QRect(40, 20, 800, 600), (768, 536)),
    ):
        monkeypatch.setattr(MetadataEditorDialog, 'screen',
                            lambda self, area=area: SimpleNamespace(availableGeometry=lambda: area))
        dialog = MetadataEditorDialog(_track(tmp_path))
        try:
            assert (dialog.width(), dialog.height()) == expected
            dialog.show()
            app.processEvents()
            assert area.contains(dialog.frameGeometry())
            original = dialog.size()
            dialog.resize(original.width() - 40, original.height() - 40)
            app.processEvents()
            assert dialog.width() == original.width() - 40
            assert dialog.height() == original.height() - 40
        finally:
            _close(dialog)


def test_editor_size_does_not_change_main_window_default(tmp_path: Path):
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui.main_window import MainWindow

    app = _app()
    previous_style = app.styleSheet()
    window = MainWindow(AppSettings((), LibraryPaths(tmp_path / 'library')),
                        QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    try:
        before = window.size()
        dialog = MetadataEditorDialog(_track(tmp_path), window)
        try:
            assert window.size() == before
            dialog.resize(1200, 850)
            app.processEvents()
            assert window.size() == before
        finally:
            _close(dialog)
    finally:
        window.close()
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
        assert marker.property('statusKind') == 'ok'
    finally:
        _close(dialog)


def test_selected_cover_proposal_has_small_corner_marker(tmp_path: Path):
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        pixmap = QPixmap(40, 40)
        pixmap.fill(QColor('#345678'))
        dialog._cover_candidate_pixmaps['source'] = pixmap
        dialog._rebuild_cover_proposals()
        dialog._select_cover_choice('source', record_undo=False)
        card = dialog._cover_proposal_labels['source'].parentWidget()
        badge = card.findChild(QLabel, 'CoverProposalSelectedMarker')
        assert card.property('selected') is True
        assert badge is not None
        assert not badge.isHidden()
        assert badge.text() == ''
        assert badge.pixmap() is not None and not badge.pixmap().isNull()
    finally:
        _close(dialog)
