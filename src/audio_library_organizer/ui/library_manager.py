from __future__ import annotations

from datetime import datetime
import html
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl, QSize
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QFileDialog, QMessageBox, QLineEdit, QFrame, QToolButton, QMenu, QInputDialog, QAbstractItemView,
)

from audio_library_organizer.storage.library_profiles import LibraryRegistry
from audio_library_organizer.jobs.reset import reset_library_index
from audio_library_organizer.ui.i18n import apply_static_language, language_for, ui_text
from audio_library_organizer.ui.icons import alo_icon


class CreateLibraryDialog(QDialog):
    """Create an output library. Scan/source folders are added separately."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._library_root: Path | None = None
        self._name_was_edited = False
        self.setWindowTitle('Utwórz nową bibliotekę')
        self.resize(620, 340)
        root = QVBoxLayout(self); root.setContentsMargins(18, 18, 18, 18); root.setSpacing(12)

        heading = QLabel('Utwórz nową bibliotekę')
        heading.setObjectName('LibraryWizardTitle')
        root.addWidget(heading)

        description = QLabel(
            'Wybierz folder, w którym ALO będzie zapisywać gotowe i przetworzone utwory. '
            'Foldery źródłowe dodasz osobno podczas skanowania.\n\n'
            'Pliki muzyczne nie zostaną skopiowane ani usunięte. ALO nie przenosi ani nie usuwa plików źródłowych.'
        )
        description.setWordWrap(True); description.setObjectName('InfoBanner'); root.addWidget(description)

        name_label = QLabel('Nazwa biblioteki')
        name_label.setObjectName('FieldHeading'); root.addWidget(name_label)
        self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText('np. House 2000')
        self.name_edit.textEdited.connect(self._name_edited)
        root.addWidget(self.name_edit)

        folder_label = QLabel('Folder biblioteki / zapisu')
        folder_label.setObjectName('FieldHeading'); root.addWidget(folder_label)
        folder_row = QHBoxLayout(); folder_row.setSpacing(8)
        self.folder_value = QLabel('Nie wybrano folderu'); self.folder_value.setObjectName('PathPreview'); self.folder_value.setWordWrap(True)
        choose = QPushButton('Wybierz folder zapisu'); choose.setObjectName('ChooseLibraryFolderAction'); choose.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder_value, 1); folder_row.addWidget(choose); root.addLayout(folder_row)

        root.addStretch(1)
        actions = QHBoxLayout(); actions.addStretch(1)
        cancel = QPushButton('Anuluj'); cancel.clicked.connect(self.reject); actions.addWidget(cancel)
        self.create_button = QPushButton('Utwórz bibliotekę'); self.create_button.setObjectName('Primary'); self.create_button.setEnabled(False); self.create_button.clicked.connect(self.accept); actions.addWidget(self.create_button)
        root.addLayout(actions)

    def _name_edited(self, _text: str):
        self._name_was_edited = True
        self.create_button.setEnabled(self._library_root is not None and bool(self.name_edit.text().strip()))

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, ui_text(self, 'Wybierz folder biblioteki / zapisu'))
        if not folder:
            return
        self._library_root = Path(folder).expanduser().resolve()
        self.folder_value.setText(str(self._library_root))
        if not self._name_was_edited or not self.name_edit.text().strip():
            self.name_edit.setText(self._library_root.name or 'Nowa biblioteka')
        self.create_button.setEnabled(bool(self.name_edit.text().strip()))

    @property
    def library_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def library_root(self) -> Path | None:
        return self._library_root


class LibraryManagerDialog(QDialog):
    activate_requested = Signal(str)
    registry_changed = Signal()
    restart_requested = Signal(str)

    def __init__(self, registry: LibraryRegistry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self._selected_profile_id: str | None = None
        self.setWindowTitle('Biblioteki')
        self.resize(820, 710)
        root = QVBoxLayout(self); root.setContentsMargins(16, 16, 16, 16); root.setSpacing(12)

        title = QLabel('Biblioteki'); title.setObjectName('LibraryManagerTitle'); root.addWidget(title)
        note = QLabel(
            'Biblioteka to folder docelowy ALO — tutaj znajdują się lub będą zapisywane utwory wynikowe. '
            'Foldery źródłowe są dodawane osobno podczas skanowania.'
        )
        note.setWordWrap(True); note.setObjectName('MutedText'); root.addWidget(note)

        self.active_path = QLabel('')
        self.active_path.setObjectName('ActiveLibraryPathLink')
        self.active_path.setWordWrap(True)
        self.active_path.setTextFormat(Qt.TextFormat.RichText)
        self.active_path.setOpenExternalLinks(False)
        self.active_path.linkActivated.connect(lambda _link: self._open_active_library())
        root.addWidget(self.active_path)

        main_label = QLabel('Biblioteka główna'); main_label.setObjectName('FieldHeading'); root.addWidget(main_label)
        main_row = QHBoxLayout(); main_row.setSpacing(8)
        self.main_card = QPushButton(''); self.main_card.setObjectName('MainLibraryCard')
        self.main_card.setMinimumHeight(76); self.main_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.main_card.setCheckable(True); self.main_card.clicked.connect(self._select_main_library)
        main_row.addWidget(self.main_card, 1)
        self.main_activate_button = QPushButton('Ustaw jako aktywną')
        self.main_activate_button.setObjectName('ActivateLibraryAction')
        self.main_activate_button.clicked.connect(self._activate_main_library)
        main_row.addWidget(self.main_activate_button)
        root.addLayout(main_row)

        libraries_box = QGroupBox('Dodatkowe biblioteki'); lbl = QVBoxLayout(libraries_box); lbl.setContentsMargins(10, 10, 10, 10); lbl.setSpacing(8)
        hint = QLabel('Kliknij bibliotekę, aby ją zaznaczyć. Dopiero przycisk „Ustaw jako aktywną” przełącza bibliotekę. Zielony kolor oznacza bibliotekę aktualnie używaną przez ALO.')
        hint.setObjectName('MutedText'); hint.setWordWrap(True); lbl.addWidget(hint)
        self.libraries = QListWidget(); self.libraries.setObjectName('LibraryProfileList'); self.libraries.setMinimumHeight(170)
        self.libraries.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.libraries.itemSelectionChanged.connect(self._selection_changed)
        lbl.addWidget(self.libraries, 1)

        lr = QHBoxLayout(); lr.setSpacing(8)
        add_library = QPushButton('Nowa biblioteka'); add_library.setObjectName('Primary'); add_library.setIcon(alo_icon('library', '#e8fff2', 17)); add_library.clicked.connect(self._add_library); lr.addWidget(add_library)
        self.activate_library_button = QPushButton('Ustaw jako aktywną'); self.activate_library_button.setObjectName('ActivateLibraryAction')
        self.activate_library_button.clicked.connect(self._activate_selected_library); lr.addWidget(self.activate_library_button)
        self.library_actions_button = QToolButton(); self.library_actions_button.setObjectName('LibraryActionsMenuButton'); self.library_actions_button.setText('⋯')
        self.library_actions_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.library_actions_menu = QMenu(self.library_actions_button)
        self.rename_action = self.library_actions_menu.addAction(alo_icon('edit', '#89d6ea', 16), 'Zmień nazwę'); self.rename_action.triggered.connect(self._rename_selected_library)
        self.open_action = self.library_actions_menu.addAction(alo_icon('folder_open', '#a9c5d2', 16), 'Otwórz w Eksploratorze'); self.open_action.triggered.connect(self._open_selected_library)
        self.restart_action = self.library_actions_menu.addAction(alo_icon('restore', '#e4ba6e', 16), 'Zacznij od nowa'); self.restart_action.triggered.connect(self._restart_selected_library)
        self.library_actions_menu.addSeparator()
        self.delete_action = self.library_actions_menu.addAction(alo_icon('cancel', '#df7b83', 16), 'Usuń bibliotekę'); self.delete_action.triggered.connect(self._remove_library)
        self.library_actions_button.setMenu(self.library_actions_menu); lr.addWidget(self.library_actions_button)
        lr.addStretch(1); lbl.addLayout(lr); root.addWidget(libraries_box, 1)

        history_box = QFrame(); history_box.setObjectName('ScanHistoryCard')
        history_layout = QVBoxLayout(history_box); history_layout.setContentsMargins(10, 8, 10, 8); history_layout.setSpacing(5)
        history_head = QHBoxLayout(); history_head.setSpacing(8)
        self.history_heading = QLabel('Skanowane źródła'); self.history_heading.setObjectName('FieldHeading'); history_head.addWidget(self.history_heading)
        history_head.addStretch(1)
        self.clear_history_button = QPushButton('Wyczyść historię skanów'); self.clear_history_button.setObjectName('SubtleDangerAction')
        self.clear_history_button.clicked.connect(self._clear_scan_history); history_head.addWidget(self.clear_history_button)
        history_layout.addLayout(history_head)
        history_note = QLabel('Historia folderów otwieranych i skanowanych w tej bibliotece. To informacja — sama historia nie uruchamia ponownego skanowania.')
        history_note.setObjectName('MutedText'); history_note.setWordWrap(True); history_layout.addWidget(history_note)
        self.scan_history_list = QListWidget(); self.scan_history_list.setObjectName('ScanHistoryList'); self.scan_history_list.setFixedHeight(135)
        history_layout.addWidget(self.scan_history_list)
        root.addWidget(history_box)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = QPushButton('Zamknij'); close.clicked.connect(self.accept); bottom.addWidget(close); root.addLayout(bottom)
        self.refresh()

    @staticmethod
    def _format_history_time(value: str) -> str:
        try:
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return stamp.strftime('%d.%m.%Y %H:%M')
        except Exception:
            return value or '—'

    def refresh(self):
        active = self.registry.active
        path_text = str(active.library_root)
        open_text = 'Open in Explorer' if language_for(self) == 'en' else 'Otwórz w Eksploratorze'
        self.active_path.setText(f'<a href="open">{open_text}: {html.escape(path_text)}</a>')
        self.active_path.setToolTip(path_text)

        main = self.registry.find('main')
        if main is not None:
            is_main_active = active.profile_id == 'main'
            state = 'AKTYWNA' if is_main_active else 'Kliknij, aby zaznaczyć'
            self.main_card.setText(f'{ui_text(self, main.name)}\n{main.library_root}\n{ui_text(self, state)}')
            self.main_card.setProperty('activeLibrary', is_main_active)
            self.main_card.setChecked(self._selected_profile_id == 'main')
            self.main_card.style().unpolish(self.main_card); self.main_card.style().polish(self.main_card)
            self.main_activate_button.setText(ui_text(self, 'Aktywna' if is_main_active else 'Ustaw jako aktywną'))
            self.main_activate_button.setIcon(alo_icon('status' if is_main_active else 'library', '#73dda0' if is_main_active else '#b9c8d1', 16))
            self.main_activate_button.setEnabled(not is_main_active)

        wanted_selection = self._selected_profile_id
        self.libraries.blockSignals(True)
        self.libraries.clear()
        selected_item = None
        for profile in self.registry.profiles:
            if profile.kind != 'library':
                continue
            is_active = active.profile_id == profile.profile_id
            state = 'AKTYWNA' if is_active else 'Kliknij, aby zaznaczyć'
            item = QListWidgetItem(f'{profile.name}\n{profile.library_root}\n{ui_text(self, state)}')
            item.setData(Qt.ItemDataRole.UserRole, profile.profile_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, is_active)
            item.setData(Qt.ItemDataRole.UserRole + 2, 'ActiveLibraryRow' if is_active else 'LibraryRow')
            item.setSizeHint(QSize(0, 66))
            if is_active:
                item.setBackground(QColor('#173126')); item.setForeground(QColor('#d9ffe6'))
                font = item.font(); font.setBold(True); item.setFont(font)
            self.libraries.addItem(item)
            if wanted_selection == profile.profile_id:
                selected_item = item
        if selected_item is not None:
            self.libraries.setCurrentItem(selected_item)
            selected_item.setSelected(True)
        self.libraries.blockSignals(False)
        self._update_selection_controls()

        self.scan_history_list.clear()
        history = self.registry.scan_history(active.profile_id)
        self.history_heading.setText(ui_text(self, f'Skanowane źródła ({len(history)})'))
        if not history:
            self.scan_history_list.addItem(ui_text(self, 'Brak zapisanej historii skanowania.'))
        else:
            for entry in history:
                when = self._format_history_time(entry.scanned_at)
                self.scan_history_list.addItem(f'{entry.source_dir}\n{ui_text(self, "Ostatni skan:")} {when}   •   {ui_text(self, "Pliki:")} {entry.file_count}')
        self.clear_history_button.setEnabled(bool(history))

    def _select_main_library(self, checked: bool = True):
        if not checked:
            self._selected_profile_id = None
        else:
            self._selected_profile_id = 'main'
            self.libraries.clearSelection()
            self.libraries.setCurrentRow(-1)
        self._update_selection_controls()

    def _selection_changed(self):
        item = self.libraries.currentItem()
        if item is not None and item.isSelected():
            self._selected_profile_id = str(item.data(Qt.ItemDataRole.UserRole) or '') or None
            self.main_card.setChecked(False)
        elif self._selected_profile_id != 'main':
            self._selected_profile_id = None
        self._update_selection_controls()

    def _selected_library_id(self) -> str | None:
        if self._selected_profile_id and self._selected_profile_id != 'main':
            return self._selected_profile_id
        return None

    def _selected_library_profile(self):
        pid = self._selected_library_id()
        return self.registry.find(pid) if pid else None

    def _update_selection_controls(self):
        profile = self._selected_library_profile()
        has_selection = profile is not None
        is_active = bool(profile and profile.profile_id == self.registry.active.profile_id)
        self.activate_library_button.setEnabled(has_selection and not is_active)
        self.activate_library_button.setText(ui_text(self, 'Aktywna' if is_active else 'Ustaw jako aktywną'))
        self.activate_library_button.setIcon(alo_icon('status' if is_active else 'library', '#73dda0' if is_active else '#b9c8d1', 16))
        self.library_actions_button.setEnabled(has_selection)

    def _activate_main_library(self):
        if self.registry.active.profile_id != 'main':
            self._selected_profile_id = None
            self.activate_requested.emit('main')

    def _activate_selected_library(self):
        profile = self._selected_library_profile()
        if profile is not None and profile.profile_id != self.registry.active.profile_id:
            self._selected_profile_id = None
            self.activate_requested.emit(profile.profile_id)

    def _add_library(self):
        dialog = CreateLibraryDialog(self)
        apply_static_language(dialog, language_for(self))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        library_root = dialog.library_root
        name = dialog.library_name
        if library_root is None or not name:
            return
        try:
            profile = self.registry.add_library(name, (), library_root=library_root)
        except ValueError as exc:
            QMessageBox.warning(self, ui_text(self, 'Nie można dodać biblioteki'), ui_text(self, str(exc))); return
        self._selected_profile_id = profile.profile_id
        self.registry_changed.emit()
        self.refresh()

    def _rename_selected_library(self):
        profile = self._selected_library_profile()
        if profile is None:
            return
        name, ok = QInputDialog.getText(self, ui_text(self, 'Zmień nazwę'), ui_text(self, 'Nazwa biblioteki:'), text=profile.name)
        if not ok or not name.strip():
            return
        try:
            self.registry.rename_library(profile.profile_id, name)
        except (KeyError, ValueError) as exc:
            QMessageBox.warning(self, ui_text(self, 'Nie można zmienić nazwy'), ui_text(self, str(exc))); return
        self.registry_changed.emit(); self.refresh()

    def _open_selected_library(self):
        profile = self._selected_library_profile()
        if profile is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(profile.library_root)))

    def _restart_selected_library(self):
        profile = self._selected_library_profile()
        if profile is None:
            return
        if language_for(self) == 'en':
            message = f'Start library “{profile.name}” over?\n\nALO will clear only its local index, scan bindings and scan history. Music files in the output library will remain on disk.'
        else:
            message = f'Zacząć bibliotekę „{profile.name}” od nowa?\n\nALO wyczyści tylko lokalny indeks, powiązania skanowania i historię skanów. Pliki muzyczne w bibliotece pozostaną na dysku.'
        if QMessageBox.question(self, ui_text(self, 'Zacznij od nowa'), message,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        reset_library_index(profile.library_root)
        self.registry.clear_source_dirs(profile.profile_id)
        self.registry.clear_scan_history(profile.profile_id)
        was_active = self.registry.active.profile_id == profile.profile_id
        self.registry_changed.emit(); self.refresh()
        if was_active:
            self.restart_requested.emit(profile.profile_id)

    def _remove_library(self):
        profile = self._selected_library_profile()
        if profile is None:
            return
        if language_for(self) == 'en':
            message = f'Remove library “{profile.name}” from ALO?\n\nMusic files will remain on disk. Only the library entry will be removed from the app.'
        else:
            message = f'Usunąć bibliotekę „{profile.name}” z ALO?\n\nPliki muzyczne pozostaną na dysku. Usunięty zostanie tylko wpis biblioteki z programu.'
        if QMessageBox.question(
            self, ui_text(self, 'Usuń bibliotekę'), message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        was_active = self.registry.active.profile_id == profile.profile_id
        self.registry.remove_library(profile.profile_id)
        self._selected_profile_id = None
        self.registry_changed.emit(); self.refresh()
        if was_active:
            self.activate_requested.emit('main')

    def _clear_scan_history(self):
        profile = self.registry.active
        if not self.registry.scan_history(profile.profile_id):
            return
        if language_for(self) == 'en':
            message = (
                f'Clear scan history for “{profile.name}”?\n\n'
                'This removes only history entries. Music files and the output library are not changed.'
            )
        else:
            message = (
                f'Wyczyścić historię skanów biblioteki „{profile.name}”?\n\n'
                'Usunięte zostaną tylko wpisy historii. Pliki muzyczne i biblioteka wynikowa pozostaną bez zmian.'
            )
        if QMessageBox.question(
            self, ui_text(self, 'Wyczyść historię skanów'), message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.registry.clear_scan_history(profile.profile_id)
        self.registry_changed.emit(); self.refresh()

    def _open_active_library(self):
        profile = self.registry.active
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(profile.library_root)))
