"""Point checks and session display; all physical files are disposable fixtures."""
from dataclasses import replace
from pathlib import Path
import sqlite3
from threading import Event

import pytest

from audio_library_organizer.domain.file_state import (
    FileAvailability, FileFacts, FileObservation, FileState, evaluate_file_state,
)
from audio_library_organizer.jobs import file_reconciliation as checks
from audio_library_organizer.jobs.managed_files import ReadContext, SourceReadMaterial
from audio_library_organizer.ui import library_file_state as display
from test_library_reconciliation_v0427 import library, record, sql_snapshot
from test_library_reconciliation_v0427 import wait_for
from test_legacy_adoption_v0427 import library as adopted_library
from test_adopted_output_spec_v0427 import approve, request
from audio_adoption_fixtures import mp3_samples


def point(repo, track, **kwargs):
    assert hasattr(checks, 'check_track_files'), 'Missing point file check'
    return checks.check_track_files(repo, track.track_id, **kwargs)


def test_point_check_never_inventories_or_loads_other_records(tmp_path, monkeypatch):
    repo, source = library(tmp_path)
    selected = record(repo, source / 'selected.mp3')
    others = [record(repo, source / f'other-{n}.mp3') for n in range(30)]
    before = sql_snapshot(repo)
    def forbidden(*args, **kwargs):
        raise AssertionError('Point check enumerated the library')
    monkeypatch.setattr(checks, 'scan_audio_sources', forbidden)
    original = repo._row_to_track
    loaded = []
    def observed(row):
        loaded.append(row['track_id'])
        return original(row)
    monkeypatch.setattr(repo, '_row_to_track', observed)
    result = point(repo, selected)
    assert {item.track_id for item in result.files} == {selected.track_id}
    assert result.files[0].evaluation.state == FileState.SOURCE_ONLY
    assert result.files[0].evaluation.is_confirmed
    assert set(loaded) == {selected.track_id}
    assert len(sql_snapshot(repo, 'file_state_cache')) == 1
    assert all(repo.get_file_state(t.track_id) is None for t in others)
    assert sql_snapshot(repo) == before


def test_source_delete_restore_and_same_name_elsewhere(tmp_path):
    repo, source = library(tmp_path)
    track = record(repo, source / 'original.mp3')
    data = track.path.read_bytes()
    assert point(repo, track).files[0].evaluation.state == FileState.SOURCE_ONLY
    track.path.unlink()
    (source / 'elsewhere').mkdir()
    (source / 'elsewhere/original.mp3').write_bytes(data)
    missing = point(repo, track).files[0]
    assert missing.evaluation.state == FileState.SOURCE_UNAVAILABLE
    assert missing.evaluation.is_confirmed
    track.path.write_bytes(data)
    restored = point(repo, track).files[0]
    assert restored.evaluation.state == FileState.SOURCE_ONLY and restored.evaluation.is_confirmed
    assert track.path.read_bytes() == data


@pytest.mark.parametrize('failure', ['offline', 'denied', 'alias'])
def test_uncertain_point_check_does_not_confirm_absence(tmp_path, monkeypatch, failure):
    repo, source = library(tmp_path)
    track = record(repo, source / 'one.mp3')
    point(repo, track)
    if failure == 'offline':
        track.path.unlink(); source.rmdir()
    else:
        original = checks.scoped_stat
        def blocked(path, *args, **kwargs):
            if Path(path) == track.path:
                if failure == 'denied':
                    raise PermissionError('controlled denial')
                raise checks.UnsafeSourcePath('ALIAS_OR_MOUNT_UNRESOLVED')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(checks, 'scoped_stat', blocked)
    item = point(repo, track).files[0]
    assert not item.evaluation.is_confirmed
    assert item.source.availability in (FileAvailability.OFFLINE, FileAvailability.ERROR, FileAvailability.UNKNOWN)
    assert item.evaluation.state != FileState.SOURCE_UNAVAILABLE


def test_cancelled_point_check_preserves_cache_and_prior_confirmation(tmp_path):
    repo, source = library(tmp_path)
    track = record(repo, source / 'one.mp3')
    point(repo, track)
    before = sql_snapshot(repo, 'file_state_cache')
    event = Event(); event.set()
    result = point(repo, track, cancelled=event.is_set)
    assert result.cancelled and result.cache_saved == 0
    assert sql_snapshot(repo, 'file_state_cache') == before


