import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import SOURCE as AUDIO_SOURCE
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.icons import library_icon
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


@pytest.fixture
def editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    dialog = MetadataEditorDialog(TrackRecord(path=tmp_path / 'balance.mp3', artist='Artist',
                                            title='Title', year='2008', genre='Trance', bpm=128,
                                            field_sources={'title': AUDIO_SOURCE, 'year': 'Tag'}))
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
    return widget.rect().translated(widget.mapTo(parent, QPoint()))


def _covers(editor):
    image = QPixmap(1200, 1200)
    image.fill(QColor('#345678'))
    editor._cover_candidate_pixmaps['source'] = image
    editor._cover_candidate_urls = {f'external:Source {i}': f'https://example.test/{i}.jpg' for i in range(2)}
    for key in editor._cover_candidate_urls:
        editor._cover_candidate_pixmaps[key] = image
    editor._cover_details['source'] = {'type': 'Okładka główna (Front)', 'format': 'JPEG', 'bytes': 403200}
    editor._rebuild_cover_proposals()


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_cover_actions_keep_their_bottom_position_across_cover_and_metrics_changes(editor, language):
    apply_static_language(editor, language)
    app = QApplication.instance()
    app.processEvents()
    parent = editor.cover_gallery
    buttons = (editor.choose_cover_button, editor.search_cover_button)
    before = [_box(b, parent) for b in buttons]
    assert abs(before[0].bottom() - before[1].bottom()) <= 1
    assert 7 <= parent.height() - before[0].bottom() <= 12
    assert abs(before[0].left() - (parent.width() - before[1].right() - 1)) <= 1
    assert 4 <= before[1].left() - before[0].right() <= 12
    _covers(editor)
    for key in ('source', 'external:Source 0', 'placeholder'):
        editor._select_cover_choice(key, record_undo=False)
        app.processEvents()
        assert [_box(b, parent) for b in buttons] == before
        assert 68 <= editor.cover_info.height() <= 96
        assert abs(editor.metadata_card.height() - parent.height()) <= 1
        assert editor.comment.height() == 66
    assert len(editor.cover_info_values) == 5


def test_larger_four_thumbnails_are_symmetric_in_the_available_gallery_height(editor):
    _covers(editor)
    QApplication.instance().processEvents()
    grid, host = editor.cover_proposals_grid, editor.cover_proposals_host
    assert grid.count() == 4
    assert host.height() >= host.width()
    boxes = {(grid.getItemPosition(i)[0], grid.getItemPosition(i)[1]): _box(grid.itemAt(i).widget(), host)
             for i in range(4)}
    assert set(boxes) == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert len({box.size().toTuple() for box in boxes.values()}) == 1
    tl, tr, bl, br = (boxes[key] for key in ((0, 0), (0, 1), (1, 0), (1, 1)))
    assert abs(tl.left() - (host.width() - tr.right() - 1)) <= 1
    assert abs(tl.top() - (host.height() - bl.bottom() - 1)) <= 1
    assert tr.top() == tl.top() and br.bottom() == bl.bottom()
    assert all(112 <= label.width() <= 117 for label in editor._cover_proposal_labels.values())
    markers = host.findChildren(QLabel, 'CoverProposalSelectedMarker')
    assert sum(marker.isVisible() for marker in markers) == 1


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_comparison_has_only_a_directional_chevron_on_the_right(editor, language):
    apply_static_language(editor, language)
    app = QApplication.instance()
    app.processEvents()
    button = editor.source_comparison_toggle
    arrow = button.findChild(QLabel, 'SourceComparisonChevron')
    assert arrow is not None and arrow.isVisible()
    assert button.icon().isNull()
    assert button.width() <= 26 and button.height() <= 24
    assert button.menu() is None
    for checked, asset in ((True, 'collapse'), (False, 'expand'), (True, 'collapse')):
        button.setChecked(checked)
        app.processEvents()
        assert editor.source_table.isVisible() == checked
        assert arrow.isVisible() and button.rect().contains(arrow.geometry())
        assert arrow.pixmap().toImage() == library_icon(asset, '#a8bdca', 14).pixmap(14, 14).toImage()
        assert button.icon().isNull()


@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_audio_source_badge_has_the_same_bordered_shape_as_tag(editor, theme):
    app = QApplication.instance()
    app.setStyleSheet(style_for_theme(theme))
    app.processEvents()
    audio, tag = (editor._source_buttons[key] for key in ('title', 'year'))
    assert audio.property('sourceKind') == 'audio_recognition'
    assert audio.property('sourceColor') == '#a3a8ff'
    assert audio.font() == tag.font()
    assert audio.height() == tag.height()
    for button in (audio, tag):
        image = button.grab().toImage()
        assert image.pixelColor(0, image.height() // 2) != image.pixelColor(2, image.height() // 2)
        assert button.popupMode() == button.ToolButtonPopupMode.InstantPopup
        assert button.menu() is not None
