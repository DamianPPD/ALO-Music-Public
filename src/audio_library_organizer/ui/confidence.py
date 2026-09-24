from __future__ import annotations

from dataclasses import dataclass

try:
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout
    _QT_AVAILABLE = True
except ImportError:  # pure helper tests / non-GUI environments
    QFrame = object
    _QT_AVAILABLE = False


@dataclass(frozen=True, slots=True)
class ConfidencePresentation:
    percent: int | None
    label: str
    kind: str


def confidence_presentation(value) -> ConfidencePresentation:
    if value is None:
        return ConfidencePresentation(None, '—', 'none')
    percent = max(0, min(100, round(float(value) * 100)))
    if percent >= 90:
        return ConfidencePresentation(percent, 'WYSOKA', 'high')
    if percent >= 65:
        return ConfidencePresentation(percent, 'ŚREDNIA', 'medium')
    return ConfidencePresentation(percent, 'NISKA', 'low')


def confidence_color(percent: int | None) -> str:
    """Smooth red -> amber -> green confidence spectrum."""
    if percent is None:
        return '#7d8894'
    value = max(0, min(100, int(percent)))
    if value <= 50:
        # #e45656 -> #f0b84d
        t = value / 50.0
        a = (228, 86, 86); b = (240, 184, 77)
    else:
        t = (value - 50) / 50.0
        a = (240, 184, 77); b = (67, 209, 125)
    rgb = tuple(round(x + (y - x) * t) for x, y in zip(a, b))
    return '#%02x%02x%02x' % rgb


class ConfidenceWidget(QFrame):
    def __init__(self, value=None, parent=None):
        if not _QT_AVAILABLE:
            raise RuntimeError('PySide6 is required for ConfidenceWidget')
        super().__init__(parent)
        self.setObjectName('ConfidenceWidget')
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(4)
        self.percent = QLabel('—'); self.percent.setObjectName('ConfidencePercent'); root.addWidget(self.percent)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setTextVisible(False); self.bar.setFixedHeight(12); self.bar.setObjectName('ConfidenceBar'); root.addWidget(self.bar)
        self.description = QLabel('Brak wyniku rozpoznania'); self.description.setObjectName('ConfidenceDescription'); root.addWidget(self.description)
        self.set_value(value)

    def set_value(self, value):
        info = confidence_presentation(value)
        self.setProperty('confidenceKind', info.kind)
        self.percent.setText('—' if info.percent is None else f'{info.percent}%')
        self.bar.setValue(info.percent or 0)
        self.bar.setProperty('confidenceKind', info.kind)
        color = confidence_color(info.percent)
        self.bar.setStyleSheet(f'QProgressBar#ConfidenceBar::chunk {{ background:{color}; border-radius:5px; }}')
        self.percent.setStyleSheet(f'color:{color};')
        if info.percent is None:
            self.description.setText('Brak wyniku rozpoznania')
        elif info.kind == 'high':
            self.description.setText('Dopasowanie bardzo wysokie')
        elif info.kind == 'medium':
            self.description.setText('Dopasowanie wymaga krótkiej kontroli')
        else:
            self.description.setText('Niska pewność — sprawdź dane')
        for widget in (self, self.bar):
            widget.style().unpolish(widget); widget.style().polish(widget); widget.update()
