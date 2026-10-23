"""Real MainWindow + ExportWorker + QThread; no native mouse automation."""
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from time import monotonic

import pytest
import sys
from mutagen.id3 import ID3
from PySide6.QtCore import QThread, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from shiboken6 import isValid

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs import exporter
from audio_library_organizer.safety.copy_pipeline import sha256_file
from audio_library_organizer.ui import main_window, export_dialogs


@pytest.fixture(autouse=True)
def no_unhandled_qt_errors(monkeypatch):
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda kind, value, tb: errors.append((kind, value)))
    yield
    assert not errors, f'Unhandled Qt callback errors: {errors}'


def until(predicate):
    deadline = monotonic() + 6
    while not predicate() and monotonic() < deadline:
        QApplication.processEvents()
    assert predicate(), 'Bounded export condition not reached'


@pytest.fixture
def export_window(current_start_window, tmp_path, monkeypatch):
    window = current_start_window
    source = tmp_path / 'synthetic'
    source.mkdir()
    window.repository.register_source(source)
    tracks = []
    for i in range(2):
        path = source / f'track-{i}.mp3'
        ID3().save(path)
        info = path.stat()
        track = TrackRecord(path=path, artist='Artist', title=f'Title {i}', year='2000',
                            genre='House', bpm=128, status='ready', locked_fields={'__status__'}, sha256=sha256_file(path),
                            size_bytes=info.st_size, mtime_ns=info.st_mtime_ns)
        window.repository.upsert_track(track)
        tracks.append(track)
    window.refresh_data()
    monkeypatch.setattr(main_window, 'confirm_bulk_copy', lambda *a, **k: True)
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: 0)  # Old RED must not open an unattended modal.
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a, **k: 0)
    summaries = []
    gui_updates = []
    update = export_dialogs.ExportProgressDialog.update_event

    def observe_update(dialog, event):
        gui_updates.append(QThread.currentThread())
        return update(dialog, event)

    monkeypatch.setattr(export_dialogs.ExportProgressDialog, 'update_event', observe_update)

    def summary_exec(dialog):
        assert all(thread == window.thread() for thread in gui_updates)
        summaries.append((SimpleNamespace(outcome=dialog.outcome, created_text=dialog.created_label.text(),
                                         report=dialog.report, notice_text=dialog.notice.text(), gui_updates=list(gui_updates)),
                          QThread.currentThread(), window._thread))
        return 0

    monkeypatch.setattr(export_dialogs.ExportSummaryDialog, 'exec', summary_exec)
    return window, tracks, summaries


def test_real_export_summary_waits_for_thread_and_preserves_repository(export_window):
    window, tracks, summaries = export_window
    before = [asdict(window.repository.get_track(t.track_id)) for t in tracks]
    sources = {t.path: (t.path.read_bytes(), t.path.stat().st_mtime_ns) for t in tracks}
    window.export_library()
    thread, worker = window._thread, window._worker
    until(lambda: window._thread is None)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert len(summaries) == 1
    dialog, gui_thread, finished_thread = summaries[0]
    assert gui_thread == window.thread() and finished_thread is None
    assert dialog.gui_updates
    assert dialog.outcome == 'success' and dialog.created_text == '2'
    assert dialog.report.is_file()
    assert not isValid(worker) and not isValid(thread)
    assert [asdict(window.repository.get_track(t.track_id)) for t in tracks] == before
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in sources.items())


def test_stop_and_close_keep_gui_alive_until_current_item_finishes(export_window, monkeypatch):
    window, tracks, summaries = export_window
    entered, release = Event(), Event()
    original = exporter.write_resolved_tags

    def blocked_tags(*args, **kwargs):
        entered.set()
        assert release.wait(5), 'Test did not release the current file'
        return original(*args, **kwargs)

    monkeypatch.setattr(exporter, 'write_resolved_tags', blocked_tags)
    window.export_library()
    try:
        until(entered.is_set)
        thread = window._thread
        window.export_library()  # A second operation must not be admitted.
        assert window._thread is thread
        window.close()
        assert window.isVisible() and thread.isRunning()
        assert window._export_dialog.stopping
        assert not summaries
        # Pump a real posted GUI event while the worker is held in the current item.
        observed = []
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: observed.append(True))
        until(lambda: bool(observed))
    finally:
        release.set()
        until(lambda: window._thread is None)
    assert len(summaries) == 1 and summaries[0][0].outcome == 'cancelled'
    assert summaries[0][0].created_text == '1'
    assert len(list(window.app_settings.library.root.rglob('*.mp3'))) == 1


def test_fatal_preflight_error_has_no_false_success(export_window, monkeypatch):
    window, tracks, summaries = export_window
    def fail(*args, **kwargs):
        raise ValueError('controlled adoption guard refusal')
    monkeypatch.setattr('audio_library_organizer.jobs.legacy_adoption.assert_legacy_export_allowed', fail)
    window.export_library()
    until(lambda: window._thread is None)
    assert len(summaries) == 1 and summaries[0][0].outcome == 'problems'
    assert 'controlled adoption guard refusal' in summaries[0][0].notice_text
    assert not list(window.app_settings.library.root.rglob('*.mp3'))


def test_report_failure_cannot_turn_into_full_success(export_window, monkeypatch):
    window, tracks, summaries = export_window

    def fail_report(*args, **kwargs):
        raise OSError('controlled report failure')

    monkeypatch.setattr(main_window, 'export_verification_csv', fail_report)
    window.export_library()
    until(lambda: window._thread is None)
    assert summaries[0][0].outcome == 'problems'
    assert summaries[0][0].created_text == '2' and summaries[0][0].report is None
    assert 'controlled report failure' in summaries[0][0].notice_text


def test_review_warning_still_requires_explicit_permission(export_window, monkeypatch):
    window, tracks, summaries = export_window
    track = window.repository.get_track(tracks[0].track_id)
    track.status = 'review'
    window.repository.upsert_track(track)
    previews = []
    monkeypatch.setattr(main_window, 'confirm_bulk_copy', lambda *a, **k: previews.append(True) or True)
    window.export_library()  # QMessageBox.exec above returns without choosing continue.
    assert not previews and window._thread is None and not summaries
    assert not list(window.app_settings.library.root.rglob('*.mp3'))


def test_result_alone_does_not_release_thread_or_show_summary(export_window):
    from PySide6.QtCore import QObject, Slot, Qt
    window, tracks, summaries = export_window
    entered, release = Event(), Event()

    class FinishGate(QObject):
        @Slot(object)
        def hold(self, result):
            entered.set()
            assert release.wait(5), 'Test did not release worker teardown'

    # Gate the real worker only after its result has been emitted. This is a
    # real running QThread, not a mock thread with a fabricated isRunning().
    window.export_library()
    thread = window._thread
    gate = FinishGate()
    gate.moveToThread(thread)
    window._worker.finished.connect(gate.hold, Qt.ConnectionType.DirectConnection)
    thread.finished.connect(gate.deleteLater)
    try:
        until(entered.is_set)
        until(lambda: window._export_result is not None)
        assert window._thread is thread and thread.isRunning() and not summaries
        window.export_library()
        assert window._thread is thread
        window.close()
        assert window.isVisible() and thread.isRunning() and not summaries
    finally:
        release.set()
        until(lambda: window._thread is None)
    assert summaries[0][0].outcome == 'cancelled'
    assert summaries[0][0].created_text == '2'
