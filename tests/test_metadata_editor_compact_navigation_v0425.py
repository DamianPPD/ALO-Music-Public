import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QSettings, QTimer, Qt
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QToolButton, QWidget

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme
from audio_library_organizer.ui.v0411_theme import style_for_v0411


@pytest.fixture
def app():
    application = QApplication.instance() or QApplication([])
    previous = application.styleSheet()
    application.setStyleSheet(style_for_theme('dark'))
    try:
        yield application
    finally:
        application.setStyleSheet(previous)


def _track(tmp_path, name='first'):
    return TrackRecord(path=tmp_path / f'{name}.mp3', artist='Artist', title=name,
                       year='2008', genre='Trance', bpm=128, duration_seconds=200,
                       bitrate_kbps=320, field_sources={'artist': 'Tag'})


def _close(editor):
    editor._force_closing = True
    editor.close()
    editor.deleteLater()


def _settle(app):
    for _ in range(3):
        app.processEvents()


@pytest.fixture
def editor(app, tmp_path):
    dialog = MetadataEditorDialog(_track(tmp_path))
    dialog.resize(1540, 1000)
    dialog.show()
    _settle(app)
    try:
        yield dialog
    finally:
        _close(dialog)


class _WindowPaletteObserver(QObject):
    def __init__(self):
        super().__init__()
        self.colors = []

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.WinIdChange and watched.internalWinId():
            self.colors.append(watched.palette().color(QPalette.ColorRole.Window).name())
        return False


@pytest.mark.parametrize('language', ['pl', 'en'])
@pytest.mark.parametrize('complete_theme', [False, True])
def test_navigation_replacement_is_dark_before_native_window_creation(app, tmp_path, language, complete_theme):
    if complete_theme:
        app.setStyleSheet(style_for_theme('dark') + style_for_v0411('dark'))
    observer = _WindowPaletteObserver()
    requested = []
    for index, name in enumerate(('first', 'second', 'first')):
        editor = MetadataEditorDialog(_track(tmp_path, name), navigation_index=index % 2,
                                      navigation_total=2)
        editor.installEventFilter(observer)
        editor.navigation_requested.connect(requested.append)
        apply_static_language(editor, language)
        try:
            editor.show()
            app.processEvents()
            assert editor.grab().toImage().pixelColor(1, 1).value() < 60
            button = editor.next_file_button if index % 2 == 0 else editor.previous_file_button
            button.click()
            assert not editor.isVisible()
        finally:
            _close(editor)
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert requested == [1, -1, 1]
    assert len(observer.colors) == 3
    assert all(int(color[1:3], 16) < 60 and int(color[3:5], 16) < 60
               and int(color[5:7], 16) < 60 for color in observer.colors), observer.colors


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_main_window_previous_next_keeps_order_geometry_and_dark_native_palette(app, tmp_path, monkeypatch, language):
    from audio_library_organizer.domain.preferences import AppPreferences
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui import main_window

    observer = _WindowPaletteObserver()
    visits = []
    geometries = []
    counters = []

    class DrivenEditor(MetadataEditorDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.installEventFilter(observer)
            # Drive the real modal event loop with test clicks; no production delay.
            QTimer.singleShot(0, self._test_click)

        def _test_click(self):
            visits.append(self.track.path)
            geometries.append(self.geometry())
            counters.append(self.file_counter.text())
            if len(visits) == 1:
                self.next_file_button.click()
            elif len(visits) == 2:
                self.previous_file_button.click()
            else:
                self._force_closing = True
                self.accept()

    monkeypatch.setattr(main_window, 'MetadataEditorDialog', DrivenEditor)
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat)
    AppPreferences(language=language).save(store)
    window = main_window.MainWindow(AppSettings((), LibraryPaths(tmp_path / 'library')), store)
    first, second = _track(tmp_path, 'Alpha'), _track(tmp_path, 'Beta')
    window.library.set_tracks([first, second])
    timed_out = []
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    def stop_stalled_navigation():
        timed_out.append(True)
        active = window._active_metadata_editor
        if active is not None:
            active.navigation_delta = 0
            active._force_closing = True
            active.accept()

    watchdog.timeout.connect(stop_stalled_navigation)
    try:
        watchdog.start(5000)
        window._open_metadata_editor(first)
        assert not timed_out, 'Previous/next modal navigation did not finish within 5 seconds'
        assert visits == [first.path, second.path, first.path]
        assert geometries[0] == geometries[1] == geometries[2]
        assert counters == (['Plik 1 z 2', 'Plik 2 z 2', 'Plik 1 z 2'] if language == 'pl'
                            else ['File 1 of 2', 'File 2 of 2', 'File 1 of 2'])
        assert len(observer.colors) == 3 and '#efefef' not in observer.colors
        assert all(max(int(color[start:start + 2], 16) for start in (1, 3, 5)) < 60
                   for color in observer.colors)
        assert window._active_metadata_editor is None
        assert [track.path for track in window.library.visible_tracks()] == [first.path, second.path]
    finally:
        watchdog.stop()
        window.close()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_recognition_disclosure_hides_only_its_body_and_preserves_data(editor, app, language):
    apply_static_language(editor, language)
    toggle = editor.findChild(QToolButton, 'EditorRecognitionToggle')
    body = editor.findChild(QWidget, 'EditorRecognitionDetails')
    assert toggle is not None and body is not None
    assert not toggle.isChecked() and body.isHidden()
    collapsed_height = editor.recognition_card.height()
    assert collapsed_height <= 52
    before = {key: value.text() for key, value in editor.recognition_values.items()}
    before_state = editor._capture_editor_state()
    closed_icon = toggle.icon().pixmap(16, 16).toImage()
    toggle.click()
    _settle(app)
    assert body.isVisible() and toggle.isChecked()
    assert editor.recognition_card.height() > collapsed_height + 50
    assert all(value.isVisible() for value in editor.recognition_values.values())
    assert toggle.icon().pixmap(16, 16).toImage() != closed_icon
    assert toggle.toolTip() == ('Zwiń szczegóły' if language == 'pl' else 'Collapse details')
    toggle.click()
    _settle(app)
    assert body.isHidden() and editor.recognition_card.height() == collapsed_height
    assert toggle.icon().pixmap(16, 16).toImage() == closed_icon
    assert toggle.toolTip() == ('Rozwiń szczegóły' if language == 'pl' else 'Expand details')
    assert {key: value.text() for key, value in editor.recognition_values.items()} == before
    assert editor._capture_editor_state() == before_state


