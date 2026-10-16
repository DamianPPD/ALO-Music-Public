"""Production SQLite bindings, worker barriers and explicit approval UI."""
import importlib
import importlib.util
from pathlib import Path
from time import monotonic

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication

from audio_adoption_fixtures import mp3_samples, copy_audio
from test_legacy_adoption_v0427 import library, inventory, adoption_api
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.domain.file_state import FileState, FileAvailability
from audio_library_organizer.jobs.managed_files import ReadPurpose, MaterialKind, resolve_read_path, read_material
from audio_library_organizer.storage.repository import LibraryRepository


@pytest.fixture
def app():
    app = QApplication.instance() or QApplication([])
    previous_style = app.styleSheet()
    try:
        yield app
    finally:
        try:
            assert QThreadPool.globalInstance().waitForDone(5000)
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        finally:
            app.setStyleSheet(previous_style)


def approved(library):
    repo, root, _, _ = library
    proposal = inventory(library).proposals[0]
    return adoption_api().adopt_legacy_output(repo, proposal.proposal_id, confirmed=True, library_root=root)


def context(repository, root):
    reader = getattr(repository, 'read_context', None)
    assert callable(reader), 'Persistent approved bindings must feed the production read resolver'
    return reader(root)


@pytest.mark.parametrize('purpose', list(ReadPurpose))
def test_restart_reads_approved_managed_without_injected_evidence(library, purpose):
    repo, root, track, output = library
    binding = approved(library)
    track.path.unlink()
    restarted = LibraryRepository(repo.database_path); restarted.initialize()
    saved = restarted.get_track(track.track_id)
    ctx = context(restarted, root)
    assert ctx.managed_bindings[0].revision == binding.binding_id
    plan = resolve_read_path(saved, ctx, purpose)
    result = read_material(plan, lambda path: path.read_bytes())
    assert result.resolution.is_verified and result.resolution.kind == MaterialKind.MANAGED
    assert result.value == output.read_bytes()
    assert saved.track_id == track.track_id and saved.source_id == track.source_id
    assert saved.title == track.title and saved.locked_fields == track.locked_fields


def test_production_reconciliation_uses_binding_and_detects_external_changes(library):
    from audio_library_organizer.jobs.file_reconciliation import check_library
    repo, root, track, output = library
    binding = approved(library)
    result = check_library(repo, library_root=root)
    facts = next(f.facts for f in result.files if f.track_id == track.track_id)
    assert facts.managed_expected and facts.owner_track_id == track.track_id
    assert facts.applied.value == binding.applied_snapshot['value']
    assert facts.managed.availability == FileAvailability.PRESENT and facts.managed.is_current
    output.write_bytes(output.read_bytes() + b'foreign bytes')
    changed = check_library(repo, library_root=root)
    record = next(f for f in changed.files if f.track_id == track.track_id)
    assert record.evaluation.state == FileState.CONFLICT
    assert repo.list_managed_bindings()[0].binding_id == binding.binding_id


def test_export_worker_blocks_suffix_copy_when_adoption_is_unresolved(library, app):
    from audio_library_organizer.jobs.exporter import ExportPlan
    from audio_library_organizer.ui.workers import ExportWorker
    import inspect
    repo, root, track, output = library
    copy_audio(output, root/'NIE_WYBRANE'/'second (2).mp3')
    assert 'adoption_repository' in inspect.signature(ExportWorker).parameters, 'Missing actual worker export barrier'
    before = {str(p): p.read_bytes() for p in root.rglob('*.mp3')}
    worker = ExportWorker(ExportPlan.from_tracks([track], LibraryPaths(root)),
                          adoption_repository=repo, library_root=root)
    errors, successes = [], []
    worker.failed.connect(errors.append); worker.finished.connect(successes.append)
    worker.run()
    assert errors and not successes
    assert {str(p): p.read_bytes() for p in root.rglob('*.mp3')} == before


