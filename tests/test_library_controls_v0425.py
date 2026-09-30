import os
from pathlib import Path
from xml.etree import ElementTree

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.library_page import LibraryPage


def _app():
    return QApplication.instance() or QApplication([])


def _page(tmp_path):
    _app()
    page = LibraryPage()
    tracks = [
        TrackRecord(path=tmp_path / 'a.mp3', artist='Madonna', title='Alpha', status='review'),
        TrackRecord(path=tmp_path / 'b.flac', artist='Madonna', title='Beta', year='2005', genre='Pop', bpm=120, status='ready'),
        TrackRecord(path=tmp_path / 'c.wav', artist='Other', title='Gamma', status='review'),
        TrackRecord(path=tmp_path / 'd.m4a', artist='Other', title='Delta', year='2005', genre='Pop', bpm=120, status='ready'),
        TrackRecord(path=tmp_path / 'e.weird', artist='Other', title='Epsilon', year='2005', genre='Pop', bpm=120, status='ready'),
    ]
    page.set_tracks(tracks)
    return page, tracks


def _checked_names(page):
    return [page.model.item(row, 0).data(Qt.ItemDataRole.UserRole).path.name
            for row in range(page.model.rowCount())
            if page.model.item(row, 0).checkState() == Qt.CheckState.Checked]


def _row_for(page, track):
    return next(row for row in range(page.model.rowCount())
                if page.model.item(row, 0).data(Qt.ItemDataRole.UserRole) is track)