def test_source_legend_control_is_on_the_right_and_chevron_tracks_menu(editor, app):
    title = next(label for label in editor.findChildren(QLabel, 'EditorSectionTitle')
                 if label.text().startswith('Porównanie źródeł'))
    mark = title.parentWidget().findChild(QLabel, 'LibrarySectionMark')
    button = editor.source_legend_button
    assert mark is not None
    assert mark.mapTo(editor, QPoint()).x() < title.mapTo(editor, QPoint()).x()
    assert button.mapTo(editor, QPoint()).x() > title.mapTo(editor, title.rect().topRight()).x()
    assert button.width() >= 40  # room for the existing legend glyph and a separate chevron
    assert button.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup
    assert len(button.menu().actions()) == 9
    closed = button.icon().pixmap(button.iconSize()).toImage()
    menu = button.menu()
    try:
        menu.popup(button.mapToGlobal(QPoint(0, button.height())))
        _settle(app)
        assert menu.isVisible() and button.property('expanded') is True
        assert button.icon().pixmap(button.iconSize()).toImage() != closed
        assert editor.source_table.isVisible()
    finally:
        menu.close()
        _settle(app)
    assert button.property('expanded') is False
    assert button.icon().pixmap(button.iconSize()).toImage() == closed


@pytest.mark.parametrize('language', ['pl', 'en'])
@pytest.mark.parametrize('size', [(1540, 1000), (1420, 900), (1180, 760)])
def test_compact_info_layout_does_not_stretch_comment(editor, app, language, size):
    apply_static_language(editor, language)
    editor.resize(*size)
    _settle(app)
    assert 60 <= editor.comment.height() <= 82
    shell = editor._field_value_shells['comment']
    top = editor.comment.mapTo(shell, QPoint()).y()
    assert top <= 5 and shell.height() - top - editor.comment.height() <= 5
    assert editor.cover_info.height() <= 96
    assert editor.cover_info.height() <= editor.cover_info.sizeHint().height() + 2
    assert set(editor.cover_info_values) == {'source', 'resolution', 'type', 'format', 'size'}
    for value in editor.cover_info_values.values():
        assert value.geometry().height() >= value.fontMetrics().height()
    assert editor.metadata_card.mapTo(editor, QPoint()).y() == editor.cover_gallery.mapTo(editor, QPoint()).y()
    gap = editor.recognition_card.mapTo(editor, QPoint()).y() - editor.cover_gallery.mapTo(editor, editor.cover_gallery.rect().bottomLeft()).y()
    assert 4 <= gap <= 12
    assert editor.save_button.isVisible() and editor.status_button.isVisible()


@pytest.mark.parametrize('candidate_count', [0, 1, 3, 5])
def test_cover_grid_shows_at_most_four_without_dropping_candidates(editor, app, candidate_count):
    pixmap = QPixmap(40, 40)
    pixmap.fill(QColor('#345678'))
    candidates = {f'external:Source {n}': f'https://example.test/{n}.jpg'
                  for n in range(candidate_count)}
    editor._cover_candidate_urls = candidates.copy()
    editor._cover_candidate_pixmaps.update({key: pixmap for key in candidates})
    editor._rebuild_cover_proposals()
    _settle(app)
    assert editor.cover_proposals_grid.count() == min(candidate_count + 1, 4)
    assert 'placeholder' in editor._cover_proposal_labels
    assert editor._cover_candidate_urls == candidates
    assert all(key in editor._cover_candidate_pixmaps for key in candidates)
    assert all(editor.cover_proposals_grid.getItemPosition(n)[:2] in ((0, 0), (0, 1), (1, 0), (1, 1))
               for n in range(editor.cover_proposals_grid.count()))
    if candidate_count:
        selected = f'external:Source {candidate_count - 1}'
        editor._select_cover_choice(selected, record_undo=False)
        _settle(app)
        assert selected in editor._cover_proposal_labels
        assert 'placeholder' in editor._cover_proposal_labels
        assert editor.cover_proposals_grid.count() <= 4
        markers = editor.cover_gallery.findChildren(QLabel, 'CoverProposalSelectedMarker')
        assert sum(not marker.isHidden() for marker in markers) == 1
        assert editor.cover_save_state()['cover_art_url'] == candidates[selected]
    assert editor._cover_candidate_urls == candidates
