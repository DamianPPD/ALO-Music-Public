import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.metadata_editor import EditorCloseGuardDialog, MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


MAIN_WINDOW_SOURCE = Path('src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')


def _app():
    return QApplication.instance() or QApplication([])


def _track(tmp_path: Path, **updates) -> TrackRecord:
    values = dict(
        path=tmp_path / 'BT feat. Jes - Every Other Way (Armin Van Buuren Remix).mp3',
        artist='BT feat. Jes',
        title='Every Other Way (Armin Van Buuren Remix)',
        year='2010',
        genre='Trance',
        bpm=132,
        duration_seconds=452,
        codec='MP3',
        status='review',
        field_sources={'artist': 'Tag', 'title': 'MusicBrainz', 'bpm': 'Analiza audio'},
        field_source_values={
            'artist': {'Tag': 'BT feat. Jes', 'Discogs': 'BT feat. JES'},
            'title': {'MusicBrainz': 'Every Other Way (Armin van Buuren Remix)'},
            'bpm': {'Analiza audio': 132},
        },
    )
    values.update(updates)
    return TrackRecord(**values)


def _close(dialog: MetadataEditorDialog) -> None:
    dialog._force_closing = True
    dialog.close()


def test_source_dropdown_colors_provider_name_but_keeps_value_neutral(tmp_path: Path):
    app = _app()
    previous_style = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        dialog.show()
        app.processEvents()
        menu = dialog._source_buttons['artist'].menu()
        rows = [action.defaultWidget() for action in menu.actions() if hasattr(action, 'defaultWidget')]
        rows = [row for row in rows if row is not None]
        assert len(rows) == 2

        tag_name = rows[0].findChild(QLabel, 'SourceMenuProvider')
        tag_value = rows[0].findChild(QLabel, 'SourceMenuValue')
        assert tag_name.text() == 'TAG'
        assert tag_name.display_color() == '#5ca3ff'
        assert tag_value.display_color() == '#c8d3da'
        assert dialog._source_buttons['artist'].property('sourceColor') == '#5ca3ff'

        menu.actions()[1].trigger()
        assert dialog._current_sources['artist'] == 'Discogs'
        assert dialog.artist.text() == 'BT feat. JES'
    finally:
        _close(dialog)
        app.setStyleSheet(previous_style)


