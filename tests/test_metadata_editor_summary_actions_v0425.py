import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QTextDocument
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import SOURCE as AUDIO_SOURCE
from audio_library_organizer.ui.i18n import apply_static_language, ui_text
from audio_library_organizer.ui.icons import library_icon
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


@pytest.fixture
def editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    dialog = MetadataEditorDialog(TrackRecord(
        path=tmp_path / 'summary.mp3', artist='Artist', title='Title', year='2008',
        genre='Trance', bpm=128, field_sources={'title': 'MusicBrainz'},
        audio_recognition={'artist': 'Artist', 'title': 'Title', 'score': .88}))
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
@pytest.mark.parametrize('source,display', [
    ('Tag', 'TAG'), ('Discogs', 'Discogs'), ('MusicBrainz', 'MusicBrainz'),
    ('Ręcznie', 'Ręcznie'), ('Apple / iTunes', 'Apple'),
    ('Analiza audio', 'Analiza audio'), (AUDIO_SOURCE, AUDIO_SOURCE),
])
def test_summary_has_one_primary_source_with_existing_source_color(editor, language, source, display):
    apply_static_language(editor, language)
    editor._current_sources['title'] = source
    editor.refresh_audio_language()
    QApplication.instance().processEvents()
    label = editor.recognition_result_status
    document = QTextDocument()
    document.setHtml(label.text())
    prefix, name = ui_text(editor, 'Główne źródło') + ': ', ui_text(editor, display)
    assert document.toPlainText() == prefix + name
    assert ui_text(editor, 'Źródło audio zatwierdzone') not in document.toPlainText()
    assert editor.audio_summary_heading.text() == ui_text(editor, 'Źródło audio zatwierdzone')
    assert editor.audio_summary.isVisible()
    colors = []
    fragment = document.begin().begin()
    while not fragment.atEnd():
        text = fragment.fragment()
        colors.append((text.text(), text.charFormat().foreground().color().name()))
        fragment += 1
    expected = editor.SOURCE_COLORS[source]
    assert (name, expected) in colors
    assert all(color != expected for text, color in colors if text == prefix)
    assert label.palette().color(label.foregroundRole()) != QColor(expected)
    assert label.property('sourceColor') == expected
    assert editor._source_buttons['title'].property('sourceColor') == expected
    rendered = label.grab().toImage()
    assert any(rendered.pixelColor(x, y).name() == expected
               for y in range(rendered.height()) for x in range(rendered.width()))


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_details_control_keeps_icon_and_visible_chevron_in_both_states(editor, language):
    apply_static_language(editor, language)
    app = QApplication.instance()
    app.processEvents()
    button = editor.recognition_details_button
    arrow = button.findChild(QLabel, 'RecognitionDetailsChevron')
    assert arrow is not None and arrow.isVisible()
    assert button.text() == ui_text(editor, 'Szczegóły')
    assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    assert button.icon().pixmap(14, 14).toImage() == library_icon('details', '#bdcfd8', 14).pixmap(14, 14).toImage()
    assert button.height() == 24 and button.width() <= 160
    before = editor.cover_gallery.geometry()
    closed = arrow.grab().toImage()
    assert arrow.pixmap().toImage() == library_icon('expand', '#bdcfd8', 14).pixmap(14, 14).toImage()
    assert button.rect().contains(arrow.geometry())
    button.click()
    app.processEvents()
    assert editor.recognition_details_popup.isVisible() and button.isChecked()
    assert arrow.isVisible() and arrow.grab().toImage() != closed
    assert arrow.pixmap().toImage() == library_icon('collapse', '#bdcfd8', 14).pixmap(14, 14).toImage()
    editor.recognition_details_popup.hide()
    app.processEvents()
    assert not button.isChecked() and arrow.grab().toImage() == closed
    assert editor.cover_gallery.geometry() == before


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_comparison_chevron_is_painted_and_legend_stays_above_table(editor, language):
    apply_static_language(editor, language)
    app = QApplication.instance()
    app.processEvents()
    toggle = editor.source_comparison_toggle
    legend = editor.source_legend_button
    title = next(label for label in editor.findChildren(QLabel, 'EditorSectionTitle')
                 if label.text().startswith(('Porównanie źródeł', 'Source comparison')))
    assert title.parentWidget().layout().itemAt(0).widget().objectName() == 'LibrarySectionMark'
    table_top = editor.source_table.mapTo(editor, QPoint()).y()
    assert legend.mapTo(editor, legend.rect().bottomLeft()).y() < table_top
    assert legend.mapTo(editor, QPoint()).x() > title.mapTo(editor, title.rect().topRight()).x()
    for expanded, asset in ((True, 'collapse'), (False, 'expand'), (True, 'collapse')):
        if toggle.isChecked() != expanded:
            toggle.click()
            app.processEvents()
        assert toggle.isVisible()
        assert editor.source_table.isVisible() == expanded
        assert toggle.icon().pixmap(16, 16).toImage() == library_icon(asset, '#a8bdca', 16).pixmap(16, 16).toImage()
        painted = toggle.grab().toImage()
        assert any(painted.pixelColor(x, y).value() > 100
                   for y in range(painted.height()) for x in range(painted.width()))


