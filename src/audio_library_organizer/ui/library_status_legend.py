from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QToolButton

from audio_library_organizer.ui.state import status_presentation
from audio_library_organizer.ui.icons import alo_icon


LEGEND_ITEMS = (
    ('ready', 'GOTOWE', 'Utwór gotowy do użycia / eksportu.', None),
    ('duplicate', 'DUPLIKAT', 'Utwór należy do grupy wymagającej porównania.', None),
    ('review', 'DO SPRAWDZENIA', 'Dane wymagają ręcznej kontroli.', None),
    ('review', 'PROBLEM', 'Poważny problem lub podejrzane dane wymagające szczególnej uwagi.', '#f34d64'),
    ('not_selected', 'NIE WYBIERAM', 'Utwór pominięty decyzją użytkownika.', None),
)


def install_library_status_legend(library_page) -> QToolButton:
    """Install the compact status legend at the right end of the upper toolbar."""
    existing = getattr(library_page, '_status_legend_button', None)
    if existing is not None:
        return existing

    button = QToolButton(library_page)
    button.setObjectName('LibraryStatusLegendButton')
    button.setText('Legenda statusów')
    button.setIcon(alo_icon('info', '#72d8f0', 16))
    button.setToolTip('Pokaż znaczenie kolorów statusów')
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

    button.setFixedSize(28, 28)
    library_page._toolbar_top.addWidget(button, 0, Qt.AlignmentFlag.AlignRight)

    library_page._status_legend_button = button
    return button
