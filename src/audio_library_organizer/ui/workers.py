from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot, Qt
from threading import Event
import subprocess
import requests

from audio_library_organizer.jobs.file_reconciliation import check_library


def _audio_error_text(exc: Exception) -> str:
    if isinstance(exc, requests.Timeout):
        return 'Przekroczono czas oczekiwania na AcoustID.'
    if isinstance(exc, requests.ConnectionError):
        return 'Brak połączenia z AcoustID. Sprawdź internet.'
    if isinstance(exc, requests.HTTPError):
        return 'AcoustID odrzucił zapytanie.'
    if isinstance(exc, subprocess.SubprocessError):
        return 'Nie udało się wygenerować fingerprintu audio.'
    return str(exc).strip() if isinstance(exc, (ValueError, RuntimeError)) else 'Błąd rozpoznawania audio.'


class ScanWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)
    track_ready = Signal(int, int, object)

    def __init__(self, service, source_dirs=None):
        super().__init__()
        self.service = service
        self.source_dirs = source_dirs
        self._cancelled = Event()

    def cancel(self):
        self._cancelled.set()

    @Slot()
    def run(self):
        try:
            self.finished.emit(self.service.scan(
                source_dirs=self.source_dirs,
                cancelled=self._cancelled.is_set,
                progress=lambda current, total, name: self.progress.emit(current, total, name),
                track_ready=lambda current, total, track: self.track_ready.emit(current, total, track),
            ))
        except Exception as exc:
            self.failed.emit(str(exc))


class FileReconciliationWorker(QObject):
    """One pinned operation, with context on every GUI-bound message."""

    finished = Signal(object)
    failed = Signal(str, str, str)
    progress = Signal(str, str, int, int, str)

    def __init__(self, repository, *, library_id, operation_id, managed_roots=()):
        super().__init__()
        self.repository = repository
        self.library_id = library_id
        self.operation_id = operation_id
        self.managed_roots = tuple(managed_roots)
        self._cancelled = Event()

    def cancel(self):
        self._cancelled.set()

    @Slot()
    def run(self):
        try:
            result = check_library(self.repository, library_id=self.library_id,
                operation_id=self.operation_id, managed_roots=self.managed_roots,
                cancelled=self._cancelled.is_set,
                progress=lambda current, total, name: self.progress.emit(
                    self.library_id, self.operation_id, current, total, name))
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(self.library_id, self.operation_id, str(exc))


class _GuiThreadRelay(QObject):
    """Receives worker results with an explicit queued hop to the GUI thread."""

    finished = Signal(object)
    failed = Signal(str)
    phase = Signal(str)

    @Slot(object)
    def forward_finished(self, result):
        self.finished.emit(result)

    @Slot(str)
    def forward_failed(self, message: str):
        self.failed.emit(message)

    @Slot(str)
    def forward_phase(self, phase: str):
        self.phase.emit(phase)


class AudioIdentificationWorker(QObject):
    """Run a single fingerprint lookup away from the GUI thread."""

    _raw_finished = Signal(object)
    _raw_failed = Signal(str)
    _raw_phase = Signal(str)

    def __init__(self, job, track):
        super().__init__()
        self.job = job
        self.track = track
        self._gui_relay = _GuiThreadRelay()
        for signal, slot in (
            (self._raw_finished, self._gui_relay.forward_finished),
            (self._raw_failed, self._gui_relay.forward_failed),
            (self._raw_phase, self._gui_relay.forward_phase),
        ):
            signal.connect(slot, Qt.ConnectionType.QueuedConnection)

    @property
    def finished(self):
        return self._gui_relay.finished

    @property
    def failed(self):
        return self._gui_relay.failed

    @property
    def phase(self):
        return self._gui_relay.phase

    @Slot()
    def run(self):
        try:
            self._raw_finished.emit(self.job.lookup(self.track, progress=self._raw_phase.emit))
        except Exception as exc:
            self._raw_failed.emit(_audio_error_text(exc))


class IdentificationWorker(QObject):
    _raw_finished = Signal(object)
    _raw_failed = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, job):
        super().__init__()
        self.job = job
        self._cancelled = Event()
        self.job.progress = lambda cur,total,name: self.progress.emit(cur,total,name)
        self.job.cancelled = self._cancelled.is_set

        # The worker is constructed on the GUI thread and moved afterwards.
        # Keep this relay parentless so its thread affinity remains the GUI
        # thread. Any Python lambda connected to ``finished``/``failed`` is
        # therefore invoked from the GUI thread rather than from QThread.run().
        self._gui_relay = _GuiThreadRelay()
        self._raw_finished.connect(
            self._gui_relay.forward_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._raw_failed.connect(
            self._gui_relay.forward_failed,
            Qt.ConnectionType.QueuedConnection,
        )

    @property
    def finished(self):
        return self._gui_relay.finished

    @property
    def failed(self):
        return self._gui_relay.failed

    def cancel(self):
        self._cancelled.set()

    @Slot()
    def run(self):
        try:
            self._raw_finished.emit(self.job.run())
        except Exception as exc:
            self._raw_failed.emit(str(exc))


class ExportWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, plan):
        super().__init__()
        self.plan = plan

    @Slot()
    def run(self):
        from audio_library_organizer.jobs.exporter import execute_copy_plan
        try:
            result = execute_copy_plan(
                self.plan,
                progress=lambda current, total, name: self.progress.emit(current, total, name),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
