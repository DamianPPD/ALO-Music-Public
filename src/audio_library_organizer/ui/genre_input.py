from __future__ import annotations

from collections.abc import Iterable
import re

from mutagen.id3 import TCON

from audio_library_organizer.domain.genres import GenreSettings
from audio_library_organizer.metadata.genre import genre_items
from audio_library_organizer.ui.i18n import ui_text

# Preserve the existing Library filter vocabulary; editor choices use GenreSettings.
DEFAULT_GENRES = (
    'House', 'Deep House', 'Progressive House', 'Funky House', 'Tech House',
    'Trance', 'Progressive Trance', 'Vocal Trance', 'Psy-Trance',
    'Techno', 'Minimal', 'Hardstyle', 'Drum & Bass', 'Breaks', 'Garage',
    'Disco', 'Nu Disco', 'Funk', 'Dance', 'Eurodance', 'Pop', 'Rock',
    'Ambient', 'Chillout', 'Downtempo', 'Electro', 'EDM', 'Hip-Hop', 'R&B',
)

_NORMALIZED_PATH = r'(?P<tail>(?:\s+/\s+[^\s/,;|]+(?:[ \t]+[^\s/,;|]+)*)*)'
_URL = re.compile(r'(?<![\w])(?:[a-z][a-z0-9+.-]*://|www\.)[^\s,;|]+' + _NORMALIZED_PATH, re.IGNORECASE)
# Imported genres have already gone through normalize_genre_list: an URL can
# therefore arrive as "https: / example.com / download". Remove that whole
# address before genre_items can turn its host/path into separate suggestions.
_SPLIT_URL = re.compile(r'(?<![\w])(?:https?|ftp):\s*/\s*(?:/\s*)?[^\s,;|]+' + _NORMALIZED_PATH, re.IGNORECASE)
_DOMAIN = re.compile(
    r'(?<![\w.-])(?P<address>(?:[^\W_](?:(?:[^\W_]|-){0,61}[^\W_])?\.)+'
    r'(?:[^\W\d_]{2,63}|xn--[a-z0-9-]{2,59})(?::[0-9]{1,5})?'
    r'(?:[/?#][^\s,;|]*)?)(?![\w.-])' + _NORMALIZED_PATH, re.IGNORECASE)
_MUSIC_NAMES = DEFAULT_GENRES + tuple(TCON.GENRES)
_KNOWN_GENRE_FORMS = {re.sub(r'\W+', '', genre.casefold()) for genre in _MUSIC_NAMES}
_MUSIC_WORDS = {word for genre in _MUSIC_NAMES
                for word in re.findall(r'[^\W\d_]{3,}', genre.casefold())}


def _is_music_label(value: str) -> bool:
    compact = re.sub(r'\W+', '', value.casefold())
    words = re.findall(r'[^\W\d_]+', value.casefold())
    return compact in _KNOWN_GENRE_FORMS or (len(words) > 1 and words[-1] in _MUSIC_WORDS)


def _keep_music_from_normalized_path(match) -> str:
    # Slash normalization loses the distinction between a URL path and a
    # following genre ("www.example.com; House" becomes "... / House").
    # Preserve recognizable music labels in that ambiguous spaced tail.
    return ' / '.join(item for item in genre_items(match.group('tail'), limit=50)
                      if _is_music_label(item))


def _suggestion_genres(value: str | None) -> list[str]:
    text = _URL.sub(_keep_music_from_normalized_path, str(value or ''))
    text = _SPLIT_URL.sub(_keep_music_from_normalized_path, text)

    def remove_domain(match):
        address = match.group('address')
        # Retain ambiguous dotted music labels, including subgenres outside
        # the defaults (Hard.Trance, Melodic.Techno, Post.Punk). The existing
        # ID3 vocabulary is used only for recognition, not added to suggestions.
        # A path/port or an explicit URL is still an unambiguous web address.
        if not any(char in address for char in '/:?#'):
            if _is_music_label(address):
                tail = ' / '.join(genre_items(match.group('tail'), limit=50))
                return ' / '.join([address, *_suggestion_genres(tail)])
        return _keep_music_from_normalized_path(match)

    return genre_items(_DOMAIN.sub(remove_domain, text), limit=50)