def test_library_icons_cover_every_real_category_and_edit_action(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        assert [page.status.itemData(i) for i in range(page.status.count()) if not page.status.itemText(i)] == [None, None]
        for i in range(page.status.count()):
            if page.status.itemData(i) is not None:
                assert not page.status.itemIcon(i).isNull(), page.status.itemText(i)
        assert not page.status.itemIcon(page.status.findData('no_cover')).isNull()
        assert not page.status.itemIcon(page.status.findData('not_selected')).isNull()
        assert not page.detail_edit.icon().isNull()
        emitted = []
        page.edit_requested.connect(emitted.append)
        page.table.selectRow(0)
        page.detail_edit.click()
        assert emitted == [tracks[0]]
        assets = Path(__file__).resolve().parents[1] / 'src/audio_library_organizer/assets/icons/library_a'
        for path in assets.glob('*.svg'):
            svg = ElementTree.parse(path).getroot()
            assert svg.attrib['viewBox'] == '0 0 24 24'
            assert svg.attrib.get('fill') == 'none'
        assert len(list(assets.glob('*.svg'))) >= 7
    finally:
        page.close()


def test_checkbox_selection_stays_with_tracks_through_sort_and_filters(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        check = page.model.item(0, 0)
        check.setCheckState(Qt.CheckState.Checked)
        assert '1' in page.selected_count.text()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.PartiallyChecked
        page.table.sortByColumn(page.HEADERS.index('Tytuł'), Qt.SortOrder.DescendingOrder)
        assert page._checked_paths == {page._path_key(tracks[0])}
        assert _checked_names(page) == ['a.mp3']
        page.search.setText('Madonna')
        assert not page._checked_paths
        assert not page.table.selectionModel().selectedRows()
        assert page.selected_count.isHidden()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Unchecked
        page.format_filter.setCurrentIndex(0)
        page.search.clear()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
        assert len(page._checked_paths) == 0
    finally:
        page.close()


def test_header_checkbox_toggles_only_visible_tracks_and_partial_state(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        page.status.setCurrentIndex(page.status.findData('review'))
        header = page.table.horizontalHeader()
        header.toggleVisibleChecks()
        assert page._checked_paths == {page._path_key(tracks[0]), page._path_key(tracks[2])}
        assert header.checkState() == Qt.CheckState.Checked
        page.model.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        assert header.checkState() == Qt.CheckState.PartiallyChecked
        header.toggleVisibleChecks()
        assert header.checkState() == Qt.CheckState.Checked
        header.toggleVisibleChecks()
        assert header.checkState() == Qt.CheckState.Unchecked
        page.status.setCurrentIndex(page.status.findData('all'))
        assert header.checkState() == Qt.CheckState.Unchecked
        header.toggleVisibleChecks()
        assert len(page._checked_paths) == 5
        header.toggleVisibleChecks()
        assert not page._checked_paths
        assert page.selected_count.isHidden()
    finally:
        page.close()


def test_format_is_dynamic_sortable_and_combines_with_search_and_status(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        column = page.HEADERS.index('Format')
        assert [page.format_filter.itemData(i) for i in range(page.format_filter.count())] == ['', 'FLAC', 'M4A', 'MP3', 'WAV', 'WEIRD']
        assert {page.model.item(i, column).text() for i in range(5)} == {'MP3', 'FLAC', 'WAV', 'M4A', 'WEIRD'}
        page.table.sortByColumn(column, Qt.SortOrder.AscendingOrder)
        assert [page.model.item(i, column).text() for i in range(5)] == ['FLAC', 'M4A', 'MP3', 'WAV', 'WEIRD']
        page.table.sortByColumn(column, Qt.SortOrder.DescendingOrder)
        assert [page.model.item(i, column).text() for i in range(5)] == ['WEIRD', 'WAV', 'MP3', 'M4A', 'FLAC']
        page.format_filter.setCurrentIndex(page.format_filter.findData('FLAC'))
        page.search.setText('Madonna')
        assert [t.path.name for t in page.visible_tracks()] == ['b.flac']
        page.status.setCurrentIndex(page.status.findData('review'))
        assert page.visible_tracks() == []
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
        assert [t.path.name for t in page.visible_tracks()] == ['a.mp3']
        page._reset_view()
        assert page.format_filter.currentData() == ''
        page.set_tracks([tracks[0], TrackRecord(path=tmp_path / 'no-extension')])
        assert [page.format_filter.itemData(i) for i in range(page.format_filter.count())] == ['', 'MP3']
        assert {page.model.item(i, column).text() for i in range(2)} == {'MP3', '—'}
    finally:
        page.close()


def test_library_new_controls_switch_pl_en_without_losing_filter_or_checks(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
        page.model.item(0, 0).setCheckState(Qt.CheckState.Checked)
        apply_static_language(page, 'en')
        page.refresh(preserve_order=True)
        assert page.format_filter.currentData() == 'MP3'
        assert 'Selected:' in page.selected_count.text()
        assert page.model.headerData(page.HEADERS.index('Format'), Qt.Orientation.Horizontal) == 'Format'
        assert page.format_filter.currentText() == 'Format: MP3'
        assert page.detail_edit.text() == 'Edit metadata'
        assert page.collection_btn.text() == 'Create folder from selected'
        assert page.playlist_btn.text() == 'Add to playlist'
        assert page.playlist_btn.toolTip() == 'Save selected tracks as an M3U8 playlist'
        apply_static_language(page, 'pl')
        page.refresh(preserve_order=True)
        assert 'Zaznaczono:' in page.selected_count.text()
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Checked
        assert page.detail_edit.text() == 'Edytuj metadane'
        assert page.collection_btn.text() == 'Utwórz folder z zaznaczonych'
        assert page.playlist_btn.text() == 'Dodaj do playlisty'
        assert page.playlist_btn.toolTip() == 'Zapisz zaznaczone utwory jako playlistę M3U8'
    finally:
        page.close()


def test_checkbox_hit_area_and_existing_group_actions(tmp_path):
    page, tracks = _page(tmp_path)
    page.resize(1520, 750)
    page.show()
    _app().processEvents()
    try:
        header = page.table.horizontalHeader()
        QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(header.sectionViewportPosition(0) + header.sectionSize(0) // 2, header.height() // 2))
        assert len(page._checked_paths) == 5
        checkbox = page.table.visualRect(page.model.index(0, 0)).center()
        QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=checkbox)
        assert len(page._checked_paths) == 4
        emitted = []
        page.create_collection_requested.connect(emitted.append)
        _app().processEvents()
        page.collection_btn.click()
        assert len(emitted) == 1 and len(emitted[0]) == 4
        played = []
        page.play_requested.connect(played.append)
        title_cell = page.table.visualRect(page.model.index(0, 3)).center()
        QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=title_cell)
        QTest.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=title_cell)
        assert played and played[0] in tracks
    finally:
        page.close()


def test_format_filter_survives_reload_but_selection_is_cleared(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        page.model.item(0, 0).setCheckState(Qt.CheckState.Checked)
        page.table.selectRow(0)
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
        replacement = TrackRecord(path=tracks[0].path, artist='Updated', title='Same file', status='review')
        page.set_tracks([replacement, TrackRecord(path=tmp_path / 'new.OPUS', title='New')])
        assert page.format_filter.currentData() == 'MP3'
        assert page.model.rowCount() == 1
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Unchecked
        assert page.selected_count.isHidden()
        assert not page.table.selectionModel().selectedRows()
        assert 'OPUS' in [page.format_filter.itemData(i) for i in range(page.format_filter.count())]
        page.set_tracks([TrackRecord(path=tmp_path / 'new.OPUS', title='New')])
        assert page.format_filter.currentData() == ''
        assert not page._checked_paths
    finally:
        page.close()


def test_refresh_discards_checked_track_that_no_longer_matches_filter(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        page.search.setText('Madonna')
        page.model.item(_row_for(page, tracks[0]), 0).setCheckState(Qt.CheckState.Checked)
        tracks[0].artist = 'Other'
        page.refresh(preserve_order=True)
        assert page.model.rowCount() == 1
        assert page._checked_paths == set()
        assert page.selected_count.isHidden()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
        assert not page.collection_btn.isEnabled() and not page.playlist_btn.isEnabled()
    finally:
        page.close()


def test_group_actions_follow_checkboxes_not_row_highlight_and_clear_at_zero(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        folders, playlists = [], []
        page.create_collection_requested.connect(folders.append)
        page.playlist_requested.connect(playlists.append)
        page.table.selectRow(0)  # the current details row is not a group selection
        assert page.selected_count.isHidden()
        assert not page.collection_btn.isEnabled()
        assert not page.playlist_btn.isEnabled()
        page.model.item(_row_for(page, tracks[1]), 0).setCheckState(Qt.CheckState.Checked)
        assert page.selected_count.text().endswith('1')
        assert page.collection_btn.isEnabled() and page.playlist_btn.isEnabled()
        page.collection_btn.click()
        page.playlist_btn.click()
        assert folders == [[tracks[1]]]
        assert playlists == [[tracks[1].path]]
        page.model.item(_row_for(page, tracks[2]), 0).setCheckState(Qt.CheckState.Checked)
        assert page.selected_count.text().endswith('2')
        page.table.sortByColumn(page.HEADERS.index('Format'), Qt.SortOrder.DescendingOrder)
        page.collection_btn.click()
        assert {t.path for t in folders[-1]} == {tracks[1].path, tracks[2].path}
        for row in range(page.model.rowCount()):
            page.model.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        assert page.selected_count.isHidden()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
        assert not page.collection_btn.isEnabled() and not page.playlist_btn.isEnabled()
    finally:
        page.close()


def test_filters_reset_all_checks_and_group_buttons(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        changes = [
            lambda: page.search.setText('Madonna'),
            lambda: page.genre_filter.setText('Pop'),
            lambda: page.bpm_min.setText('100'),
            lambda: page.bpm_max.setText('130'),
            lambda: page.status.setCurrentIndex(page.status.findData('ready')),
            lambda: page.format_filter.setCurrentIndex(page.format_filter.findData('MP3')),
            lambda: page._reset_view(),
        ]
        for change in changes:
            page._reset_view()
            page.table.selectRow(0)
            page.table.horizontalHeader().toggleVisibleChecks()
            assert page.selected_count.text().endswith('5')
            change()
            assert page._checked_paths == set()
            assert not page.table.selectionModel().selectedRows()
            assert page.selected_count.isHidden()
            assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
            assert all(page.model.item(row, 0).checkState() == Qt.CheckState.Unchecked
                       for row in range(page.model.rowCount()))
            assert not page.collection_btn.isEnabled() and not page.playlist_btn.isEnabled()
    finally:
        page.close()


def test_library_toolbar_and_detail_footer_expose_only_intended_actions(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        buttons = [button.text() for button in page.findChildren(QPushButton)]
        assert 'Zaznacz wszystko' not in buttons
        assert 'Gatunek dla zaznaczonych' not in buttons
        assert 'Cofnij ostatnią zmianę' not in buttons
        assert 'ZATWIERDŹ JAKO GOTOWE' not in buttons
        assert '⋯' not in [button.text() for button in page.findChildren(QToolButton)]
        assert buttons.count('Edytuj metadane') == 1
        page.table.selectRow(0)
        edits = []
        page.edit_requested.connect(edits.append)
        page.detail_edit.click()
        assert edits == [tracks[0]]
        assert page.model.item(0, 1).text() == 'DO SPRAWDZENIA'
    finally:
        page.close()


def test_toolbar_actions_fit_at_common_logical_dpi_widths(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        page.show()
        page.model.item(0, 0).setCheckState(Qt.CheckState.Checked)
        for width in (1920, 1536, 1280, 960):
            page.resize(width, 720)
            _app().processEvents()
            assert page.width() <= width
            widgets = [page.collection_btn, page.playlist_btn, page.selected_count,
                       page.view_state_label]
            boxes = [widget.geometry().translated(widget.parentWidget().mapTo(page, QPoint(0, 0)))
                     for widget in widgets if widget.isVisible()]
            assert all(box.left() >= 0 and box.right() < page.width() for box in boxes)
            assert all(not left.intersects(right) for i, left in enumerate(boxes) for right in boxes[i + 1:])
            assert page.reset_view_btn.geometry().right() < page.width()
    finally:
        page.close()
