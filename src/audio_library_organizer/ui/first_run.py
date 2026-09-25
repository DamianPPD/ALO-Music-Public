from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QFileDialog, QLineEdit, QMessageBox, QFrame
)

from audio_library_organizer import __version__
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.icons import alo_icon
from audio_library_organizer.ui.state import build_library_root
from audio_library_organizer.ui.i18n import ui_text


class LanguageSelectionDialog(QDialog):
    """Small bilingual language gate shown before the first ALO setup."""

    def __init__(self, parent=None, initial_language: str = 'pl'):
        super().__init__(parent)
        self.selected_language: str | None = None
        self.setWindowTitle('ALO Music — Wybierz język / Choose language')
        self.setModal(True)
        self.resize(620, 300)
        self.setMinimumSize(590, 280)
        root = QVBoxLayout(self); root.setContentsMargins(34, 28, 34, 28); root.setSpacing(16)

        title = QLabel('Wybierz język / Choose language')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet('font-size:18pt;font-weight:800;')
        title.setMinimumHeight(46)
        root.addWidget(title)
        desc = QLabel('Język można później zmienić w Ustawieniach.\nYou can change the language later in Settings.')
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter); desc.setWordWrap(True); desc.setObjectName('MutedText')
        root.addWidget(desc)
        root.addStretch(1)

        buttons = QHBoxLayout(); buttons.setSpacing(18)
        pl = QPushButton('Polski'); pl.setObjectName('Primary'); pl.setMinimumHeight(54)
        pl.setIcon(QIcon(str(asset_path('flag_pl.svg')))); pl.setIconSize(QSize(36, 22))
        en = QPushButton('English'); en.setObjectName('Primary'); en.setMinimumHeight(54)
        en.setIcon(QIcon(str(asset_path('flag_gb.svg')))); en.setIconSize(QSize(36, 22))
        pl.clicked.connect(lambda: self._choose('pl')); en.clicked.connect(lambda: self._choose('en'))
        buttons.addWidget(pl); buttons.addWidget(en); root.addLayout(buttons)
        if initial_language == 'en': en.setFocus()
        else: pl.setFocus()

    def _choose(self, language: str) -> None:
        self.selected_language = language if language in {'pl', 'en'} else 'pl'
        self.accept()


