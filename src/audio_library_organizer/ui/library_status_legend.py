from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QLabel, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)

from audio_library_organizer.ui.state import status_presentation
from audio_library_organizer.ui.icons import alo_icon, library_icon
from audio_library_organizer.ui.i18n import apply_static_language, language_for, ui_text
from audio_library_organizer.ui.library_file_state import FILE_STATE_COLORS


LEGEND_ITEMS = (
    ('ready', 'GOTOWE', 'Kompletne wymagane dane; utwór oznaczony jako gotowy.', None),
    ('duplicate', 'DUPLIKAT', 'Utwór należy do grupy wymagającej porównania.', None),
    ('review', 'DO SPRAWDZENIA', 'Dane wymagają ręcznej kontroli.', None),
    ('review', 'PROBLEM', 'Poważny problem lub podejrzane dane wymagające szczególnej uwagi.', '#f34d64'),
    ('not_selected', 'NIE WYBIERAM', 'Utwór pominięty decyzją użytkownika.', None),
)

FILE_LEGEND_DESCRIPTIONS = (
    'Potwierdzony plik wynikowy zgodny z oczekiwaniami.',
    'Dostępne źródło, bez przypisanego pliku biblioteki.',
    'Potwierdzona różnica między wynikiem a oczekiwaniami.',
    'Kontrola potwierdziła brak pliku źródłowego.',
    'Kontrola potwierdziła brak oczekiwanego pliku biblioteki.',
    'Potwierdzona kolizja lub sprzeczne powiązania plików.',
)
UNCONFIRMED_NOTE = ('Stan pliku niepotwierdzony oznacza, że program nie ma wystarczających '
                    'danych do jego wiarygodnego określenia.')


def _status_icon(status, accent_override):
    # Keep exactly the shipped metadata icon assets and color recipes.
    presentation = status_presentation(status)
    icons = {'ready': 'status_ready', 'duplicate': 'duplicates', 'review': 'status_review', 'not_selected': 'cancel'}
    accent = accent_override or {'ready': '#35d893', 'review': '#d8a23a'}.get(status, presentation.accent)
    factory = library_icon if status in {'ready', 'review'} else alo_icon
    return factory('status_problem' if accent_override else icons[status], accent, 16), accent


class LibraryLegendDialog(QDialog):
    """One owned, non-modal legend; it never changes Library data or filters."""

    def __init__(self, owner):
        super().__init__(owner)
        self.setObjectName('LibraryLegendDialog')
        self.setWindowTitle('Legenda')
        owner.installEventFilter(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        self._scroll = QScrollArea(self)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        grid = QGridLayout(self._body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(2, 1)

        def heading(row, text):
            label = QLabel(text)
            label.setObjectName('LibraryLegendHeading')
            font = label.font(); font.setBold(True); label.setFont(font)
            grid.addWidget(label, row, 0, 1, 3)

        def entry(row, name, description, accent, icon=None):
            if icon is not None:
                image = QLabel()
                image.setObjectName('LibraryLegendIcon')
                image.setPixmap(icon.pixmap(16, 16))
                image.setFixedSize(20, 20)
                grid.addWidget(image, row, 0, Qt.AlignmentFlag.AlignTop)
            label = QLabel(name)
            label.setObjectName('LibraryLegendName')
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setStyleSheet(f'color: {accent};')
            font = label.font(); font.setBold(True); label.setFont(font)
            grid.addWidget(label, row, 1, Qt.AlignmentFlag.AlignTop)
            detail = QLabel(description)
            detail.setObjectName('LibraryLegendDescription')
            detail.setTextFormat(Qt.TextFormat.PlainText)
            detail.setWordWrap(True)
            grid.addWidget(detail, row, 2, Qt.AlignmentFlag.AlignTop)

        heading(0, 'STANY UTWORÓW')
        for row, (status, name, description, override) in enumerate(LEGEND_ITEMS, 1):
            icon, accent = _status_icon(status, override)
            entry(row, name, description, accent, icon)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(line, 6, 0, 1, 3)
        heading(7, 'STANY TECHNICZNE PLIKÓW')
        for row, (color, description) in enumerate(zip(FILE_STATE_COLORS.values(), FILE_LEGEND_DESCRIPTIONS), 8):
            entry(row, color.label, description, color.accent)
        note = QLabel(UNCONFIRMED_NOTE)
        note.setObjectName('LibraryLegendUnconfirmed')
        note.setWordWrap(True)
        grid.addWidget(note, 14, 0, 1, 3)
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('Zamknij')
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def open_legend(self):
        # Refresh on every opening; parent language switches also reach all labels.
        apply_static_language(self, language_for(self.parentWidget()))
        area = self.parentWidget().screen().availableGeometry()
        width = min(820, area.width() - 32)
        margins = self.layout().contentsMargins()
        body_width = width - margins.left() - margins.right()
        self._body.layout().activate()
        body_height = self._body.layout().totalHeightForWidth(body_width)
        if body_height < 0:
            body_height = self._body.sizeHint().height()
        height = body_height + margins.top() + margins.bottom() + self.layout().spacing() + self.findChild(QDialogButtonBox).sizeHint().height()
        self.resize(width, min(height, area.height() - 32))
        self.show()
        self.raise_()
        self.activateWindow()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() in (QEvent.Type.Close, QEvent.Type.Hide):
            self.hide()
        return super().eventFilter(watched, event)


class LibraryLegendButton(QToolButton):
    def event(self, event):
        if event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            color = '#6de6a5' if event.type() == QEvent.Type.Enter else '#bdcbd3'
            self.setIcon(library_icon('legend', color, 20))
        return super().event(event)


def install_library_status_legend(library_page) -> QToolButton:
    """Reuse the existing compact button; one dialog replaces the nested menu."""
    existing = getattr(library_page, '_status_legend_button', None)
    if existing is not None:
        return existing
    button = LibraryLegendButton(library_page)
    button.setObjectName('LibraryStatusLegendButton')
    button.setText(ui_text(library_page, 'Legenda'))
    button.setIcon(library_icon('legend', '#bdcbd3', 20))
    button.setIconSize(QSize(20, 20))
    button.setToolTip(ui_text(library_page, 'Legenda'))
    dialog = LibraryLegendDialog(library_page)
    button.clicked.connect(dialog.open_legend)
    button.setFixedSize(34, 34)
    library_page._filters_top.addWidget(button, 0, Qt.AlignmentFlag.AlignRight)
    library_page._status_legend_button = button
    return button
