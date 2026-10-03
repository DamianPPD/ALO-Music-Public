from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLayout, QLabel, QLineEdit,
    QPushButton, QTabWidget, QSizePolicy,
)

from audio_library_organizer.domain.genres import ALO_GENRES, GenreSettings
from audio_library_organizer.ui.genre_input import GenreTag
from audio_library_organizer.ui.i18n import ui_text


class GenreWrapLayout(QLayout):
    """Small wrapping layout shared by the two settings vocabularies."""

    def __init__(self, parent):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), measure=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, measure=False)

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        return size

    def sizeHint(self):
        return self.minimumSize()

    def _arrange(self, rect, *, measure):
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            if x > rect.x() and x + size.width() > rect.right() + 1:
                x = rect.x()
                y += line_height + self.spacing()
                line_height = 0
            if not measure:
                item.setGeometry(QRect(x, y, size.width(), size.height()))
            x += size.width() + self.spacing()
            line_height = max(line_height, size.height())
        return y - rect.y() + line_height


class GenreSettingsWidget(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = GenreSettings.from_store(store)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(9)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Wyszukaj gatunek…')
        self.search.setClearButtonEnabled(True)
        root.addWidget(self.search)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('GenreSettingsTabs')
        root.addWidget(self.tabs)

        base = QWidget()
        base_layout = QVBoxLayout(base)
        base_layout.setSpacing(9)
        note = QLabel('Lista bazowa ALO — tylko do odczytu.')
        note.setObjectName('MutedText')
        base_layout.addWidget(note)
        self.base_host = QWidget()
        self.base_layout = GenreWrapLayout(self.base_host)
        for name in sorted(ALO_GENRES, key=str.casefold):
            self.base_layout.addWidget(GenreTag(name))
        base_layout.addWidget(self.base_host)
        base_layout.addStretch(1)
        self.tabs.addTab(base, '')

        custom = QWidget()
        custom_layout = QVBoxLayout(custom)
        custom_layout.setSpacing(9)
        add_row = QHBoxLayout()
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText('Wpisz własny gatunek…')
        self.add_button = QPushButton('+ Dodaj')
        self.add_button.setObjectName('GenreAddButton')
        add_row.addWidget(self.custom_edit, 1)
        add_row.addWidget(self.add_button)
        custom_layout.addLayout(add_row)
        self.notice = QLabel()
        self.notice.setObjectName('MutedText')
        self.notice.setWordWrap(True)
        custom_layout.addWidget(self.notice)
        self.custom_host = QWidget()
        self.custom_layout = GenreWrapLayout(self.custom_host)
        custom_layout.addWidget(self.custom_host)
        custom_layout.addStretch(1)
        self.tabs.addTab(custom, '')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.search.textChanged.connect(self._filter)
        self.add_button.clicked.connect(self._add)
        self.custom_edit.returnPressed.connect(self._add)
        self._rebuild_custom()

    def _add(self):
        name = self.custom_edit.text().strip()
        candidate = GenreSettings((*self.settings.custom_genres, name))
        if candidate == self.settings:
            caption = 'Wpisz nazwę gatunku.' if not name else 'Ten gatunek jest już na liście.'
            self.notice.setProperty('_alo_pl_text', caption)
            self.notice.setText(ui_text(self, caption))
            return
        self.settings = candidate
        self.settings.save(self.store)
        self.custom_edit.clear()
        self.notice.setProperty('_alo_pl_text', '')
        self.notice.clear()
        self._rebuild_custom()

    def _remove(self, name):
        self.settings = GenreSettings(tuple(value for value in self.settings.custom_genres if value != name))
        self.settings.save(self.store)
        self._rebuild_custom()

    def _rebuild_custom(self):
        while self.custom_layout.count():
            widget = self.custom_layout.takeAt(0).widget()
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        for name in self.settings.custom_genres:
            tag = GenreTag(name, removable=True, parent=self.custom_host)
            tag.removed.connect(self._remove)
            self.custom_layout.addWidget(tag)
        titles = [f'Gatunki ALO  {len(ALO_GENRES)}', f'Moje gatunki  {len(self.settings.custom_genres)}']
        self.tabs.setProperty('_alo_pl_tabs', titles)
        for index, title in enumerate(titles):
            self.tabs.setTabText(index, ui_text(self, title))
        self._filter()

    def _filter(self):
        needle = self.search.text().strip().casefold()
        for host, layout in ((self.base_host, self.base_layout), (self.custom_host, self.custom_layout)):
            for index in range(layout.count()):
                tag = layout.itemAt(index).widget()
                tag.setVisible(needle in str(tag.property('genreName')).casefold())
            layout.invalidate()
            host.updateGeometry()