def test_output_filename_uses_existing_document_edit_asset(editor):
    mark = editor.findChild(QLabel, 'OutputFilenameIcon')
    assert mark is not None and mark.isVisible()
    assert mark.pixmap().toImage() == library_icon('metadata_edit', '#91adbe', 20).pixmap(20, 20).toImage()
    assert mark.mapTo(editor, mark.rect().topRight()).x() < editor.filename_override.mapTo(editor, QPoint()).x()


def test_cover_action_captions_follow_live_language_changes(editor):
    for language in ('pl', 'en', 'pl'):
        apply_static_language(editor, language)
        editor.refresh_audio_language()
        assert editor.choose_cover_button.text() == ('Dodaj' if language == 'pl' else 'Add')
        assert editor.search_cover_button.text() == (
            'Szukaj okładki online' if language == 'pl' else 'Search for cover art online')


@pytest.mark.parametrize('language', ['pl', 'en'])
@pytest.mark.parametrize('scale', ['1', '1.25', '1.5', '2'])
def test_cover_actions_use_space_below_four_thumbnails_and_preserve_alignment(language, scale):
    code = '''
from pathlib import Path
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme
app = QApplication([])
app.setStyleSheet(style_for_theme('dark'))
editor = MetadataEditorDialog(TrackRecord(path=Path('/tmp/gallery.mp3')))
apply_static_language(editor, LANG)
assert editor.choose_cover_button.text() == ('Dodaj' if LANG == 'pl' else 'Add')
assert editor.search_cover_button.text() == ('Szukaj okładki online' if LANG == 'pl' else 'Search for cover art online')
image = QPixmap(80, 80)
image.fill(QColor('#456789'))
editor._cover_candidate_pixmaps['source'] = image
editor._cover_candidate_urls = {f'external:Source {i}': f'https://example.test/{i}.jpg' for i in range(3)}
for key in editor._cover_candidate_urls:
    editor._cover_candidate_pixmaps[key] = image
editor._rebuild_cover_proposals()
editor.show()
for width, height in ((1540, 1000), (1420, 900), (1180, 760)):
    editor.resize(width, height)
    for _ in range(3):
        app.processEvents()
    host = editor.content_scroll.widget()
    panels = (editor.metadata_card, editor.cover_gallery)
    bottoms = [p.mapTo(host, p.rect().bottomLeft()).y() for p in panels]
    assert abs(bottoms[0] - bottoms[1]) <= 1, bottoms
    assert 60 <= editor.comment.height() <= 82
    assert editor.cover_info.height() <= 80
    assert editor.cover_main_preview.size().toTuple() == (288, 288)
    grid = editor.cover_proposals_grid
    assert grid.count() == 4
    assert {grid.getItemPosition(i)[:2] for i in range(4)} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    parent = editor.cover_gallery
    proposals = editor.cover_proposals_host
    left = proposals.mapTo(parent, QPoint()).x()
    bottom = proposals.mapTo(parent, proposals.rect().bottomLeft()).y()
    buttons = (editor.choose_cover_button, editor.search_cover_button)
    for button in buttons:
        top = button.mapTo(parent, QPoint())
        right = button.mapTo(parent, button.rect().topRight()).x()
        assert top.x() >= left
        assert top.y() > bottom
        assert right <= left + proposals.width()
        assert button.width() >= button.sizeHint().width()
    assert buttons[0].mapTo(parent, QPoint()).y() - bottom <= 12
    assert buttons[1].mapTo(parent, QPoint()).y() - buttons[0].mapTo(parent, buttons[0].rect().bottomLeft()).y() <= 12
    assert buttons[1].mapTo(parent, buttons[1].rect().bottomLeft()).y() <= editor.cover_info.mapTo(parent, editor.cover_info.rect().bottomLeft()).y() + 8
    before = [p.geometry() for p in panels]
    editor.recognition_details_button.click()
    app.processEvents()
    assert [p.geometry() for p in panels] == before
    editor.recognition_details_popup.hide()
editor._force_closing = True
editor.close()
'''.replace('LANG', repr(language))
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR=scale,
                       PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', code], env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
