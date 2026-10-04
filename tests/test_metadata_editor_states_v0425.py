import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QLabel

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import SOURCE as AUDIO_SOURCE
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


@pytest.fixture
def editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    track = TrackRecord(path=tmp_path / 'states.mp3', artist='Artist', title='Title',
                        year='2008', genre='House', bpm=128,
                        field_sources={'title': AUDIO_SOURCE},
                        field_source_values={'title': {'Tag': 'Tag title', 'Discogs': 'Discogs title', 'MusicBrainz': 'MB title', AUDIO_SOURCE: 'Audio title'},
                                             'artist': {'Discogs': 'Discogs artist', 'MusicBrainz': 'MB artist'}},
                        audio_recognition={'recording_id': 'r1', 'artist': 'Artist', 'title': 'Title', 'score': .88})
    dialog = MetadataEditorDialog(track)
    dialog.resize(1540, 1000)
    dialog.show()
    app.processEvents()
    yield dialog
    dialog._force_closing = True
    dialog.close()
    app.setStyleSheet(previous)


def _row(editor, source):
    return next(row for row in range(editor.source_table.rowCount())
                if editor.source_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == source)


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_last_applied_source_caption_fits_and_previous_source_remains_clickable(editor, language):
    app = QApplication.instance()
    apply_static_language(editor, language)
    selected = '✓ Aktualnie wybrane' if language == 'pl' else '✓ Currently selected'
    for source, wanted in [('Tag', 'Tag title'), ('MusicBrainz', 'MB title'), ('Tag', 'Tag title'),
                           ('Discogs', 'Discogs title'), ('MusicBrainz', 'MB title'), ('Discogs', 'Discogs title')]:
        row = _row(editor, source)
        button = editor.source_table.cellWidget(row, 6).findChild(QPushButton, 'UseSourceDataButton')
        assert button.isEnabled()
        button.click()
        app.processEvents()
        assert editor.title.text() == wanted
        for other in range(editor.source_table.rowCount()):
            action = editor.source_table.cellWidget(other, 6).findChild(QPushButton, 'UseSourceDataButton')
            assert action.isEnabled()
            assert (action.text() == selected) == (other == row)
            assert action.width() >= action.fontMetrics().horizontalAdvance(action.text()) + 14
            cell_widget = editor.source_table.cellWidget(other, 6)
            assert cell_widget.contentsRect().contains(action.geometry())
            cell_rect = editor.source_table.visualRect(editor.source_table.model().index(other, 6))
            action_rect = action.rect().translated(action.mapTo(editor.source_table.viewport(), QPoint()))
            assert cell_rect.contains(action_rect)
            assert editor.source_table.item(other, 1).background().style() == Qt.BrushStyle.NoBrush
        painted = editor.source_table.viewport().grab().toImage()
        cell = editor.source_table.visualItemRect(editor.source_table.item(row, 1))
        color = painted.pixelColor(cell.right() - 12, cell.center().y())
        assert color.blue() >= color.green(), color.name()
    editor.artist.setText('Manual artist')
    apply_static_language(editor, 'en' if language == 'pl' else 'pl')
    editor.refresh_audio_language()
    action = editor.source_table.cellWidget(_row(editor, 'Discogs'), 6).findChild(QPushButton, 'UseSourceDataButton')
    assert action.text() == ('✓ Currently selected' if language == 'pl' else '✓ Aktualnie wybrane')
    assert action.isEnabled()


def test_source_comparison_hover_is_subtle_neutral_and_leaves_applied_caption(editor):
    app = QApplication.instance()
    editor._apply_source_bundle('Tag')
    app.processEvents()
    table = editor.source_table
    editor.content_scroll.ensureWidgetVisible(table)
    QTest.mouseMove(editor.source_comparison_toggle, editor.source_comparison_toggle.rect().center())
    app.processEvents()
    row = _row(editor, 'MusicBrainz')
    before = table.viewport().grab().toImage()
    QTest.mouseMove(table.viewport(), table.visualItemRect(table.item(row, 1)).center())
    app.processEvents()
    hover = table.viewport().grab().toImage()
    for column in range(6):
        rect = table.visualItemRect(table.item(row, column))
        point = QPoint(rect.right() - 12, rect.center().y())
        base, color = before.pixelColor(point), hover.pixelColor(point)
        assert 0 < color.value() - base.value() < 30
        assert color.blue() >= color.green()
        assert max(color.red(), color.green(), color.blue()) - min(color.red(), color.green(), color.blue()) < 20
    action = table.cellWidget(_row(editor, 'Tag'), 6).findChild(QPushButton, 'UseSourceDataButton')
    assert action.text() == '✓ Aktualnie wybrane'