def test_point_rejects_metadata_change_before_atomic_commit(tmp_path, monkeypatch):
    repo, source = library(tmp_path)
    track = record(repo, source / 'one.mp3')
    original = repo.save_file_facts_batch
    def changed(facts, **kwargs):
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute('UPDATE tracks SET title=? WHERE track_id=?', ('new title', track.track_id))
        return original(facts, **kwargs)
    monkeypatch.setattr(repo, 'save_file_facts_batch', changed)
    result = point(repo, track)
    assert result.cache_saved == 0 and 'CACHE_WRITE_REJECTED' in result.reason_codes
    assert sql_snapshot(repo, 'file_state_cache') == []


def test_point_result_rejects_context_change_after_cache_commit(tmp_path, monkeypatch):
    repo, source = library(tmp_path); track = record(repo, source / 'one.mp3')
    original = repo.save_file_facts_batch
    def changed(facts, **kwargs):
        result = original(facts, **kwargs)
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute('UPDATE tracks SET title=? WHERE track_id=?', ('newer edit', track.track_id))
        return result
    monkeypatch.setattr(repo, 'save_file_facts_batch', changed)
    result = point(repo, track)
    assert result.cache_saved == 1 and result.display_snapshot is None
    assert 'CHECK_CONTEXT_CHANGED' in result.reason_codes


def test_cancel_during_postcommit_snapshot_is_reported_as_cancelled(tmp_path, monkeypatch):
    repo, source = library(tmp_path); track = record(repo, source / 'one.mp3')
    original = repo.file_check_snapshot; stop = Event(); calls = []
    def snapshot(**kwargs):
        result = original(**kwargs); calls.append(True)
        if len(calls) == 2:
            stop.set()
        return result
    monkeypatch.setattr(repo, 'file_check_snapshot', snapshot)
    result = point(repo, track, cancelled=stop.is_set)
    assert result.cancelled and result.display_snapshot is None
    assert result.pending_output_assessment is None


def evaluation(track, at=100, availability=FileAvailability.PRESENT):
    return evaluate_file_state(FileFacts(track.track_id, at, managed_expected=False,
        source=FileObservation(track.track_id, str(track.path), availability, at, track.source_id)))


def session():
    assert hasattr(display, 'FileStateSession'), 'Missing presentation-only session registry'
    return display.FileStateSession()


def context(repo, track):
    return ReadContext(repo.library_id, str(repo.database_path.parent), tuple(repo.list_sources()),
                       source_materials=(SourceReadMaterial.from_track(track),))


def test_session_retains_confirmation_across_historical_cache_reload(tmp_path):
    repo, source = library(tmp_path)
    track = record(repo, source / 'one.mp3')
    ctx = context(repo, track)
    fresh = evaluation(track)
    historical = replace(fresh, is_confirmed=False, reason='CACHE_REQUIRES_REVALIDATION')
    registry = session()
    assert not registry.evaluation(track, ctx, historical).is_confirmed
    registry.remember(track, ctx, fresh)
    assert registry.evaluation(track, ctx, historical).is_confirmed
    assert not session().evaluation(track, ctx, historical).is_confirmed
    assert registry.evaluation(track, ctx, historical).requires_revalidation
    assert not registry.evaluation(track, ctx, historical).safe_for_file_mutation


def test_confirmed_missing_survives_legacy_availability_cache_sync(tmp_path):
    repo, source = library(tmp_path); track = record(repo, source / 'one.mp3')
    ctx = context(repo, track)
    missing = evaluation(track, availability=FileAvailability.MISSING)
    registry = session(); registry.remember(track, ctx, missing)
    cached_track = replace(track, is_available=False)
    historical = replace(missing, is_confirmed=False, reason='CACHE_REQUIRES_REVALIDATION')
    assert registry.evaluation(cached_track, ctx, historical).is_confirmed


