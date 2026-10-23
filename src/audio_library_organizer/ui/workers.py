from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot, Qt, QRunnable, QCoreApplication
from threading import Event
from copy import deepcopy
import subprocess
import requests

from audio_library_organizer.jobs.file_reconciliation import check_library
from audio_library_organizer.jobs.managed_files import read_material


class ReadTaskSignals(QObject):
    ready = Signal(int, object)


class ReadTask(QRunnable):
    """Cancellable physical read; the receiver applies its context/generation guard."""
    def __init__(self, plan, reader, cancel):
        super().__init__()
        self.plan, self.reader, self.cancel = plan, reader, cancel
        # Created on the GUI thread and owned there. A very short QRunnable may
        # otherwise destroy its last Python-owned QObject from a pool thread.
        self.signals = ReadTaskSignals(QCoreApplication.instance())

    def run(self):
        try:
            if self.cancel.is_set():
                return
            result = read_material(self.plan, self.reader, cancelled=self.cancel.is_set)
            if not self.cancel.is_set():
                self.signals.ready.emit(self.plan.generation, result)
        finally:
            self.signals.deleteLater()


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

    def __init__(self, repository, *, library_id, operation_id, managed_roots=(),
                 library_root=None, known_libraries=()):
        super().__init__()
        self.repository = repository
        self.library_id = library_id
        self.operation_id = operation_id
        self.managed_roots = tuple(managed_roots)
        self.library_root = library_root
        self.known_libraries = tuple(known_libraries)
        self._cancelled = Event()

    def cancel(self):
        self._cancelled.set()

    @Slot()
    def run(self):
        try:
            result = check_library(self.repository, library_id=self.library_id,
                operation_id=self.operation_id, managed_roots=self.managed_roots,
                library_root=self.library_root, known_libraries=self.known_libraries,
                include_adoption=self.library_root is not None,
                cancelled=self._cancelled.is_set,
                progress=lambda current, total, name: self.progress.emit(
                    self.library_id, self.operation_id, current, total, name))
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(self.library_id, self.operation_id, str(exc))


class LegacyAdoptionWorker(FileReconciliationWorker):
    """One explicit approval, with the existing pinned operation/cancel guard."""
    def __init__(self, repository, *, proposal_id, library_id, operation_id,
                 library_root, known_libraries=()):
        super().__init__(repository, library_id=library_id, operation_id=operation_id,
                         library_root=library_root, known_libraries=known_libraries)
        self.proposal_id = proposal_id

    @Slot()
    def adopt(self):
        # A distinct slot is registered on this subclass. PySide's inherited
        # run() signature otherwise routes the override through a GUI proxy.
        self.run()

    @Slot()
    def run(self):
        from audio_library_organizer.jobs.legacy_adoption import adopt_legacy_output
        from types import SimpleNamespace
        try:
            if self.repository.library_id != self.library_id:
                raise ValueError('Library context changed before approval.')
            binding = adopt_legacy_output(self.repository, self.proposal_id, confirmed=True,
                library_root=self.library_root, known_libraries=self.known_libraries,
                cancelled=self._cancelled.is_set)
            self.finished.emit(SimpleNamespace(library_id=self.library_id,
                operation_id=self.operation_id, binding=binding))
        except Exception as exc:
            self.failed.emit(self.library_id, self.operation_id, str(exc))


class _GuiThreadRelay(QObject):
    """Receives worker results with an explicit queued hop to the GUI thread."""

    finished = Signal(object)
    failed = Signal(str)
    phase = Signal(str)
    progress = Signal(int, int, str)

    @Slot(int, int, str)
    def forward_progress(self, current: int, total: int, name: str):
        self.progress.emit(current, total, name)

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
        self.track = deepcopy(track)
        self._cancelled = Event()
        self.job.cancelled = self._cancelled.is_set
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

    def cancel(self):
        self._cancelled.set()

    @Slot()
    def run(self):
        try:
            result = self.job.lookup(self.track, progress=self._raw_phase.emit)
            if self._cancelled.is_set():
                raise InterruptedError('Audio lookup cancelled.')
            self._raw_finished.emit(result)
        except Exception as exc:
            self._raw_failed.emit(_audio_error_text(exc))