def dialog_api():
    name='audio_library_organizer.ui.adoption_dialog'
    assert importlib.util.find_spec(name) is not None, 'Missing explicit adoption confirmation UI'
    return importlib.import_module(name)


def test_dialog_has_no_default_approval_and_discloses_validation(library, app):
    repo, root, track, output = library
    result = inventory(library)
    dialog = dialog_api().LegacyAdoptionDialog(result)
    approved_ids=[]; dialog.approve_requested.connect(approved_ids.append)
    assert dialog.table.currentRow() == -1 and not dialog.confirm_check.isChecked()
    assert not dialog.approve_button.isEnabled() and not approved_ids
    dialog.table.selectRow(0)
    details=dialog.details.toPlainText()
    for value in (track.track_id, result.library_id, str(output), result.proposals[0].audio_algorithm):
        assert value in details
    assert not dialog.approve_button.isEnabled()
    dialog.confirm_check.setChecked(True)
    assert dialog.approve_button.isEnabled()
    dialog.approve_button.click()
    assert approved_ids == [result.proposals[0].proposal_id]
    assert repo.list_managed_bindings() == ()  # a UI signal cannot confer ownership
    dialog.close()


def test_dialog_cannot_confirm_conflicting_rows(library, app):
    repo, root, _, output = library
    copy_audio(output, root/'DO_SPRAWDZENIA'/'copy.mp3')
    dialog=dialog_api().LegacyAdoptionDialog(inventory(library))
    approved_ids=[]; dialog.approve_requested.connect(approved_ids.append)
    dialog.table.selectRow(0); dialog.confirm_check.setChecked(True)
    assert not dialog.approve_button.isEnabled()
    assert not approved_ids and repo.list_managed_bindings() == ()
    dialog.close()


def make_window(library, tmp_path):
    from PySide6.QtCore import QSettings
    from audio_library_organizer.domain.settings import AppSettings
    from audio_library_organizer.ui.main_window import MainWindow
    _, root, track, _ = library
    store = QSettings(str(tmp_path/'window.ini'), QSettings.Format.IniFormat)
    return MainWindow(AppSettings((track.path.parent,), LibraryPaths(root)), store)


def wait(app, predicate):
    deadline=monotonic()+10
    while not predicate() and monotonic()<deadline:
        app.processEvents()
    assert predicate(), 'Adoption worker did not finish its bounded operation'


def test_main_window_loads_authoritative_binding_on_restart(library, app, tmp_path):
    repo, root, track, output = library
    binding=approved(library); track.path.unlink()
    window=make_window(library,tmp_path)
    try:
        assert window._read_context.managed_bindings, 'MainWindow has not loaded persistent managed ownership'
        plan=resolve_read_path(repo.get_track(track.track_id),window._read_context,ReadPurpose.PLAYBACK)
        assert plan.locator==str(output) and plan.expected_sha256==binding.expected_sha256
    finally:
        window.close()


def test_check_and_user_confirmation_are_the_only_production_adoption_path(library, app, tmp_path):
    repo,root,track,output=library
    window=make_window(library,tmp_path)
    try:
        assert hasattr(window,'adoption_btn'), 'Missing minimal review-to-approval entry point'
        assert window.adoption_btn.isHidden() and repo.list_managed_bindings()==()
        window._check_library_clicked()
        wait(app,lambda:window._thread is None)
        result=window.last_reconciliation_result
        assert result.adoption_inventory is not None and repo.list_managed_bindings()==()
        assert not window.adoption_btn.isHidden()
        window.adoption_btn.click()
        dialog=window._adoption_dialog
        assert dialog is not None and not dialog.approve_button.isEnabled()
        dialog.table.selectRow(0); dialog.confirm_check.setChecked(True)
        dialog.approve_button.click()
        wait(app,lambda:window._thread is None)
        assert len(repo.list_managed_bindings())==1
        assert window._read_context.managed_bindings
        assert window.adoption_btn.isHidden()
    finally:
        window.close()