@pytest.mark.parametrize('source,expected', [
    ('Tag', '#5ca3ff'), ('Discogs', '#43d17d'), ('MusicBrainz', '#7289ff'),
    ('Apple / iTunes', '#ff6670'), (AUDIO_SOURCE, '#a3a8ff'),
    ('Ręcznie', '#ffb84d'), ('Analiza audio', '#49d6cf'), ('Nazwa pliku', '#7d8894'),
])
def test_metadata_field_border_uses_source_color(editor, source, expected):
    app = QApplication.instance()
    for field in ('title', 'comment'):
        editor._source_values.setdefault(field, {})[source] = 'Source value'
        editor._select_source_value(field, source)
        app.processEvents()
        widget = editor._field_widgets[field]
        picture = widget.grab().toImage()
        assert picture.pixelColor(0, picture.height() // 2).name() == expected
        assert editor._source_buttons[field].property('sourceKind') == editor.SOURCE_KINDS[source]
    if source in ('Apple / iTunes', AUDIO_SOURCE):
        editor.title.clear()
        editor._current_sources['title'] = source
        editor._refresh_source_badge('title')
        app.processEvents()
        picture = editor.title.grab().toImage()
        assert picture.pixelColor(0, picture.height() // 2).name() == '#f34d64'


def test_audio_panel_uses_dark_indigo_and_empty_result_stays_red(editor):
    app = QApplication.instance()
    panel = editor.audio_panel.grab().toImage()
    border = panel.pixelColor(0, panel.height() // 2)
    assert 225 <= border.hue() <= 285, border.name()
    assert panel.pixelColor(4, 4).value() < 90
    heading = editor.audio_summary_heading.palette().color(editor.audio_summary_heading.foregroundRole())
    assert 225 <= heading.hue() <= 285, heading.name()
    assert editor._source_buttons['title'].property('sourceKind') == 'audio_recognition'
    assert 225 <= QColor(editor._source_buttons['title'].property('sourceColor')).hue() <= 285
    editor.show_audio_candidates([])
    app.processEvents()
    error = editor.audio_empty_heading.palette().color(editor.audio_empty_heading.foregroundRole())
    assert error.red() > error.green() + 60 and error.red() > error.blue() + 30


@pytest.mark.parametrize('width', [1540, 1420])
def test_cover_grid_uses_available_height_with_larger_centered_four_proposals(editor, width):
    editor.resize(width, 1000)
    image = QPixmap(300, 300)
    image.fill(QColor('#345678'))
    editor._cover_candidate_pixmaps['source'] = image
    editor._cover_candidate_urls = {f'external:{i}': f'https://example.test/{i}.jpg' for i in range(4)}
    for key in editor._cover_candidate_urls:
        editor._cover_candidate_pixmaps[key] = image
    editor._rebuild_cover_proposals()
    QApplication.instance().processEvents()
    host, grid = editor.cover_proposals_host, editor.cover_proposals_grid
    assert grid.count() == 4
    assert {grid.getItemPosition(i)[:2] for i in range(4)} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert all(112 <= preview.width() <= 117 for preview in editor._cover_proposal_labels.values())
    boxes = [grid.itemAt(i).widget().geometry() for i in range(4)]
    assert len({box.size().toTuple() for box in boxes}) == 1
    assert abs(boxes[0].top() - (host.height() - boxes[2].bottom() - 1)) <= 2
    assert abs(boxes[0].left() - (host.width() - boxes[1].right() - 1)) <= 2
    actions = editor.choose_cover_button.parentWidget()
    host_bottom = host.mapTo(editor.cover_gallery, host.rect().bottomLeft()).y()
    actions_top = actions.mapTo(editor.cover_gallery, QPoint()).y()
    assert 0 <= actions_top - host_bottom <= 14
    assert editor.cover_main_preview.size().toTuple() == (288, 288)
    assert abs(editor.metadata_card.height() - editor.cover_gallery.height()) <= 1
    markers = host.findChildren(QLabel, 'CoverProposalSelectedMarker')
    assert sum(marker.isVisible() for marker in markers) == 1
    picture = host.grab().toImage()
    x, y = host.width() // 2, host.height() // 2
    separator = '#293944'
    assert picture.pixelColor(x, 20).name() == separator
    assert picture.pixelColor(20, y).name() == separator
    assert picture.pixelColor(x + 1, 20).name() != separator
    assert picture.pixelColor(x, 4).name() != separator
    assert picture.pixelColor(4, y).name() != separator


@pytest.mark.parametrize('language,cover_title,source_title', [
    ('pl', 'Wybór okładki', 'Porównanie źródeł'),
    ('en', 'Cover selection', 'Source comparison'),
])
def test_cover_and_source_headers_use_short_titles_and_keep_controls(editor, language, cover_title, source_title):
    apply_static_language(editor, language)
    titles = editor.findChildren(QLabel, 'EditorSectionTitle')
    assert editor.cover_gallery.findChild(QLabel, 'EditorSectionTitle').text() == cover_title
    source_heading = next(title for title in titles if title.text() == source_title)
    assert source_heading.parentWidget() is editor.source_legend_button.parentWidget()
    assert editor.source_legend_button.menu() is not None
    assert not editor.source_legend_button.icon().isNull()
    assert editor.source_comparison_toggle.icon().isNull()
