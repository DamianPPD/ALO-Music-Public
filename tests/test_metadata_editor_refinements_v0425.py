import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QToolButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.icons import editor_icon, library_icon
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


@pytest.fixture
def editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    track = TrackRecord(path=tmp_path / 'track.mp3', artist='Artist', title='Track (Mix)',
                        album='Album', year='2008', genre='Trance', bpm=128,
                        duration_seconds=200, bitrate_kbps=320, status='review',
                        field_sources={'artist': 'Tag', 'year': 'MusicBrainz'})
    dialog = MetadataEditorDialog(track)
    dialog.resize(1540, 1000)
    dialog.show()
    app.processEvents()
    try:
        yield dialog
    finally:
        dialog._force_closing = True
        dialog.close()
        app.setStyleSheet(previous)


def _box(widget, parent):
    return widget.geometry().translated(widget.parentWidget().mapTo(parent, QPoint()))


@pytest.mark.parametrize('language', ['pl', 'en'])
@pytest.mark.parametrize('width,height', [(1540, 1000), (1420, 900), (1180, 760)])
def test_recognition_popup_keeps_cover_workspace_compact_without_overlap(editor, language, width, height):
    apply_static_language(editor, language)
    editor.refresh_audio_language()
    editor.resize(width, height)
    QApplication.instance().processEvents()
    body = editor.content_scroll.widget()
    metadata, cover = (_box(w, body) for w in (
        editor.metadata_card, editor.cover_gallery))
    assert metadata.top() == cover.top()
    assert not body.isAncestorOf(editor.recognition_details_popup)
    assert editor.recognition_details_popup.isHidden()
    assert 4 <= cover.left() - metadata.right() <= 12
    assert 60 <= editor.comment.height() <= 82
    assert editor.cover_main_preview.size().toTuple() == (288, 288)
    assert editor.recognition_values['fields'].text() == '5/5'
    assert not editor.findChild(QFrame, 'MetadataStatusCompact')
    assert editor.save_button.isVisible() and editor.status_button.isVisible()


@pytest.mark.parametrize('field', ['artist', 'title', 'year', 'genre', 'bpm'])
def test_only_problematic_fields_have_visible_status_icons_and_recover(editor, field):
    widget = editor._field_widgets[field]
    marker = editor._field_status_icons[field]
    initial = widget.text()
    assert marker.isHidden() and marker.pixmap().isNull()
    widget.setText('')
    editor._refresh_all()
    assert not marker.isHidden() and marker.property('statusKind') == 'critical'
    assert marker.pixmap().toImage() == library_icon('status_problem', '#f34d64', 20).pixmap(20, 20).toImage()
    line = getattr(widget, 'edit', widget)
    assert line.palette().color(QPalette.ColorRole.Base) == QColor('#29151b')
    widget.setText(initial)
    editor._refresh_all()
    assert marker.isHidden() and marker.pixmap().isNull()
    assert line.property('fieldProblem') is False


