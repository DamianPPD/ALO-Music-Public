from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QHeaderView, QLabel, QMenu,
    QPushButton, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from audio_library_organizer.storage.library_profiles import LibraryRegistry
from audio_library_organizer.ui.i18n import ui_text


def scan_time_text(value: str) -> str:
    try:
        when = datetime.fromisoformat(value)
        if when.tzinfo is not None:
            when = when.astimezone()
        return when.strftime('%d.%m.%Y %H:%M')
    except ValueError:
        return '—'


class ScanSourcesWidget(QWidget):
    """Compact view of the active library's existing informational scan history."""

    HEADERS = ('Folder źródłowy', 'Ostatni skan', 'Pliki', 'Status', 'Akcja')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry: LibraryRegistry | None = None
        self.store = None
        self.history_dialog: QDialog | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(5)
        self.table = QTableWidget(0, 5, self)
        self.table.setObjectName('StartScanSourcesTable')
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.verticalHeader().setMinimumSectionSize(26)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setStretchLastSection(False)
        for index, width in enumerate((210, 119, 42, 44, 48)):
            self.table.setColumnWidth(index, width)
        layout.addWidget(self.table, 1)
        self.add_button = QPushButton('+ Dodaj źródło', self)
        self.add_button.setObjectName('StartAddSource')
        self.add_button.setToolTip('Wybierz folder z nowymi plikami')
        footer = QHBoxLayout(); footer.addWidget(self.add_button); footer.addStretch(1)
        layout.addLayout(footer)
        self.refresh()

    def set_registry(self, registry: LibraryRegistry, store) -> None:
        self.registry, self.store = registry, store
        self.refresh()

    def refresh(self) -> None:
        table = self.table
        scroll = table.verticalScrollBar().value()
        table.setHorizontalHeaderLabels([ui_text(self, text) for text in self.HEADERS])
        entries = self.registry.scan_history() if self.registry else ()
        previous_widgets = [table.cellWidget(row, column) for row in range(table.rowCount())
                            for column in (3, 4)]
        table.setRowCount(len(entries))
        path_width = 210
        for row, entry in enumerate(entries):
            path = entry.source_dir
            text = str(path)
            path_width = max(path_width, table.fontMetrics().horizontalAdvance(text) + 18)
            for column, value in enumerate((text, scan_time_text(entry.scanned_at), str(entry.file_count))):
                item = QTableWidgetItem(value)
                item.setToolTip(text if column == 0 else value)
                if column == 2: item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)
            available = path.is_dir()
            status = QWidget(table)
            status_layout = QHBoxLayout(status); status_layout.setContentsMargins(0, 0, 0, 0)
            dot = QLabel(status); dot.setObjectName('ScanSourceStatusDot')
            dot.setFixedSize(7, 7); dot.setProperty('available', available)
            dot.setToolTip(ui_text(self, 'Dostępna' if available else 'Niedostępna'))
            dot.setAccessibleName(dot.toolTip())
            status_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row, 3, status)
            action = QToolButton(table); action.setObjectName('ScanSourceActions')
            action.setText('⋮'); action.setAutoRaise(True)
            action.setToolTip(ui_text(self, 'Akcja'))
            menu = self.menu_for_source(path, parent=action)
            action.setMenu(menu)
            action.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            action.menu().aboutToShow.connect(lambda target=path, menu=action.menu():
                                             menu.actions()[0].setEnabled(target.is_dir()))
            table.setCellWidget(row, 4, action)
            table.setRowHeight(row, 26)
        table.setColumnWidth(0, path_width)
        table.verticalScrollBar().setValue(scroll)
        # Qt deletes replaced widgets later; keep them out of subsequent paints.
        for previous in previous_widgets:
            if previous is not None: previous.hide()
        self.add_button.setText(ui_text(self, '+ Dodaj źródło'))

    def menu_for_source(self, path: Path, *, parent=None) -> QMenu:
        path = Path(path)
        menu = QMenu(parent or self)
        menu.setObjectName('StartScanSourceMenu')
        open_action = menu.addAction(ui_text(self, 'Otwórz folder'))
        open_action.setEnabled(path.is_dir())
        open_action.triggered.connect(lambda: self._open_source(path))
        copy = menu.addAction(ui_text(self, 'Kopiuj ścieżkę'))
        copy.triggered.connect(lambda: QApplication.clipboard().setText(str(path)))
        history = menu.addAction(ui_text(self, 'Pokaż historię skanów'))
        history.triggered.connect(lambda: self._show_history(path))
        remove = menu.addAction(ui_text(self, 'Usuń z historii'))
        remove.triggered.connect(lambda: self._remove_history(path))
        return menu

    def _open_source(self, path: Path) -> None:
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.refresh()

    def _show_history(self, path: Path) -> None:
        if not self.registry: return
        if self.history_dialog is not None: self.history_dialog.close()
        dialog = QDialog(self); dialog.setObjectName('StartScanHistoryDialog')
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle(ui_text(self, 'Historia skanów'))
        dialog.resize(500, 330)
        layout = QVBoxLayout(dialog)
        title = QLabel(str(path)); title.setWordWrap(True); layout.addWidget(title)
        entries = self.registry.scan_history_for_source(path)
        table = QTableWidget(len(entries), 2, dialog)
        table.setHorizontalHeaderLabels([ui_text(self, 'Ostatni skan'), ui_text(self, 'Pliki')])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, entry in enumerate(entries):
            table.setItem(row, 0, QTableWidgetItem(scan_time_text(entry.scanned_at)))
            table.setItem(row, 1, QTableWidgetItem(str(entry.file_count)))
        layout.addWidget(table)
        self.history_dialog = dialog
        def clear_dialog():
            if self.history_dialog is dialog: self.history_dialog = None
        dialog.destroyed.connect(clear_dialog)
        dialog.show()

    def _remove_history(self, path: Path) -> None:
        if not self.registry: return
        self.registry.remove_source_history(path)
        if self.store is not None: self.registry.save(self.store)
        self.refresh()