@pytest.mark.parametrize('change', ['library', 'source', 'metadata', 'newer_error'])
def test_session_invalidates_changed_context_or_uncertain_observation(tmp_path, change):
    repo, source = library(tmp_path)
    track = record(repo, source / 'one.mp3')
    ctx = context(repo, track); fresh = evaluation(track)
    registry = session(); registry.remember(track, ctx, fresh)
    historical = replace(fresh, is_confirmed=False, reason='CACHE_REQUIRES_REVALIDATION')
    if change == 'library': ctx = replace(ctx, library_id='other')
    elif change == 'source': track = replace(track, path=source / 'other.mp3')
    elif change == 'metadata': track = replace(track, title='Changed expected output')
    else: historical = replace(historical, checked_at=200, reason='SOURCE_ERROR')
    assert not registry.evaluation(track, ctx, historical).is_confirmed


def test_session_refuses_older_results_and_preserves_confirmation_on_cancel(tmp_path):
    repo, source = library(tmp_path); track = record(repo, source / 'one.mp3'); ctx = context(repo, track)
    registry = session(); latest = evaluation(track, 200)
    registry.remember(track, ctx, latest)
    registry.remember(track, ctx, evaluation(track, 100, FileAvailability.MISSING))
    historical = replace(latest, is_confirmed=False, reason='CACHE_REQUIRES_REVALIDATION')
    current = registry.evaluation(track, ctx, historical)
    assert current.state == FileState.SOURCE_ONLY and current.checked_at == 200 and current.is_confirmed


def test_session_invalidates_foreign_owner_dependency(tmp_path):
    from audio_library_organizer.jobs.managed_files import ManagedReadBinding
    repo, root = library(tmp_path); track = record(repo, root / 'one.mp3')
    own = ManagedReadBinding(repo.library_id, track.track_id, str(root / 'owned.mp3'), 'a' * 64, 'own')
    foreign = ManagedReadBinding(repo.library_id, 'other', str(root / 'other.mp3'), 'b' * 64, 'foreign')
    ctx = replace(context(repo, track), managed_bindings=(own, foreign))
    fresh = evaluation(track); historical = replace(fresh, is_confirmed=False, reason='CACHE_REQUIRES_REVALIDATION')
    registry = session(); registry.remember(track, ctx, fresh)
    changed = replace(ctx, managed_bindings=(own, replace(foreign, revision='new owner proof')))
    assert not registry.evaluation(track, changed, historical).is_confirmed


def test_delivery_rejects_foreign_owner_change(adopted_library):
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui.library_page import LibraryPage
    from audio_library_organizer.jobs.managed_files import ManagedReadBinding
    repo, root, track, _ = adopted_library; approve(adopted_library)
    app = QApplication.instance() or QApplication([])
    page = LibraryPage(); snapshot = repo.file_check_snapshot(); ctx = snapshot.read_context(root)
    foreign = ManagedReadBinding(repo.library_id, 'other', str(root / 'other.mp3'), 'b' * 64, 'new foreign')
    page.set_read_context(replace(ctx, managed_bindings=ctx.managed_bindings + (foreign,)))
    page.set_tracks(list(snapshot.tracks))
    result = point(repo, track, library_root=root)
    assert page.accept_file_check(result) == ()
    page.close(); page.deleteLater()


