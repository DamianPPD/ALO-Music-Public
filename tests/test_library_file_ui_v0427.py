"""Stage 4.1: physical file knowledge stays separate from metadata decisions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import pytest
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMenu

from audio_library_organizer.domain.file_state import (
    FileState, FileFacts, FileObservation, FileAvailability, OutputSnapshot,
    Ownership, ConflictReason,
)
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.managed_files import ReadContext
from audio_library_organizer.ui.library_page import LibraryPage
from audio_adoption_fixtures import mp3_samples
from test_legacy_adoption_v0427 import library


def facts_for(track, state, root):
    source = FileObservation(track.track_id, str(track.path), FileAvailability.PRESENT, 10,
                             source_id=track.source_id)
    managed = FileObservation(track.track_id, str(root / (track.track_id+'.mp3')),
                              FileAvailability.PRESENT, 10)
    f = FileFacts(track.track_id, 10, source=source, managed_expected=False)
    if state in (FileState.IN_LIBRARY, FileState.NEEDS_UPDATE, FileState.MANAGED_FILE_MISSING, FileState.CONFLICT):
        snap = OutputSnapshot('test', 1, 'same')
        f = replace(f, managed=managed, managed_expected=True, ownership=Ownership.CONFIRMED,
                    owner_track_id=track.track_id, desired=snap, applied=snap)
    if state == FileState.NEEDS_UPDATE:
        f = replace(f, desired=OutputSnapshot('test', 1, 'changed'))
    elif state == FileState.MANAGED_FILE_MISSING:
        f = replace(f, managed=replace(managed, availability=FileAvailability.MISSING))
    elif state == FileState.SOURCE_UNAVAILABLE:
        f = replace(f, source=replace(source, availability=FileAvailability.MISSING))
    elif state == FileState.CONFLICT:
        f = replace(f, conflict=ConflictReason.TARGET_COLLISION)
    return f


def library_page(tmp_path, states=tuple(FileState)):
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    tracks = [TrackRecord(tmp_path / ('source'+str(i)+'.mp3'), track_id=str(uuid4()),
                         artist='Artist', title='Song '+str(i), genre='House', bpm=120,
                         year='2000', status='review') for i, _ in enumerate(states)]
    facts = tuple(facts_for(t, s, tmp_path / 'managed') for t,s in zip(tracks, states))
    context = ReadContext('test-library', str(tmp_path / 'managed'), facts=facts)
    page.set_read_context(context)
    page.set_tracks(tracks)
    return page, tracks, context


def row_for(page, track):
    return next(r for r in range(page.model.rowCount())
                if page.model.item(r, 0).data(Qt.ItemDataRole.UserRole).track_id == track.track_id)


@pytest.mark.parametrize('state', tuple(FileState))
def test_physical_state_colors_entire_row_without_replacing_metadata_icon(tmp_path, state):
    from audio_library_organizer.ui.library_file_state import FILE_STATE_COLORS, file_state_presentation
    page, tracks, context = library_page(tmp_path, (state,))
    track = tracks[0]
    presentation = file_state_presentation(track, context)
    assert presentation.state == state and presentation.confirmed
    row = row_for(page, track)
    color = FILE_STATE_COLORS[state]
    for column in range(page.model.columnCount()):
        brush = page.model.item(row, column).background()
        assert (brush.color().name() if brush.style() != Qt.BrushStyle.NoBrush else None) == color.background
    assert page.model.columnCount() == 10
    assert 'Plik' not in page.HEADERS
    assert not page.model.item(row, 1).icon().isNull()
    assert track.status == 'review'
    assert presentation.label in page.model.item(row, 3).toolTip()


def test_unknown_or_ambiguous_facts_never_invent_a_state(tmp_path):
    from audio_library_organizer.ui.library_file_state import file_state_presentation
    page, tracks, context = library_page(tmp_path, (FileState.IN_LIBRARY,))
    track = tracks[0]
    f = context.facts[0]
    for facts in ((), (replace(f, is_current=False),), (f, f)):
        p = file_state_presentation(track, replace(context, facts=facts))
        assert p.state is None and not p.confirmed
    assert track.status == 'review'


def test_backend_priorities_and_managed_offline_are_preserved(tmp_path):
    from audio_library_organizer.ui.library_file_state import file_state_presentation
    page, tracks, context = library_page(tmp_path, (FileState.IN_LIBRARY,))
    f = context.facts[0]
    offline = replace(f, source=replace(f.source, availability=FileAvailability.OFFLINE))
    assert file_state_presentation(tracks[0], replace(context, facts=(offline,))).state == FileState.IN_LIBRARY
    missing = replace(offline, managed=replace(f.managed, availability=FileAvailability.MISSING))
    assert file_state_presentation(tracks[0], replace(context, facts=(missing,))).state == FileState.MANAGED_FILE_MISSING
    conflict = replace(missing, conflict=ConflictReason.TARGET_COLLISION)
    assert file_state_presentation(tracks[0], replace(context, facts=(conflict,))).state == FileState.CONFLICT


def test_file_filter_combines_search_sort_and_does_not_write_or_change_status(tmp_path):
    from copy import deepcopy
    page, tracks, context = library_page(tmp_path)
    before = deepcopy(tracks)
    assert page.file_filter.count() == 7
    assert page.file_filter.currentData() == ''
    page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    for track, state in zip(tracks, FileState):
        page.file_filter.setCurrentIndex(page.file_filter.findData(state.value))
        assert [t.track_id for t in page.visible_tracks()] == [track.track_id]
        page.search.setText('no such track')
        assert page.visible_tracks() == []
        page.search.setText('Song')
        assert page.visible_tracks() == [track]
        assert page.table.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    assert tracks == before and context == page._read_context
    page._reset_view()
    assert page.file_filter.currentData() == '' and page.model.rowCount() == 6


def test_file_filter_dots_and_pl_en_labels(tmp_path):
    from audio_library_organizer.ui.i18n import apply_static_language
    from audio_library_organizer.ui.library_file_state import FILE_STATE_COLORS
    page, tracks, context = library_page(tmp_path)
    for state, color in FILE_STATE_COLORS.items():
        index = page.file_filter.findData(state.value)
        assert color.label in page.file_filter.itemText(index)
        icon = page.file_filter.itemIcon(index).pixmap(14, 14).toImage()
        assert icon.pixelColor(7, 7).name() == color.accent
    page.file_filter.setCurrentIndex(2)
    apply_static_language(page, 'en')
    assert page.file_filter.currentText() == 'File: Source only'
    page.refresh()
    assert page.file_filter.currentText() == 'File: Source only'
    apply_static_language(page, 'pl')
    assert page.file_filter.currentText() == 'Plik: Tylko źródło'


def menu_for(page, track):
    page.resize(1500, 850)
    page.show()
    QApplication.processEvents()
    index = page.model.index(row_for(page, track), 3)
    menu = page._build_context_menu(page.table.visualRect(index).center())
    from time import monotonic
    deadline = monotonic() + 4
    while not menu.property('availabilityComplete') and monotonic() < deadline:
        QApplication.processEvents()
    assert menu.property('availabilityComplete'), 'Async menu probe did not complete'
    return menu


def menu_actions(menu):
    result = {}
    for action in menu.actions():
        submenu = QMenu.menuInAction(action)
        if submenu is not None:
            result.update(menu_actions(submenu))
        elif action.data():
            result[action.data()] = action
    return result


@pytest.mark.parametrize('state', tuple(FileState))
def test_menu_all_states_uses_read_resolver_and_only_existing_safe_operations(tmp_path, state):
    page, tracks, context = library_page(tmp_path, (state,))
    menu = menu_for(page, tracks[0])
    actions = menu_actions(menu)
    assert {'edit', 'ready', 'review', 'details'} <= actions.keys()
    assert not {'delete', 'move', 'relink', 'adopt', 'overwrite'} & actions.keys()
    assert not actions['play'].isEnabled()  # No registered source or approved read binding.
    assert not actions['open'].isEnabled()
    emitted = []
    page.edit_requested.connect(emitted.append)
    actions['edit'].trigger()
    settle_context_read(page)
    assert emitted == [tracks[0]]


def test_context_menu_blank_area_and_right_click_preserve_multiselection(tmp_path):
    from PySide6.QtCore import QPoint
    page, tracks, context = library_page(tmp_path)
    page.table.selectRow(row_for(page, tracks[0]))
    selection = page.table.selectionModel()
    selection.select(page.model.index(row_for(page, tracks[1]), 0),
                     QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    before = {t.track_id for t in page._selected_tracks()}
    menu = menu_for(page, tracks[0])
    assert {t.track_id for t in page._selected_tracks()} == before
    assert not {'ready', 'review'} & menu_actions(menu).keys()
    assert page._build_context_menu(QPoint(-1, -1)) is None
    assert {t.track_id for t in page._selected_tracks()} == before


@pytest.mark.parametrize('change', ['switch', 'changed', 'removed', 'close'])
def test_stale_menu_cannot_act_on_changed_record_library_or_closed_page(tmp_path, change):
    page, tracks, context = library_page(tmp_path, (FileState.SOURCE_ONLY,))
    fresh = [context, tracks]
    page.set_context_provider(lambda: tuple(fresh), worker_reader=lambda: lambda: tuple(fresh))
    action = menu_actions(menu_for(page, tracks[0]))['edit']
    emitted = []
    page.edit_requested.connect(emitted.append)
    if change == 'switch':
        fresh[0] = replace(context, library_id='other-library')
    elif change == 'changed':
        fresh[1] = [replace(tracks[0], title='changed in SQLite')]
    elif change == 'removed':
        fresh[1] = []
    else:
        page.close()
    action.trigger()
    settle_context_read(page)
    assert emitted == []


def test_real_sqlite_snapshot_displays_last_confirmed_states_without_claiming_freshness(tmp_path):
    from audio_library_organizer.storage.repository import LibraryRepository
    from audio_library_organizer.ui.library_page import FILE_STATE_ROLE
    QApplication.instance() or QApplication([])
    root = tmp_path / 'library'
    repo = LibraryRepository(root / '.alo/library.sqlite3')
    repo.initialize()
    source = tmp_path / 'sources'
    source.mkdir()
    repo.bootstrap_sources([source])
    tracks = []
    for i, state in enumerate(FileState):
        t = TrackRecord(source / f'{i}.mp3', title=state.value)
        repo.upsert_track(t)
        repo.save_file_facts(facts_for(t, state, root))
        tracks.append(t)
    snapshot = repo.file_check_snapshot()
    context = snapshot.read_context(root)
    assert all(not c.evaluation.is_confirmed for _,c in snapshot.cached)
    assert {c.evaluation.state for _,c in snapshot.cached} == set(FileState)
    before = repo.database_path.read_bytes()
    page = LibraryPage()
    page.set_read_context(context)
    page.set_file_state_evaluations(snapshot.library_id, {tid:c.evaluation for tid,c in snapshot.cached})
    page.set_tracks(list(snapshot.tracks))
    for state in FileState:
        page.file_filter.setCurrentIndex(page.file_filter.findData(state.value))
        assert page.model.rowCount() == 1
        assert page.model.item(0,0).data(FILE_STATE_ROLE) == state
        assert 'ostatni potwierdzony' in page.model.item(0,3).toolTip().lower()
    assert repo.database_path.read_bytes() == before


def settle_context_read(page):
    from PySide6.QtCore import QThreadPool
    from time import monotonic
    deadline = monotonic() + 4
    while page._context_pending is not None and monotonic() < deadline:
        QApplication.processEvents()
    assert QThreadPool.globalInstance().waitForDone(2000)
    QApplication.processEvents()
    assert page._context_pending is None


def adopted_page(library):
    from audio_library_organizer.jobs.legacy_adoption import inventory_legacy_outputs, adopt_legacy_output
    repo, root, track, output = library
    proposal = inventory_legacy_outputs(repo, library_root=root).proposals[0]
    adopt_legacy_output(repo, proposal.proposal_id, confirmed=True, library_root=root)
    snapshot = repo.file_check_snapshot()
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    page.set_read_context(snapshot.read_context(root))
    page.set_file_state_evaluations(snapshot.library_id, {tid:c.evaluation for tid,c in snapshot.cached})
    page.set_tracks(list(snapshot.tracks))
    page.set_context_provider(lambda: (repo.read_context(root), repo.list_tracks()),
                              worker_reader=lambda: lambda: (repo.read_context(root), repo.list_tracks()))
    return page, repo.get_track(track.track_id)


def test_real_adopted_managed_read_with_source_offline_is_read_only(library):
    import hashlib
    page, track = adopted_page(library)
    repo, root, _, output = library
    # Move only this synthetic SOURCE out of the registered path.
    offline = track.path.with_suffix('.offline')
    track.path.rename(offline)
    database_before = repo.database_path.read_bytes()
    binding_before = repo.list_managed_bindings()
    audio_before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (offline, output)}
    emitted = []
    page.play_requested.connect(emitted.append)
    action = menu_actions(menu_for(page, track))['play']
    assert action.isEnabled()
    action.trigger()
    settle_context_read(page)
    assert [t.track_id for t in emitted] == [track.track_id]
    assert repo.database_path.read_bytes() == database_before
    assert repo.list_managed_bindings() == binding_before
    assert audio_before == {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (offline, output)}


def test_managed_specific_folder_never_falls_back_after_wrong_sha(library, monkeypatch):
    from audio_library_organizer.ui import library_page as module
    page, track = adopted_page(library)
    repo, root, _, output = library
    output.write_bytes(output.read_bytes()+b'controlled synthetic change')
    opened = []
    monkeypatch.setattr(module.QDesktopServices, 'openUrl', lambda url: opened.append(url.toLocalFile()) or True)
    action = menu_actions(menu_for(page, track))['reveal_managed']
    assert action.isEnabled()
    action.trigger()
    settle_context_read(page)
    assert opened == []
    # Generic playback may still safely fall back to the registered SOURCE.
    played = []
    page.play_requested.connect(played.append)
    menu_actions(menu_for(page, track))['play'].trigger()
    settle_context_read(page)
    assert len(played) == 1


def test_wrong_sha_and_missing_source_cannot_emit_play_or_open(library, monkeypatch):
    from audio_library_organizer.ui import library_page as module
    page, track = adopted_page(library)
    repo, root, _, output = library
    track.path.rename(track.path.with_suffix('.offline'))
    output.write_bytes(output.read_bytes()+b'changed after adoption')
    played, opened = [], []
    page.play_requested.connect(played.append)
    monkeypatch.setattr(module.QDesktopServices, 'openUrl', lambda url: opened.append(url) or True)
    for name in ('play', 'open'):
        menu_actions(menu_for(page, track))[name].trigger()
        settle_context_read(page)
    assert played == opened == []


@pytest.mark.parametrize('change', ['source', 'binding', 'record', 'cancel', 'close'])
def test_active_real_read_task_drops_results_after_change_or_close(library, monkeypatch, change):
    from threading import Event
    from audio_library_organizer.ui import library_page as module
    from audio_library_organizer.jobs import context_menu as context_jobs
    real_read_material = context_jobs.read_material
    page, track = adopted_page(library)
    repo, root, _, output = library
    entered, release = Event(), Event()
    def barrier_task(plan, reader, *, cancelled=None):
        def gated_reader(path):
            entered.set()
            assert release.wait(4), 'Test barrier was not released'
            return reader(path)
        return real_read_material(plan, gated_reader, cancelled=cancelled)
    monkeypatch.setattr(context_jobs, 'read_material', barrier_task)
    played = []
    page.play_requested.connect(played.append)
    menu_actions(menu_for(page, track))['play'].trigger()
    try:
        assert entered.wait(3)
        if change == 'source':
            page.set_read_context(replace(page._read_context, library_id='different-library'))
        elif change == 'binding':
            # The fresh provider sees a changed immutable proof before delivery.
            current = page._read_context
            proof = replace(current.managed_bindings[0], sha256='0'*64)
            captured_tracks = tuple(page._tracks)
            provider = lambda: (replace(current, managed_bindings=(proof,)), captured_tracks)
            page.set_context_provider(provider, worker_reader=lambda: provider)
        elif change == 'record':
            fresh = repo.get_track(track.track_id)
            fresh.title = 'Concurrent manual edit'
            repo.upsert_track(fresh)
        elif change == 'cancel':
            page.cancel_context_actions()
        else:
            page.close()
    finally:
        release.set()
        settle_context_read(page)
    assert played == []


@pytest.mark.parametrize('state', tuple(FileState))
def test_rendered_file_tints_hover_and_selection_have_independent_priority(tmp_path, state):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QPoint
    from audio_library_organizer.ui.library_file_state import FILE_STATE_COLORS
    from audio_library_organizer.ui.library_page import SELECTED_BACKGROUND, HOVER_BACKGROUND
    from audio_library_organizer.ui.theme import DARK_STYLE
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    page, tracks, _ = library_page(tmp_path, (state,))
    try:
        page.detail.hide()
        page.resize(1500, 450)
        page.show()
        page.table.clearSelection()
        QTest.mouseMove(page, QPoint(1, 1))
        app.processEvents()
        def color(column):
            pixmap = page.table.viewport().grab()
            rect = page.table.visualRect(page.model.index(0, column))
            scale = pixmap.devicePixelRatio()
            return pixmap.toImage().pixelColor(round((rect.left()+12)*scale), round((rect.top()+5)*scale)).name()
        expected = FILE_STATE_COLORS[state].background or '#11171e'
        assert color(3) == color(8) == expected
        QTest.mouseMove(page.table.viewport(), page.table.visualRect(page.model.index(0,3)).center())
        app.processEvents()
        assert color(3) == HOVER_BACKGROUND.name()
        page.table.selectRow(0)
        app.processEvents()
        assert color(3) == color(8) == SELECTED_BACKGROUND.name()
    finally:
        page.close()
        app.setStyleSheet(previous)


def test_binding_changed_history_and_cross_library_ids_never_reuse_selection(tmp_path):
    from audio_library_organizer.ui.library_file_state import presentation_from_evaluation
    from audio_library_organizer.domain.file_state import evaluate_file_state
    page, tracks, context = library_page(tmp_path, (FileState.IN_LIBRARY,))
    changed = replace(evaluate_file_state(context.facts[0]), reason='TRACK_BINDING_CHANGED', is_confirmed=False)
    assert presentation_from_evaluation(changed).state is None
    page.table.selectRow(0)
    page.set_read_context(replace(context, library_id='other-library', facts=()))
    page.set_tracks([replace(tracks[0], title='Other library same UUID')])
    assert page.table.selectionModel().selectedRows() == []
    assert not page.table.currentIndex().isValid()


@pytest.mark.parametrize('action_name', ['playlist', 'collection'])
def test_source_multiselection_after_sort_dispatches_exact_captured_uuids(tmp_path, action_name):
    from audio_library_organizer.storage.repository import LibraryRepository
    repo = LibraryRepository(tmp_path / 'library/.alo/library.sqlite3')
    repo.initialize()
    source = tmp_path / 'source'
    source.mkdir()
    repo.bootstrap_sources([source])
    for i in range(3):
        path = source / f'{i}.wav'
        path.write_bytes(b'Synthetic read-only test material '+bytes([i]))
        stat = path.stat()
        repo.upsert_track(TrackRecord(path, title=f'Song {i}', size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns))
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    page.set_read_context(repo.read_context(tmp_path / 'library'))
    tracks = repo.list_tracks()
    page.set_tracks(tracks)
    page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    page.search.setText('Song')
    page.table.selectRow(0)
    page.table.selectionModel().select(page.model.index(2,0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    selected = page._selected_tracks()
    menu = menu_for(page, selected[0])
    emitted = []
    signal = page.context_playlist_requested if action_name == 'playlist' else page.context_collection_requested
    signal.connect(emitted.append)
    action = menu_actions(menu)[action_name]
    assert action.isEnabled()
    action.trigger()
    settle_context_read(page)
    assert len(emitted) == 1
    if action_name == 'playlist':
        assert set(emitted[0][1]) == {t.path for t in selected}
    else:
        assert {t.track_id for t in emitted[0][1]} == {t.track_id for t in selected}


def test_offline_managed_does_not_enable_source_only_copy_actions(library):
    page, track = adopted_page(library)
    track.path.rename(track.path.with_suffix('.offline'))
    actions = menu_actions(menu_for(page, track))
    assert actions['play'].isEnabled()
    assert not actions['collection'].isEnabled() and not actions['playlist'].isEnabled()


def test_fresh_cache_change_or_quit_rejects_open_menu_actions(tmp_path):
    from audio_library_organizer.domain.file_state import evaluate_file_state
    page, tracks, context = library_page(tmp_path, (FileState.IN_LIBRARY,))
    evaluation = evaluate_file_state(context.facts[0])
    page.set_file_state_evaluations(context.library_id, {tracks[0].track_id:evaluation})
    fresh = [context, tracks, dict(page._file_evaluations)]
    page.set_context_provider(lambda: tuple(fresh), worker_reader=lambda: lambda: tuple(fresh))
    action = menu_actions(menu_for(page, tracks[0]))['edit']
    emitted = []
    page.edit_requested.connect(emitted.append)
    fresh[2] = {tracks[0].track_id:replace(evaluation, checked_at=11)}
    action.trigger()
    settle_context_read(page)
    assert emitted == []
    fresh[2] = dict(page._file_evaluations)
    action = menu_actions(menu_for(page, tracks[0]))['edit']
    page._context_quit()
    action.trigger()
    settle_context_read(page)
    assert emitted == []


def test_real_mainwindow_snapshot_provider_and_existing_editor_player(current_start_window, tmp_path):
    from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
    from PySide6.QtMultimedia import QMediaPlayer
    window = current_start_window
    source = tmp_path / 'synthetic-source'
    source.mkdir()
    path = source / 'one.wav'
    path.write_bytes(b'isolated synthetic metadata fixture')
    window.repository.replace_sources([source])
    track = TrackRecord(path, artist='Fixture', title='Original', status='review')
    window.repository.upsert_track(track)
    window.refresh_data()
    context, tracks, evaluations = window._library_context_snapshot()
    assert context.library_id == window.repository.library_id
    assert tracks == window.library._tracks
    assert evaluations == window.library._file_evaluations
    assert isinstance(window.player.player, QMediaPlayer)
    editor = MetadataEditorDialog(tracks[0], window, read_context=context)
    assert editor.library_id == window.repository.library_id
    # This component test does not simulate a user's close-guard decision.
    # done() runs the real read-task teardown without entering that modal guard.
    from PySide6.QtWidgets import QDialog
    editor.done(QDialog.DialogCode.Rejected)
    assert window.repository.get_track(track.track_id).title == 'Original'


def test_ignored_mainwindow_close_does_not_permanently_disable_library(current_start_window):
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    from PySide6.QtGui import QCloseEvent
    window = current_start_window
    worker = FileReconciliationWorker(window.repository, library_id=window.repository.library_id,
                                      operation_id='close-branch-test')
    window._worker = worker
    try:
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted()
        assert not window.library._context_closed
    finally:
        window._worker = None


def test_delegate_preserves_checkbox_hover_while_overriding_row_hover(tmp_path, monkeypatch):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem, QStyle
    from audio_library_organizer.ui import library_page as module
    page, tracks, context = library_page(tmp_path, (FileState.SOURCE_ONLY,))
    seen = []
    original = module._paint_library_checkbox
    def observe(painter, square, state, hovered=False):
        seen.append(hovered)
        original(painter, square, state, hovered)
    monkeypatch.setattr(module, '_paint_library_checkbox', observe)
    image = QImage(50, 40, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    option = QStyleOptionViewItem()
    option.rect = QRect(0,0,50,40)
    option.widget = page.table
    option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_MouseOver
    try:
        page.table.itemDelegate().paint(painter, option, page.model.index(0,0))
    finally:
        painter.end()
    assert seen == [True]
