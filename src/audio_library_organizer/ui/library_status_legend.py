from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QToolButton

from audio_library_organizer.ui.state import status_presentation
from audio_library_organizer.ui.icons import alo_icon


LEGEND_ITEMS = (
    ('ready', 'GOTOWE', 'Utwór gotowy do użycia / eksportu.', None),
    ('duplicate', 'DUPLIKAT', 'Utwór należy do grupy wymagającej porównania.', None),
    ('review', 'DO SPRAWDZENIA', 'Dane wymagają ręcznej kontroli.', None),
    ('review', 'DO SPRAWDZENIA — ważne', 'Poważny problem lub podejrzane dane wymagające szczególnej uwagi.', '#ff7777'),
    ('not_selected', 'NIE WYBIERAM', 'Utwór pominięty decyzją użytkownika.', None),
)


def _color_icon(color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def install_library_status_legend(library_page) -> QToolButton:
    """Install a compact dropdown legend in the existing Library view-control row."""
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
        accent = accent_override or presentation.accent
        action = menu.addAction(_color_icon(accent), f'{label} — {description}')
        action.setToolTip(description)
    button.setMenu(menu)

    root = library_page.layout()
    view_controls = root.itemAt(1).layout() if root is not None and root.count() > 1 else None
    if view_controls is not None:
        view_controls.addWidget(button)
    elif root is not None:
        root.addWidget(button)

    library_page._status_legend_button = button
    return button
