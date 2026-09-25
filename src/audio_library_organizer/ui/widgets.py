from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QCursor, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QDialog, QHBoxLayout, QPushButton, QLineEdit


class StatCard(QFrame):
    def __init__(self, title: str, value: str = '0', parent=None, *, accent: str = '#4a91ff'):
        super().__init__(parent)
        self.setStyleSheet(f'QFrame {{ background:#171c24; border:1px solid #252d3a; border-top:3px solid {accent}; border-radius:10px; }}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f'font-size:29pt;font-weight:800;border:0;color:{accent};')
        caption = QLabel(title)
        caption.setStyleSheet('color:#9eabbc;border:0;')
        layout.addWidget(self.value_label)
        layout.addWidget(caption)

    def set_value(self, value: int | str):
        self.value_label.setText(str(value))


class ClickableCoverLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str = 'Brak okładki', parent=None):
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip('Kliknij, aby powiększyć okładkę')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.pixmap() is not None and not self.pixmap().isNull():
            self.clicked.emit()
        super().mousePressEvent(event)


class ElidedLabel(QLabel):
    """Label that keeps its full value but paints an elided one when narrow."""

    def __init__(self, text: str = '', parent=None):
        super().__init__(parent)
        self._full_text = ''
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        self._full_text = str(text or '')
        self.setToolTip(self._full_text)
        self._refresh_elision()

    def fullText(self) -> str:  # noqa: N802 - Qt-style accessor
        return self._full_text

    def _refresh_elision(self) -> None:
        width = max(0, self.contentsRect().width())
        visible = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, width)
        QLabel.setText(self, visible)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_elision()


class SelectableElidedLineEdit(QLineEdit):
    """Read-only text that elides at rest and exposes the full value on focus.

    Keeping the complete value in QLineEdit makes normal mouse selection,
    Ctrl+C and the native context menu work without a separate copy action.
    """

    def __init__(self, text: str = '', parent=None):
        super().__init__(str(text or ''), parent)
        self.setReadOnly(True)
        self.setFrame(False)
        self.setMinimumWidth(0)
        self.setTextMargins(2, 0, 2, 0)
        self.setToolTip(self.text())
        self.setCursorPosition(0)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setText(str(text or ''))
        self.setToolTip(super().text())
        self.setCursorPosition(0)
        self.update()

    def fullText(self) -> str:  # noqa: N802 - compatibility with ElidedLabel
        return super().text()

    def displayedText(self) -> str:  # noqa: N802 - Qt-style accessor
        width = max(0, self.contentsRect().adjusted(2, 0, -2, 0).width())
        return self.fontMetrics().elidedText(super().text(), Qt.TextElideMode.ElideRight, width)

    def paintEvent(self, event):
        if self.hasFocus():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        rect = self.contentsRect().adjusted(2, 0, -2, 0)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.displayedText())

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if event.reason() == Qt.FocusReason.PopupFocusReason:
            # The native context menu temporarily takes focus.  Keeping the
            # selection intact is what makes its Copy action reliable.
            self.update()
            return
        self.deselect()
        self.setCursorPosition(0)
        self.update()


def show_cover_preview(parent, pixmap: QPixmap | None, *, title: str = 'Podgląd okładki', note: str = '') -> None:
    if pixmap is None or pixmap.isNull():
        return
    from audio_library_organizer.ui.i18n import ui_text
    dialog = QDialog(parent)
    dialog.setWindowTitle(ui_text(parent, title))
    dialog.resize(820, 860)
    root = QVBoxLayout(dialog)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(10)

    image = QLabel()
    image.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image.setPixmap(pixmap.scaled(760, 760, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    root.addWidget(image, 1)

    size = QLabel(f'{ui_text(parent, "Rozmiar obrazu: ")}{pixmap.width()} × {pixmap.height()} px')
    size.setObjectName('MutedText')
    size.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(size)
    if note:
        info = QLabel(ui_text(parent, note))
        info.setWordWrap(True)
        info.setObjectName('MutedText')
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(info)

    row = QHBoxLayout(); row.addStretch()
    close = QPushButton(ui_text(parent, 'Zamknij')); close.clicked.connect(dialog.accept); row.addWidget(close)
    root.addLayout(row)
    dialog.exec()