def test_file_check_teardown_finishes_in_worker_thread_before_gui_is_idle(library, app, tmp_path, monkeypatch):
    """finished is emitted before deferred deletion: idle must await native teardown."""
    from PySide6.QtCore import QEventLoop, QThread, Qt
    import shiboken6
    window = make_window(library, tmp_path)
    destroyed_threads, premature_idle = [], []
    original_busy = window._set_busy

    def set_busy(busy, *args, **kwargs):
        if not busy and not destroyed_threads:
            premature_idle.append(True)
        return original_busy(busy, *args, **kwargs)

    monkeypatch.setattr(window, '_set_busy', set_busy)
    try:
        window._check_library_clicked()
        thread = window._thread
        worker_thread = shiboken6.getCppPointer(thread)[0]
        window._worker.destroyed.connect(
            lambda: destroyed_threads.append(shiboken6.getCppPointer(QThread.currentThread())[0]),
            Qt.ConnectionType.DirectConnection)
        loop = QEventLoop()
        thread.finished.connect(loop.quit, Qt.ConnectionType.QueuedConnection)
        loop.exec()
        assert window._thread is None and window._worker is None
        assert not premature_idle, 'GUI became idle while native worker teardown was pending'
        assert destroyed_threads == [worker_thread], 'Python released an owned worker in the GUI thread'
    finally:
        window.close()


def test_wrong_root_cannot_forge_a_read_binding(library):
    repo,root,_,_=library; approved(library)
    with pytest.raises(ValueError,match='root|Root'):
        context(repo,root.parent/'foreign')


def test_production_adoption_runs_in_worker_affinity_not_gui(library, app, tmp_path, monkeypatch):
    from PySide6.QtCore import QEventLoop, QThread, Qt
    import shiboken6
    adoption = adoption_api()
    original_adopt = adoption.adopt_legacy_output
    execution_threads = []

    def adopt(*args, **kwargs):
        execution_threads.append(shiboken6.getCppPointer(QThread.currentThread())[0])
        return original_adopt(*args, **kwargs)

    window = make_window(library, tmp_path)
    try:
        window._check_library_clicked()
        wait(app, lambda: window._thread is None)
        monkeypatch.setattr(adoption, 'adopt_legacy_output', adopt)
        window.adoption_btn.click()
        dialog = window._adoption_dialog
        dialog.table.selectRow(0); dialog.confirm_check.setChecked(True)
        dialog.approve_button.click()
        thread = window._thread
        worker_thread = shiboken6.getCppPointer(thread)[0]
        loop = QEventLoop()
        thread.finished.connect(loop.quit, Qt.ConnectionType.QueuedConnection)
        loop.exec()
        assert execution_threads == [worker_thread], 'Adoption executed in GUI despite moveToThread'
        assert len(library[0].list_managed_bindings()) == 1
    finally:
        window.close()