def build_genre_suggestions(values: Iterable[str | None], query: str = '') -> list[str]:
    """Sanitize legacy values used by the Library's genre filter."""
    seen: set[str] = set()
    result: list[str] = []
    for value in tuple(values) + DEFAULT_GENRES:
        for item in _suggestion_genres(value):
            key = item.casefold()
            if key not in seen:
                seen.add(key); result.append(item)
    result.sort(key=str.casefold)
    needle = query.strip().casefold()
    if needle:
        result = [item for item in result if needle in item.casefold()]
    return result


def controlled_genre_suggestions(values: Iterable[str | None]) -> list[str]:
    """Use explicitly configured choices, preserving names such as R&B / Soul."""
    clean = []
    for value in values:
        if not isinstance(value, str):
            continue
        name = value.strip()
        sanitized = _suggestion_genres(name)
        if sanitized == genre_items(name, limit=50):
            clean.append(name)
        else:
            clean.extend(sanitized)
    return GenreSettings(tuple(clean)).suggestions()


try:
    from PySide6.QtCore import Qt, Signal, QStringListModel
    from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLineEdit, QToolButton, QCompleter, QLabel
    _QT = True
except ImportError:
    QWidget = object
    _QT = False


if _QT:
    class GenreTag(QFrame):
        removed = Signal(str)

        def __init__(self, name: str, *, removable: bool = False, parent=None):
            super().__init__(parent)
            self.setObjectName('GenreChip')
            self.setProperty('genreName', name)
            self.setFixedHeight(25)
            row = QHBoxLayout(self)
            row.setContentsMargins(8, 0, 5 if removable else 8, 0)
            row.setSpacing(5)
            label = QLabel(name)
            label.setObjectName('GenreTagLabel')
            label.setProperty('literalText', True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            row.addWidget(label)
            if removable:
                remove = QToolButton()
                remove.setObjectName('GenreTagRemove')
                remove.setText('×')
                remove.setFixedSize(16, 18)
                remove.setCursor(Qt.CursorShape.PointingHandCursor)
                remove.setProperty('_alo_pl_tooltip', 'Usuń gatunek')
                remove.setToolTip(ui_text(self, 'Usuń gatunek'))
                remove.setAccessibleName(ui_text(self, 'Usuń gatunek') + ': ' + name)
                remove.clicked.connect(lambda: self.removed.emit(name))
                row.addWidget(remove)


    class GenreChipInput(QWidget):
        """Compact multi-genre editor with autocomplete and removable chips."""

        textChanged = Signal(str)
        textEdited = Signal(str)

        def __init__(self, value: str | None = None, *, suggestions: Iterable[str | None] = (), max_items: int = 3, parent=None):
            super().__init__(parent)
            self.max_items = max(1, int(max_items))
            self._items: list[str] = []
            self._all_suggestions = controlled_genre_suggestions(suggestions)

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
            self._all_suggestions = controlled_genre_suggestions(suggestions)
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
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            for index, genre in enumerate(self._items):
                chip = GenreTag(genre, removable=True, parent=self.chip_host)
                tooltip = 'Pierwszy gatunek jest główny i decyduje o folderze. Kliknij ×, aby usunąć.' if index == 0 else 'Kliknij prawym przyciskiem, aby ustawić jako główny. Kliknij ×, aby usunąć.'
                chip.setProperty('_alo_pl_tooltip', tooltip)
                chip.setToolTip(ui_text(self, tooltip))
                chip.removed.connect(lambda _name, i=index: self._remove(i))
                chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                chip.customContextMenuRequested.connect(lambda _pos, i=index: self._move_first(i))
                self.chip_row.insertWidget(self.chip_row.count() - 1, chip)
            if emit:
                self.textChanged.emit(self.text())
