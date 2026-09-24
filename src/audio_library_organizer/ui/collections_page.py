from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QAbstractItemView, QHeaderView, QMessageBox, QTabWidget,
)

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs.collections import list_collections, remove_collection_file
from audio_library_organizer.ui.i18n import ui_text


class CollectionsPage(QWidget):
    """Browser for physical user-created MP3 folders."""

    refresh_requested = Signal()
    add_from_library_requested = Signal()
    play_requested = Signal(object)
    playlist_requested = Signal(object)

    HEADERS = ('Folder', 'Utwory', 'Rozmiar')

    def __init__(self, library: LibraryPaths, parent=None):
        super().__init__(parent)
        self.library = library
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(10)

        title = QLabel('Moje foldery MP3')
        title.setStyleSheet('font-size:20pt;font-weight:750;')
        root.addWidget(title)
        note = QLabel('Fizyczne kopie wybranych utworów. Ten katalog jest wyłączony ze skanowania głównej biblioteki.')
        note.setWordWrap(True); note.setObjectName('MutedText'); root.addWidget(note)

        actions = QHBoxLayout()
        self.open_root = QPushButton('Otwórz MOJE_FOLDERY_MP3')
        self.open_root.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.custom_folders))))
        self.add_from_library = QPushButton('Dodaj z Biblioteki'); self.add_from_library.clicked.connect(self.add_from_library_requested)
        self.playlist_btn = QPushButton('Utwórz playlistę M3U8'); self.playlist_btn.clicked.connect(self._request_playlist)
        self.remove_file = QPushButton('Usuń zaznaczony plik z folderu'); self.remove_file.clicked.connect(self._remove_selected_file)
        self.refresh_btn = QPushButton('Odśwież'); self.refresh_btn.clicked.connect(self.refresh)
        actions.addWidget(self.open_root); actions.addWidget(self.add_from_library); actions.addWidget(self.playlist_btn); actions.addWidget(self.remove_file); actions.addWidget(self.refresh_btn); actions.addStretch(1)
        root.addLayout(actions)

        self.tabs = QTabWidget(); self.tabs.setObjectName('CollectionsTabs')
        folders_tab = QWidget(); folders_lay = QVBoxLayout(folders_tab); folders_lay.setContentsMargins(0, 4, 0, 0)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._open_files_tab)
        self.table.itemSelectionChanged.connect(self._refresh_files)
        folders_lay.addWidget(self.table, 1)
        self.empty = QLabel('Nie masz jeszcze własnych folderów MP3. W Bibliotece zaznacz utwory i wybierz „Utwórz folder z zaznaczonych”.')
        self.empty.setWordWrap(True); self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty.setObjectName('MutedText'); folders_lay.addWidget(self.empty)

        files_tab = QWidget(); files_lay = QVBoxLayout(files_tab); files_lay.setContentsMargins(0, 4, 0, 0)
        self.files_title = QLabel('Wybierz folder w zakładce „Moje foldery”.'); self.files_title.setObjectName('MutedText'); files_lay.addWidget(self.files_title)
        self.files = QTableWidget(0, 2); self.files.setHorizontalHeaderLabels(('Plik w folderze', 'Rozmiar'))
        self.files.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.files.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); self.files.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch); self.files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.files.doubleClicked.connect(self._play_selected_file)
        files_lay.addWidget(self.files, 1)

        self.tabs.addTab(folders_tab, 'Moje foldery')
        self.tabs.addTab(files_tab, 'Moje pliki')
        root.addWidget(self.tabs, 1)
        self.refresh()

    def set_library(self, library: LibraryPaths):
        self.library = library
        self.refresh()

    def refresh(self):
        items = list_collections(self.library)
        self.table.setRowCount(0)
        for info in items:
            row = self.table.rowCount(); self.table.insertRow(row)
            name = QTableWidgetItem(info.name); name.setData(Qt.ItemDataRole.UserRole, str(info.path)); self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(str(info.file_count)))
            self.table.setItem(row, 2, QTableWidgetItem(self._fmt_size(info.size_bytes)))
        self.empty.setVisible(not items)
        self.table.setVisible(bool(items))
        if items and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self._refresh_files()

    def _selected_collection_path(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return None if not value else Path(value)

    def _collection_files(self) -> list[Path]:
        folder = self._selected_collection_path()
        if folder is None or not folder.is_dir():
            return []
        return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {'.mp3','.flac','.wav','.m4a','.aac','.ogg','.opus','.wma'}), key=lambda p: p.name.casefold())

    def _refresh_files(self):
        self.files.setRowCount(0)
        folder = self._selected_collection_path()
        self.files_title.setText(folder.name if folder else 'Wybierz folder w zakładce „Moje foldery”.')
        for path in self._collection_files():
            row = self.files.rowCount(); self.files.insertRow(row)
            item = QTableWidgetItem(path.name); item.setData(Qt.ItemDataRole.UserRole, str(path)); self.files.setItem(row, 0, item)
            self.files.setItem(row, 1, QTableWidgetItem(self._fmt_size(path.stat().st_size)))

    def _open_files_tab(self):
        self._refresh_files(); self.tabs.setCurrentIndex(1)

    def _selected_file_path(self) -> Path | None:
        row = self.files.currentRow()
        if row < 0:
            return None
        item = self.files.item(row, 0); value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return Path(value) if value else None

    def _play_selected_file(self):
        path = self._selected_file_path()
        if path is None or not path.is_file():
            return
        stat = path.stat()
        self.play_requested.emit(TrackRecord(path=path, size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns, title=path.stem, status='ready'))

    def _request_playlist(self):
        paths = self._collection_files()
        if not paths:
            QMessageBox.information(self, ui_text(self, 'Brak plików'), ui_text(self, 'Wybierz folder zawierający utwory.'))
            return
        self.playlist_requested.emit(paths)

    def _remove_selected_file(self):
        folder = self._selected_collection_path(); path = self._selected_file_path()
        if folder is None or path is None:
            QMessageBox.information(self, ui_text(self, 'Brak zaznaczenia'), ui_text(self, 'Wybierz plik we własnym folderze MP3.')); return
        answer = QMessageBox.question(self, ui_text(self, 'Usuń z folderu'), ui_text(self, 'Usunąć tylko tę kopię z MOJE_FOLDERY_MP3? Oryginalny plik i główna biblioteka pozostaną bez zmian.'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes and remove_collection_file(folder, path):
            self.refresh(); self._refresh_files()

    def _open_selected(self):
        path = self._selected_collection_path()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @staticmethod
    def _fmt_size(size: int) -> str:
        if size >= 1024 ** 3:
            return f'{size / (1024 ** 3):.2f} GB'
        return f'{size / (1024 ** 2):.1f} MB'
