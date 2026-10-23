"""Folder/playlist presentation only; existing jobs still own every write."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QFileDialog, QMessageBox, QSizePolicy,
    QScrollArea, QWidget, QPlainTextEdit,
)

from audio_library_organizer.ui.dialog_style import configure_dialog_button
from audio_library_organizer.ui.i18n import language_for
from audio_library_organizer.ui.icons import alo_icon, library_icon


def track_count(count, language):
    if language == 'en':
        return f'{count} track' if count == 1 else f'{count} tracks'
    noun = 'utwór' if count == 1 else 'utwory' if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else 'utworów'
    return f'{count} {noun}'


class _CreationDialog(QDialog):
    def __init__(self, kind, parent=None, *, language=None):
        super().__init__(parent)
        self.kind = kind
        self.language = language or language_for(parent)
        self.setProperty('_alo_language', self.language)
        self.accent = '#fc71b7' if kind == 'playlist' else '#35d893'
        self.setObjectName('CreationDialog')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        field_bg = '#291d2b' if kind == 'playlist' else '#17212a'
        field_border = '#65314f' if kind == 'playlist' else '#344955'
        self.setStyleSheet(f'''
            QDialog#CreationDialog, QWidget#CreationBody {{ background:#11171e; color:#dbe8ee; }}
            QScrollArea {{ background:transparent; border:0; }}
            QLabel {{ color:#dbe8ee; background:transparent; border:0; font-size:13px; }}
            QLabel[muted="true"] {{ color:#91a3b0; }}
            QLineEdit {{ background:{field_bg}; color:#e0eaf0; border:1px solid {field_border};
                border-radius:7px; padding:9px 10px; font-size:14px; selection-background-color:{field_border}; }}
            QLineEdit:focus {{ border-color:{self.accent}; }}
            QPlainTextEdit {{ background:#0e151c; color:#dbe8ee; border:1px solid {field_border}; border-radius:7px; padding:8px; }}
            QFrame#CreationDetails {{ background:#17212a; border:1px solid {field_border}; border-radius:8px; }}
        ''')
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(22, 20, 22, 18)
        self.outer.setSpacing(14)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(); content.setObjectName('CreationBody')
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(14)
        self.scroll.setWidget(content)
        self.outer.addWidget(self.scroll, 1)
        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(0, 4, 0, 0)
        self.footer.addStretch()

    def text(self, pl, en):
        return en if self.language == 'en' else pl

    def label(self, text, *, muted=False, selectable=False):
        label = QLabel(str(text))
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setProperty('muted', muted)
        if selectable:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            label.setToolTip(str(text))
        return label

    def heading(self, title, *, success=False):
        self.setWindowTitle(title)
        row = QHBoxLayout()
        glyph = QLabel()
        icon = (alo_icon('check', '#35d893', 28) if success else
                library_icon('list_music' if self.kind == 'playlist' else 'folder_add', self.accent, 28))
        glyph.setPixmap(icon.pixmap(28, 28))
        row.addWidget(glyph)
        label = self.label(title)
        label.setStyleSheet(f'font-size:21px; font-weight:600; color:{self.accent};')
        row.addWidget(label, 1)
        self.body.addLayout(row)

    def fit(self):
        self.outer.addLayout(self.footer)
        width = min(450, max(300, self.screen().availableGeometry().width() - 60))
        content_height = self.body.totalHeightForWidth(width - 44)
        if content_height < 0:
            content_height = self.body.sizeHint().height()
        height = content_height + self.footer.sizeHint().height() + 52
        self.resize(width, min(height, self.screen().availableGeometry().height() - 60))


class CreationNameDialog(_CreationDialog):
    def __init__(self, kind, selected_count, parent=None, *, initial_target=None, available_count=None, language=None):
        super().__init__(kind, parent, language=language)
        playlist = kind == 'playlist'
        self.heading(self.text('Nowa playlista', 'New playlist') if playlist else self.text('Nowy folder', 'New folder'))
        selected = f'{selected_count} zaznaczonego utworu' if selected_count == 1 else f'{selected_count} zaznaczonych utworów'
        self.description = self.label(self.text(
            f'Utwórz playlistę z {selected}.' if playlist else f'Utwórz folder dla {selected}.',
            f'Create a {"playlist from" if playlist else "folder for"} {selected_count} selected {"track" if selected_count == 1 else "tracks"}.'), muted=True)
        self.body.addWidget(self.description)
        self.availability_label = self.label('', muted=True)
        if available_count is not None and available_count != selected_count:
            self.availability_label.setText(self.text('Dostępne do operacji: ', 'Available for this operation: ') + track_count(available_count, self.language))
        self.availability_label.setVisible(bool(self.availability_label.text()))
        self.body.addWidget(self.availability_label)
        self.body.addWidget(self.label(self.text('Nazwa playlisty', 'Playlist name') if playlist else self.text('Nazwa folderu', 'Folder name')))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(self.text('Wpisz nazwę playlisty...', 'Enter playlist name...') if playlist else self.text('Wpisz nazwę folderu...', 'Enter folder name...'))
        self.body.addWidget(self.name_edit)
        self.validation_notice = self.label('')
        self.validation_notice.setStyleSheet('color:#f3b16c;')
        self.validation_notice.hide()
        self.body.addWidget(self.validation_notice)
        self._directory = Path(initial_target).parent if initial_target is not None else Path.cwd()
        if playlist:
            self.name_edit.setText(Path(initial_target).name if initial_target is not None else 'playlista.m3u8')
            self.destination_label = self.label(str(self._directory), muted=True, selectable=True)
            self.body.addWidget(self.destination_label)
            self.location_button = QPushButton(self.text('Wybierz lokalizację…', 'Choose location…'))
            configure_dialog_button(self.location_button)
            self.location_button.clicked.connect(self.choose_target)
            self.body.addWidget(self.location_button)
        self.cancel_button = QPushButton(self.text('Anuluj', 'Cancel'))
        self.create_button = QPushButton(self.text('Utwórz playlistę', 'Create playlist') if playlist else self.text('Utwórz folder', 'Create folder'))
        configure_dialog_button(self.cancel_button)
        configure_dialog_button(self.create_button, accent='magenta' if playlist else 'green')
        self.create_button.setIcon(library_icon('playlist' if playlist else 'folder_add', '#fc71b7' if playlist else '#dbfaeb', 18))
        self.create_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.create_button.clicked.connect(self.accept)
        self.name_edit.textChanged.connect(self._name_changed)
        self.create_button.setEnabled(bool(self.name_edit.text().strip()))
        self.footer.addWidget(self.cancel_button)
        self.footer.addWidget(self.create_button)
        self.fit()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def target_path(self):
        return self._directory / self.name_edit.text().strip()

    def _name_changed(self, text):
        self.create_button.setEnabled(bool(text.strip()))
        self.validation_notice.clear()
        self.validation_notice.hide()

    def choose_target(self):
        # Location selection is still explicit; final confirmation is in accept().
        filename, _ = QFileDialog.getSaveFileName(self, self.text('Zapisz playlistę M3U8', 'Save M3U8 playlist'),
            str(self.target_path()), self.text('Playlista M3U8 (*.m3u8)', 'M3U8 playlist (*.m3u8)'),
            options=QFileDialog.Option.DontConfirmOverwrite)
        if filename:
            target = Path(filename)
            self._directory = target.parent
            self.name_edit.setText(target.name)
            self.destination_label.setText(str(self._directory))
            self.destination_label.setToolTip(str(self._directory))

    def accept(self):
        if not self.name_edit.text().strip():
            return
        if self.kind == 'playlist':
            try:
                target = self.target_path()
                if not Path(self.name_edit.text().strip()).name or target.name in {'.', '..'} or '\0' in str(target):
                    raise ValueError(self.text('Podaj nazwę pliku.', 'Enter a filename.'))
                if target.suffix.lower() != '.m3u8':
                    target = target.with_suffix('.m3u8')
                exists = target.exists()
            except (OSError, ValueError) as exc:
                self.validation_notice.setText(self.text('Nie można zapisać playlisty: ', 'Cannot save playlist: ') + str(exc))
                self.validation_notice.show()
                self.name_edit.setFocus()
                return
            if exists:
                question = QMessageBox(self)
                question.setWindowTitle(self.text('Zastąpić playlistę?', 'Replace playlist?'))
                question.setTextFormat(Qt.TextFormat.PlainText)
                question.setText(self.text('Plik już istnieje. Zastąpić go?\n', 'The file already exists. Replace it?\n') + str(target))
                question.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                question.button(QMessageBox.StandardButton.Yes).setText(self.text('Tak', 'Yes'))
                question.button(QMessageBox.StandardButton.No).setText(self.text('Nie', 'No'))
                question.setDefaultButton(QMessageBox.StandardButton.No)
                question.setEscapeButton(QMessageBox.StandardButton.No)
                if question.exec() != QMessageBox.StandardButton.Yes:
                    return
        super().accept()


class CreationResultDialog(_CreationDialog):
    def __init__(self, kind, name, count, location, parent=None, *, outcome='success', expected_count=None, errors=(), language=None):
        super().__init__(kind, parent, language=language)
        playlist = kind == 'playlist'
        title = self.text('Playlista utworzona', 'Playlist created') if playlist else self.text('Folder utworzony', 'Folder created')
        if outcome != 'success':
            title = self.text('Tworzenie folderu zatrzymane', 'Folder creation stopped') if outcome == 'cancelled' else self.text('Folder utworzony częściowo' if count else 'Nie utworzono folderu', 'Folder partly created' if count else 'Folder not created')
        self.heading(title, success=outcome == 'success')
        message = self.text(f'Playlista „{name}” została utworzona.', f'Playlist “{name}” was created.') if playlist else self.text(f'Folder „{name}” został utworzony.', f'Folder “{name}” was created.')
        if outcome != 'success':
            message = self.text(f'Operacja dla folderu „{name}” nie zakończyła się w całości.', f'The operation for folder “{name}” did not complete in full.')
        self.message = self.label(message)
        self.body.addWidget(self.message)
        frame = QFrame(); frame.setObjectName('CreationDetails')
        details = QVBoxLayout(frame); details.setContentsMargins(12, 12, 12, 12); details.setSpacing(8)
        details.addWidget(self.label(self.text('Liczba utworów', 'Track count') if playlist else self.text('Utwory skopiowane w tej operacji', 'Tracks copied in this operation'), muted=True))
        self.count_label = self.label(track_count(count, self.language))
        details.addWidget(self.count_label)
        if expected_count is not None and count != expected_count:
            details.addWidget(self.label(self.text(f'Planowano: {expected_count}', f'Planned: {expected_count}'), muted=True))
        if playlist:
            details.addWidget(self.label('Format: M3U8', muted=True))
        details.addWidget(self.label(self.text('Lokalizacja', 'Location'), muted=True))
        location_text = str(location) if location is not None else self.text('Brak potwierdzonej lokalizacji', 'No confirmed location')
        self.location_label = QLineEdit(location_text)
        self.location_label.setReadOnly(True)
        self.location_label.setToolTip(location_text)
        details.addWidget(self.location_label)
        self.body.addWidget(frame)
        self.details = QPlainTextEdit('\n'.join(str(e) for e in errors if e))
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(70)
        self.details.setMaximumHeight(160)
        self.details.setVisible(bool(self.details.toPlainText()))
        self.body.addWidget(self.details)
        self.close_button = QPushButton(self.text('Zamknij', 'Close'))
        configure_dialog_button(self.close_button)
        self.close_button.setMinimumWidth(112)
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        self.footer.addWidget(self.close_button)
        self.fit()
