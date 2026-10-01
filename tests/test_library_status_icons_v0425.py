import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.icons import alo_icon, library_icon
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.theme import DARK_STYLE


@pytest.fixture
def status_page(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    page = LibraryPage()
    tracks = [
        TrackRecord(path=tmp_path / 'ready.mp3', artist='Artist', title='Ready',
                    year='2008', genre='House', bpm=120, status='ready',
                    locked_fields={'__status__', '__online_lock__'}),
        TrackRecord(path=tmp_path / 'review.flac', artist='Artist', title='Review', status='review',
                    size_bytes=800000, duration_seconds=180, codec='FLAC'),
        TrackRecord(path=tmp_path / 'problem.wav', title='Problem', status='review'),
        TrackRecord(path=tmp_path / 'error.m4a', artist='Artist', title='Error', status='error'),
    ]
    page.set_tracks(tracks)
    page.resize(1600, 900)
    page.show()
    app.processEvents()
    try:
        yield app, page, tracks
    finally:
        page.close()
        app.setStyleSheet(previous)


def _row(page, track):
    return next(row for row in range(page.model.rowCount())
                if page.model.item(row, 0).data(Qt.ItemDataRole.UserRole) is track)


def _icon_pixels(icon):
    return icon.pixmap(QSize(16, 16)).toImage()


def _body_pixel(page, track, column=3):
    QApplication.instance().processEvents()
    pixmap = page.table.viewport().grab()
    box = page.table.visualRect(page.model.index(_row(page, track), column))
    ratio = pixmap.devicePixelRatio()
    return pixmap.toImage().pixelColor(round((box.left() + 12) * ratio),
                                      round((box.top() + 5) * ratio))


def test_ready_review_and_problem_use_final_reference_shapes(status_page):
    _, page, tracks = status_page
    for track, name, color in zip(tracks,
                                 ('status', 'warning', 'alert_circle', 'alert_circle'),
                                 ('#35d893', '#f5b649', '#f34d64', '#f34d64')):
        item = page.model.item(_row(page, track), 1)
        assert _icon_pixels(item.icon()) == _icon_pixels(alo_icon(name, color, 16))
    # A critical review is a visual problem, not a new backend status.
    assert tracks[2].status == 'review'
    assert page.model.item(_row(page, tracks[2]), 1).toolTip() == 'PROBLEM'
    assert 'Zablokowany przed ponownym rozpoznaniem online' in page.model.item(
        _row(page, tracks[0]), 1).toolTip()


def test_status_column_is_icon_only_compact_and_keeps_accessible_labels(status_page):
    _, page, tracks = status_page
    assert 50 <= page.table.columnWidth(1) <= 90
    assert page.table.iconSize() == QSize(16, 16)
    for track in tracks:
        item = page.model.item(_row(page, track), 1)
        assert item.toolTip()
        assert item.data(Qt.ItemDataRole.AccessibleTextRole) == item.toolTip()
        # DisplayRole remains available for the existing sort mechanism.
        assert item.text()
    page.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    assert [page.model.item(i, 1).text() for i in range(4)] == sorted(
        page.model.item(i, 1).text() for i in range(4))


def test_status_tints_cover_row_without_coloring_text(status_page):
    _, page, tracks = status_page
    for track in tracks:
        row = _row(page, track)
        assert all(page.model.item(row, column).foreground().style() == Qt.BrushStyle.NoBrush
                   for column in range(page.model.columnCount()))
    assert _body_pixel(page, tracks[0]).name() == '#11171e'
    assert _body_pixel(page, tracks[1]).name() == '#211e16'
    assert _body_pixel(page, tracks[2]).name() == '#23181d'
    assert _body_pixel(page, tracks[1], 8) == _body_pixel(page, tracks[1])


def test_cyan_selection_overrides_review_and_problem_tints(status_page):
    _, page, tracks = status_page
    for track in tracks:
        page.table.selectRow(_row(page, track))
        assert _body_pixel(page, track).name() == '#153a42'


def test_status_icons_are_painted_at_cell_center_with_compact_bounds(status_page):
    app, page, tracks = status_page
    app.processEvents()
    pixmap = page.table.viewport().grab()
    image, ratio = pixmap.toImage(), pixmap.devicePixelRatio()
    for track in tracks:
        box = page.table.visualRect(page.model.index(_row(page, track), 1))
        pixels = []
        # Row borders are tested separately; inspect only the icon's interior.
        for y in range(round((box.top() + 3) * ratio), round((box.bottom() - 2) * ratio)):
            for x in range(round(box.left() * ratio), round((box.right() + 1) * ratio)):
                color = image.pixelColor(x, y)
                if max(color.red(), color.green(), color.blue()) > 155 and max(
                        color.red(), color.green(), color.blue()) - min(
                        color.red(), color.green(), color.blue()) > 55:
                    pixels.append((x / ratio, y / ratio))
        assert pixels
        xs, ys = zip(*pixels)
        assert max(xs) - min(xs) <= 16
        assert max(ys) - min(ys) <= 16
        assert abs((min(xs) + max(xs)) / 2 - box.center().x()) <= 1.5


def test_review_and_problem_accents_are_visible_and_selection_has_priority(status_page):
    app, page, tracks = status_page
    for track, expected in ((tracks[1], '#ad8037'), (tracks[2], '#bc3d50')):
        app.processEvents()
        pixmap = page.table.viewport().grab()
        box = page.table.visualRect(page.model.index(_row(page, track), 0))
        ratio = pixmap.devicePixelRatio()
        pixel = pixmap.toImage().pixelColor(round((box.left() + 1) * ratio),
                                           round(box.center().y() * ratio))
        assert pixel.name() == expected
    page.table.selectRow(_row(page, tracks[2]))
    app.processEvents()
    pixmap = page.table.viewport().grab()
    box = page.table.visualRect(page.model.index(_row(page, tracks[2]), 0))
    ratio = pixmap.devicePixelRatio()
    assert pixmap.toImage().pixelColor(round((box.left() + 1) * ratio),
                                      round(box.center().y() * ratio)).name() == '#31d7c8'


def test_nonsemantic_category_icons_are_neutral_until_hover_or_active(status_page):
    _, page, _ = status_page
    for category, asset in (('no_cover', 'no_cover'), ('no_year', 'no_year'),
                            ('not_selected', 'unselected')):
        index = page.status.findData(category)
        assert _icon_pixels(page.status.itemIcon(index)) == _icon_pixels(
            library_icon(asset, '#bdcbd3', 18))
        page._paint_category_icons(index)
        assert _icon_pixels(page.status.itemIcon(index)) == _icon_pixels(
            library_icon(asset, '#6de6a5', 18))
        page._paint_category_icons()
        page.status.setCurrentIndex(index)
        assert _icon_pixels(page.status.itemIcon(index)) == _icon_pixels(
            library_icon(asset, '#6de6a5', 18))
        page.status.setCurrentIndex(page.status.findData('all'))


def test_edit_metadata_button_is_prominent_but_compact(status_page):
    _, page, tracks = status_page
    assert 34 <= page.detail_edit.height() <= 40
    assert page.detail_edit.width() < page.detail.width() * .8
    assert page.detail_edit.iconSize().width() > page.collection_btn.iconSize().width()
    assert page.detail_edit.toolTip() == 'Edytuj metadane'
    edits = []
    page.edit_requested.connect(edits.append)
    page.select_track(tracks[1])
    page.detail_edit.click()
    assert edits == [tracks[1]]


def test_reset_view_repaints_active_category_icons(status_page):
    _, page, _ = status_page
    page.status.setCurrentIndex(page.status.findData('no_cover'))
    page.reset_view_btn.click()
    assert page.status.currentData() == 'all'
    assert _icon_pixels(page.status.itemIcon(page.status.findData('all'))) == _icon_pixels(
        library_icon('all_tracks', '#6de6a5', 18))
    assert _icon_pixels(page.status.itemIcon(page.status.findData('no_cover'))) == _icon_pixels(
        library_icon('no_cover', '#bdcbd3', 18))


def test_status_accessibility_and_legend_refresh_live_in_both_languages(status_page):
    _, page, tracks = status_page
    from audio_library_organizer.ui.library_status_legend import install_library_status_legend
    legend = install_library_status_legend(page)
    problem = next(action for action in legend.menu().actions() if action.text().startswith('PROBLEM'))
    assert not problem.icon().isNull()
    for language, review_caption in (('en', 'NEEDS REVIEW'), ('pl', 'DO SPRAWDZENIA')):
        apply_static_language(page, language)
        page.refresh(preserve_order=True)
        assert page.model.item(_row(page, tracks[1]), 1).toolTip() == review_caption
        assert page.model.item(_row(page, tracks[2]), 1).toolTip() == 'PROBLEM'
        assert problem.text().startswith('PROBLEM')
        assert ('Poważny' if language == 'pl' else 'serious') in problem.text()
