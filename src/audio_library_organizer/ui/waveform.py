"""Bounded-memory waveform extraction and an accessible seek control."""
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider


def read_waveform(path: Path, bins: int = 240, cancel: Event | None = None) -> list[float]:
    if bins <= 0:
        return []
    try:
        import numpy as np
        import soundfile as sf
        with sf.SoundFile(str(path)) as audio:
            count = min(bins, len(audio))
            peaks = []
            for i in range(count):
                remaining = (i + 1) * len(audio) // count - audio.tell()
                peak = 0.0
                while remaining > 0:
                    if cancel is not None and cancel.is_set():
                        return []
                    samples = audio.read(min(65536, remaining), dtype='float32', always_2d=True)
                    if not len(samples):
                        return []
                    peak = max(peak, float(np.max(np.abs(np.nan_to_num(samples)))))
                    remaining -= len(samples)
                peaks.append(min(1.0, peak))
            return peaks
    except (ImportError, OSError, RuntimeError, ValueError):
        # Unsupported files keep an ordinary seek line, never a fake waveform.
        return []


class WaveformSignals(QObject):
    ready = Signal(int, object)


class WaveformJob(QRunnable):
    def __init__(self, path: Path, generation: int, cancel: Event):
        super().__init__()
        self.path, self.generation, self.cancel = path, generation, cancel
        self.signals = WaveformSignals()

    def run(self):
        peaks = read_waveform(self.path, cancel=self.cancel)
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
