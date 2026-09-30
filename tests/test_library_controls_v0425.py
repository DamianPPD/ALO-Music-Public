import os
from pathlib import Path
from xml.etree import ElementTree

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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


def test_library_icons_cover_every_real_category_and_edit_action(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        assert [page.status.itemData(i) for i in range(page.status.count()) if not page.status.itemText(i)] == [None, None]
        for i in range(page.status.count()):
            if page.status.itemData(i) is not None:
                assert not page.status.itemIcon(i).isNull(), page.status.itemText(i)
        assert not page.status.itemIcon(page.status.findData('no_cover')).isNull()
        assert not page.status.itemIcon(page.status.findData('not_selected')).isNull()
        assert not page.edit_main.icon().isNull()
        emitted = []
        page.edit_requested.connect(emitted.append)
        page.table.selectRow(0)
        page.edit_main.click()
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
        page.search.setText('Madonna')
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.PartiallyChecked
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Checked
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Checked
        page.format_filter.setCurrentIndex(0)
        page.search.clear()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.PartiallyChecked
        assert len(page._checked_paths) == 1
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
        page.status.setCurrentIndex(page.status.findData('all'))
        assert header.checkState() == Qt.CheckState.PartiallyChecked
        page.model.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        assert header.checkState() == Qt.CheckState.PartiallyChecked
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
        page.model.item(0, 0).setCheckState(Qt.CheckState.Checked)
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
        apply_static_language(page, 'en')
        page.refresh(preserve_order=True)
        assert page.format_filter.currentData() == 'MP3'
        assert 'Selected:' in page.selected_count.text()
        assert page.model.headerData(page.HEADERS.index('Format'), Qt.Orientation.Horizontal) == 'Format'
        assert page.format_filter.currentText() == 'Format: MP3'
        assert page.edit_main.text() == 'Edit metadata'
        assert page.more_actions.menu().actions()[1].text() == 'Create folder from selected'
        apply_static_language(page, 'pl')
        page.refresh(preserve_order=True)
        assert 'Zaznaczono:' in page.selected_count.text()
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Checked
        assert page.edit_main.text() == 'Edytuj metadane'
        assert page.more_actions.menu().actions()[1].text() == 'Utwórz folder z zaznaczonych'
    finally:
        page.close()


def test_checkbox_hit_area_and_existing_row_and_menu_actions(tmp_path):
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
        page.table.selectRow(0)
        _app().processEvents()
        page.more_actions.menu().actions()[1].trigger()
        assert len(emitted) == 1 and len(emitted[0]) == 1
        played = []
        page.play_requested.connect(played.append)
        title_cell = page.table.visualRect(page.model.index(0, 3)).center()
        QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=title_cell)
        QTest.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=title_cell)
        assert played and played[0] in tracks
    finally:
        page.close()


def test_format_and_checked_identity_follow_library_reload(tmp_path):
    page, tracks = _page(tmp_path)
    try:
        page.model.item(0, 0).setCheckState(Qt.CheckState.Checked)
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
        replacement = TrackRecord(path=tracks[0].path, artist='Updated', title='Same file', status='review')
        page.set_tracks([replacement, TrackRecord(path=tmp_path / 'new.OPUS', title='New')])
        assert page.format_filter.currentData() == 'MP3'
        assert page.model.rowCount() == 1
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Checked
        assert 'OPUS' in [page.format_filter.itemData(i) for i in range(page.format_filter.count())]
        page.set_tracks([TrackRecord(path=tmp_path / 'new.OPUS', title='New')])
        assert page.format_filter.currentData() == ''
        assert not page._checked_paths
    finally:
        page.close()
