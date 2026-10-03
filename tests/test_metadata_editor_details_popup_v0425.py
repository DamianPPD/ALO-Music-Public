import os
import json
import subprocess
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.icons import library_icon
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


@pytest.fixture
def app():
    application = QApplication.instance() or QApplication([])
    previous = application.styleSheet()
    application.setStyleSheet(style_for_theme('dark'))
    try:
        yield application
    finally:
        application.setStyleSheet(previous)


@pytest.fixture
def editor(app, tmp_path):
    track = TrackRecord(path=tmp_path / 'song.mp3', artist='Artist', title='Title',
                        year='2008', genre='Trance', bpm=128, duration_seconds=200,
                        bitrate_kbps=320, confidence=.91, field_sources={'title': 'Tag'})
    dialog = MetadataEditorDialog(track)
    dialog.resize(1540, 1000)
    dialog.show()
    app.processEvents()
    try:
        yield dialog
    finally:
        dialog._force_closing = True
        dialog.close()
        dialog.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _geometry(editor):
    body = editor.content_scroll.widget()
    return [(widget.mapTo(body, QPoint()).toTuple(), widget.size().toTuple())
            for widget in (editor.metadata_card, editor.cover_gallery,
                           editor.filename_override, editor.source_table)]


@pytest.mark.parametrize('language', ['pl', 'en'])
@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_recognition_popup_preserves_values_and_editor_geometry(editor, app, language, theme):
    app.setStyleSheet(style_for_theme(theme))
    apply_static_language(editor, language)
    editor.refresh_audio_language()
    for _ in range(3):
        app.processEvents()
    popup = editor.recognition_details_popup
    button = editor.recognition_details_button
    before = _geometry(editor)
    saved = editor._capture_editor_state()
    assert not popup.isVisible()
    assert button.text() == ('Szczegóły' if language == 'pl' else 'Details')
    assert button.toolTip() == ('Szczegóły rozpoznania' if language == 'pl' else 'Identification details')
    assert popup.isWindow() and popup.windowFlags() & Qt.WindowType.Popup
    assert not editor.content_scroll.widget().isAncestorOf(popup)
    assert button.mapTo(editor, QPoint()).y() < editor.cover_gallery.mapTo(editor, QPoint()).y()
    assert editor.recognition_result_status.isVisible()
    button.click()
    app.processEvents()
    assert popup.isVisible() and button.isChecked()
    assert _geometry(editor) == before
    assert popup.width() <= 560 and popup.height() < 250
    assert popup.grab().toImage().pixelColor(4, 4).value() < 60
    assert {key: value.text() for key, value in editor.recognition_values.items()} == {
        'source': 'TAG', 'fields': '5/5', 'duration': '03:20', 'bitrate': '320 kb/s',
        'audio_status': '—', 'audio_score': '—', 'audio_result': '—'}
    assert editor.recognition_confidence.text() == '91%'
    assert editor.recognition_bar.value() == 91
    assert all(value.isVisible() for value in editor.recognition_values.values())
    popup.hide()
    app.processEvents()
    assert not popup.isVisible() and not button.isChecked()
    assert _geometry(editor) == before
    assert editor._capture_editor_state() == saved