class FirstRunDialog(QDialog):
    def __init__(self, parent=None, initial_settings: AppSettings | None = None):
        super().__init__(parent)
        self.setWindowTitle('ALO Music — konfiguracja biblioteki')
        self.resize(860, 690)
        self.settings_result: AppSettings | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        brand = QHBoxLayout(); brand.setSpacing(14)
        icon = QLabel(); pix = QPixmap(str(asset_path('alo_icon.png')))
        if not pix.isNull(): icon.setPixmap(pix.scaled(74, 74, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        icon.setFixedSize(78, 78); brand.addWidget(icon)
        names = QVBoxLayout(); names.setSpacing(0)
        title = QLabel('ALO Music'); title.setObjectName('FirstRunBrand')
        subtitle = QLabel('Audio Library Organizer'); subtitle.setObjectName('FirstRunSubtitle')
        ver = QLabel(f'v{__version__}  •  2026'); ver.setObjectName('FinePrint')
        names.addWidget(title); names.addWidget(subtitle); names.addWidget(ver)
        brand.addLayout(names); brand.addStretch(); root.addLayout(brand)

        intro = QFrame(); intro.setObjectName('SafeIntroCard')
        il = QVBoxLayout(intro); il.setContentsMargins(14, 11, 14, 11)
        intro_title = QLabel('Utwórz bezpieczną bibliotekę muzyczną'); intro_title.setStyleSheet('font-size:14pt;font-weight:750;')
        intro_text = QLabel('Oryginalne pliki pozostaną nietknięte. ALO Music analizuje źródła tylko do odczytu, a uporządkowane pliki tworzy w wybranej przez Ciebie bibliotece.')
        intro_text.setWordWrap(True); intro_text.setObjectName('MutedText')
        safe = QLabel('Źródła nie są modyfikowane ani usuwane'); safe.setObjectName('SavedNotice')
        il.addWidget(intro_title); il.addWidget(intro_text); il.addWidget(safe); root.addWidget(intro)

        src = QFrame(); src.setObjectName('SetupCard')
        sl = QVBoxLayout(src); sl.setContentsMargins(16, 14, 16, 14); sl.setSpacing(8)
        sh = QLabel('1. Muzyka źródłowa'); sh.setObjectName('SetupHeading'); sl.addWidget(sh)
        sd = QLabel('Dodaj jeden lub kilka folderów, które program ma przeskanować. Pliki w tych folderach są tylko odczytywane.')
        sd.setWordWrap(True); sd.setObjectName('MutedText'); sl.addWidget(sd)
        self.sources = QListWidget(); self.sources.setMinimumHeight(105); sl.addWidget(self.sources)
        row = QHBoxLayout(); add_btn = QPushButton('Dodaj folder…'); remove_btn = QPushButton('Usuń zaznaczony')
        add_btn.setIcon(alo_icon('folder', '#75dff8', 17)); remove_btn.setIcon(alo_icon('cancel', '#e89097', 17))
        add_btn.clicked.connect(self._add_source); remove_btn.clicked.connect(self._remove_source)
        row.addWidget(add_btn); row.addWidget(remove_btn); row.addStretch(); sl.addLayout(row); root.addWidget(src)

        dest = QFrame(); dest.setObjectName('SetupCard')
        dl = QVBoxLayout(dest); dl.setContentsMargins(16, 14, 16, 14); dl.setSpacing(8)
        dh = QLabel('2. Gdzie utworzyć nową bibliotekę'); dh.setObjectName('SetupHeading'); dl.addWidget(dh)
        loc_label = QLabel('LOKALIZACJA'); loc_label.setObjectName('FieldHeading'); dl.addWidget(loc_label)
        loc_help = QLabel('Wybierz dysk lub folder nadrzędny, np. D:\\Muzyka.'); loc_help.setObjectName('MutedText'); dl.addWidget(loc_help)
        dest_row = QHBoxLayout(); self.dest_parent = QLineEdit(); self.dest_parent.setPlaceholderText('np. D:\\Muzyka')
        choose = QPushButton('Wybierz lokalizację…'); choose.setIcon(alo_icon('folder_open', '#a8c9d7', 17)); choose.clicked.connect(self._choose_destination)
        dest_row.addWidget(self.dest_parent, 1); dest_row.addWidget(choose); dl.addLayout(dest_row)
        name_label = QLabel('NAZWA FOLDERU BIBLIOTEKI'); name_label.setObjectName('FieldHeading'); dl.addWidget(name_label)
        name_help = QLabel('ALO Music utworzy w nim podfoldery GOTOWE, NIE_WYBRANE, DO_SPRAWDZENIA, MOJE_FOLDERY_MP3 i raporty oraz własną bazę .alo.')
        name_help.setObjectName('MutedText'); name_help.setWordWrap(True); dl.addWidget(name_help)
        self.dest_name = QLineEdit('ALO Music - Biblioteka'); dl.addWidget(self.dest_name); root.addWidget(dest)

        preview = QFrame(); preview.setObjectName('PathPreviewCard')
        pl = QVBoxLayout(preview); pl.setContentsMargins(14, 10, 14, 10); pl.setSpacing(3)
        ph = QLabel('BIBLIOTEKA ZOSTANIE UTWORZONA TUTAJ'); ph.setObjectName('FieldHeading')
        self.preview_path = QLabel('Wybierz lokalizację powyżej'); self.preview_path.setObjectName('PathPreview'); self.preview_path.setWordWrap(True)
        folders = QLabel('GOTOWE   •   NIE WYBRANE   •   DO SPRAWDZENIA   •   MOJE FOLDERY MP3   •   raporty'); folders.setObjectName('MutedText')
        pl.addWidget(ph); pl.addWidget(self.preview_path); pl.addWidget(folders); root.addWidget(preview)

        if initial_settings is not None:
            for source in initial_settings.source_dirs: self.sources.addItem(str(source))
            self.dest_parent.setText(str(initial_settings.library.root.parent)); self.dest_name.setText(initial_settings.library.root.name)

        self.dest_parent.textChanged.connect(self._update_preview); self.dest_name.textChanged.connect(self._update_preview)
        self._update_preview()

        actions = QHBoxLayout(); actions.addStretch()
        cancel = QPushButton('Anuluj'); cancel.setIcon(alo_icon('cancel', '#d7a0a5', 17)); start = QPushButton('UTWÓRZ BIBLIOTEKĘ I DALEJ'); start.setObjectName('Primary'); start.setIcon(alo_icon('library', '#e8fff2', 18))
        cancel.clicked.connect(self.reject); start.clicked.connect(self._accept_settings)
        actions.addWidget(cancel); actions.addWidget(start); root.addLayout(actions)

    def _update_preview(self):
        parent = self.dest_parent.text().strip()
        name = self.dest_name.text().strip()
        if not parent or not name:
            self.preview_path.setText(ui_text(self, 'Wybierz lokalizację i nazwę folderu'))
            return
        self.preview_path.setText(str(Path(parent) / name))

    def _add_source(self):
        folder = QFileDialog.getExistingDirectory(self, ui_text(self, 'Wybierz folder z muzyką'))
        if folder and not self.sources.findItems(folder, Qt.MatchFlag.MatchExactly): self.sources.addItem(folder)

    def _remove_source(self):
        for item in self.sources.selectedItems(): self.sources.takeItem(self.sources.row(item))

    def _choose_destination(self):
        folder = QFileDialog.getExistingDirectory(self, ui_text(self, 'Wybierz miejsce dla nowej biblioteki'))
        if folder: self.dest_parent.setText(folder)

    def _accept_settings(self):
        try:
            sources = tuple(Path(self.sources.item(i).text()) for i in range(self.sources.count()))
            if not sources:
                raise ValueError('Dodaj przynajmniej jeden folder z muzyką.')
            parent_text = self.dest_parent.text().strip()
            if not parent_text:
                raise ValueError('Wybierz lokalizację folderu docelowego.')
            parent = Path(parent_text)
            library = LibraryPaths(build_library_root(parent, self.dest_name.text()))
            settings = AppSettings(sources, library); library.ensure_created(); self.settings_result = settings
        except Exception as exc:
            QMessageBox.warning(self, ui_text(self, 'Nie można utworzyć biblioteki'), ui_text(self, str(exc))); return
        self.accept()