@pytest.mark.parametrize('operation', ['check', 'adoption'])
@pytest.mark.parametrize('ending', ['success', 'error', 'cancel', 'close', 'switch', 'quit'])
def test_check_and_adoption_terminal_lifecycle(library, app, tmp_path, monkeypatch, operation, ending):
    """Real workers/backend; bounded Event barriers expose every terminal route."""
    from threading import Event
    from PySide6.QtCore import QEventLoop, QObject, QThread, Qt, Slot
    import shiboken6
    import audio_library_organizer.ui.workers as workers
    repo, root, track, output = library
    source_bytes, output_bytes = track.path.read_bytes(), output.read_bytes()
    window = make_window(library, tmp_path)
    before = repo.get_track(track.track_id)
    other = window.library_registry.add_library('Other', (), tmp_path/'other-library') if ending == 'switch' else None
    entered, release = Event(), Event()
    execution_threads, destroyed_threads, gui_threads, terminal = [], [], [], []
    target = workers if operation == 'check' else adoption_api()
    name = 'check_library' if operation == 'check' else 'adopt_legacy_output'
    original = getattr(target, name)
    original_busy = window._set_busy

    class Results(QObject):
        @Slot(object)
        def finished(self, result):
            gui_threads.append(shiboken6.getCppPointer(QThread.currentThread())[0])
            terminal.append('finished')

        @Slot(str, str, str)
        def failed(self, library_id, operation_id, message):
            gui_threads.append(shiboken6.getCppPointer(QThread.currentThread())[0])
            terminal.append('failed')

    results = Results(window)

    def blocked(*args, **kwargs):
        execution_threads.append(shiboken6.getCppPointer(QThread.currentThread())[0])
        entered.set()
        if ending in {'cancel', 'close', 'switch', 'quit'}:
            assert kwargs['cancelled'].__self__.wait(5), 'Cancellation did not reach the worker'
        else:
            assert release.wait(5), 'Test did not release its bounded backend barrier'
        if ending == 'error':
            raise RuntimeError('injected terminal error')
        return original(*args, **kwargs)

    def set_busy(*args, **kwargs):
        gui_threads.append(shiboken6.getCppPointer(QThread.currentThread())[0])
        return original_busy(*args, **kwargs)

    try:
        if operation == 'adoption':
            window._check_library_clicked()
            wait(app, lambda: window._thread is None)
        prior_result = window.last_reconciliation_result
        monkeypatch.setattr(target, name, blocked)
        monkeypatch.setattr(window, '_set_busy', set_busy)
        if operation == 'check':
            window._check_library_clicked()
        else:
            window.adoption_btn.click()
            dialog = window._adoption_dialog
            dialog.table.selectRow(0); dialog.confirm_check.setChecked(True)
            dialog.approve_button.click()
        assert entered.wait(5), 'Backend did not start without GUI event dispatch'
        thread = window._thread
        worker_thread = shiboken6.getCppPointer(thread)[0]
        window._worker.destroyed.connect(
            lambda: destroyed_threads.append(shiboken6.getCppPointer(QThread.currentThread())[0]),
            Qt.ConnectionType.DirectConnection)
        window._worker.finished.connect(results.finished, Qt.ConnectionType.QueuedConnection)
        window._worker.failed.connect(results.failed, Qt.ConnectionType.QueuedConnection)
        loop = QEventLoop()
        thread.finished.connect(loop.quit, Qt.ConnectionType.QueuedConnection)
        if ending == 'cancel':
            window._check_library_clicked()
        elif ending == 'close':
            window.close()
        elif ending == 'switch':
            window._rebind_active_profile(window.library_registry.activate(other.profile_id))
        elif ending == 'quit':
            window._stop_file_check_on_quit()
        else:
            release.set()
        loop.exec()
        assert window._thread is None and window._worker is None
        assert execution_threads == destroyed_threads == [worker_thread]
        assert gui_threads and set(gui_threads) == {shiboken6.getCppPointer(app.thread())[0]}
        expected_terminal = 'failed' if ending == 'error' or (operation == 'adoption' and ending != 'success') else 'finished'
        assert terminal == [expected_terminal]
        assert len(repo.list_managed_bindings()) == (1 if operation == 'adoption' and ending == 'success' else 0)
        assert repo.get_track(track.track_id) == before
        assert track.path.read_bytes() == source_bytes and output.read_bytes() == output_bytes
        if ending == 'switch':
            assert window.last_reconciliation_result is None
        elif ending in {'close', 'quit'}:
            assert window.last_reconciliation_result is prior_result
        if ending == 'switch':
            assert window.repository.library_id != repo.library_id
            assert window.repository.list_tracks() == [] and window.repository.list_managed_bindings() == ()
        if ending == 'close':
            assert not window.isVisible()
    finally:
        release.set()
        if window._thread is not None:
            window._stop_file_check_on_quit()
            app.processEvents()
        window.close()