class IdentificationWorker(QObject):
    _raw_finished = Signal(object)
    _raw_failed = Signal(str)
    _raw_progress = Signal(int, int, str)

    def __init__(self, job):
        super().__init__()
        self.job = job
        self._cancelled = Event()
        self.job.progress = lambda cur,total,name: self._raw_progress.emit(cur,total,name)
        self.job.cancelled = self._cancelled.is_set

        # The worker is constructed on the GUI thread and moved afterwards.
        # Keep this relay parentless so its thread affinity remains the GUI
        # thread. Python callbacks connected to progress/finished/failed are
        # therefore invoked from the GUI thread rather than from QThread.run().
        self._gui_relay = _GuiThreadRelay()
        self._raw_progress.connect(
            self._gui_relay.forward_progress,
            Qt.ConnectionType.QueuedConnection,
        )
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

    @property
    def progress(self):
        return self._gui_relay.progress

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
    phase = Signal(object)

    def __init__(self, plan, *, adoption_repository=None, library_root=None, known_libraries=()):
        super().__init__()
        self.plan = plan
        self.adoption_repository = adoption_repository
        self.library_root = library_root
        self.known_libraries = tuple(known_libraries)
        self._cancelled = Event()
        self._preflight_stage = 'context'

    def cancel(self):
        # Called directly by GUI: only the thread-safe Event is touched.
        self._cancelled.set()

    def _preflight_phase(self, stage):
        from audio_library_organizer.jobs.exporter import ExportEvent
        self._preflight_stage = stage
        self.phase.emit(ExportEvent('preflight_' + stage, len(self.plan.items), 0, 0, 0))

    def _preflight_progress(self, current, total, name):
        from pathlib import Path
        from audio_library_organizer.jobs.exporter import ExportEvent
        self.phase.emit(ExportEvent('preflight_' + self._preflight_stage, len(self.plan.items), 0, 0, 0,
                                   Path(name) if name else None, check_current=current, check_total=total))

    @Slot()
    def run(self):
        from dataclasses import replace
        from time import perf_counter
        from audio_library_organizer.jobs.exporter import execute_copy_plan, ExportEvent, ExportResult
        started = perf_counter()
        checking_preflight = True

        def finish(result):
            result = replace(result, elapsed_seconds=perf_counter() - started,
                             cancelled=result.cancelled or self._cancelled.is_set())
            if result.cancelled and not result.stop_phase:
                result = replace(result, stop_phase='copying')
            self.phase.emit(ExportEvent('operation_finishing', len(self.plan.items), result.processed,
                                       result.created, result.failed, skipped=result.skipped))
            self.finished.emit(result)

        def stop_preflight():
            finish(ExportResult((), (), planned=len(self.plan.items), cancelled=True, stop_phase='preflight'))

        try:
            if self._cancelled.is_set():
                stop_preflight()
                return
            if self.adoption_repository is not None:
                from audio_library_organizer.jobs.legacy_adoption import inventory_legacy_outputs, assert_legacy_export_allowed
                self._preflight_phase('context')
                inventory = inventory_legacy_outputs(self.adoption_repository, library_root=self.library_root,
                    known_libraries=self.known_libraries, cancelled=self._cancelled.is_set,
                    progress=self._preflight_progress, phase=self._preflight_phase)
                if inventory.cancelled or self._cancelled.is_set():
                    stop_preflight()
                    return
                assert_legacy_export_allowed(inventory, [item.track for item in self.plan.items])
            if self._cancelled.is_set():
                stop_preflight()
                return
            checking_preflight = False
            result = execute_copy_plan(
                self.plan,
                progress=lambda current, total, name: self.progress.emit(current, total, name),
                cancelled=self._cancelled.is_set,
                event=self.phase.emit,
            )
            finish(result)
        except InterruptedError as exc:
            if checking_preflight and self._cancelled.is_set():
                stop_preflight()
            else:
                self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
