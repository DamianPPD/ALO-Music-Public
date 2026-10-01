from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QMenu, QToolButton

from audio_library_organizer.ui.state import status_presentation
from audio_library_organizer.ui.icons import alo_icon, library_icon
from audio_library_organizer.ui.i18n import ui_text


LEGEND_ITEMS = (
    ('ready', 'GOTOWE', 'Utwór gotowy do użycia / eksportu.', None),
    ('duplicate', 'DUPLIKAT', 'Utwór należy do grupy wymagającej porównania.', None),
    ('review', 'DO SPRAWDZENIA', 'Dane wymagają ręcznej kontroli.', None),
    ('review', 'PROBLEM', 'Poważny problem lub podejrzane dane wymagające szczególnej uwagi.', '#f34d64'),
    ('not_selected', 'NIE WYBIERAM', 'Utwór pominięty decyzją użytkownika.', None),
)


class LibraryLegendButton(QToolButton):
    def event(self, event):
        if event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            color = '#6de6a5' if event.type() == QEvent.Type.Enter else '#bdcbd3'
            self.setIcon(library_icon('legend', color, 20))
        return super().event(event)


def install_library_status_legend(library_page) -> QToolButton:
    """Install the compact status list in the top filter row above details."""
    existing = getattr(library_page, '_status_legend_button', None)
    if existing is not None:
        return existing

    button = LibraryLegendButton(library_page)
    button.setObjectName('LibraryStatusLegendButton')
    button.setText(ui_text(library_page, 'Legenda'))
    button.setIcon(library_icon('legend', '#bdcbd3', 20))
    button.setIconSize(QSize(20, 20))
    button.setToolTip(ui_text(library_page, 'Legenda'))
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    menu = QMenu(button)
    for status, label, description, accent_override in LEGEND_ITEMS:
        presentation = status_presentation(status)
        icons = {'ready': 'status', 'duplicate': 'duplicates', 'review': 'warning', 'not_selected': 'cancel'}
        accent = accent_override or {'ready': '#35d893', 'review': '#f5b649'}.get(status, presentation.accent)
        icon = alo_icon('alert_circle' if accent_override else icons[status], accent, 16)
        action = menu.addAction(icon, f'{label} — {description}')
        action.setToolTip(description)
    button.setMenu(menu)

    button.setFixedSize(34, 34)
    library_page._filters_top.addWidget(button, 0, Qt.AlignmentFlag.AlignRight)

    library_page._status_legend_button = button
    return button