@pytest.mark.parametrize('close_action', ['escape', 'outside'])
def test_recognition_popup_closes_and_can_be_opened_again(editor, app, close_action):
    button = editor.recognition_details_button
    popup = editor.recognition_details_popup
    button.click()
    app.processEvents()
    assert popup.isVisible()
    if close_action == 'escape':
        QTest.keyClick(popup, Qt.Key.Key_Escape)
    else:
        QTest.mouseClick(editor.windowHandle(), Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    app.processEvents()
    assert not popup.isVisible() and not button.isChecked()
    button.click()
    app.processEvents()
    assert popup.isVisible()


def test_hidden_recognition_data_updates_and_long_audio_result_wraps(editor, app):
    popup = editor.recognition_details_popup
    editor.artist.clear()
    editor.track.audio_recognition = {'artist': 'Long recognized artist',
                                      'title': 'A title with remix and release information ' * 8,
                                      'score': .88}
    editor._refresh_recognition_info()
    assert editor.recognition_values['fields'].text() == '4/5'
    assert not popup.isVisible()
    editor.recognition_details_button.click()
    app.processEvents()
    assert editor.recognition_values['audio_status'].text() == 'Zatwierdzone'
    assert editor.recognition_values['audio_score'].text() == '88%'
    value = editor.recognition_values['audio_result']
    assert value.wordWrap()
    assert value.height() >= value.heightForWidth(value.width())
    assert popup.height() <= min(360, popup.screen().availableGeometry().height() - 32)
    scroll = editor.recognition_details_scroll
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    app.processEvents()
    confidence_bottom = editor.recognition_bar.mapTo(scroll.viewport(), editor.recognition_bar.rect().bottomLeft()).y()
    assert confidence_bottom < scroll.viewport().height()


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_open_popup_updates_long_values_without_clipping_and_scrolls(editor, app, language):
    apply_static_language(editor, language)
    editor.recognition_details_button.click()
    app.processEvents()
    before = _geometry(editor)
    editor.track.audio_recognition = {'artist': 'Artist', 'title': 'Long recognized title ' * 80, 'score': .88}
    editor._refresh_recognition_info()
    app.processEvents()
    value = editor.recognition_values['audio_result']
    assert value.height() >= value.heightForWidth(value.width())
    scroll = editor.recognition_details_scroll
    assert scroll.verticalScrollBar().isVisible() and scroll.verticalScrollBar().maximum() > 0
    assert _geometry(editor) == before
    assert editor.recognition_details_popup.height() <= 360
    editor.track.audio_recognition = None
    editor._refresh_recognition_info()
    app.processEvents()
    assert not scroll.verticalScrollBar().isVisible()
    assert editor.recognition_details_popup.height() < 250


@pytest.mark.parametrize('scale', ['1.25', '1.5', '2'])
@pytest.mark.parametrize('language', ['pl', 'en'])
def test_scaled_popup_keeps_dynamic_content_accessible_and_inside_screen(scale, language):
    code = '''
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme
app = QApplication([])
app.setStyleSheet(style_for_theme('dark'))
editor = MetadataEditorDialog(TrackRecord(path=Path('/tmp/scaled.mp3')))
apply_static_language(editor, LANG)
editor.show()
app.processEvents()
editor.recognition_details_button.click()
app.processEvents()
popup, scroll = editor.recognition_details_popup, editor.recognition_details_scroll
first_height = None
for count in (1, 8, 80, 1, 0):
    editor.track.audio_recognition = ({'artist': 'Artist', 'title': 'Recognized title with remix ' * count, 'score': .88} if count else None)
    editor._refresh_recognition_info()
    app.processEvents()
    assert popup.screen().availableGeometry().contains(popup.frameGeometry())
    assert scroll.horizontalScrollBar().maximum() == 0
    for value in editor.recognition_values.values():
        assert value.height() >= value.heightForWidth(value.width())
        assert value.mapTo(scroll.viewport(), QPoint()).x() >= 0
        assert value.mapTo(scroll.viewport(), value.rect().topRight()).x() < scroll.viewport().width()
    if count == 80:
        assert scroll.verticalScrollBar().maximum() > 0
    if count == 0:
        assert scroll.verticalScrollBar().maximum() == 0
    if count == 1:
        if first_height is None:
            first_height = popup.height()
        else:
            assert popup.height() == first_height
editor._force_closing = True
editor.close()
'''.replace('LANG', repr(language))
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR=scale,
                       PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', code], env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_hiding_editor_also_closes_details_popup(editor, app):
    editor.recognition_details_button.click()
    app.processEvents()
    editor.hide()
    app.processEvents()
    assert not editor.recognition_details_popup.isVisible()
    assert not editor.recognition_details_button.isChecked()


@pytest.mark.parametrize('language', ['pl', 'en'])
@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_real_cover_metrics_remain_readable_in_compact_panel(editor, app, language, theme):
    app.setStyleSheet(style_for_theme(theme))
    apply_static_language(editor, language)
    pixmap = QPixmap(1200, 1200)
    pixmap.fill(QColor('#345678'))
    editor._cover_candidate_pixmaps['source'] = pixmap
    editor._cover_details['source'] = {'type': 'Okładka główna (Front)', 'format': 'JPEG', 'bytes': 403200}
    editor._selected_cover_key = 'source'
    editor._refresh_cover_information()
    for _ in range(3):
        app.processEvents()
    assert editor.cover_info.height() <= (72 if theme == 'dark' else 80)
    for value in editor.cover_info_values.values():
        if value.wordWrap():
            assert value.height() >= value.heightForWidth(value.width())
        else:
            assert value.fontMetrics().horizontalAdvance(value.text()) <= value.width()
    assert editor.cover_info.minimumSizeHint().width() <= editor.cover_info.width()


@pytest.mark.parametrize('language', ['pl', 'en'])
@pytest.mark.parametrize('size', [(1540, 1000), (1420, 900), (1180, 760)])
def test_enlarged_cover_and_compact_metrics_leave_no_large_workspace_gap(editor, app, language, size):
    apply_static_language(editor, language)
    editor.resize(*size)
    app.processEvents()
    cover = editor.cover_main_preview
    assert 280 <= cover.width() <= 320 and cover.width() == cover.height()
    assert editor.cover_info.width() == cover.width()
    assert editor.cover_info.height() <= 72
    assert editor.cover_info.height() <= editor.cover_info.sizeHint().height() + 2
    assert set(editor.cover_info_values) == {'source', 'resolution', 'type', 'format', 'size'}
    for value in editor.cover_info_values.values():
        assert value.height() >= value.fontMetrics().height()
    body = editor.content_scroll.widget()
    metadata_bottom = editor.metadata_card.mapTo(body, editor.metadata_card.rect().bottomLeft()).y()
    cover_bottom = editor.cover_gallery.mapTo(body, editor.cover_gallery.rect().bottomLeft()).y()
    assert abs(metadata_bottom - cover_bottom) <= 40
    assert 60 <= editor.comment.height() <= 82
    assert cover.findChild(QLabel, 'CoverSelectedBadge') is None
    pixmap = QPixmap(60, 100)
    pixmap.fill(QColor('#345678'))
    editor._cover_candidate_pixmaps['source'] = pixmap
    editor._selected_cover_key = 'source'
    editor._update_cover_main_preview()
    rendered = cover.pixmap()
    assert abs(rendered.width() / rendered.height() - .6) < .02


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_source_header_has_small_legend_after_title_and_independent_chevron(editor, app, language):
    apply_static_language(editor, language)
    app.processEvents()
    title = next(label for label in editor.findChildren(QLabel, 'EditorSectionTitle')
                 if label.text().startswith(('Porównanie źródeł', 'Source comparison')))
    legend = editor.source_legend_button
    toggle = editor.source_comparison_toggle
    title_right = title.mapTo(editor, title.rect().topRight()).x()
    legend_left = legend.mapTo(editor, QPoint()).x()
    assert 2 <= legend_left - title_right <= 14
    assert legend.iconSize().toTuple() == (18, 18)
    assert legend.width() <= 26 and legend.height() <= 24
    assert legend.icon().pixmap(QSize(18, 18), 3.0).toImage() == library_icon('legend', '#bdcbd3', 18).pixmap(QSize(18, 18), 3.0).toImage()
    assert toggle.mapTo(editor, QPoint()).x() > legend.mapTo(editor, legend.rect().topRight()).x() + 40
    assert toggle.menu() is None and toggle.text() == ''
    assert toggle.isChecked() and editor.source_table.isVisible()
    open_icon = toggle.icon().pixmap(16, 16).toImage()
    rows = editor.source_table.rowCount()
    toggle.click()
    app.processEvents()
    assert not toggle.isChecked() and editor.source_table.isHidden()
    assert toggle.icon().pixmap(16, 16).toImage() != open_icon
    assert editor.source_table.rowCount() == rows
    toggle.click()
    app.processEvents()
    assert editor.source_table.isVisible() and toggle.isChecked()
    assert toggle.icon().pixmap(16, 16).toImage() == open_icon
    menu = legend.menu()
    try:
        menu.popup(legend.mapToGlobal(QPoint(0, legend.height())))
        app.processEvents()
        assert menu.isVisible() and len(menu.actions()) == 9
        assert toggle.isChecked() and editor.source_table.isVisible()
    finally:
        menu.hide()


class _SurfacePaletteObserver(QObject):
    def __init__(self, widgets):
        super().__init__()
        self.widgets = widgets
        self.bright = []

    def eventFilter(self, watched, event):
        if watched in self.widgets and event.type() in (QEvent.Type.PaletteChange, QEvent.Type.Show, QEvent.Type.WinIdChange):
            color = watched.palette().color(watched.backgroundRole())
            if color.alpha() and min(color.red(), color.green(), color.blue()) > 180:
                self.bright.append((watched.objectName(), event.type().name, color.name()))
        return False


def test_editor_surfaces_remain_dark_during_unpolish_repolish(editor, app):
    surfaces = (editor, editor.content_scroll, editor.content_scroll.viewport(),
                editor.content_scroll.widget())
    observer = _SurfacePaletteObserver(surfaces)
    for surface in surfaces:
        surface.installEventFilter(observer)
    for _ in range(3):
        app.setStyleSheet(style_for_theme('dark'))
        app.processEvents()
        assert editor.grab().toImage().pixelColor(1, 1).name() == '#10141a'
    assert observer.bright == []


def test_panel_updates_popup_cycles_and_cover_rebuild_keep_surfaces_dark(editor, app):
    surfaces = (editor, editor.content_scroll, editor.content_scroll.viewport(),
                editor.content_scroll.widget(), editor.recognition_details_popup)
    observer = _SurfacePaletteObserver(surfaces)
    for surface in surfaces:
        surface.installEventFilter(observer)
    candidates = {f'external:{n}': f'https://example.test/{n}.jpg' for n in range(5)}
    editor._cover_candidate_urls = candidates.copy()
    pixmap = QPixmap(60, 60)
    pixmap.fill(QColor('#345678'))
    editor._cover_candidate_pixmaps.update({key: pixmap for key in candidates})
    for _ in range(20):
        editor.start_audio_lookup()
        editor.show_audio_candidates([])
        editor.audio_panel.hide()
        editor._rebuild_cover_proposals()
        editor.artist.setText('Changed')
        editor.artist.setText('Artist')
        app.processEvents()
        before = _geometry(editor)
        editor.recognition_details_button.click()
        app.processEvents()
        assert _geometry(editor) == before
        editor.recognition_details_popup.hide()
        app.processEvents()
        assert _geometry(editor) == before
        assert editor.cover_proposals_grid.count() == 4
        assert editor._cover_candidate_urls == candidates
    assert observer.bright == []


def test_editor_surface_diagnostics_identifies_widgets_and_popup_lifecycle(tmp_path):
    log = tmp_path / 'alo_crash_debug.log'
    code = '''
from pathlib import Path
from PySide6.QtWidgets import QApplication
from audio_library_organizer import crash_debug
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme
crash_debug.initialize()
app = QApplication([])
app.setStyleSheet(style_for_theme('dark'))
editor = MetadataEditorDialog(TrackRecord(path=Path('/tmp/trace.mp3')), navigation_total=2)
editor.show()
app.processEvents()
editor.recognition_details_button.click()
app.processEvents()
editor.recognition_details_popup.hide()
editor.show_audio_candidates([])
app.processEvents()
app.setStyleSheet(style_for_theme('dark'))
app.processEvents()
editor.next_file_button.click()
app.processEvents()
'''
    environment = dict(os.environ, ALO_CRASH_DEBUG='1', ALO_CRASH_DEBUG_LOG=str(log),
                       PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', code], env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
    surfaces = [row for row in events if row['event'] == 'editor.surface']
    assert {'dialog', 'scroll', 'viewport', 'content', 'recognition-popup'} <= {row['surface'] for row in surfaces}
    popup = [row for row in surfaces if row['surface'] == 'recognition-popup']
    assert {'Show', 'Hide', 'Paint'} <= {row['stage'] for row in popup}
    assert all(row['background'] not in ('#ffffff', '#efefef') for row in surfaces)
    assert all(row['object_name'] and 'styled_background' in row and 'native_window' in row for row in surfaces)
    assert any(row['event'] == 'editor.navigation.request' and row['delta'] == 1 for row in events)
