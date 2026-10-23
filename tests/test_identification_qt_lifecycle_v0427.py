"""Real Qt delivery and editor lifecycle; providers use controlled responses."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import time
import sys
import hashlib
import wave
from threading import Event
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThread, Qt
from PySide6.QtWidgets import QApplication
from shiboken6 import getCppPointer, isValid

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.workers import IdentificationWorker, AudioIdentificationWorker


@pytest.fixture(autouse=True)
def no_unhandled_qt_callback_errors(monkeypatch):
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda kind, value, tb: errors.append((kind, value)))
    yield
    assert not errors, f'Unhandled exception in a Qt callback: {errors}'


@pytest.fixture
def editor_context(current_start_window, tmp_path):
    from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
    window = current_start_window
    source = tmp_path / 'synthetic-source'
    source.mkdir()
    path = source / 'Artist - Synthetic.wav'
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b'\0\0' * 8000)
    window.repository.register_source(source)
    info = path.stat()
    track = TrackRecord(path=path, artist='Manual artist', title='Manual title',
                        year='2001', status='review', locked_fields={'artist', 'title', 'year'},
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        size_bytes=info.st_size, mtime_ns=info.st_mtime_ns)
    window.repository.upsert_track(track)
    window.refresh_data()
    track = window.repository.get_track(track.track_id)
    editor = MetadataEditorDialog(track, window, read_context=window._read_context)
    window._active_metadata_editor = editor
    editor.online_scan_requested.connect(lambda e: window._start_single_track_identification(track, e))
    editor.audio_scan_requested.connect(lambda e: window._start_audio_identification(track, e))
    editor.show()
    QApplication.processEvents()
    try:
        yield window, editor, track
    finally:
        if isValid(editor):
            editor.done(0)
        window._active_metadata_editor = None
        wait_until(lambda: window._thread is None)


@pytest.mark.parametrize('button_name', ('scan_online_button', 'search_cover_button'))
def test_real_editor_online_progress_guard_never_reads_widgets_from_worker(
        editor_context, monkeypatch, button_name):
    from audio_library_organizer.matching.resolver import IdentificationOutcome
    window, editor, track = editor_context
    entered, release = Event(), Event()
    calls, provider_threads = [], []

    class Provider:
        def identify(self, current):
            provider_threads.append(thread_id())
            entered.set()
            assert release.wait(3), 'Test did not release the provider'
            return IdentificationOutcome(current, None, 'uncertain')

    monkeypatch.setattr(window, '_build_identifier', lambda: Provider())
    gui = thread_id()
    original_guard = window._editor_request_current

    def guard(*args):
        calls.append(thread_id())
        # Observe the violation without deliberately racing native widget reads.
        return original_guard(*args) if thread_id() == gui else False

    monkeypatch.setattr(window, '_editor_request_current', guard)
    original_bytes = track.path.read_bytes()
    try:
        getattr(editor, button_name).click()
        wait_until(entered.is_set)
        # The old queued lambda cannot run until worker.run() yields its event loop.
        release.set()
        wait_until(lambda: window._thread is None)
        assert provider_threads and provider_threads[0] != gui
        assert len(calls) >= 2  # progress and finished both pass the production guard
        assert set(calls) == {gui}, 'Editor state was accessed from a worker thread'
        assert not editor._online_scan_busy
        assert editor.scan_online_button.isEnabled()
        stored = window.repository.get_track(track.track_id)
        assert (stored.artist, stored.title, stored.year) == ('Manual artist', 'Manual title', '2001')
        assert track.path.read_bytes() == original_bytes
        assert stored.sha256 == hashlib.sha256(original_bytes).hexdigest()
    finally:
        release.set()
        wait_until(lambda: window._thread is None)


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
    assert predicate(), 'Expected Qt event was not delivered'


def thread_id():
    return getCppPointer(QThread.currentThread())[0]


@pytest.mark.parametrize('kind', ('online', 'audio'))
@pytest.mark.parametrize('failure', (False, True))
def test_worker_callbacks_enter_gui_in_order_and_native_worker_is_deleted(kind, failure, tmp_path):
    app = QApplication.instance() or QApplication([])
    gui = thread_id()
    events, destroyed = [], []

    class Job:
        def run(self):
            events.append(('job', thread_id()))
            for current in (1, 2, 3):
                self.progress(current, 3, 'synthetic.mp3')
            if failure:
                raise ValueError('controlled provider error')
            return SimpleNamespace(processed=1)

        def lookup(self, _track, *, progress):
            events.append(('job', thread_id()))
            progress('lookup')
            if failure:
                raise ValueError('controlled provider error')
            return []

    job = Job()
    worker = (IdentificationWorker(job) if kind == 'online'
              else AudioIdentificationWorker(job, TrackRecord(path=tmp_path / 'synthetic.mp3')))
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    if kind == 'online':
        # The GUI relay supplies the queued hop; MainWindow uses AutoConnection.
        worker.progress.connect(lambda *_args: events.append(('progress', thread_id())))
    else:
        worker.phase.connect(lambda _phase: events.append(('progress', thread_id())))
    worker.finished.connect(lambda _result: events.append(('finished', thread_id())))
    worker.failed.connect(lambda _message: events.append(('failed', thread_id())))
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    worker.destroyed.connect(lambda: destroyed.append(thread_id()), Qt.ConnectionType.DirectConnection)
    try:
        thread.start()
        wait_until(lambda: not thread.isRunning())
        assert thread.wait(3000)
        wait_until(lambda: any(name == 'progress' for name, _ in events))
        expected = 'failed' if failure else 'finished'
        wait_until(lambda: any(name == expected for name, _ in events))
        assert next(t for name, t in events if name == 'job') != gui
        assert [(name, t) for name, t in events if name != 'job'] == (
            [('progress', gui)] * (3 if kind == 'online' else 1) + [(expected, gui)])
        assert destroyed and destroyed[0] != gui
        assert not isValid(worker)
    finally:
        thread.quit()
        assert thread.wait(3000)
        thread.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not isValid(thread)


def controlled_provider(window, monkeypatch, kind, entered, release, *, failure=False):
    from audio_library_organizer.matching.resolver import IdentificationOutcome
    from audio_library_organizer.domain.provider_settings import ProviderSettings
    from audio_library_organizer.domain.candidates import AcoustIDHit
    from audio_library_organizer.audio.fingerprint import FingerprintResult
    from audio_library_organizer.jobs import audio_identification
    from audio_library_organizer.providers.acoustid import AcoustIDClient

    def response():
        entered.set()
        assert release.wait(3), 'Test did not release the provider'
        if failure:
            raise ValueError('controlled provider error')

    if kind == 'online':
        class Provider:
            def identify(self, current):
                response()
                return IdentificationOutcome(current, None, 'uncertain')
        monkeypatch.setattr(window, '_build_identifier', lambda: Provider())
    else:
        ProviderSettings(acoustid_key='synthetic-test-key').save(window.qt_settings)
        monkeypatch.setattr(audio_identification, 'fingerprint_audio',
                            lambda _path: FingerprintResult('synthetic-fingerprint', 1))

        def lookup(_client, _fingerprint, _duration):
            response()
            return [AcoustIDHit('synthetic-recording', .95, 'Provider title', 'Provider artist',
                               'Synthetic album', '2002', 'synthetic-acoustid')]

        monkeypatch.setattr(AcoustIDClient, 'lookup', lookup)


@pytest.mark.parametrize('kind', ('online', 'audio'))
@pytest.mark.parametrize('transition', ('close', 'destroy', 'cancel', 'supersede', 'reopen', 'switch', 'quit'))
@pytest.mark.parametrize('failure', (False, True))
def test_late_worker_result_obeys_editor_library_and_shutdown_guards(
        editor_context, monkeypatch, tmp_path, kind, transition, failure):
    import sqlite3
    from audio_library_organizer.jobs.managed_files import ReadPurpose
    from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
    window, editor, track = editor_context
    original_repo = window.repository
    entered, release = Event(), Event()
    controlled_provider(window, monkeypatch, kind, entered, release, failure=failure)
    gui = thread_id()
    callbacks, worker_destroyed = [], []
    replacement = None
    for method in ('apply_online_result', 'set_online_scan_busy', 'set_audio_phase',
                   'show_audio_candidates', 'show_audio_error', 'finish_audio_lookup'):
        original = getattr(editor, method)

        def observe(*args, _name=method, _original=original, **kwargs):
            callbacks.append((_name, thread_id()))
            if thread_id() == gui:
                return _original(*args, **kwargs)

        monkeypatch.setattr(editor, method, observe)
    original_bytes = track.path.read_bytes()
    try:
        button = editor.scan_online_button if kind == 'online' else editor.audio_scan_button
        button.click()
        wait_until(entered.is_set)
        worker = window._worker
        thread = window._thread
        worker.destroyed.connect(lambda: worker_destroyed.append(thread_id()),
                                 Qt.ConnectionType.DirectConnection)
        if transition in ('close', 'reopen'):
            editor.done(0)
        elif transition == 'destroy':
            editor.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert not isValid(editor)
        elif transition == 'cancel':
            worker.cancel()
        elif transition == 'supersede':
            purpose = ReadPurpose.METADATA_EDITOR_READ if kind == 'online' else ReadPurpose.AUDIO_IDENTIFICATION
            editor.begin_async_request(purpose)
        elif transition == 'switch':
            profile = window.library_registry.add_library('Synthetic second library', (), tmp_path / 'second')
            window.library_registry.activate(profile.profile_id)
            window._rebind_active_profile(profile)
            assert window.repository.library_id != original_repo.library_id
        elif transition == 'quit':
            window.close()
            assert window._identification_closing
            assert window.isVisible()  # Wait for the active worker rather than destroying QThread.
        if transition == 'reopen':
            replacement = MetadataEditorDialog(track, window, read_context=window._read_context)
            window._active_metadata_editor = replacement
            replacement.show()
        before_late = len(callbacks)
        release.set()
        wait_until(lambda: window._thread is None)
        assert worker_destroyed and worker_destroyed[0] != gui
        assert not isValid(worker)
        assert all(t == gui for _name, t in callbacks)
        if transition in ('close', 'destroy', 'reopen'):
            assert callbacks[before_late:] == [], 'Late results touched a closed editor'
        elif transition in ('switch', 'supersede', 'quit'):
            assert not any(name in ('apply_online_result', 'show_audio_candidates', 'show_audio_error')
                           for name, _ in callbacks[before_late:])
        if replacement is not None:
            assert not replacement._online_scan_busy and not replacement._audio_scan_busy
            assert replacement.audio_candidates.rowCount() == 0
        if transition == 'quit':
            assert not window.isVisible()
        stored = original_repo.get_track(track.track_id)
        assert (stored.artist, stored.title, stored.year) == ('Manual artist', 'Manual title', '2001')
        assert not stored.audio_recognition  # Lookup never confirms a source automatically.
        assert track.path.read_bytes() == original_bytes
        assert stored.sha256 == hashlib.sha256(original_bytes).hexdigest()
        with sqlite3.connect(original_repo.database_path) as db:
            assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not isValid(thread)
    finally:
        release.set()
        wait_until(lambda: window._thread is None)
        if replacement is not None:
            replacement.done(0)


@pytest.mark.parametrize('failure', (False, True))
def test_real_audio_result_and_errors_stay_in_gui_without_automatic_approval(
        editor_context, monkeypatch, failure):
    window, editor, track = editor_context
    entered, release = Event(), Event()
    controlled_provider(window, monkeypatch, 'audio', entered, release, failure=failure)
    original = window.repository.get_track(track.track_id)
    try:
        editor.audio_scan_button.click()
        wait_until(entered.is_set)
        release.set()
        wait_until(lambda: window._thread is None)
        assert not editor._audio_scan_busy
        assert editor.audio_scan_button.isEnabled()
        if failure:
            assert editor.audio_phase.text() == 'Błąd rozpoznawania audio'
            assert editor.audio_candidates.rowCount() == 0
        else:
            assert editor.audio_candidates.rowCount() == 1
            assert editor.audio_candidates.item(0, 1).text() == 'Provider title'
        assert window.repository.get_track(track.track_id) == original
        assert not editor.track.audio_recognition
    finally:
        release.set()
        wait_until(lambda: window._thread is None)


def test_batch_online_progress_uses_the_same_gui_delivery(editor_context, monkeypatch):
    window, editor, track = editor_context
    entered, release = Event(), Event()
    controlled_provider(window, monkeypatch, 'online', entered, release)
    gui, calls = thread_id(), []
    original = window._identification_context_current

    def current(*args):
        calls.append(thread_id())
        return original(*args) if thread_id() == gui else False

    monkeypatch.setattr(window, '_identification_context_current', current)
    try:
        window.start_identification()
        wait_until(entered.is_set)
        release.set()
        wait_until(lambda: window._thread is None)
        assert len(calls) >= 2 and set(calls) == {gui}
        assert window.repository.get_track(track.track_id).title == 'Manual title'
    finally:
        release.set()
        wait_until(lambda: window._thread is None)


def test_result_refreshes_library_inside_real_modal_editor(editor_context, monkeypatch):
    from PySide6.QtCore import QTimer
    window, previous, track = editor_context
    previous.done(0)
    window._active_metadata_editor = None
    entered, release = Event(), Event()
    release.set()
    controlled_provider(window, monkeypatch, 'online', entered, release)
    seen, timed_out = [], []
    watchdog = QTimer(window)
    watchdog.setSingleShot(True)

    def timeout():
        timed_out.append(True)
        if window._active_metadata_editor is not None:
            window._active_metadata_editor.done(0)

    def begin():
        editor = window._active_metadata_editor
        seen.append(editor)
        editor.scan_online_button.click()
        window._thread.finished.connect(lambda: editor.done(0))

    watchdog.timeout.connect(timeout)
    QTimer.singleShot(0, begin)  # Enter the real dialog.exec() loop, without a time delay.
    watchdog.start(3000)
    try:
        window._open_metadata_editor(track)
        assert not timed_out and len(seen) == 1 and entered.is_set()
        assert seen[0]._read_closed
        wait_until(lambda: window._thread is None)
        assert window._active_metadata_editor is None
        for _ in range(3):
            window.refresh_data()
            window.library.select_track(track)
        assert window.library._current_track().track_id == track.track_id
        assert window.repository.get_track(track.track_id).artist == 'Manual artist'
    finally:
        watchdog.stop()
        watchdog.deleteLater()