def test_managed_point_check_never_probes_foreign_outputs(adopted_library, monkeypatch):
    import json
    from uuid import uuid4
    from audio_library_organizer.audio.identity import stat_identity
    from audio_library_organizer.storage.managed_bindings import sqlite_file_ids
    from audio_library_organizer.jobs.managed_files import lexical_locator
    repo, root, track, output = adopted_library; approve(adopted_library)
    foreign_paths = set()
    with sqlite3.connect(repo.database_path) as connection:
        connection.row_factory = sqlite3.Row
        template = dict(connection.execute('SELECT * FROM managed_bindings').fetchone())
    for n in range(8):
        other = record(repo, track.path.with_name(f'other-{n}.mp3'))
        path = root / 'GOTOWE' / f'other-{n}.mp3'; path.write_bytes(output.read_bytes()); foreign_paths.add(path)
        token = stat_identity(path.stat()); dev, ino = sqlite_file_ids(*token[:2])
        row = dict(template, track_id=other.track_id, binding_id=str(uuid4()),
                   relative_path=path.relative_to(root).as_posix(), locator_key=lexical_locator(path),
                   device=dev, inode=ino, stat_json=json.dumps(token))
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute('INSERT INTO managed_bindings (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
    before = sql_snapshot(repo, 'file_state_cache')
    originals = {name: getattr(Path, name) for name in ('stat', 'lstat', 'open')}
    for name, original in originals.items():
        def checked(path, *args, _original=original, **kwargs):
            assert path not in foreign_paths, 'Point check probed a foreign output'
            return _original(path, *args, **kwargs)
        monkeypatch.setattr(Path, name, checked)
    result = point(repo, track, library_root=root)
    assert result.cache_saved == 1 and not result.files[0].evaluation.is_confirmed
    assert result.files[0].facts.managed.availability == FileAvailability.PRESENT
    assert result.pending_output_assessment is None
    after = sql_snapshot(repo, 'file_state_cache')
    assert len(after) == len(before)
    assert all(row in after for row in before if row[0] != track.track_id)


def test_point_action_targets_right_clicked_row_with_multiple_selection(current_start_window):
    from PySide6.QtCore import Qt, QItemSelectionModel
    window = current_start_window
    source = window.app_settings.library.root.parent / 'source'; source.mkdir()
    window.repository.register_source(source)
    tracks = [record(window.repository, source / f'{n}.mp3') for n in range(3)]
    window.refresh_data(); page = window.library
    selection = page.table.selectionModel()
    for row in range(3):
        selection.select(page.model.index(row, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    index = page.model.index(1, 3); target = page.model.item(1, 0).data(Qt.ItemDataRole.UserRole)
    menu = page._build_context_menu(page.table.visualRect(index).center())
    actions = {a.data(): a for a in menu.actions()}
    assert 'check_files' in actions, 'Missing point-check context action'
    assert actions['check_files'].isEnabled()
    selected = []
    page.check_files_requested.disconnect()
    page.check_files_requested.connect(selected.append)
    actions['check_files'].trigger()
    assert selected == [target.track_id]
    menu.deleteLater()


def file_item(page, track):
    from PySide6.QtCore import Qt
    for row in range(page.model.rowCount()):
        if page.model.item(row, 0).data(Qt.ItemDataRole.UserRole).track_id == track.track_id:
            return page.model.item(row, 10)
    raise AssertionError('Track not displayed')


def window_tracks(window):
    source = window.app_settings.library.root.parent / 'source'; source.mkdir()
    window.repository.register_source(source)
    tracks = [record(window.repository, source / f'{n}.mp3') for n in range(2)]
    checks.check_library(window.repository)
    window.refresh_data()
    return tracks


def test_real_point_worker_preserves_other_rows_and_session_on_reload(current_start_window, monkeypatch):
    from PySide6.QtCore import QThread, Qt
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui import workers
    window = current_start_window
    one, two = window_tracks(window)
    assert 'Niepotwierdzony' in file_item(window.library, one).text()

    other_text = file_item(window.library, two).text()
    snapshot = window.repository.file_check_snapshot
    calls = []
    def tracked(**kwargs):
        calls.append((QThread.currentThread() == QApplication.instance().thread(), kwargs))
        return snapshot(**kwargs)
    monkeypatch.setattr(window.repository, 'file_check_snapshot', tracked)
    def no_full(*args, **kwargs):
        raise AssertionError('Point worker called full check')
    monkeypatch.setattr(workers, 'check_library', no_full)
    window._check_track_files(one.track_id)
    wait_for(QApplication.instance(), lambda: window._thread is None)
    assert calls and all(not gui and args.get('track_id') == one.track_id for gui, args in calls)
    assert file_item(window.library, one).text() == 'Tylko źródło'
    assert file_item(window.library, two).text() == other_text
    assert 'Kontrola zakończona' in window.operation_status.text()
    monkeypatch.setattr(window.repository, 'file_check_snapshot', snapshot)
    window.refresh_data()
    window.library.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    window.library.refresh(preserve_order=True)
    assert file_item(window.library, one).text() == 'Tylko źródło'
    assert 'Niepotwierdzony' in file_item(window.library, two).text()
    assert 'Potwierdzone w bieżącej sesji' in file_item(window.library, one).toolTip()
    # A new presentation session must not inherit process-local confirmation.
    window.library._file_state_session = display.FileStateSession()
    window.library.refresh(preserve_order=True)
    assert 'Niepotwierdzony' in file_item(window.library, one).text()


def test_context_actions_work_immediately_after_point_check(current_start_window):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    window = current_start_window; one, two = window_tracks(window)
    window._check_track_files(one.track_id)
    wait_for(QApplication.instance(), lambda: window._thread is None)
    page = window.library
    row = file_item(page, one).row()
    menu = page._build_context_menu(page.table.visualRect(page.model.index(row, 3)).center())
    actions = {a.data(): a for a in menu.actions()}
    page.edit_requested.disconnect(); edited = []
    page.edit_requested.connect(lambda t: edited.append(t.track_id))
    actions['edit'].trigger()
    wait_for(QApplication.instance(), lambda: page._menu_tasks.queue.active is None)
    assert edited == [one.track_id]
    menu.deleteLater()


def test_full_check_confirms_only_credible_rows_and_cancel_retains_previous(current_start_window, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui import workers
    window = current_start_window; one, two = window_tracks(window)
    other_root = one.path.parent.parent / 'offline'; other_root.mkdir()
    window.repository.register_source(other_root)
    offline = record(window.repository, other_root / 'offline.mp3')
    checks.check_library(window.repository); window.refresh_data()
    offline.path.unlink(); other_root.rmdir()
    window._check_library_clicked()
    wait_for(QApplication.instance(), lambda: window._thread is None)
    assert file_item(window.library, one).text() == 'Tylko źródło'
    assert 'Niepotwierdzony' in file_item(window.library, offline).text()
    original = workers.check_library
    entered, release = Event(), Event()
    def blocked(repo, **kwargs):
        entered.set(); assert release.wait(5)
        return original(repo, **kwargs)
    monkeypatch.setattr(workers, 'check_library', blocked)
    before = sql_snapshot(window.repository, 'file_state_cache')
    window._check_library_clicked()
    wait_for(QApplication.instance(), entered.is_set)
    window._worker.cancel(); release.set()
    wait_for(QApplication.instance(), lambda: window._thread is None)
    assert sql_snapshot(window.repository, 'file_state_cache') == before
    assert file_item(window.library, one).text() == 'Tylko źródło'


def test_point_result_after_gui_record_change_is_not_presented(current_start_window):
    window = current_start_window; one, two = window_tracks(window)
    result = point(window.repository, one, operation_id='test-late')
    window._file_check_context = (result.library_id, result.operation_id, window._file_check_generation)
    window._file_check_repository = window.repository
    local = next(t for t in window.library._tracks if t.track_id == one.track_id)
    local.title = 'A later metadata edit'
    window._file_check_finished(result)
    assert 'Niepotwierdzony' in file_item(window.library, one).text()
    assert 'Nie udało się potwierdzić' in window.operation_status.text()


@pytest.mark.parametrize('lang', ['pl', 'en'])
def test_tooltip_uses_local_confirmation_time_and_understandable_reason(tmp_path, lang):
    from datetime import datetime
    assert hasattr(display, 'file_state_tooltip')
    stamp = int(datetime(2026, 11, 13, 21, 35).timestamp() * 1_000_000_000)
    e = evaluate_file_state(FileFacts('track', stamp, conflict=__import__(
        'audio_library_organizer.domain.file_state', fromlist=['ConflictReason']).ConflictReason.MULTIPLE_OWNERS))
    p = display.presentation_from_evaluation(e)
    tooltip = display.file_state_tooltip(p, lang)
    assert '13.11.2026, 21:35' in tooltip
    assert ('więcej niż jednym utworem' if lang == 'pl' else 'more than one track') in tooltip
    assert 'MULTIPLE_OWNERS' not in tooltip
    assert ('bieżącej sesji' if lang == 'pl' else 'current session') in tooltip
    old = display.file_state_tooltip(replace(p, confirmed=False), lang)
    assert ('Stan historyczny' if lang == 'pl' else 'Historical state') in old
    no_date = display.file_state_tooltip(replace(p, last_confirmed_at=None), lang)
    assert '21:35' not in no_date


def test_unconfirmed_adopted_cache_without_history_reason_can_render(adopted_library):
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui.library_page import LibraryPage
    repo, root, track, _ = adopted_library; approve(adopted_library)
    app = QApplication.instance() or QApplication([])
    page = LibraryPage(); snapshot = repo.file_check_snapshot()
    page.set_read_context(snapshot.read_context(root))
    page._file_confirmed_reasons = {tid: state.last_confirmed_reason for tid, state in snapshot.cached}
    page.set_file_state_evaluations(snapshot.library_id, {tid: state.evaluation for tid, state in snapshot.cached})
    page.set_tracks(list(snapshot.tracks))
    assert file_item(page, track).toolTip()
    assert 'None' not in file_item(page, track).toolTip()
    page.close(); page.deleteLater()


def test_point_consumer_preserves_accepted_windows_history(current_start_window, monkeypatch):
    from types import SimpleNamespace
    window = current_start_window; one, two = window_tracks(window)
    result = point(window.repository, one, operation_id='accepted-output-history')
    window._file_check_context = (result.library_id, result.operation_id, window._file_check_generation)
    window._file_check_repository = window.repository
    history = replace(result.files[0].evaluation, state=FileState.NEEDS_UPDATE, is_confirmed=False,
                      reason='OUTPUT_HISTORY_REQUIRES_REVALIDATION')
    def accept_guarded_history(_result):
        window._output_history[one.track_id] = SimpleNamespace(evaluation=history)
    monkeypatch.setattr(window, '_accept_output_delivery', accept_guarded_history)
    window._file_check_finished(result)
    shown = window.library._file_evaluations[one.track_id]
    assert shown.state == FileState.NEEDS_UPDATE and not shown.is_confirmed
    assert 'Do aktualizacji' in file_item(window.library, one).text()
    assert 'Niepotwierdzony' in file_item(window.library, one).text()


def test_confirmed_output_delivery_is_not_masked_by_baseline_session(tmp_path):
    repo, root = library(tmp_path); track = record(repo, root / 'one.mp3'); ctx = context(repo, track)
    registry = session(); baseline = replace(evaluation(track), is_confirmed=False)
    registry.remember(track, ctx, baseline)
    output = replace(evaluation(track), state=FileState.NEEDS_UPDATE, reason='MANAGED_FIELD_DIFFERENCE')
    assert registry.evaluation(track, ctx, output).state == FileState.NEEDS_UPDATE


def test_managed_delete_and_restore_keep_approved_binding(adopted_library):
    repo, root, track, output = adopted_library
    binding = approve(adopted_library)
    data = output.read_bytes()
    result = point(repo, track, library_root=root)
    assert result.files[0].source.availability == FileAvailability.PRESENT
    saved_path = output.with_suffix('.saved')
    output.rename(saved_path)
    absent = point(repo, track, library_root=root).files[0]
    assert absent.evaluation.state == FileState.MANAGED_FILE_MISSING and absent.evaluation.is_confirmed
    saved_path.rename(output)
    restored = point(repo, track, library_root=root).files[0]
    assert restored.facts.managed.availability == FileAvailability.PRESENT
    # The historical missing observation may remain in SQLite; restored bytes
    # alone must not fabricate complete current OutputSpec/P/H/U evidence.
    assert not restored.evaluation.is_confirmed
    assert repo.list_managed_bindings() == (binding,)
    assert output.read_bytes() == data


def test_restored_managed_presence_removes_current_missing_tint_without_promotion(adopted_library):
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui.library_page import LibraryPage
    repo, root, track, output = adopted_library; approve(adopted_library)
    app = QApplication.instance() or QApplication([])
    page = LibraryPage(); snapshot = repo.file_check_snapshot()
    page.set_read_context(snapshot.read_context(root)); page.set_tracks(list(snapshot.tracks))
    saved = output.with_suffix('.saved'); output.rename(saved)
    missing = point(repo, track, library_root=root)
    assert page.accept_file_check(missing) == (track.track_id,)
    page.set_file_state_evaluations(repo.library_id, {track.track_id: replace(missing.files[0].evaluation, is_confirmed=False, reason='CACHE_REQUIRES_REVALIDATION')})
    page.refresh(); assert page._file_presentation(track).state == FileState.MANAGED_FILE_MISSING
    saved.rename(output); restored = point(repo, track, library_root=root)
    page.accept_file_check(restored)
    page.set_file_state_evaluations(repo.library_id, {track.track_id: replace(restored.files[0].evaluation, is_confirmed=False, reason='CACHE_REQUIRES_REVALIDATION')})
    page.refresh(); presentation = page._file_presentation(track)
    assert presentation.state is None and presentation.background is None and not presentation.confirmed
    assert 'jest dostępny' in file_item(page, track).toolTip()
    page.close(); page.deleteLater()


def test_point_adopted_difference_stays_behind_existing_delivery_guard(adopted_library):
    from audio_library_organizer.jobs import adopted_output as ao
    repo, root, track, output = adopted_library
    binding = approve(adopted_library); req = request(ao, repo, track, binding)
    before = (track.path.read_bytes(), output.read_bytes(), sql_snapshot(repo, 'managed_bindings'))
    result = point(repo, track, library_root=root, operation_id=req.operation_id,
                   output_request=req, current_output_request=lambda: req)
    assert result.pending_output_assessment.assessment.difference
    assert result.pending_output_assessment.evaluation.state == FileState.NEEDS_UPDATE
    assert result.output_delivery is None
    assert not repo.get_file_state(track.track_id).evaluation.is_confirmed
    assert before == (track.path.read_bytes(), output.read_bytes(), sql_snapshot(repo, 'managed_bindings'))


def test_missing_managed_result_does_not_try_to_acquire_positive_pair_lease(adopted_library):
    from audio_library_organizer.jobs import adopted_output as ao
    repo, root, track, output = adopted_library; binding = approve(adopted_library)
    req = request(ao, repo, track, binding); output.unlink()
    def forbidden():
        raise AssertionError('Missing file cannot acquire a positive output lease')
    result = point(repo, track, library_root=root, operation_id=req.operation_id,
                   output_request=req, current_output_request=lambda: req, before_output_check=forbidden)
    assert result.files[0].evaluation.state == FileState.MANAGED_FILE_MISSING
    assert result.cache_saved == 1 and result.pending_output_assessment is None


def test_point_full_digest_refuses_same_size_replacement(tmp_path):
    import os
    repo, root = library(tmp_path); track = record(repo, root / 'one.mp3', content=b'AAAA')
    track.path.write_bytes(b'BBBB'); os.utime(track.path, ns=(track.mtime_ns, track.mtime_ns))
    item = point(repo, track).files[0]
    assert not item.evaluation.is_confirmed
    assert item.source.availability == FileAvailability.UNKNOWN


def test_newer_cache_observation_rejects_late_point_result(tmp_path, monkeypatch):
    repo, root = library(tmp_path); track = record(repo, root / 'one.mp3')
    original = repo.save_file_facts_batch
    def newer(facts, **kwargs):
        source = replace(facts[0].source, checked_at=300)
        repo.save_file_facts(replace(facts[0], checked_at=300, source=source))
        return original(facts, **kwargs)
    monkeypatch.setattr(repo, 'save_file_facts_batch', newer)
    result = point(repo, track, checked_at=200)
    assert result.cache_saved == 0 and 'CACHE_WRITE_REJECTED' in result.reason_codes
    assert repo.get_file_state(track.track_id).facts.checked_at == 300


@pytest.mark.parametrize('phase', ['adoption', 'point_snapshot'])
def test_late_cancel_preserves_only_prior_completed_confirmation(current_start_window, monkeypatch, phase):
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.jobs import legacy_adoption
    window = current_start_window; one, two = window_tracks(window)
    window._check_track_files(one.track_id)
    wait_for(QApplication.instance(), lambda: window._thread is None)
    prior_at = window.last_reconciliation_result.files[0].evaluation.last_confirmed_at
    assert file_item(window.library, one).text() == 'Tylko źródło'
    if phase == 'adoption':
        original = legacy_adoption.inventory_legacy_outputs
        def cancelled(*args, **kwargs):
            window._worker.cancel()
            return original(*args, **kwargs)
        monkeypatch.setattr(legacy_adoption, 'inventory_legacy_outputs', cancelled)
        window._check_library_clicked()
    else:
        original = window.repository.file_check_snapshot
        calls = []
        def cancelled(**kwargs):
            result = original(**kwargs); calls.append(True)
            if len(calls) == 2:
                window._worker.cancel()
            return result
        monkeypatch.setattr(window.repository, 'file_check_snapshot', cancelled)
        window._check_track_files(one.track_id)
    wait_for(QApplication.instance(), lambda: window._thread is None)
    assert window.last_reconciliation_result.cancelled
    assert window.last_reconciliation_result.cache_saved > 0
    window.refresh_data()
    assert file_item(window.library, one).text() == 'Tylko źródło'
    current = next(t for t in window.library._tracks if t.track_id == one.track_id)
    assert window.library._file_presentation(current).last_confirmed_at == prior_at
    assert 'Niepotwierdzony' in file_item(window.library, two).text()
    # A later real uncertain observation still revokes the retained proof.
    facts = window.repository.get_file_state(one.track_id).facts
    later = facts.checked_at + 100
    window.repository.save_file_facts(replace(facts, checked_at=later,
        source=replace(facts.source, checked_at=later, availability=FileAvailability.ERROR)))
    window.refresh_data()
    assert 'Niepotwierdzony' in file_item(window.library, one).text()


@pytest.mark.parametrize('delivery_kind', ['none', 'history', 'session'])
def test_queued_point_result_cannot_overwrite_newer_uncertain_display(current_start_window, monkeypatch, delivery_kind):
    window = current_start_window; one, two = window_tracks(window)
    old = point(window.repository, one, operation_id='queued-old-result')
    facts = old.files[0].facts; later = old.checked_at + 100
    window.repository.save_file_facts(replace(facts, checked_at=later,
        source=replace(facts.source, checked_at=later, availability=FileAvailability.ERROR)))
    window.refresh_data()
    assert 'Niepotwierdzony' in file_item(window.library, one).text()
    if delivery_kind != 'none':
        from types import SimpleNamespace
        older = replace(old.files[0].evaluation, state=FileState.NEEDS_UPDATE, is_confirmed=False,
                        reason='OUTPUT_HISTORY_REQUIRES_REVALIDATION')
        def accepted_delivery(result):
            # Reproduce existing H/session display effects on this Linux host;
            # this is not a native NTFS/lease validation.
            window._output_baseline_evals[one.track_id] = result.files[0].evaluation
            if delivery_kind == 'history':
                window._output_history[one.track_id] = SimpleNamespace(evaluation=older)
            else:
                window._output_session[one.track_id] = SimpleNamespace(pending=SimpleNamespace(evaluation=older))
            window._refresh_output_display()
        monkeypatch.setattr(window, '_accept_output_delivery', accepted_delivery)
    window._file_check_context = (old.library_id, old.operation_id, window._file_check_generation)
    window._file_check_repository = window.repository
    window._file_check_finished(old)
    assert window.library._file_evaluations[one.track_id].checked_at == later
    assert 'Niepotwierdzony' in file_item(window.library, one).text()
    assert one.track_id not in window._output_history and one.track_id not in window._output_session


@pytest.mark.parametrize('lang', ['pl', 'en'])
def test_changed_content_tooltip_does_not_claim_current_absence(tmp_path, lang):
    repo, root = library(tmp_path); track = record(repo, root / 'one.mp3', content=b'AAAA')
    point(repo, track)
    track.path.unlink(); point(repo, track)
    track.path.write_bytes(b'BBBB')
    item = point(repo, track).files[0]
    assert not item.evaluation.is_confirmed
    tooltip = display.file_state_tooltip(display.presentation_from_evaluation(item.evaluation), lang)
    assert ('Nie znaleziono pliku źródłowego' if lang == 'pl' else 'The source file was not found') not in tooltip
    assert ('nie udało' if lang == 'pl' else 'could not') in tooltip.lower()
