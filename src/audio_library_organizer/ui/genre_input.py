from __future__ import annotations

from collections.abc import Iterable

from audio_library_organizer.metadata.genre import genre_items

DEFAULT_GENRES = (
    'House', 'Deep House', 'Progressive House', 'Funky House', 'Tech House',
    'Trance', 'Progressive Trance', 'Vocal Trance', 'Psy-Trance',
    'Techno', 'Minimal', 'Hardstyle', 'Drum & Bass', 'Breaks', 'Garage',
    'Disco', 'Nu Disco', 'Funk', 'Dance', 'Eurodance', 'Pop', 'Rock',
    'Ambient', 'Chillout', 'Downtempo', 'Electro', 'EDM', 'Hip-Hop', 'R&B',
)


def build_genre_suggestions(values: Iterable[str | None], query: str = '') -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in tuple(values) + DEFAULT_GENRES:
        for item in genre_items(value, limit=50):
            key = item.casefold()
            if key not in seen:
                seen.add(key); result.append(item)
    result.sort(key=str.casefold)
    needle = query.strip().casefold()
    if needle:
        result = [item for item in result if needle in item.casefold()]
    return result


try:
    from PySide6.QtCore import Qt, Signal, QStringListModel
    from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QToolButton, QCompleter, QLabel
    from audio_library_organizer.ui.icons import alo_icon
    _QT = True
except ImportError:
    QWidget = object
    _QT = False


if _QT:
    class GenreChipInput(QWidget):
        """Compact multi-genre editor with autocomplete and removable chips."""

        textChanged = Signal(str)
        textEdited = Signal(str)

        def __init__(self, value: str | None = None, *, suggestions: Iterable[str | None] = (), max_items: int = 3, parent=None):
            super().__init__(parent)
            self.max_items = max(1, int(max_items))
            self._items: list[str] = []
            self._all_suggestions = build_genre_suggestions(suggestions)

            root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(4)
            self.chip_host = QWidget(); self.chip_row = QHBoxLayout(self.chip_host); self.chip_row.setContentsMargins(0, 0, 0, 0); self.chip_row.setSpacing(5)
            self.chip_row.addStretch(1); root.addWidget(self.chip_host)
            self.edit = QLineEdit(); self.edit.setPlaceholderText('Wpisz lub wybierz gatunek…'); root.addWidget(self.edit)
            self.model = QStringListModel(self._all_suggestions, self)
            self.completer = QCompleter(self.model, self); self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive); self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self.edit.setCompleter(self.completer)
            self.completer.activated.connect(self._add_from_text)
            self.edit.returnPressed.connect(self._commit_edit)
            self.edit.textEdited.connect(self._edit_changed)
            self.setText(value or '')

        def text(self) -> str:
            return ' / '.join(self._items)

        def setText(self, value: str) -> None:
            self._items = genre_items(value, limit=self.max_items)
            self.edit.clear()
            self._rebuild_chips(emit=False)

        def set_suggestions(self, suggestions: Iterable[str | None]) -> None:
            self._all_suggestions = build_genre_suggestions(suggestions)
            self.model.setStringList(self._all_suggestions)

        def genres(self) -> tuple[str, ...]:
            return tuple(self._items)

        def primary_genre(self) -> str | None:
            return self._items[0] if self._items else None

        def _edit_changed(self, text: str) -> None:
            if any(sep in text for sep in (',', ';', '|', '/')):
                self._add_from_text(text)

        def _commit_edit(self) -> None:
            self._add_from_text(self.edit.text())

        def _add_from_text(self, text: str) -> None:
            candidates = genre_items(text, limit=self.max_items)
            known = {item.casefold() for item in self._items}
            changed = False
            for item in candidates:
                if len(self._items) >= self.max_items:
                    break
                if item.casefold() in known:
                    continue
                self._items.append(item)
                known.add(item.casefold())
                changed = True
            self.edit.clear()
            if changed:
                self._rebuild_chips()
                self.textEdited.emit(self.text())

        def _remove(self, index: int) -> None:
            if 0 <= index < len(self._items):
                self._items.pop(index); self._rebuild_chips(); self.textEdited.emit(self.text())

        def _move_first(self, index: int) -> None:
            if 0 < index < len(self._items):
                item = self._items.pop(index); self._items.insert(0, item); self._rebuild_chips(); self.textEdited.emit(self.text())

        def _rebuild_chips(self, *, emit: bool = True) -> None:
            while self.chip_row.count() > 1:
                item = self.chip_row.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            for index, genre in enumerate(self._items):
                chip = QToolButton(); chip.setObjectName('GenreChip'); chip.setText(f'{genre} ×')
                chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                chip.setIcon(alo_icon('status' if index == 0 else 'cancel', '#62df98' if index == 0 else '#8da1ad', 13))
                chip.setToolTip('Pierwszy gatunek jest główny i decyduje o folderze. Kliknij, aby usunąć.' if index == 0 else 'Kliknij prawym przyciskiem, aby ustawić jako główny. Kliknij, aby usunąć.')
                chip.clicked.connect(lambda _=False, i=index: self._remove(i))
                chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                chip.customContextMenuRequested.connect(lambda _pos, i=index: self._move_first(i))
                self.chip_row.insertWidget(self.chip_row.count() - 1, chip)
            if emit:
                self.textChanged.emit(self.text())
