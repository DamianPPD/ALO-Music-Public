"""Cancellation through real export preflight, synthetic MP3 and real SQLite."""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from audio_adoption_fixtures import mp3_samples, copy_audio
from test_legacy_adoption_v0427 import _database_state
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.safety.copy_pipeline import sha256_file
from audio_library_organizer.jobs import legacy_adoption as adoption, exporter
from audio_library_organizer.ui.workers import ExportWorker
from test_export_window_v0427 import export_window, until, no_unhandled_qt_errors


@pytest.fixture
def preflight(tmp_path, mp3_samples):
    app = QApplication.instance() or QApplication([])
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    source = tmp_path / 'synthetic-source'
    source.mkdir()
    repo = LibraryRepository(paths.database)
    repo.initialize()
    repo.bootstrap_sources([source])
    tracks = []
    for index in range(2):
        path = copy_audio(mp3_samples['original'], source / f'track-{index}.mp3')
        info = path.stat()
        track = TrackRecord(path=path, status='ready', artist='Fixture artist', title='Fixture title',
                            year='2000', genre='House', bpm=128, locked_fields={'__status__'},
                            sha256=sha256_file(path), size_bytes=info.st_size, mtime_ns=info.st_mtime_ns)
        repo.upsert_track(track)
        tracks.append(track)
    worker = ExportWorker(exporter.ExportPlan.from_tracks(tracks, paths),
                          adoption_repository=repo, library_root=paths.root)
    results, errors, events = [], [], []
    worker.finished.connect(results.append)
    worker.failed.connect(errors.append)
    worker.phase.connect(events.append)
    return app, repo, paths, worker, results, errors, events


def assert_no_outputs_or_db_change(repo, paths, before):
    assert _database_state(repo, include_cache=True) == before
    assert not list(paths.ready.rglob('*.mp3'))
    assert not list(paths.review.rglob('*.mp3'))
    assert not list(paths.not_selected.rglob('*.mp3'))


