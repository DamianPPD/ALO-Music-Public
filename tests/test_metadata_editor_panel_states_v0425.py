import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMessageBox

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
    track = TrackRecord(path=tmp_path / 'track.mp3', artist='Artist', title='Track (Mix)',
                        album='Album', year='2008', genre='Trance', bpm=128,
                        status='review', duration_seconds=200, bitrate_kbps=320,
                        field_sources={'artist': 'Tag', 'year': 'MusicBrainz', 'bpm': 'Analiza audio'})
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


@pytest.mark.parametrize('width,height', [(1540, 1000), (1180, 760)])
def test_removed_status_panel_leaves_metadata_and_recognition_beside_cover(editor, width, height):
    editor.resize(width, height)
    QApplication.instance().processEvents()
    assert not editor.findChild(QFrame, 'MetadataStatusCompact')
    assert 'Status pliku' not in [label.text() for label in editor.findChildren(QLabel)]
    body = editor.content_scroll.widget()
    metadata, recognition, cover = (_box(widget, body) for widget in (
        editor.metadata_card, editor.recognition_card, editor.cover_gallery))
    assert metadata.top() == cover.top()
    assert metadata.right() == recognition.right()
    assert metadata.left() == recognition.left()
    assert 4 <= recognition.top() - metadata.bottom() <= 12
    assert recognition.bottom() == cover.bottom()
    assert 4 <= cover.left() - metadata.right() <= 12
    assert editor.cover_main_preview.size().toTuple() == (248, 248)
    assert editor.recognition_values['fields'].text() == '5/5'
    assert editor.filename_override.text()
    assert editor.recognition_bar.height() == 6


def test_source_comparison_heading_reuses_actual_library_legend_asset(editor):
    title = next(label for label in editor.findChildren(QLabel, 'EditorSectionTitle')
                 if label.text().startswith('Porównanie źródeł'))
    icon = title.parentWidget().findChild(QLabel, 'EditorSectionIcon')
    assert icon is not None
    assert icon.pixmap().toImage() == library_icon('legend', '#bdcbd3', 18).pixmap(18, 18).toImage()
    header_icons = editor.findChildren(QLabel, 'EditorSectionIcon')
    assert len(header_icons) == 4
    assert all(icon.pixmap().size().toTuple() == (18, 18) for icon in header_icons)


@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_section_titles_have_readable_contrast_on_actual_panel_backgrounds(editor, theme):
    QApplication.instance().setStyleSheet(style_for_theme(theme))
    QApplication.instance().processEvents()

    def luminance(color):
        channels = [value / 255 for value in (color.red(), color.green(), color.blue())]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                  for value in channels]
        return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    for title in editor.findChildren(QLabel, 'EditorSectionTitle'):
        header = title.parentWidget()
        editor.content_scroll.ensureWidgetVisible(header, 0, 0)
        QApplication.instance().processEvents()
        # Compose transparent headers with their real panel background.
        panel = header.parentWidget()
        sample = panel.mapTo(editor, QPoint(panel.width() - 16, 16))
        ratio = editor.devicePixelRatioF()
        rendered = editor.grab().toImage()
        background = rendered.pixelColor(round(sample.x() * ratio), round(sample.y() * ratio))
        foreground = title.palette().color(QPalette.ColorRole.WindowText)
        levels = sorted((luminance(foreground), luminance(background)))
        assert (levels[1] + 0.05) / (levels[0] + 0.05) >= 4.5, (theme, title.text())


@pytest.mark.parametrize('field', ['artist', 'title', 'year', 'genre', 'bpm'])
def test_required_missing_fields_are_red_with_approved_problem_circle_and_recover(editor, field):
    widget = editor._field_widgets[field]
    initial = widget.text()
    widget.setText('')
    editor._refresh_all()
    QApplication.instance().processEvents()
    marker = editor._field_status_icons[field]
    assert marker.isVisible()
    assert marker.property('statusKind') == 'critical'
    assert marker.pixmap().toImage() == library_icon('status_problem', '#f34d64', 20).pixmap(20, 20).toImage()
    line = getattr(widget, 'edit', widget)
    assert line.palette().color(QPalette.ColorRole.Base) == QColor('#29151b')
    image = line.grab().toImage()
    ratio = line.devicePixelRatioF()
    edge = image.pixelColor(round(line.width() / 2 * ratio), round((line.height() - 1) * ratio))
    assert edge.red() > 180 and edge.red() > edge.green() * 2 and edge.red() > edge.blue() * 1.5
    widget.setText(initial)
    editor._refresh_all()
    assert marker.property('statusKind') == 'ok' and marker.isVisible()
    assert marker.pixmap().toImage() == library_icon('status_ready', '#35d893', 20).pixmap(20, 20).toImage()
    assert line.property('missingRequired') is False
    assert line.palette().color(QPalette.ColorRole.Base) != QColor('#29151b')


def test_partial_year_is_visually_red_but_existing_save_validation_and_recovery_remain(editor, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[2]))
    saved = QSignalSpy(editor.save_requested)
    editor.year.setText('20')
    assert editor._field_status_icons['year'].property('statusKind') == 'critical'
    assert editor._request_save() is False and saved.count() == 0
    assert warnings == ['Rok musi składać się dokładnie z 4 cyfr, np. 2009.']
    editor.year.setText('2009')
    assert editor._field_status_icons['year'].property('statusKind') == 'ok'
    assert editor._request_save() is True and saved.count() == 1
    assert editor.values()['year'] == '2009'


def test_invalid_bpm_has_problem_icon_without_changing_existing_value_fallback(editor):
    editor.bpm.setText('invalid')
    marker = editor._field_status_icons['bpm']
    assert marker.property('statusKind') == 'critical'
    assert editor.bpm.property('fieldProblem') is True
    assert editor.values()['bpm'] == editor.track.bpm
    editor.bpm.setText('130,5')
    assert marker.property('statusKind') == 'ok'
    assert editor.bpm.property('fieldProblem') is False
    assert editor.values()['bpm'] == 130.5


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_no_audio_candidates_have_problem_circle_and_neutral_message_without_changing_retry(editor, language):
    apply_static_language(editor, language)
    editor.show_audio_candidates([])
    editor.refresh_audio_language()
    QApplication.instance().processEvents()
    assert editor.audio_empty_status.isVisible()
    icon = editor.audio_empty_status.findChild(QLabel, 'AudioRecognitionEmptyIcon')
    assert icon is not None
    assert icon.pixmap().toImage() == library_icon('status_problem', '#f34d64', 20).pixmap(20, 20).toImage()
    assert editor.audio_empty_heading.palette().color(QPalette.ColorRole.WindowText) == QColor('#ff8792')
    assert editor.audio_empty_message.palette().color(QPalette.ColorRole.WindowText) == QColor('#d6dde3')
    assert editor.audio_empty_status.height() < 100
    assert not editor.audio_candidate_content.isVisible() and not editor.audio_summary.isVisible()
    requests = QSignalSpy(editor.audio_scan_requested)
    editor.audio_empty_retry.click()
    assert requests.count() == 1 and requests.at(0)[0] is editor
    editor.start_audio_lookup()
    assert not editor.audio_empty_status.isVisible()
