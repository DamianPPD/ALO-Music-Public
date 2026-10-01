"""Bounded-memory waveform extraction and an accessible seek control."""
import json
import logging
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Lock, get_native_id
from time import monotonic

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider

from audio_library_organizer.audio import waveform_worker


_DECODER_LOCK = Lock()
_DECODER_TIMEOUT = 60.0
_POLL_INTERVAL = 0.025
_LOG = logging.getLogger(__name__)


def _waveform_command(path, bins, output, trace, generation):
    arguments = [str(path), str(bins), str(output), str(trace), str(generation)]
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--waveform-worker', *arguments]
    return [sys.executable, '-I', str(Path(waveform_worker.__file__).resolve()), *arguments]


def _decode_isolated(path, bins, cancel, generation):
    with TemporaryDirectory(prefix='alo-waveform-') as directory:
        output = Path(directory) / 'peaks.json'
        trace = Path(directory) / 'decoder.log'
        command = _waveform_command(path, bins, output, trace, generation)
        with (Path(directory) / 'stderr.log').open('w+b') as stderr:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=stderr,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            _LOG.debug('waveform started path=%s generation=%s pid=%s thread=%s',
                       path, generation, process.pid, get_native_id())
            deadline = monotonic() + _DECODER_TIMEOUT
            wake = cancel if cancel is not None else Event()
            try:
                while process.poll() is None:
                    if (cancel is not None and cancel.is_set()) or monotonic() >= deadline:
                        return []
                    wake.wait(_POLL_INTERVAL)
                if cancel is not None and cancel.is_set():
                    return []
                if process.returncode != 0:
                    # Access violations terminate only the child, never the GUI.
                    stderr.seek(0)
                    details = stderr.read(16384).decode('utf-8', errors='replace')
                    if trace.is_file():
                        with trace.open('rb') as child_trace:
                            child_trace.seek(max(0, trace.stat().st_size - 16384))
                            details += child_trace.read().decode('utf-8', errors='replace')
                    _LOG.warning('waveform decoder failed path=%s generation=%s pid=%s exit=%s\n%s',
                                 path, generation, process.pid, process.returncode, details)
                    return []
                if not output.is_file() or output.stat().st_size > 128 * 1024:
                    return []
                peaks = json.loads(output.read_text(encoding='utf-8'))
                if (not isinstance(peaks, list) or len(peaks) > bins
                        or any(type(value) not in (int, float) or not math.isfinite(value)
                               or not 0 <= value <= 1 for value in peaks)):
                    return []
                return peaks
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)


def read_waveform(path: Path, bins: int = 240, cancel: Event | None = None,
                  *, generation: int = 0) -> list[float]:
    """Decode outside the GUI process; at most one native decoder is active.

    Cancellation kills and reaps the old process before another starts. A
    failed, unavailable or hung decoder leaves the ordinary seek line.
    """
    if not 0 < bins <= 4096 or (cancel is not None and cancel.is_set()):
        return []
    try:
        path = Path(path).resolve()
        if not path.is_file():
            return []
    except OSError:
        return []
    while not _DECODER_LOCK.acquire(timeout=_POLL_INTERVAL):
        if cancel is not None and cancel.is_set():
            return []
    try:
        if cancel is not None and cancel.is_set():
            return []
        return _decode_isolated(path, bins, cancel, generation)
    except (OSError, subprocess.SubprocessError, ValueError):
        # IPC/startup errors cannot prevent playback or seek.
        return []
    finally:
        _DECODER_LOCK.release()


class WaveformSignals(QObject):
    ready = Signal(int, object)


class WaveformJob(QRunnable):
    def __init__(self, path: Path, generation: int, cancel: Event):
        super().__init__()
        self.path, self.generation, self.cancel = path, generation, cancel
        self.signals = WaveformSignals()

    def run(self):
        _LOG.debug('WaveformJob path=%s generation=%s thread=%s',
                   self.path, self.generation, get_native_id())
        peaks = read_waveform(self.path, cancel=self.cancel, generation=self.generation)
        if not self.cancel.is_set():
            self.signals.ready.emit(self.generation, peaks)


class WaveformSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.peaks: list[float] = []
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName('Pozycja odtwarzania / Playback position')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_peaks(self, peaks):
        self.peaks = list(peaks)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = max(1, self.width() - 8)
        progress = (self.value() - self.minimum()) / max(1, self.maximum() - self.minimum())
        cursor = 4 + progress * width
        center = self.height() / 2
        for i, peak in enumerate(self.peaks or [0.0] * max(2, width // 4)):
            count = len(self.peaks) if self.peaks else max(2, width // 4)
            x = 4 + i * width / max(1, count - 1)
            half = max(1, peak * (center - 4))
            pen = QPen(QColor('#31e2b0' if x <= cursor else '#536875'), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(x), int(center - half), int(x), int(center + half))
        if self.hasFocus() or self.isSliderDown():
            painter.setPen(QPen(QColor('#e3fff7'), 1))
            painter.drawLine(int(cursor), 2, int(cursor), self.height() - 2)
        painter.end()

    def _seek_at(self, event):
        fraction = max(0.0, min(1.0, (event.position().x() - 4) / max(1, self.width() - 8)))
        self.setValue(round(self.minimum() + fraction * (self.maximum() - self.minimum())))
        self.sliderMoved.emit(self.value())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.setSliderDown(True)
            self._seek_at(event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self._seek_at(event)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self._seek_at(event)
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        self.sliderMoved.emit(self.value())