def test_recognition_main_source_uses_shared_provider_color(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        dialog.show()
        app.processEvents()
        source = dialog.recognition_values['source']
        assert source.text() == 'MusicBrainz'
        assert source.property('sourceColor') == '#b36cff'
        assert source.palette().color(QPalette.ColorRole.WindowText) == QColor('#b36cff')
    finally:
        _close(dialog)


def test_online_actions_have_clear_hierarchy_and_equal_height(tmp_path: Path):
    app = _app()
    previous_style = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        dialog.show()
        app.processEvents()
        assert dialog.scan_online_button.property('actionRole') == 'primary'
        assert dialog.restore_pre_online_button.property('actionRole') == 'secondary'
        assert dialog.online_lock.property('actionRole') == 'tool'
        assert dialog.online_lock.height() == dialog.scan_online_button.height()
        assert dialog.online_lock.height() == dialog.restore_pre_online_button.height()
        gap = dialog.scan_online_button.geometry().left() - dialog.track_header_format.geometry().right()
        assert gap >= 20
    finally:
        _close(dialog)
        app.setStyleSheet(previous_style)


def test_track_header_name_is_read_only_selectable_and_copies_fragment(tmp_path: Path):
    app = _app()
    track = _track(tmp_path)
    dialog = MetadataEditorDialog(track)
    try:
        title = dialog.track_header_title
        dialog.show()
        title.setFocus()
        app.processEvents()
        assert isinstance(title, QLineEdit)
        assert title.isReadOnly()
        assert title.text() == track.path.name
        title.setSelection(0, 2)
        title.copy()
        assert app.clipboard().text() == 'BT'
        assert title.toolTip() == track.path.name

        title.clearFocus()
        app.processEvents()
        assert not title.hasSelectedText()
        title.resize(90, title.height())
        assert title.displayedText().endswith('…')
    finally:
        _close(dialog)


def test_cover_panel_uses_larger_art_and_two_column_proposals(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        stale_cards = [
            dialog.cover_proposals_grid.itemAt(index).widget()
            for index in range(dialog.cover_proposals_grid.count())
        ]
        dialog._cover_candidate_urls = {
            f'external:Source {index}': f'https://example.test/{index}.jpg'
            for index in range(4)
        }
        for key in dialog._cover_candidate_urls:
            pixmap = QPixmap(100, 100)
            pixmap.fill(QColor('#345678'))
            dialog._cover_candidate_pixmaps[key] = pixmap
        dialog._rebuild_cover_proposals()
        dialog.show()
        app.processEvents()

        assert all(not card.isVisible() for card in stale_cards)
        assert dialog.cover_main_preview.width() >= 236
        assert min(label.width() for label in dialog._cover_proposal_labels.values()) >= 78
        columns = {
            dialog.cover_proposals_grid.getItemPosition(index)[1]
            for index in range(dialog.cover_proposals_grid.count())
        }
        assert columns == {0, 1}
        for index in range(dialog.cover_proposals_grid.count()):
            card = dialog.cover_proposals_grid.itemAt(index).widget()
            preview = card.findChild(QLabel, 'CoverProposalPreview')
            assert card.minimumWidth() >= preview.width() + 6
            assert card.minimumHeight() >= preview.height() + 6
        assert abs(dialog.choose_cover_button.geometry().bottom() - dialog.search_cover_button.geometry().bottom()) <= 1
    finally:
        _close(dialog)


def test_editor_header_has_pencil_and_file_navigation(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path), navigation_index=2, navigation_total=5)
    requested = []
    dialog.navigation_requested.connect(requested.append)
    try:
        dialog.show()
        app.processEvents()
        assert not dialog.editor_heading_icon.pixmap().isNull()
        assert dialog.file_counter.text() == 'Plik 3 z 5'
        assert dialog.previous_file_button.isEnabled()
        assert dialog.next_file_button.isEnabled()
        dialog.previous_file_button.click()
        assert requested == [-1]
    finally:
        _close(dialog)


def test_library_navigation_tracks_follow_visible_sorted_rows(tmp_path: Path):
    app = _app()
    page = LibraryPage()
    tracks = [
        _track(tmp_path, path=tmp_path / 'c.mp3', title='Charlie'),
        _track(tmp_path, path=tmp_path / 'a.mp3', title='Alpha'),
        _track(tmp_path, path=tmp_path / 'b.mp3', title='Beta'),
    ]
    try:
        page.set_tracks(tracks)
        page.table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
        app.processEvents()
        assert [track.title for track in page.visible_tracks()] == ['Alpha', 'Beta', 'Charlie']
        page.search.setText('beta')
        app.processEvents()
        assert [track.title for track in page.visible_tracks()] == ['Beta']
    finally:
        page.close()


def test_close_guard_lists_unsaved_review_and_critical_missing_items(tmp_path: Path):
    dialog = MetadataEditorDialog(_track(tmp_path, artist=None, title=None))
    try:
        dialog.artist.setText('Temporary artist')
        items = dialog.close_attention_items()
        assert ('amber', 'Niezapisane zmiany') in items
        assert ('amber', 'Status: DO SPRAWDZENIA') in items
        assert ('critical', 'Brak ważnych danych: tytuł / wersja') in items

        close_dialog = dialog.create_close_guard_dialog()
        buttons = {button.text(): button for button in close_dialog.findChildren(QPushButton)}
        assert {'Zapisz i zamknij', 'Wróć do edycji', 'Odrzuć zmiany'} <= set(buttons)
        assert buttons['Zapisz i zamknij'].objectName() == 'CloseSaveAction'
        assert buttons['Wróć do edycji'].objectName() == 'CloseReturnAction'
        assert buttons['Odrzuć zmiany'].objectName() == 'CloseDiscardAction'
        close_dialog.close()
    finally:
        _close(dialog)


def test_escape_and_window_close_share_the_same_guard(tmp_path: Path, monkeypatch):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    guard_calls = []

    def block_close():
        guard_calls.append('checked')
        return False

    monkeypatch.setattr(dialog, '_confirm_close', block_close)
    try:
        dialog.show()
        app.processEvents()

        dialog.reject()  # QDialog maps Esc to reject().
        assert dialog.isVisible()
        dialog.close()  # Window close button enters closeEvent().
        assert dialog.isVisible()
        assert guard_calls == ['checked', 'checked']
    finally:
        _close(dialog)


def test_editor_cannot_close_while_online_recognition_is_running(tmp_path: Path, monkeypatch):
    _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    shown_items = []

    def record_guard(guard):
        shown_items.extend(guard.items)
        return 0

    monkeypatch.setattr(EditorCloseGuardDialog, 'exec', record_guard)
    try:
        dialog.set_online_scan_busy(True)
        assert dialog._confirm_close() is False
        assert ('amber', 'Rozpoznawanie online nadal trwa. Poczekaj na zakończenie operacji.') in shown_items
    finally:
        dialog.set_online_scan_busy(False)
        _close(dialog)


def test_navigation_disposes_completed_editor_and_light_theme_styles_new_controls():
    editor_loop = MAIN_WINDOW_SOURCE.split('def _open_metadata_editor', 1)[1].split('def _copy_track_state', 1)[0]
    assert 'dialog.deleteLater()' in editor_loop

    light_style = style_for_theme('light')
    assert 'QDialog#EditorCloseGuardDialog' in light_style
    assert 'QPushButton#SingleTrackOnlineButton' in light_style
    assert 'QLabel#SourceMenuValue' in light_style
