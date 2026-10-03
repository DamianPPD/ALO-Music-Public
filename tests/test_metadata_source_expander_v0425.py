import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.icons import library_icon
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


@pytest.fixture
def editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    dialog = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3', artist='Artist',
                                            title='Title', year='2008', genre='House', bpm=128))
    dialog.resize(1540, 1000)
    dialog.show()
    app.processEvents()
    try:
        yield dialog
    finally:
        dialog._force_closing = True
        dialog.close()
        app.setStyleSheet(previous)


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_legend_opens_its_menu_and_only_right_chevron_collapses_table(editor, language):
    app = QApplication.instance()
    apply_static_language(editor, language)
    app.processEvents()
    legend, toggle = editor.source_legend_button, editor.source_comparison_toggle
    title = next(label for label in editor.findChildren(QLabel, 'EditorSectionTitle')
                 if label.text().startswith(('Porównanie źródeł', 'Source comparison')))
    assert title.parentWidget().layout().itemAt(0).widget().objectName() == 'LibrarySectionMark'
    assert 2 <= legend.mapTo(editor, QPoint()).x() - title.mapTo(editor, title.rect().topRight()).x() <= 14
    assert legend.width() <= 42 and legend.height() <= 22
    assert legend.mapTo(editor, legend.rect().bottomLeft()).y() < editor.source_table.mapTo(editor, QPoint()).y()
    arrow = legend.findChild(QLabel, 'SourceLegendChevron')
    assert arrow is not None and arrow.isVisible()
    assert not legend.icon().isNull() and legend.menu() is not None
    assert arrow.pixmap().toImage() == library_icon('expand', '#bdcbd3', 14).pixmap(14, 14).toImage()
    menu = legend.menu()
    table_geometry = editor.source_table.geometry()
    try:
        menu.popup(legend.mapToGlobal(QPoint(0, legend.height())))
        app.processEvents()
        assert menu.isVisible() and len(menu.actions()) == 9
        assert arrow.pixmap().toImage() == library_icon('collapse', '#bdcbd3', 14).pixmap(14, 14).toImage()
        assert toggle.isChecked() and editor.source_table.isVisible()
        assert editor.source_table.geometry() == table_geometry
    finally:
        menu.close()
        app.processEvents()
    assert arrow.pixmap().toImage() == library_icon('expand', '#bdcbd3', 14).pixmap(14, 14).toImage()
    assert toggle.icon().isNull() and toggle.menu() is None and toggle.text() == ''
    assert toggle.width() <= 26 and toggle.height() <= 24
    right_arrow = toggle.findChild(QLabel, 'SourceComparisonChevron')
    assert right_arrow is not None and right_arrow.isVisible()
    for expanded, asset in ((True, 'collapse'), (False, 'expand'), (True, 'collapse')):
        if toggle.isChecked() != expanded:
            toggle.click()
            app.processEvents()
        assert editor.source_table.isVisible() == expanded
        assert right_arrow.pixmap().toImage() == library_icon(asset, '#a8bdca', 14).pixmap(14, 14).toImage()
        assert toggle.rect().contains(right_arrow.geometry()) and toggle.icon().isNull()


def test_cover_file_action_refreshes_language_and_still_selects_local_image(editor, tmp_path, monkeypatch):
    app = QApplication.instance()
    for language, label in [('pl', 'Dodaj okładkę z pliku'), ('en', 'Add cover from file'),
                            ('pl', 'Dodaj okładkę z pliku'), ('en', 'Add cover from file')]:
        apply_static_language(editor, language)
        editor.refresh_audio_language()
        app.processEvents()
        assert editor.choose_cover_button.text() == label
        assert editor.search_cover_button.text() == ('Szukaj okładki online' if language == 'pl' else 'Search for cover art online')
    image = QPixmap(80, 80)
    image.fill(QColor('#456789'))
    path = tmp_path / 'local-cover.png'
    assert image.save(str(path))
    calls = []

    def select_file(parent, caption, directory, file_filter):
        calls.append((parent, caption, file_filter))
        return str(path), 'Images (*.png)'

    monkeypatch.setattr(QFileDialog, 'getOpenFileName', select_file)
    editor.choose_cover_button.click()
    app.processEvents()
    assert calls and calls[0][0] is editor
    assert calls[0][1] == 'Choose cover' and '*.png' in calls[0][2]
    assert str(path) in editor._manual_cover_paths.values()
    assert editor._selected_cover_key in editor._manual_cover_paths


