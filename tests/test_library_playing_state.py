"""Playback notifications must preserve the view's active model/index objects."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPersistentModelIndex, Qt
import pytest

from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtGui import QBrush
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.library_page import LibraryPage, PLAYING_ROLE, PLAYING_BACKGROUND
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.player import PlayerBar


def test_double_click_playback_never_removes_rows_or_invalidates_active_index(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    page, player = LibraryPage(), PlayerBar()
    tracks = [TrackRecord(path=tmp_path / f'{i}.mp3', title=f'Song {i}') for i in range(3)]
    page.set_tracks(tracks)
    page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    page.table.selectRow(1)
    index = page.table.currentIndex()
    persistent = QPersistentModelIndex(index)
    active_track = page._current_track()
    # Keep the actual load_track/track_changed signal path; audio is independent
    # of the model mutation under investigation.
    monkeypatch.setattr(player, 'load', lambda *args, **kwargs: None)
    player.track_changed.connect(page.set_playing_track)
    inside_playback = False
    removed_inside_playback = []

    def play(track):
        nonlocal inside_playback
        inside_playback = True
        try:
            player.load_track(track, autoplay=False)
        finally:
            inside_playback = False

    page.play_requested.connect(play)
    page.model.rowsAboutToBeRemoved.connect(
        lambda *args: removed_inside_playback.append(inside_playback))
    removed = QSignalSpy(page.model.rowsRemoved)
    inserted = QSignalSpy(page.model.rowsInserted)
    reset = QSignalSpy(page.model.modelReset)
    selection_changed = QSignalSpy(page.table.selectionModel().selectionChanged)
    detail_changed = QSignalSpy(page.track_selected)
    try:
        # The view's doubleClicked slot and the complete playback notification
        # chain run synchronously before this emission returns.
        page.table.doubleClicked.emit(index)
        assert removed_inside_playback == []
        assert removed.count() == inserted.count() == reset.count() == 0
        assert persistent.isValid() and persistent == page.table.currentIndex()
        assert page._current_track() is active_track
        assert selection_changed.count() == detail_changed.count() == 0
        assert page.model.item(persistent.row(), 0).data(PLAYING_ROLE) is True
        app.processEvents()
        assert removed.count() == inserted.count() == reset.count() == 0
    finally:
        page.close(); player.close()


def _row(page, track):
    return next(row for row in range(page.model.rowCount())
                if page._path_key(page.model.item(row, 0).data(Qt.ItemDataRole.UserRole)) == page._path_key(track))


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_playing_updates_only_old_and_new_rows_and_restores_status_presentation(tmp_path, language):
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    tracks = [
        TrackRecord(path=tmp_path / 'ready.mp3', artist='Artist', title='Ready', status='ready',
                    year='2008', genre='House', bpm=120,
                    locked_fields={'__status__', '__online_lock__'}),
        TrackRecord(path=tmp_path / 'review.flac', artist='Artist', title='Review', status='review',
                    size_bytes=800000, duration_seconds=180, codec='FLAC'),
        TrackRecord(path=tmp_path / 'problem.wav', title='Problem', status='review'),
        TrackRecord(path=tmp_path / 'error.m4a', title='Error', status='error'),
        TrackRecord(path=tmp_path / 'chosen.mp3', artist='Artist', title='Chosen', status='duplicate',
                    locked_fields={'duplicate_primary'}),
        TrackRecord(path=tmp_path / 'unselected.mp3', title='Unselected', status='not_selected'),
    ]
    apply_static_language(page, language)
    page.set_tracks(tracks)
    page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    page.select_track(tracks[1])
    page.model.item(_row(page, tracks[1]), 0).setCheckState(Qt.CheckState.Checked)
    rows = {page._path_key(track): _row(page, track) for track in tracks}
    bases = {row: ([page.model.item(row, col).background() for col in range(page.model.columnCount())],
                   page.model.item(row, 1).toolTip(), page.model.item(row, 1).icon().cacheKey(),
                   page.model.item(row, 1).text()) for row in rows.values()}
    identities = [[page.model.item(row, col) for col in range(page.model.columnCount())]
                  for row in range(page.model.rowCount())]
    current = QPersistentModelIndex(page.table.currentIndex())
    checked = page._checked_paths.copy()
    changes = []
    page.model.dataChanged.connect(lambda top, bottom, roles: changes.append((top.row(), bottom.row(), roles)))
    try:
        old_row = None
        for track in [*tracks, None]:
            changes.clear()
            new_row = _row(page, track) if track else None
            page.set_playing_track(track)
            assert {first for first, last, roles in changes} == {r for r in (old_row, new_row) if r is not None}
            assert all(first == last and int(Qt.ItemDataRole.DisplayRole) not in roles
                       and int(Qt.ItemDataRole.CheckStateRole) not in roles for first, last, roles in changes)
            for row, (backgrounds, tooltip, icon_key, status_text) in bases.items():
                playing = row == new_row
                for column in range(page.model.columnCount()):
                    item = page.model.item(row, column)
                    assert item is identities[row][column]
                    assert bool(item.data(PLAYING_ROLE)) == playing
                    expected_background = QBrush(PLAYING_BACKGROUND) if playing else backgrounds[column]
                    assert item.background() == expected_background
                status = page.model.item(row, 1)
                assert status.icon().cacheKey() == icon_key and status.text() == status_text
                assert status.data(Qt.ItemDataRole.AccessibleTextRole) == status.toolTip()
                if not playing:
                    assert status.toolTip() == tooltip
                else:
                    assert ('TERAZ GRA' if language == 'pl' else 'NOW PLAYING') in status.toolTip()
            assert current.isValid() and current == page.table.currentIndex()
            assert page._checked_paths == checked
            assert page.table.horizontalHeader().checkState() == Qt.CheckState.PartiallyChecked
            assert page.selected_count.text().endswith('1')
            old_row = new_row
        changes.clear()
        page.set_playing_track(None)
        assert changes == []
    finally:
        page.close()


def test_hidden_playing_track_is_applied_when_filter_clears_without_playback_rebuild(tmp_path):
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    tracks = [TrackRecord(path=tmp_path / 'A.mp3', title='Alpha'),
              TrackRecord(path=tmp_path / 'B.flac', title='Beta')]
    page.set_tracks(tracks)
    page.set_playing_track(tracks[0])
    page.search.setText('Alpha')
    current = QPersistentModelIndex(page.model.index(0, 0))
    removed = QSignalSpy(page.model.rowsRemoved)
    try:
        # A different record object representing the same stable path is valid.
        page.set_playing_track(TrackRecord(path=tracks[1].path))
        assert current.isValid() and removed.count() == 0
        assert not page.model.item(0, 0).data(PLAYING_ROLE)
        page.search.clear()  # Filter changes still perform their ordinary refresh.
        assert page.model.item(_row(page, tracks[1]), 0).data(PLAYING_ROLE) is True
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
        removed_after_filter = removed.count()
        page.set_playing_track(None)
        assert removed.count() == removed_after_filter
        page.format_filter.setCurrentIndex(0)
        assert all(not page.model.item(row, 0).data(PLAYING_ROLE) for row in range(2))
    finally:
        page.close()


@pytest.mark.parametrize('filtered', [False, True])
def test_100_real_double_clicks_with_sort_checks_and_details_preserve_model(tmp_path, monkeypatch, filtered):
    app = QApplication.instance() or QApplication([])
    page, player = LibraryPage(), PlayerBar()
    tracks = [TrackRecord(path=tmp_path / f'{i}.mp3', artist='Artist', title=f'Song {i}',
                          album='Album', genre='House', year='2008', bpm=120) for i in range(6)]
    tracks.append(TrackRecord(path=tmp_path / 'hidden.flac', title='Hidden'))
    page.set_tracks(tracks)
    if filtered:
        page.search.setText('Song')
        page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
    page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    page.resize(1600, 900); page.show(); app.processEvents()
    monkeypatch.setattr(player, 'load', lambda *args, **kwargs: None)
    player.track_changed.connect(page.set_playing_track)
    page.play_requested.connect(lambda track: player.load_track(track, autoplay=False))
    page.queue_next_requested.connect(player.queue_next)
    page.model.item(0, 0).setCheckState(Qt.CheckState.Checked)
    page.model.item(2, 0).setCheckState(Qt.CheckState.Checked)
    checked = page._checked_paths.copy()
    order = page.visible_tracks()
    identities = [page.model.item(row, 0) for row in range(page.model.rowCount())]
    persistent = [QPersistentModelIndex(page.model.index(row, 3)) for row in range(page.model.rowCount())]
    removed, inserted, reset = (QSignalSpy(page.model.rowsRemoved), QSignalSpy(page.model.rowsInserted),
                                QSignalSpy(page.model.modelReset))
    layout_changed = QSignalSpy(page.model.layoutChanged)
    plays = QSignalSpy(page.play_requested)
    qt_messages = []
    previous_handler = qInstallMessageHandler(lambda kind, context, message: qt_messages.append(message))
    try:
        for i in range(100):
            row = i % len(order)
            index = page.model.index(row, 3)
            center = page.table.visualRect(index).center()
            before = plays.count()
            QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=center, delay=0)
            assert plays.count() == before  # Single click remains selection only.
            QTest.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=center, delay=0)
            QTest.mouseRelease(page.table.viewport(), Qt.MouseButton.LeftButton, pos=center, delay=0)
            app.processEvents()
            assert plays.count() == before + 1
            assert page._current_track() is order[row] and player.current_track is order[row]
            assert page.detail.isVisible() and page.detail_labels['title'].text() == order[row].title
            assert persistent[row].isValid() and persistent[row] == page.table.currentIndex()
            assert page.visible_tracks() == order
            assert page._checked_paths == page._visible_checked_paths() == checked
            assert page.table.horizontalHeader().checkState() == Qt.CheckState.PartiallyChecked
            assert [page.model.item(r, 0).data(PLAYING_ROLE) for r in range(len(order))] == [r == row for r in range(len(order))]
        assert removed.count() == inserted.count() == reset.count() == layout_changed.count() == 0
        assert all(index.isValid() for index in persistent)
        assert all(page.model.item(row, 0) is item for row, item in enumerate(identities))
        assert not [message for message in qt_messages if 'index' in message.lower() or 'model' in message.lower()]
        page.table.horizontalHeader().toggleVisibleChecks()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Checked
        page.table.horizontalHeader().toggleVisibleChecks()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
        page.queue_next_requested.emit(order[0])
        assert player.queued_track is order[0]
        edits = QSignalSpy(page.edit_requested)
        page.detail_edit.click()
        assert edits.count() == 1 and edits.at(0)[0] is page._current_track()
    finally:
        qInstallMessageHandler(previous_handler)
        page.close(); player.close()
