"""GUI-owned bounded admission; worker owns only immutable work and an Event."""
from threading import Event
from weakref import WeakMethod

from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, QCoreApplication, Qt

from audio_library_organizer.jobs.context_menu import LatestMenuWork, execute_menu_work


class _MenuSignals(QObject):
    done = Signal(int, object)


class _MenuTask(QRunnable):
    def __init__(self, serial, work, cancel):
        super().__init__()
        self.serial, self.work, self.cancel = serial, work, cancel
        self.signals = _MenuSignals(QCoreApplication.instance())
        self.signals.setObjectName('LibraryMenuTaskSignals')
        self.gate = Event()

    def start(self):
        gate = self.gate
        try:
            QThreadPool.globalInstance().start(self)
        finally:
            # Preserve the proven PySide start/autoDelete ownership handoff.
            gate.set()

    def run(self):
        self.gate.wait()
        try:
            try:
                value = execute_menu_work(self.work, self.cancel)
                outcome = (value, None)
            except Exception as error:
                outcome = (None, str(error))
            # Terminal delivery is mandatory even after cancellation.
            self.signals.done.emit(self.serial, outcome)
        finally:
            self.signals.deleteLater()


class MenuTasks(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.queue = LatestMenuWork()

    def submit(self, work, callback, *args):
        # Queued work must not keep a closed page/window's Python wrapper alive.
        entry = self.queue.submit(work, (WeakMethod(callback), args))
        if entry is not None:
            self._start(entry)

    def _start(self, entry):
        serial, work, cancel, _callback = entry
        task = _MenuTask(serial, work, cancel)
        task.signals.done.connect(self._done, Qt.ConnectionType.QueuedConnection)
        task.start()

    @Slot(int, object)
    def _done(self, serial, outcome):
        finished, following = self.queue.complete(serial)
        if following is not None:
            self._start(following)
        if finished is not None and not finished[2].is_set() and not self.queue.closed:
            reference, args = finished[3]
            callback = reference()
            if callback is not None:
                callback(*args, *outcome)

    def cancel(self, *, closing=False):
        # Never wait in the GUI for an OS stat; late results are discarded.
        self.queue.cancel(closing=closing)

    def cancel_probe(self):
        if self.queue.active is not None and self.queue.active[1].operation == 'probe':
            self.queue.active[2].set()
        if self.queue.pending is not None and self.queue.pending[1].operation == 'probe':
            self.queue.pending = None
