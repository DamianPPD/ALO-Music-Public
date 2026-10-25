"""Stage 6.1: technical-state UI consumes evidence, never grants ownership."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from dataclasses import replace
from copy import deepcopy
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.file_state import FileState, FileFacts, evaluate_file_state
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.managed_files import ReadContext
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.library_page import FILE_STATE_ROLE, PLAYING_ROLE
from audio_library_organizer.ui.library_status_legend import install_library_status_legend
from test_library_file_ui_v0427 import library_page, row_for, facts_for


LABELS = ['W bibliotece', 'Tylko źródło', 'Do aktualizacji', 'Źródło niedostępne',
          'Brak pliku biblioteki', 'Konflikt']


def file_column(page):
    assert 'Plik' in page.HEADERS, 'Technical state must be visible as a named column'
    return page.HEADERS.index('Plik')


@pytest.mark.parametrize('position,label,tint', [
    (0, 'W bibliotece', '#142b23'), (1, 'Tylko źródło', '#142235'),
    (2, 'Do aktualizacji', '#30251b'), (3, 'Źródło niedostępne', '#351b24'),
    (4, 'Brak pliku biblioteki', '#302b18'), (5, 'Konflikt', '#302036'),
])
def test_six_state_column_and_muted_tint_keep_metadata_independent(tmp_path, position, label, tint):
    page, tracks, _ = library_page(tmp_path)
    track = tracks[position]; row = row_for(page, track)
    item = page.model.item(row, file_column(page))
    assert item.text() == label
    assert item.data(FILE_STATE_ROLE) == tuple(FileState)[position]
    assert item.background().color().name() == tint
    assert item.foreground().style() != Qt.BrushStyle.NoBrush
    assert not page.model.item(row, 1).icon().isNull()
    assert track.status == 'review'
    assert 'ponownej weryfikacji' in item.toolTip()


def test_column_appends_without_reindexing_existing_width_or_hidden_preferences(tmp_path):
    page, _, _ = library_page(tmp_path)
    assert page.HEADERS[:10] == ['', 'Status', 'Wykonawca', 'Tytuł', 'Rok', 'Gatunek',
                                 'BPM', 'Długość', 'Jakość', 'Format']
    assert file_column(page) == 10 and page.model.columnCount() == 11
    page._restore_view_state({'column_widths': [36, 45, 210, 310, 62, 150, 62, 76, 125, 72]})
    page.table.setColumnHidden(4, True)
    page.table.horizontalHeader().moveSection(5, 3)
    page.table.setColumnWidth(10, 230)
    page.refresh()
    assert page.table.columnWidth(2) == 210
    assert page.table.columnWidth(3) == 310
    assert page.table.isColumnHidden(4)
    assert page.table.horizontalHeader().visualIndex(5) == 3
    assert page.table.columnWidth(10) == 230


@pytest.mark.parametrize('order,positions', [
    (Qt.SortOrder.AscendingOrder, [0, 1, 2, 3, 4, 5]),
    (Qt.SortOrder.DescendingOrder, [5, 4, 3, 2, 1, 0]),
])
def test_file_header_sorts_by_existing_dropdown_order_not_translated_text(tmp_path, order, positions):
    page, tracks, _ = library_page(tmp_path)
    before = deepcopy(tracks)
    page.table.sortByColumn(file_column(page), order)
    assert [t.track_id for t in page.visible_tracks()] == [tracks[i].track_id for i in positions]
    apply_static_language(page, 'en'); page.refresh()
    assert page.model.headerData(10, Qt.Orientation.Horizontal) == 'File'
    assert [t.track_id for t in page.visible_tracks()] == [tracks[i].track_id for i in positions]
    assert tracks == before


def test_equal_states_sort_stably_and_keep_selected_and_checked_uuids(tmp_path):
    page, tracks, _ = library_page(tmp_path, (FileState.SOURCE_ONLY,)*3)
    col = file_column(page)
    initial = [t.track_id for t in page.visible_tracks()]
    target = tracks[1]
    row = row_for(page, target)
    page.table.selectRow(row)
    page.model.item(row, 0).setCheckState(Qt.CheckState.Checked)
    for order in [Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder]*2:
        page.table.sortByColumn(col, order)
        assert [t.track_id for t in page.visible_tracks()] == initial
        assert [t.track_id for t in page._selected_tracks()] == [target.track_id]
        assert page._checked_tracks() == [target]


def test_file_filter_keeps_surviving_uuid_selection_without_hidden_batch_actions(tmp_path):
    page, tracks, _ = library_page(tmp_path, (FileState.SOURCE_ONLY, FileState.SOURCE_ONLY, FileState.CONFLICT))
    before = deepcopy(tracks)
    selection = page.table.selectionModel()
    for track in tracks:
        row = row_for(page, track)
        selection.select(page.model.index(row, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        page.model.item(row, 0).setCheckState(Qt.CheckState.Checked)
    page.file_filter.setCurrentIndex(page.file_filter.findData('SOURCE_ONLY'))
    assert {t.track_id for t in page._selected_tracks()} == {t.track_id for t in tracks[:2]}
    assert {t.track_id for t in page._checked_tracks()} == {t.track_id for t in tracks[:2]}
    assert tracks[2] not in page._checked_tracks()
    assert tracks == before


def test_unknown_is_explicit_and_cannot_be_promoted_from_path_existence(tmp_path):
    page, tracks, context = library_page(tmp_path, (FileState.IN_LIBRARY,))
    tracks[0].path.write_bytes(b'synthetic-not-valid-audio')
    unproven = FileFacts(tracks[0].track_id, 10)
    page.set_read_context(replace(context, facts=(unproven,)))
    page.refresh()
    item = page.model.item(0, file_column(page))
    assert item.text() == 'Stan pliku niepotwierdzony'
    assert item.data(FILE_STATE_ROLE) is None
    assert item.background().style() == Qt.BrushStyle.NoBrush
    page.file_filter.setCurrentIndex(page.file_filter.findData('IN_LIBRARY'))
    assert page.model.rowCount() == 0
    assert tracks[0].path.read_bytes() == b'synthetic-not-valid-audio'


def test_stale_history_is_annotated_then_refresh_updates_current_state(tmp_path):
    page, tracks, context = library_page(tmp_path, (FileState.IN_LIBRARY,))
    evaluation = replace(evaluate_file_state(context.facts[0]), is_confirmed=False, reason='STALE_FACTS')
    page.set_file_state_evaluations(context.library_id, {tracks[0].track_id:evaluation})
    page.refresh()
    item = page.model.item(0, file_column(page))
    assert item.text() == 'W bibliotece · Niepotwierdzony'
    assert 'Ostatni potwierdzony stan' in item.toolTip()
    page.set_file_state_evaluations(context.library_id, {tracks[0].track_id:evaluate_file_state(facts_for(tracks[0],FileState.CONFLICT,tmp_path))})
    page.refresh()
    assert page.model.item(0,10).text() == 'Konflikt'
    assert page.model.item(0,10).data(FILE_STATE_ROLE) == FileState.CONFLICT


def test_legend_separates_all_technical_states_from_existing_metadata_categories(tmp_path):
    page, _, _ = library_page(tmp_path)
    legend = install_library_status_legend(page)
    from PySide6.QtWidgets import QDialog, QLabel
    assert legend.menu() is None
    dialog = page.findChild(QDialog, 'LibraryLegendDialog')
    names = dialog.findChildren(QLabel, 'LibraryLegendName')
    assert [label.text() for label in names[5:]] == LABELS
    assert all(label.text() for label in dialog.findChildren(QLabel, 'LibraryLegendDescription'))
    assert [label.text() for label in names[:5]] == ['GOTOWE','DUPLIKAT','DO SPRAWDZENIA','PROBLEM','NIE WYBIERAM']
    apply_static_language(page,'en')
    assert dialog.findChildren(QLabel, 'LibraryLegendHeading')[1].text() == 'TECHNICAL FILE STATES'
    assert names[5].text() == 'In library'
    apply_static_language(page,'pl')
    assert names[5].text() == 'W bibliotece'


def test_file_sort_never_probes_disk_and_preserves_playing_marker(tmp_path, monkeypatch):
    from pathlib import Path
    page, tracks, _ = library_page(tmp_path)
    page.set_playing_track(tracks[2])
    col = file_column(page)
    def forbidden(*a, **k): raise AssertionError('Disk I/O on header sort')
    monkeypatch.setattr(Path,'stat',forbidden)
    for order in [Qt.SortOrder.AscendingOrder,Qt.SortOrder.DescendingOrder]:
        page.table.sortByColumn(col,order)
        playing=[page.model.item(r,0).data(Qt.ItemDataRole.UserRole).track_id for r in range(page.model.rowCount()) if page.model.item(r,0).data(PLAYING_ROLE)]
        assert playing == [tracks[2].track_id]


@pytest.mark.parametrize('order,expected', [
    (Qt.SortOrder.AscendingOrder, [1, 0]),
    (Qt.SortOrder.DescendingOrder, [0, 1]),
])
def test_normal_set_tracks_reload_resorts_changed_states_without_losing_uuid_selection(tmp_path, order, expected):
    page, tracks, context = library_page(tmp_path, (FileState.SOURCE_ONLY, FileState.CONFLICT))
    page.table.sortByColumn(file_column(page), order)
    target = tracks[0]
    page.table.selectRow(row_for(page, target))
    page.model.item(row_for(page, target), 0).setCheckState(Qt.CheckState.Checked)
    swapped = (FileState.CONFLICT, FileState.SOURCE_ONLY)
    page.set_file_state_evaluations(context.library_id, {
        t.track_id:evaluate_file_state(facts_for(t,s,tmp_path)) for t,s in zip(tracks,swapped)})
    # refresh_data() uses this path after replacing cached evaluations.
    page.set_tracks(tracks)
    assert [t.track_id for t in page.visible_tracks()] == [tracks[i].track_id for i in expected]
    assert [t.track_id for t in page._selected_tracks()] == [target.track_id]
    assert page._checked_tracks() == [target]
    assert page.table.horizontalHeader().sortIndicatorSection() == 10
    assert page.table.horizontalHeader().sortIndicatorOrder() == order