@pytest.mark.parametrize('scale', ['1', '1.25', '1.5', '1.75', '2'])
def test_header_and_long_cover_labels_fit_at_all_supported_dpi(scale):
    code = '''
from pathlib import Path
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QLabel
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme
app = QApplication([])
app.setStyleSheet(style_for_theme('dark'))
editor = MetadataEditorDialog(TrackRecord(path=Path('/tmp/layout.mp3')))
editor.show()
for language, text in (('pl', 'Dodaj okładkę z pliku'), ('en', 'Add cover from file')):
    apply_static_language(editor, language)
    for size in ((1540, 1000), (1420, 900), (1180, 760)):
        editor.resize(*size)
        app.processEvents()
        assert editor.choose_cover_button.text() == text
        buttons = (editor.choose_cover_button, editor.search_cover_button)
        assert abs(buttons[0].width() - buttons[1].width()) <= 1
        assert buttons[0].height() == buttons[1].height()
        assert buttons[0].mapTo(editor.cover_gallery, QPoint()).y() == buttons[1].mapTo(editor.cover_gallery, QPoint()).y()
        for button in buttons:
            assert button.width() >= button.fontMetrics().horizontalAdvance(button.text()) + button.iconSize().width() + 14
        assert editor.cover_main_preview.size().toTuple() == (288, 288)
        assert abs(editor.cover_gallery.height() - editor.metadata_card.height()) <= 1
        legend, toggle = editor.source_legend_button, editor.source_comparison_toggle
        assert legend.width() <= 42 and toggle.width() <= 26
        for button, name in ((legend, 'SourceLegendChevron'), (toggle, 'SourceComparisonChevron')):
            arrow = button.findChild(QLabel, name)
            assert arrow is not None and arrow.isVisible() and button.rect().contains(arrow.geometry())
            assert button.mapTo(editor, button.rect().bottomLeft()).y() < editor.source_table.mapTo(editor, QPoint()).y()
        assert toggle.icon().isNull()
editor._force_closing = True
editor.close()
'''
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR=scale,
                       PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', code], env=environment, capture_output=True,
                            text=True, timeout=25)
    assert result.returncode == 0, result.stderr


class _BackgroundObserver(QObject):
    def __init__(self, surfaces):
        super().__init__()
        self.surfaces = surfaces
        self.bright = []

    def eventFilter(self, widget, event):
        if widget in self.surfaces and event.type() in (QEvent.Type.Show, QEvent.Type.PaletteChange,
                                                        QEvent.Type.WinIdChange, QEvent.Type.Paint):
            color = widget.palette().color(widget.backgroundRole())
            if color.alpha() and min(color.red(), color.green(), color.blue()) > 180:
                self.bright.append((widget.objectName(), event.type().name, color.name()))
        return False


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_navigation_popup_comparison_and_reload_keep_dark_backing_surfaces(tmp_path, language):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    requests = []
    try:
        for index, delta in ((0, 1), (1, -1)):
            editor = MetadataEditorDialog(TrackRecord(path=tmp_path / f'{index}.mp3'),
                                          navigation_index=index, navigation_total=2)
            assert editor._native_first_paint_pending is True
            surfaces = (editor, editor.content_scroll, editor.content_scroll.viewport(),
                        editor.content_scroll.widget(), editor.recognition_details_popup,
                        editor.recognition_details_scroll.viewport(), editor.recognition_details_body)
            observer = _BackgroundObserver(surfaces)
            for surface in surfaces:
                surface.installEventFilter(observer)
                assert surface.palette().color(QPalette.ColorRole.Window).value() < 60
            editor.navigation_requested.connect(requests.append)
            apply_static_language(editor, language)
            editor.show()
            app.processEvents()
            assert editor._native_first_paint_pending is False
            for _ in range(3):
                editor.recognition_details_button.click()
                app.processEvents()
                editor.recognition_details_popup.hide()
                app.processEvents()
                editor.source_comparison_toggle.click()
                app.processEvents()
                editor.source_comparison_toggle.click()
                editor.apply_online_result(editor.track)
                app.processEvents()
                assert editor.grab().toImage().pixelColor(1, 1).name() == '#10141a'
            assert observer.bright == []
            button = editor.next_file_button if delta == 1 else editor.previous_file_button
            button.click()
            assert not editor.isVisible()
            editor._force_closing = True
            editor.close()
        assert requests == [1, -1]
    finally:
        app.setStyleSheet(previous)
