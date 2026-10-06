import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionFrame

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.icons import library_icon
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.library_status_legend import install_library_status_legend
from audio_library_organizer.ui.theme import DARK_STYLE


@pytest.fixture
def toolbar_page(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    page = LibraryPage()
    tracks = [TrackRecord(path=tmp_path / f'{i}.mp3', artist='Artist', title=f'Title {i}',
                          album='Album', year='2008', genre='Trance', bpm=128,
                          status='review') for i in range(5)]
    page.set_tracks(tracks)
    page.resize(1600, 900)
    page.show()
    app.processEvents()
    try:
        yield app, page, tracks
    finally:
        page.close()
        app.setStyleSheet(previous)


def _box(page, widget):
    return widget.geometry().translated(widget.parentWidget().mapTo(page, QPoint()))


def _summary(page):
    document = QTextDocument()
    document.setHtml(page.view_state_label.text())
    return document


def _format(document, text):
    start = document.toPlainText().index(text)
    cursor = QTextCursor(document)
    cursor.setPosition(start)
    cursor.setPosition(start + len(text), QTextCursor.MoveMode.KeepAnchor)
    return cursor.charFormat()


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_variant_b_has_two_rows_and_keeps_controls_clear_on_resize_and_collapse(toolbar_page, language):
    app, page, _ = toolbar_page
    legend = install_library_status_legend(page)
    apply_static_language(page, language)
    page.refresh(preserve_order=True)
    page.model.item(0, 0).setCheckState(Qt.CheckState.Checked)
    first = [page.search, page.genre_filter, page.bpm_min, page.bpm_max, page.status,
             page.format_filter, page.reset_view_btn, legend]
    second = [page.collection_btn, page.playlist_btn, page.selected_count,
              page.view_state_label, page.details_btn]
    for width in (1920, 1600, 1280, 960, 800, 1600):
        page.resize(width, 900)
        for collapsed in (False, True):
            if page.details_btn.isChecked() == collapsed:
                page.details_btn.click()
            app.processEvents()
            boxes = [_box(page, widget) for widget in first + second]
            assert all(box.left() >= 0 and box.right() < page.width() for box in boxes)
            assert all(not a.intersects(b) for i, a in enumerate(boxes) for b in boxes[i + 1:])
            assert _box(page, legend).right() == page.width() - 5
            assert _box(page, page.details_btn).right() == page.width() - 5
            assert page.details_btn.width() >= page.details_btn.sizeHint().width()
            assert _box(page, page.details_btn).bottom() < page.split.geometry().top()
            assert abs(_box(page, legend).center().y() - _box(page, page.search).center().y()) <= 3
            if width >= 1280:
                assert max(box.center().y() for box in boxes[:8]) - min(box.center().y() for box in boxes[:8]) <= 3
                assert max(box.center().y() for box in boxes[8:]) - min(box.center().y() for box in boxes[8:]) <= 3
                assert _box(page, page.collection_btn).top() - _box(page, page.search).bottom() <= 12
            for widget in (page.bpm_min, page.bpm_max):
                option = QStyleOptionFrame()
                widget.initStyleOption(option)
                contents = widget.style().subElementRect(QStyle.SubElement.SE_LineEditContents, option, widget)
                assert widget.fontMetrics().horizontalAdvance(widget.placeholderText()) <= contents.width() - 4


@pytest.mark.parametrize('language,sort_label,filters_label,none', [
    ('pl', 'Sortowanie:', 'Filtry:', 'brak'), ('en', 'Sort:', 'Filters:', 'none')])
def test_sort_value_has_accent_and_filters_update_after_live_language_switch(
        toolbar_page, language, sort_label, filters_label, none):
    _, page, _ = toolbar_page
    apply_static_language(page, language)
    page.refresh(preserve_order=True)
    for column, order, arrow in ((1, Qt.SortOrder.AscendingOrder, '↑'),
                                 (3, Qt.SortOrder.DescendingOrder, '↓'),
                                 (2, Qt.SortOrder.AscendingOrder, '↑'),
                                 (9, Qt.SortOrder.AscendingOrder, '↑')):
        page.table.sortByColumn(column, order)
        document = _summary(page)
        name = page.model.headerData(column, Qt.Orientation.Horizontal)
        assert document.toPlainText() == f'{sort_label} {name} {arrow}   •   {filters_label} {none}'
        value = _format(document, f'{name} {arrow}')
        assert value.foreground().color().name() == '#65b5c0'
        assert value.fontWeight() > _format(document, sort_label).fontWeight()
        assert _format(document, none).foreground().color().name() == '#a5b2bd'
    page.status.setCurrentIndex(page.status.findData('review'))
    page.genre_filter.setText('Trance')
    page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
    document = _summary(page)
    assert _format(document, page.status.currentText()).foreground().color().name() == '#d8a23a'
    assert _format(document, 'Trance').foreground().color().name() == '#b6a0ce'
    assert _format(document, 'MP3').foreground().color().name() == '#85bdd6'
    page._reset_view()
    assert _summary(page).toPlainText() == f'{sort_label} Status ↑   •   {filters_label} {none}'


def test_filter_summary_renders_user_text_literally_and_keeps_full_tooltip(toolbar_page):
    _, page, _ = toolbar_page
    search = '<img src="file:///missing"> & Szukaj: literal'
    genre = '<b>Trance</b> & Genre'
    page.search.setText(search)
    page.genre_filter.setText(genre)
    page.bpm_min.setText('<i>1</i>')
    page.bpm_max.setText('2 & 3')
    apply_static_language(page, 'en')
    page.refresh(preserve_order=True)
    text = _summary(page).toPlainText()
    assert f'Search: {search}' in text and f'Genre: {genre}' in text
    assert 'BPM <i>1</i>–2 & 3' in text
    tooltip = QTextDocument()
    tooltip.setHtml(page.view_state_label.toolTip())
    assert tooltip.toPlainText() == text
    assert '\ufffc' not in text  # HTML must not turn user input into an image.
    apply_static_language(page, 'pl')
    page.refresh(preserve_order=True)
    assert f'Szukaj: {search}' in _summary(page).toPlainText()


def test_completeness_fields_keep_one_row_and_semantic_missing_statuses(toolbar_page):
    app, page, tracks = toolbar_page
    page.select_track(tracks[0])
    app.processEvents()
    positions = {key: icon.parentWidget().pos() for key, icon in page.completeness_field_icons.items()}
    keys = ['artist', 'title', 'year', 'genre', 'bpm', 'album']
    assert len({positions[key].y() for key in keys}) == 1
    assert [positions[key].x() for key in keys] == sorted(positions[key].x() for key in keys)
    tracks[0].album = None
    tracks[0].year = None
    page._show_detail()
    assert page.completeness_count.text() == '4/6'
    for key, glyph, color in [('album', 'album', '#e5b86a'), ('year', 'calendar', '#ff927c')]:
        assert page.completeness_field_icons[key].pixmap().toImage() == library_icon(
            glyph, color, 32).pixmap(32, 32).toImage()