def test_stop_before_preflight_never_reads_inventory_or_copies(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    before = _database_state(repo, include_cache=True)
    monkeypatch.setattr(adoption, 'inventory_legacy_outputs', lambda *a, **k: pytest.fail('cancelled preflight entered'))
    worker.cancel()
    worker.run()
    assert not errors and len(results) == 1 and results[0].cancelled
    assert (results[0].created, results[0].failed, results[0].remaining) == (0, 0, 2)
    assert results[0].stop_phase == 'preflight'
    assert_no_outputs_or_db_change(repo, paths, before)


def test_stop_inside_real_source_inspection_reaches_callback_and_stops_next_file(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    before = _database_state(repo, include_cache=True)
    original, seen = adoption.inspect_audio, []

    def stop_on_inspection(path, **kwargs):
        worker.cancel()
        seen.append((path, kwargs['cancelled']()))
        return original(path, **kwargs)

    monkeypatch.setattr(adoption, 'inspect_audio', stop_on_inspection)
    worker.run()
    assert len(seen) == 1 and seen[0][1] is True
    assert not errors and results[0].cancelled and results[0].stop_phase == 'preflight'
    assert all(event.created == 0 and event.processed == 0 for event in events)
    assert_no_outputs_or_db_change(repo, paths, before)


def test_cancelled_inventory_is_stopped_result_not_guard_error(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    cancelled = adoption.inventory_legacy_outputs(repo, library_root=paths.root, cancelled=lambda: True)
    before = _database_state(repo, include_cache=True)
    monkeypatch.setattr(adoption, 'inventory_legacy_outputs', lambda *a, **k: cancelled)
    worker.run()
    assert not errors and len(results) == 1 and results[0].cancelled
    assert results[0].stop_phase == 'preflight'
    assert_no_outputs_or_db_change(repo, paths, before)


def test_stop_after_guard_before_copy(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    original = adoption.assert_legacy_export_allowed
    def guarded_then_stop(*args, **kwargs):
        original(*args, **kwargs)
        worker.cancel()
    monkeypatch.setattr(adoption, 'assert_legacy_export_allowed', guarded_then_stop)
    worker.run()
    assert not errors and results[0].cancelled and results[0].stop_phase == 'preflight'
    assert results[0].created == 0 and results[0].remaining == 2
    assert not list(paths.root.rglob('*.mp3'))


def test_stop_in_inventory_transaction_rolls_back_and_finishes_normally(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    before = _database_state(repo, include_cache=True)
    original = adoption._context
    def cancel_in_transaction(repository, states, conn=None):
        value = original(repository, states, conn)
        if conn is not None:
            worker.cancel()
        return value
    monkeypatch.setattr(adoption, '_context', cancel_in_transaction)
    worker.run()
    assert not errors and results[0].cancelled and results[0].stop_phase == 'preflight'
    assert_no_outputs_or_db_change(repo, paths, before)


def test_progress_precedes_real_decoder_and_never_counts_it_as_a_copy(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    original, during = adoption.inspect_audio, []
    def observe(path, **kwargs):
        during.append(tuple(events))
        return original(path, **kwargs)
    monkeypatch.setattr(adoption, 'inspect_audio', observe)
    worker.run()
    assert not errors and results[0].created == 2
    assert during and all(snapshot for snapshot in during)
    assert all(snapshot[-1].phase == 'preflight_sources' for snapshot in during)
    assert all(snapshot[-1].check_total == 2 and snapshot[-1].processed == 0 for snapshot in during)
    assert events[-1].phase == 'operation_finishing'


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_preflight_phase_and_stop_text_at_zero_copies(preflight, language):
    from audio_library_organizer.jobs.exporter import ExportEvent
    from audio_library_organizer.ui.export_dialogs import ExportProgressDialog
    dialog = ExportProgressDialog(733, language=language)
    event = ExportEvent('preflight_sources', 733, 0, 0, 0, Path('synthetic.mp3'), check_current=12, check_total=733)
    dialog.update_event(event)
    assert dialog.progress.value() == 0 and dialog.count_labels['created'].text() == '0'
    assert '12 / 733' in dialog.check_progress.text()
    assert ('bezpieczeństwa' if language == 'pl' else 'safety') in dialog.stage.text().lower()
    dialog.request_stop()
    assert not dialog.stop_button.isEnabled()
    assert ('kontroli' if language == 'pl' else 'check') in dialog.notice.text().lower()
    assert ('Odebrano' if language == 'pl' else 'received') in dialog.log.toPlainText()
    dialog.finish()


def test_real_window_stops_at_zero_and_shows_summary_after_teardown(export_window, mp3_samples, monkeypatch):
    from threading import Event
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid
    window, tracks, summaries = export_window
    for track in tracks:
        copy_audio(mp3_samples['original'], track.path)
        info = track.path.stat()
        track.sha256, track.size_bytes, track.mtime_ns = sha256_file(track.path), info.st_size, info.st_mtime_ns
        window.repository.upsert_track(track)
    before = _database_state(window.repository, include_cache=True)
    source_bytes = {track.path: track.path.read_bytes() for track in tracks}
    original, entered, release = adoption.inspect_audio, Event(), Event()

    def controlled_inspection(path, **kwargs):
        entered.set()
        assert release.wait(5), 'Test did not release preflight I/O boundary'
        return original(path, **kwargs)

    monkeypatch.setattr(adoption, 'inspect_audio', controlled_inspection)
    window.export_library()
    thread, worker = window._thread, window._worker
    try:
        until(entered.is_set)
        until(lambda: 'bezpieczeństwa' in window._export_dialog.stage.text().lower())
        assert window._export_dialog.progress.value() == 0
        window._export_dialog.stop_button.click()
        window.close()
        assert window.isVisible() and thread.isRunning() and not summaries
        assert 'kontroli' in window._export_dialog.notice.text().lower()
    finally:
        release.set()
        until(lambda: window._thread is None)
    assert len(summaries) == 1 and summaries[0][0].outcome == 'cancelled'
    assert summaries[0][0].created_text == '0'
    assert window._export_result.stop_phase == 'preflight'
    assert 'kopiowania' in summaries[0][0].notice_text.lower()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(thread) and not isValid(worker) and window._export_dialog is None
    assert_no_outputs_or_db_change(window.repository, window.app_settings.library, before)
    assert all(path.read_bytes() == data for path, data in source_bytes.items())


def test_review_warning_occurs_once_before_preview_progress_and_summary(export_window, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox
    from audio_library_organizer.ui import main_window, confirmations, export_dialogs
    window, tracks, summaries = export_window
    track = window.repository.get_track(tracks[0].track_id)
    track.status = 'review'
    window.repository.upsert_track(track)
    sequence = []

    def warning_exec(box):
        sequence.append('warning')
        assert window._thread is None
        button = next(b for b in box.buttons() if box.buttonRole(b) == QMessageBox.ButtonRole.DestructiveRole)
        button.click()  # Real QMessageBox selection; preserve the production branch.
        return 0

    def preview_exec(dialog):
        sequence.append('preview')
        assert window._thread is None
        return QDialog.DialogCode.Accepted

    original_show = export_dialogs.ExportProgressDialog.show
    def progress_show(dialog):
        sequence.append('progress')
        original_show(dialog)

    summary_exec = export_dialogs.ExportSummaryDialog.exec
    def observed_summary(dialog):
        sequence.append('summary')
        return summary_exec(dialog)

    monkeypatch.setattr(QMessageBox, 'exec', warning_exec)
    monkeypatch.setattr(main_window, 'confirm_bulk_copy', confirmations.confirm_bulk_copy)
    monkeypatch.setattr(export_dialogs.ExportPreviewDialog, 'exec', preview_exec)
    monkeypatch.setattr(export_dialogs.ExportProgressDialog, 'show', progress_show)
    monkeypatch.setattr(export_dialogs.ExportSummaryDialog, 'exec', observed_summary)
    window.export_library()
    until(lambda: window._thread is None)
    assert sequence == ['warning', 'preview', 'progress', 'summary']
    assert len(summaries) == 1 and summaries[0][0].outcome == 'success'


def test_cancel_after_sqlite_insert_rolls_back_the_real_transaction(preflight, monkeypatch):
    import sqlite3
    _, repo, paths, worker, results, errors, events = preflight
    before = _database_state(repo, include_cache=True)
    inserted = []

    class CancellingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            result = super().execute(sql, parameters)
            if sql.startswith('INSERT INTO legacy_adoption_runs'):
                inserted.append(True)
                worker.cancel()
            return result

    def connect(repository):
        conn = sqlite3.connect(repository.database_path.absolute().as_uri() + '?mode=rw', uri=True,
                               timeout=5, factory=CancellingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    monkeypatch.setattr(adoption, '_rw', connect)
    worker.run()
    assert inserted == [True] and not errors and results[0].cancelled
    assert_no_outputs_or_db_change(repo, paths, before)


def test_real_ffmpeg_process_observes_export_cancellation(preflight, monkeypatch):
    from audio_library_organizer.audio import identity
    _, repo, paths, worker, results, errors, events = preflight
    before = _database_state(repo, include_cache=True)
    original, processes = identity.subprocess.Popen, []

    def launched(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        worker.cancel()
        return process

    monkeypatch.setattr(identity.subprocess, 'Popen', launched)
    worker.run()
    assert len(processes) == 1 and processes[0].poll() is not None
    assert not errors and results[0].cancelled and results[0].stop_phase == 'preflight'
    assert_no_outputs_or_db_change(repo, paths, before)


def test_report_scan_checks_cancellation_between_real_csv_rows(tmp_path, monkeypatch):
    from threading import Event
    root = tmp_path / 'library'
    (root / 'raporty').mkdir(parents=True)
    (root / 'raporty' / 'old.csv').write_text('source_path,destination_path\n' + 'a,b\n' * 10)
    original, seen, cancelled = adoption.csv.DictReader, [], Event()

    def rows(*args, **kwargs):
        reader = original(*args, **kwargs)
        class ObservedReader:
            fieldnames = reader.fieldnames
            def __iter__(self):
                for row in reader:
                    seen.append(row)
                    cancelled.set()
                    yield row
        return ObservedReader()

    monkeypatch.setattr(adoption.csv, 'DictReader', rows)
    assert not adoption._report_evidence(root, set(), cancelled=cancelled.is_set)
    assert len(seen) == 1


def test_interrupted_copy_engine_is_not_reported_as_cancelled_preflight(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    def interrupted(*args, **kwargs):
        worker.cancel()
        raise InterruptedError('controlled copy engine interruption')
    monkeypatch.setattr(exporter, 'execute_copy_plan', interrupted)
    worker.run()
    assert not results and errors == ['controlled copy engine interruption']


def test_copy_engine_failure_after_stop_keeps_error_without_claiming_no_copy(export_window, monkeypatch):
    from threading import Event
    window, tracks, summaries = export_window
    entered, release = Event(), Event()

    def interrupted(*args, **kwargs):
        entered.set()
        assert release.wait(5), 'Test did not release the copy engine failure'
        raise InterruptedError('controlled copy engine interruption')

    monkeypatch.setattr(exporter, 'execute_copy_plan', interrupted)
    window.export_library()
    try:
        until(entered.is_set)
        window._export_dialog.stop_button.click()
    finally:
        release.set()
        until(lambda: window._thread is None)
    assert len(summaries) == 1
    notice = summaries[0][0].notice_text
    assert 'controlled copy engine interruption' in notice
    assert window._export_result.cancelled and window._export_result.fatal_error
    assert window._export_result.stop_phase == ''
    assert 'Zatrzymano przed rozpoczęciem kopiowania' not in notice
    assert 'Stopped before copying began' not in notice


def test_unmatched_output_reports_completed_check_and_still_blocks_copy(preflight, mp3_samples):
    _, repo, paths, worker, results, errors, events = preflight
    output = copy_audio(mp3_samples['different_tail'], paths.ready / 'unmatched.mp3')
    before = output.read_bytes()
    worker.run()
    output_checks = [event for event in events if event.phase == 'preflight_outputs' and event.check_total]
    assert output_checks
    assert (output_checks[-1].check_current, output_checks[-1].check_total) == (1, 1)
    assert not results and errors  # Unmatched real audio must still reach the existing refusal.
    assert all(event.created == event.processed == 0 for event in events)
    assert output.read_bytes() == before
    assert list(paths.ready.rglob('*.mp3')) == [output]