def test_regular_sections_reuse_the_two_line_library_header_style(editor):
    marks = editor.findChildren(QLabel, 'LibrarySectionMark')
    assert len(marks) == 5  # four layout sections and the recognition popup
    for mark in marks:
        assert mark.size().toTuple() == (20, 7)
        assert mark.pixmap().isNull()
        painted = mark.grab().toImage()
        center = painted.width() // 2
        assert painted.pixelColor(center, 0) == QColor('#91adbe')
        assert painted.pixelColor(center, painted.height() - 1) == QColor('#91adbe')
        assert painted.pixelColor(center, painted.height() // 2) != QColor('#91adbe')


def test_comment_input_fills_its_row_without_an_artificial_empty_gap(editor):
    shell = editor._field_value_shells['comment']
    top = editor.comment.mapTo(shell, QPoint()).y()
    assert top <= 5
    assert shell.height() - top - editor.comment.height() <= 5


def test_comparison_has_a_section_mark_inline_legend_and_right_chevron(editor):
    title = next(label for label in editor.findChildren(QLabel, 'EditorSectionTitle')
                 if label.text().startswith('Porównanie źródeł'))
    header = title.parentWidget()
    assert header.layout().itemAt(0).widget().objectName() == 'LibrarySectionMark'
    assert header.findChildren(QToolButton) == [editor.source_legend_button]
    legend_gap = editor.source_legend_button.mapTo(editor, QPoint()).x() - title.mapTo(editor, title.rect().topRight()).x()
    assert 2 <= legend_gap <= 14
    assert editor.source_comparison_toggle.mapTo(editor, QPoint()).x() > editor.source_legend_button.mapTo(editor, QPoint()).x() + 40
    assert not header.findChildren(QLabel, 'EditorSectionIcon')
    legend = editor.source_legend_button.icon().pixmap(QSize(18, 18), 3.0).toImage()
    assert legend == library_icon('legend', '#bdcbd3', 18).pixmap(QSize(18, 18), 3.0).toImage()
    assert len(editor.source_legend_button.menu().actions()) == 9


def test_comparison_legend_menu_does_not_paint_a_second_indicator(editor):
    app = QApplication.instance()
    button = editor.source_legend_button
    QTest.mouseMove(editor, QPoint(5, 5))
    app.processEvents()
    menu = button.menu()
    with_menu = button.grab().toImage()
    try:
        button.setMenu(None)
        app.processEvents()
        without_menu = button.grab().toImage()
    finally:
        button.setMenu(menu)
    assert button.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup
    assert button.menu() is menu
    assert with_menu == without_menu


def test_recognition_buttons_have_the_approved_globe_and_waveform_search_icons(editor):
    assert editor.scan_online_button.icon().pixmap(20, 20).toImage() == editor_icon('editor_online_recognize', '#74e9fc', 20).pixmap(20, 20).toImage()
    assert editor.audio_scan_button.icon().pixmap(20, 20).toImage() == editor_icon('audio_recognize', '#c1c7ff', 20).pixmap(20, 20).toImage()
    assert editor.audio_scan_button.x() - editor.scan_online_button.geometry().right() >= 13
    editor.set_online_scan_busy(True)
    assert not editor.scan_online_button.isEnabled()
    editor.set_online_scan_busy(False)
    assert editor.scan_online_button.icon().pixmap(20, 20).toImage() == editor_icon('editor_online_recognize', '#74e9fc', 20).pixmap(20, 20).toImage()


def _button_fill(button):
    return button.grab().toImage().pixelColor(5, button.height() // 2).name()


def test_recognition_button_states_remain_distinct_and_requests_obey_lock(editor):
    app = QApplication.instance()
    online = QSignalSpy(editor.online_scan_requested)
    audio = QSignalSpy(editor.audio_scan_requested)
    states = []
    for button in (editor.scan_online_button, editor.audio_scan_button):
        QTest.mouseMove(editor, QPoint(5, 5))
        app.processEvents()
        normal = _button_fill(button)
        QTest.mouseMove(button, button.rect().center())
        app.processEvents()
        hover = _button_fill(button)
        QTest.mousePress(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        pressed = _button_fill(button)
        QTest.mouseRelease(button, Qt.MouseButton.LeftButton)
        assert len({normal, hover, pressed}) == 3
        states.append((normal, hover, pressed))
    assert all(a != b for a, b in zip(*states))
    assert online.count() == audio.count() == 1
    editor.online_lock.click()
    assert not editor.scan_online_button.isEnabled() and not editor.audio_scan_button.isEnabled()
    QTest.mouseClick(editor.scan_online_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(editor.audio_scan_button, Qt.MouseButton.LeftButton)
    assert online.count() == audio.count() == 1


def test_only_selected_small_cover_has_a_dark_triangle_with_green_check(editor, tmp_path):
    source = QPixmap(40, 40)
    source.fill(QColor('#456789'))
    manual = QPixmap(40, 40)
    manual.fill(QColor('#856749'))
    path = tmp_path / 'manual.png'
    assert manual.save(str(path))
    editor._cover_candidate_pixmaps.update({'source': source, 'manual': manual})
    editor._manual_cover_paths['manual'] = str(path)
    editor._rebuild_cover_proposals()
    assert editor.cover_main_preview.findChild(QLabel, 'CoverSelectedBadge') is None
    for key in ('source', 'manual', 'placeholder'):
        editor._select_cover_choice(key, record_undo=False)
        QApplication.instance().processEvents()
        markers = editor.cover_gallery.findChildren(QLabel, 'CoverProposalSelectedMarker')
        selected = [marker for marker in markers if not marker.isHidden()]
        assert len(selected) == 1
        marker = selected[0]
        preview = editor._cover_proposal_labels[key]
        assert marker.parentWidget() is preview
        assert marker.geometry().top() == 0
        assert marker.geometry().right() == preview.width() - 1
        assert marker.width() <= 24 and marker.height() <= 24
        assert marker.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        painted = marker.pixmap().toImage()
        assert painted.pixelColor(0, painted.height() - 1).alpha() == 0
        assert painted.pixelColor(painted.width() - 2, 1).value() < 50
        assert any(painted.pixelColor(x, y).green() > 150 and painted.pixelColor(x, y).red() < 100
                   for x in range(painted.width()) for y in range(painted.height()))
        card = preview.parentWidget()
        edge = card.grab().toImage().pixelColor(card.width() // 2, 0)
        assert edge.green() <= edge.blue()  # no green frame around the selected tile
