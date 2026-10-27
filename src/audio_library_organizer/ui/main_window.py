from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from datetime import datetime
from time import perf_counter
import shutil
import html
import json
import sqlite3
from uuid import uuid4
from functools import partial

from PySide6.QtCore import Qt, QThread, QSettings, Signal, Slot, QUrl, QTimer, QSize, QVariantAnimation, QFileSystemWatcher
from PySide6.QtGui import QPixmap, QDesktopServices, QIcon, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QMessageBox, QProgressBar, QGridLayout, QGroupBox,
    QLineEdit, QCheckBox, QScrollArea, QRadioButton, QButtonGroup, QFileDialog, QInputDialog,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QApplication,
    QDialog, QFormLayout, QDialogButtonBox, QSizePolicy, QToolButton
)

from audio_library_organizer import __version__
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.domain.provider_settings import ProviderSettings
from audio_library_organizer.domain.genres import GenreSettings
from audio_library_organizer.domain.preferences import (
    AppPreferences,
    NameNormalizationRule,
    default_name_rules,
    restore_safe_defaults,
)
from audio_library_organizer.jobs.exporter import ExportPlan, ExportResult
from audio_library_organizer.jobs.library_service import LibraryService
from audio_library_organizer.jobs.identifier import IdentificationJob
from audio_library_organizer.jobs.audio_identification import AudioIdentification
from audio_library_organizer.jobs.reporting import build_operation_summary, build_library_health, export_csv, export_session_html, export_verification_csv
from audio_library_organizer.matching.resolver import IdentificationService
from audio_library_organizer.providers.acoustid import AcoustIDClient
from audio_library_organizer.providers.musicbrainz import MusicBrainzClient
from audio_library_organizer.providers.discogs import DiscogsClient
from audio_library_organizer.providers.itunes import ITunesSearchClient
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.storage.migrations import MigrationError
from audio_library_organizer.storage.library_profiles import LibraryRegistry
from audio_library_organizer.duplicates.grouper import apply_duplicate_decision, duplicate_group_count
from audio_library_organizer.metadata.manual_edits import apply_manual_field, approve_as_ready
from audio_library_organizer.metadata.online_lock import set_online_locked
from audio_library_organizer.metadata.change_history import ChangeHistory, metadata_changes, metadata_revision
from audio_library_organizer.jobs.managed_files import ReadPurpose, track_identity, source_material_revision
from audio_library_organizer.jobs.legacy_adoption import KnownLibrary
from audio_library_organizer.ui.adoption_dialog import LegacyAdoptionDialog
from shiboken6 import isValid
from audio_library_organizer.metadata.naming import (
    DEFAULT_FILENAME_TEMPLATE, propose_filename, filename_fields_from_template, template_from_filename_fields,
)
from audio_library_organizer.ui.confirmations import confirm_bulk_copy
from audio_library_organizer.ui.export_dialogs import ExportProgressDialog, ExportSummaryDialog, ExportReviewWarning
from audio_library_organizer.ui.creation_dialogs import CreationNameDialog, CreationResultDialog
from audio_library_organizer.ui.state import should_refresh_live_scan, export_needs_library_review, library_status_text, save_app_settings
from audio_library_organizer.ui.duplicates_page import DuplicatesPage
from audio_library_organizer.ui.help_center import HelpCenter
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.collections_page import CollectionsPage
from audio_library_organizer.ui.library_manager import LibraryManagerDialog
from audio_library_organizer.jobs.collections import build_collection_plan
from audio_library_organizer.jobs.playlists import write_m3u8
from audio_library_organizer.jobs.backup import create_alo_backup, inspect_alo_backup, restore_database_from_backup, restore_profile_databases_from_backup
from audio_library_organizer.jobs.reset import reset_alo_state
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.player import PlayerBar
from audio_library_organizer.ui.workers import ScanWorker, FileReconciliationWorker, LegacyAdoptionWorker, IdentificationWorker, AudioIdentificationWorker, ExportWorker
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.icons import alo_icon, start_icon
from audio_library_organizer.ui.theme import style_for_theme, GENRE_ACCENT
from audio_library_organizer.ui.i18n import tr, apply_static_language, ui_text
from audio_library_organizer.ui.widgets import StatCard
from audio_library_organizer.ui.genre_settings import GenreSettingsWidget
from audio_library_organizer.domain.models import TrackRecord

def _icon_label(name: str, color: str = '#68d9a0', size: int = 22) -> QLabel:
    label = QLabel()
    label.setObjectName('ProviderIcon')
    label.setPixmap(alo_icon(name, color, size).pixmap(size, size))
    label.setFixedSize(size + 4, size + 4)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _provider_accent(kind: str, color: str, parent: QWidget) -> QFrame:
    accent = QFrame(parent)
    accent.setObjectName('ProviderAccent')
    accent.setProperty('providerKind', kind)
    accent.setProperty('providerColor', color)
    accent.setFixedHeight(2)
    accent.setStyleSheet(f'background:{color}; border:0; border-radius:1px;')
    return accent

class DashboardPage(QWidget):
    refresh_requested = Signal()

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._missing_dismissed = False
        self._library_root = Path(settings.library.root)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(12)

        header = QHBoxLayout(); header.setSpacing(16)
        title_box = QVBoxLayout(); title_box.setSpacing(3)
        self.dashboard_title = QLabel('Biblioteka główna'); self.dashboard_title.setStyleSheet('font-size:22pt;font-weight:750;')
        subtitle = QLabel('Biblioteka ALO Music')
        subtitle.setWordWrap(True); subtitle.setObjectName('MutedText')
        title_box.addWidget(self.dashboard_title); title_box.addWidget(subtitle); header.addLayout(title_box, 2)

        session = QFrame(); session.setObjectName('SessionCard')
        sl = QVBoxLayout(session); sl.setContentsMargins(14, 10, 14, 10); sl.setSpacing(4)
        sh = QLabel('BIBLIOTEKA'); sh.setObjectName('FieldHeading'); sl.addWidget(sh)
        self.session_count = QLabel('0 plików'); self.session_count.setStyleSheet('font-size:18pt;font-weight:800;color:#8fe9ad;'); sl.addWidget(self.session_count)
        self.library_label = QLabel(str(settings.library.root)); self.library_label.setWordWrap(True); self.library_label.setObjectName('MutedText'); sl.addWidget(self.library_label)
        header.addWidget(session, 1); root.addLayout(header)

        cards = QGridLayout(); cards.setHorizontalSpacing(12); cards.setVerticalSpacing(0)
        self.cards = {
            'total': StatCard('Wszystkie', accent='#7f8da1'),
            'ready': StatCard('Gotowe', accent='#43d17d'),
            'duplicate': StatCard('Duplikaty', accent='#b987ff'),
            'review': StatCard('Do sprawdzenia', accent='#ffb84d'),
        }
        for i, key in enumerate(('total', 'ready', 'duplicate', 'review')):
            cards.addWidget(self.cards[key], 0, i)
        root.addLayout(cards)

        self.missing_banner = QFrame(); self.missing_banner.setObjectName('MissingFilesBanner'); self.missing_banner.setVisible(False)
        mbl = QHBoxLayout(self.missing_banner); mbl.setContentsMargins(12, 8, 12, 8)
        self.missing_text = QLabel(''); self.missing_text.setWordWrap(True); mbl.addWidget(self.missing_text, 1)
        refresh = QPushButton('Odśwież / przeskanuj bibliotekę'); refresh.clicked.connect(self.refresh_requested); mbl.addWidget(refresh)
        hide = QPushButton('Pracuj dalej'); hide.clicked.connect(self._dismiss_missing); mbl.addWidget(hide)
        root.addWidget(self.missing_banner)

        health = QFrame(); health.setObjectName('LibraryHealthCard')
        hl = QVBoxLayout(health); hl.setContentsMargins(14, 11, 14, 11); hl.setSpacing(8)
        health_head = QHBoxLayout()
        hh = QLabel('Stan biblioteki'); hh.setStyleSheet('font-size:13pt;font-weight:800;'); health_head.addWidget(hh)
        health_head.addStretch(1)
        self.organized = QLabel('0% uporządkowana'); self.organized.setStyleSheet('font-size:13pt;font-weight:800;color:#8fe9ad;'); health_head.addWidget(self.organized)
        hl.addLayout(health_head)
        mini = QGridLayout(); mini.setHorizontalSpacing(18); mini.setVerticalSpacing(8)
        labels = [
            ('available', 'Dostępne pliki'), ('missing', 'Brakujące pliki'),
            ('missing_covers', 'Brak okładki'), ('online_checked', 'Utwory sprawdzone online'),
            ('size', 'Rozmiar biblioteki'), ('free_space', 'Wolne miejsce na dysku'),
            ('suspicious', 'Podejrzane dane'),
        ]
        self.health_values = {}
        for i, (key, text) in enumerate(labels):
            box = QFrame(); box.setObjectName('WorkflowMiniStep')
            bl = QVBoxLayout(box); bl.setContentsMargins(10, 7, 10, 7); bl.setSpacing(2)
            head = QLabel(text.upper()); head.setObjectName('FieldHeading'); bl.addWidget(head)
            value = QLabel('—'); value.setStyleSheet('font-size:12pt;font-weight:750;'); bl.addWidget(value)
            self.health_values[key] = value
            mini.addWidget(box, i // 4, i % 4)
        hl.addLayout(mini); root.addWidget(health)

        next_box = QFrame(); next_box.setObjectName('NextStepCard')
        nl = QVBoxLayout(next_box); nl.setContentsMargins(14, 10, 14, 10); nl.setSpacing(4)
        nh = QLabel('CO TERAZ?'); nh.setObjectName('FieldHeading'); nl.addWidget(nh)
        self.next_label = QLabel('Uruchom skanowanie folderów źródłowych.'); self.next_label.setWordWrap(True); self.next_label.setStyleSheet('font-size:11pt;font-weight:650;'); nl.addWidget(self.next_label)
        self.last_scan_label = QLabel(''); self.last_scan_label.setObjectName('MutedText'); self.last_scan_label.setWordWrap(True); self.last_scan_label.setVisible(False); nl.addWidget(self.last_scan_label)
        root.addWidget(next_box)
        root.addStretch(1)

    def _dismiss_missing(self):
        self._missing_dismissed = True
        self.missing_banner.setVisible(False)

    def set_library(self, settings: AppSettings, library_name: str | None = None):
        self._library_root = Path(settings.library.root)
        self.library_label.setText(str(settings.library.root))
        if library_name:
            self.set_library_name(library_name)

    def set_library_name(self, name: str):
        self.dashboard_title.setText(name or 'Biblioteka ALO Music')

    def set_last_scan_summary(self, text: str):
        self.last_scan_label.setText(ui_text(self, text))
        self.last_scan_label.setVisible(bool(text.strip()))

    def set_summary(self, summary: dict[str, int]):
        total = summary.get('total', 0); ready = summary.get('ready', 0); review = summary.get('review', 0); duplicate = summary.get('duplicate', 0)
        self.session_count.setText(ui_text(self, f'{total} dostępnych plików'))
        for key, card in self.cards.items():
            card.set_value(summary.get(key, 0))
        if total == 0:
            text = 'Uruchom skanowanie folderów źródłowych.'
        elif review or duplicate:
            text = f'Biblioteka wymaga uwagi: {review} do sprawdzenia, {duplicate} duplikatów.'
        elif ready:
            text = f'{ready} utworów jest gotowych. Możesz filtrować Bibliotekę albo tworzyć foldery z zaznaczonych utworów.'
        else:
            text = 'Uruchom rozpoznawanie online lub sprawdź dane w Bibliotece.'
        self.next_label.setText(ui_text(self, text))

    def set_health(self, health: dict[str, object]):
        available = int(health.get('available', 0)); missing = int(health.get('missing', 0))
        organized = int(round(float(health.get('organized_percent', 0))))
        self.organized.setText(ui_text(self, f'{organized}% uporządkowana'))
        self.health_values['available'].setText(str(available))
        self.health_values['missing'].setText(str(missing))
        self.health_values['missing_covers'].setText(str(int(health.get('missing_covers', 0))))
        online_checked = int(health.get('online_checked', 0))
        online_percent = float(health.get('online_percent', 0))
        self.health_values['online_checked'].setText(f'{online_checked} ({online_percent:.0f}%)')
        self.health_values['suspicious'].setText(str(health.get('suspicious', 0)))
        size = int(health.get('size_bytes', 0)); self.health_values['size'].setText(f'{size/(1024**3):.2f} GB' if size >= 1024**3 else f'{size/(1024**2):.1f} MB')
        free_label = self.health_values['free_space']
        try:
            usage = shutil.disk_usage(self._library_root if self._library_root.exists() else self._library_root.parent)
            free_gb = usage.free / (1024**3)
            free_label.setText(f'{free_gb:.1f} GB')
            if free_gb < 10:
                free_label.setStyleSheet('font-size:12pt;font-weight:750;color:#ff6b6b;')
            elif free_gb < 20:
                free_label.setStyleSheet('font-size:12pt;font-weight:750;color:#ffb84d;')
            else:
                free_label.setStyleSheet('font-size:12pt;font-weight:750;')
        except OSError:
            free_label.setText('—')
            free_label.setStyleSheet('font-size:12pt;font-weight:750;')
        self.missing_text.setText(ui_text(self, f'Biblioteka wymaga odświeżenia — {missing} plików nie jest już dostępnych.'))
        if missing == 0:
            self._missing_dismissed = False
        self.missing_banner.setVisible(missing > 0 and not self._missing_dismissed)


class RestoreDefaultsDialog(QDialog):
    """ALO-styled confirmation for the non-destructive preferences reset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('RestoreDefaultsDialog')
        self.setWindowTitle('Przywróć ustawienia domyślne')
        self.setModal(True)
        self.setMinimumWidth(520)
        root = QVBoxLayout(self); root.setContentsMargins(20, 18, 20, 18); root.setSpacing(12)

        heading = QHBoxLayout(); heading.setSpacing(10)
        icon = _icon_label('restore', '#67d8ef', 24); heading.addWidget(icon)
        title = QLabel('Przywrócić bezpieczne ustawienia domyślne?')
        title.setObjectName('SettingsDialogTitle'); heading.addWidget(title, 1); root.addLayout(heading)

        note = QLabel('ALO przywróci tylko nieszkodliwe preferencje programu:')
        note.setWordWrap(True); note.setObjectName('MutedText'); root.addWidget(note)
        for text in (
            'format i organizację nazw plików',
            'automatyczne rozpoznawanie po skanie',
            'normalizację nazw i jej reguły',
            'domyślne zachowanie interfejsu',
        ):
            row = QHBoxLayout(); row.setSpacing(8)
            row.addWidget(_icon_label('status', '#69d998', 15))
            row.addWidget(QLabel(text), 1); root.addLayout(row)

        safe = QLabel('Biblioteka, utwory, metadane, pliki, historia, język i klucze API pozostaną bez zmian.')
        safe.setWordWrap(True); safe.setObjectName('SafeResetNotice'); root.addWidget(safe)

        actions = QHBoxLayout(); actions.addStretch(1)
        cancel = QPushButton('Anuluj'); cancel.setObjectName('Secondary'); cancel.clicked.connect(self.reject); actions.addWidget(cancel)
        confirm = QPushButton('Przywróć domyślne'); confirm.setObjectName('Primary'); confirm.setIcon(alo_icon('restore', '#e9fdff', 17)); confirm.clicked.connect(self.accept); actions.addWidget(confirm)
        root.addLayout(actions)


class SettingsPage(QWidget):
    provider_saved = Signal()
    preferences_saved = Signal(object)
    manage_libraries_requested = Signal()
    change_library_location_requested = Signal()
    backup_requested = Signal()
    restore_backup_requested = Signal()
    full_reset_requested = Signal()
    help_requested = Signal(str)

    def __init__(self, settings: AppSettings, store: QSettings, parent=None):
        super().__init__(parent)
        self.store = store
        self.app_settings = settings
        cfg = ProviderSettings.from_store(store)
        prefs = AppPreferences.from_store(store)

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); lay = QVBoxLayout(content); lay.setContentsMargins(8, 6, 12, 16); lay.setSpacing(16)

        title = QLabel('Ustawienia i lokalizacje plików'); title.setStyleSheet('font-size:20pt;font-weight:700;'); lay.addWidget(title)
        session_note = QLabel('Biblioteka docelowa jest zapamiętywana między uruchomieniami. Historia skanów jest dostępna w oknie Biblioteki. Oryginalne pliki nie są modyfikowane.')
        session_note.setWordWrap(True); session_note.setObjectName('InfoBanner'); lay.addWidget(session_note)

        self.settings_sections: dict[str, QFrame] = {}
        self.section_layouts: dict[str, QVBoxLayout] = {}
        section_specs = (
            ('library', 'Biblioteka', 'Wybierz główną lokalizację biblioteki ALO.', 'library', '#67d8ef'),
            ('naming', 'Nazewnictwo plików', 'Ustal sposób tworzenia nazw plików wynikowych.', 'metadata', '#c7a9ff'),
            ('genres', 'Gatunki', 'Zarządzaj listą używaną w podpowiedziach pola Gatunek.', 'metadata', GENRE_ACCENT),
            ('online', 'Rozpoznawanie online', 'Dostosuj sposób korzystania ze źródeł internetowych.', 'settings_online', '#57d8ff'),
            ('integrations', 'Integracje i klucze API', 'Połącz ALO ze źródłami używanymi podczas rozpoznawania utworów.', 'integration', '#77dffc'),
            ('interface', 'Interfejs', 'Dostosuj język i zachowanie programu.', 'settings', '#78d9e6'),
            ('advanced', 'Zaawansowane', 'Opcje techniczne, diagnostyczne i serwisowe.', 'warning', '#ffbd61'),
        )
        for name, section_title, description, icon_name, accent in section_specs:
            section, section_layout = self._make_settings_section(
                name, section_title, description, icon_name, accent
            )
            self.settings_sections[name] = section
            self.section_layouts[name] = section_layout
            lay.addWidget(section)

        self.genre_settings = GenreSettingsWidget(store)
        self.section_layouts['genres'].addWidget(self.genre_settings)

        appearance = QFrame(); appearance.setObjectName('AppearanceCard')
        al = QVBoxLayout(appearance); al.setContentsMargins(16, 14, 16, 14); al.setSpacing(9)
        atitle = QLabel('Język interfejsu'); atitle.setStyleSheet('font-size:13pt;font-weight:750;color:#78d9e6;'); al.addWidget(atitle)
        adesc = QLabel('Wybierz język interfejsu. Możesz go zmienić w dowolnym momencie.')
        adesc.setWordWrap(True); adesc.setObjectName('MutedText'); al.addWidget(adesc)
        ar = QHBoxLayout(); ar.setSpacing(10)
        ar.addWidget(QLabel('Język'))
        self.language_combo = QComboBox(); self.language_combo.addItem('Polski', 'pl'); self.language_combo.addItem('English', 'en')
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(prefs.language))); ar.addWidget(self.language_combo)
        self.save_language_button = QPushButton('Zapisz język'); self.save_language_button.setObjectName('SectionSaveButton'); self.save_language_button.clicked.connect(self._save_language); ar.addWidget(self.save_language_button)
        self.language_saved_label = QLabel('Zapisano'); self.language_saved_label.setObjectName('SavedNotice'); self.language_saved_label.setVisible(False); ar.addWidget(self.language_saved_label)
        ar.addStretch(1); al.addLayout(ar); self.section_layouts['interface'].addWidget(appearance)

        self.locations_card = QFrame(); self.locations_card.setObjectName('LocationCard')
        self.locations_layout = QVBoxLayout(self.locations_card); self.locations_layout.setContentsMargins(16, 14, 16, 14); self.locations_layout.setSpacing(9)
        self.section_layouts['library'].addWidget(self.locations_card)
        self._rebuild_location_rows()

        naming = QFrame(); naming.setObjectName('NamingCard')
        nl = QVBoxLayout(naming); nl.setContentsMargins(16, 14, 16, 14); nl.setSpacing(8)
        ntitle = QLabel('Format nazwy pliku'); ntitle.setStyleSheet('font-size:13pt;font-weight:750;color:#c7a9ff;'); nl.addWidget(ntitle)
        ndesc = QLabel('Wybierz dane umieszczane w nazwie. Domyślnie: Wykonawca - Tytuł (Wersja) (Rok) [BPMbpm].')
        ndesc.setWordWrap(True); ndesc.setObjectName('MutedText'); nl.addWidget(ndesc)
        selected_fields = filename_fields_from_template(cfg.filename_template or DEFAULT_FILENAME_TEMPLATE)
        fields_row = QHBoxLayout(); fields_row.setSpacing(10); self.filename_checks = {}
        for key, label, required in [
            ('Artist', 'Wykonawca', True), ('Title', 'Tytuł', True), ('Version', 'Wersja / Remix', False),
            ('Year', 'Rok', False), ('BPM', 'BPM', False), ('Genre', 'Gatunek', False), ('Album', 'Album', False),
        ]:
            check = QCheckBox(label); check.setChecked(required or key in selected_fields)
            check.setProperty('requiredLocked', required)
            if required:
                check.setToolTip('Element wymagany — nie można wyłączyć')
                tick = asset_path('check_green.svg').as_posix()
                check.setStyleSheet(f'QCheckBox::indicator:checked {{ image: url("{tick}"); background: transparent; border: 0; width:16px; height:16px; }}')
                check.toggled.connect(lambda checked, c=check: (not checked) and c.setChecked(True))
            check.toggled.connect(self._filename_fields_changed); fields_row.addWidget(check); self.filename_checks[key] = check
        fields_row.addStretch(1); nl.addLayout(fields_row)
        self.filename_template = QLineEdit(cfg.filename_template or DEFAULT_FILENAME_TEMPLATE); self.filename_template.setPlaceholderText(DEFAULT_FILENAME_TEMPLATE); nl.addWidget(self.filename_template)
        advanced = QLabel('Pola wyboru tworzą standardowy układ; szablon można też poprawić ręcznie.'); advanced.setObjectName('MutedText'); nl.addWidget(advanced)
        self.filename_preview = QLabel(''); self.filename_preview.setObjectName('FilenamePreview'); self.filename_preview.setWordWrap(True); nl.addWidget(self.filename_preview)
        nr = QHBoxLayout(); reset_name = QPushButton('Przywróć domyślny format'); reset_name.clicked.connect(self._reset_filename_format); nr.addWidget(reset_name); nr.addStretch(1); nl.addLayout(nr)
        self.filename_template.textChanged.connect(self._filename_template_changed); self._updating_filename_controls = False; self._update_filename_preview()
        self.section_layouts['naming'].addWidget(naming)

        normalization = QFrame(); normalization.setObjectName('NormalizationCard')
        nol = QVBoxLayout(normalization); nol.setContentsMargins(16, 14, 16, 14); nol.setSpacing(8)
        notitle = QLabel('Normalizacja nazw'); notitle.setStyleSheet('font-size:13pt;font-weight:750;color:#ffcf63;'); nol.addWidget(notitle)
        nodesc = QLabel('Automatycznie ujednolica typowe określenia muzyczne przy zapisie, np. dj → DJ, club → Club, feat → Feat. Każdą regułę możesz wyłączyć lub edytować.')
        nodesc.setWordWrap(True); nodesc.setObjectName('MutedText'); nol.addWidget(nodesc)
        self.normalize_names = QCheckBox('Automatycznie poprawiaj nazwy przy zapisie'); self.normalize_names.setChecked(prefs.normalize_names); nol.addWidget(self.normalize_names)
        self.normalization_table = QTableWidget(0, 3); self.normalization_table.setHorizontalHeaderLabels(('Włączona', 'Znajdź', 'Zamień na'))
        self.normalization_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.normalization_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.normalization_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.SelectedClicked)
        self.normalization_table.verticalHeader().setDefaultSectionSize(42)
        self.normalization_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.normalization_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch); self.normalization_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.normalization_table.setMinimumHeight(270); self.normalization_table.setMinimumWidth(640); nol.addWidget(self.normalization_table)
        self._load_normalization_rules(prefs.name_rules)
        nor = QHBoxLayout(); add_rule = QPushButton('Dodaj regułę'); add_rule.setIcon(alo_icon('add_tracks', '#8ecfe6', 16)); add_rule.clicked.connect(self._add_normalization_rule); nor.addWidget(add_rule)
        edit_rule = QPushButton('Edytuj zaznaczoną'); edit_rule.clicked.connect(self._edit_normalization_rule); nor.addWidget(edit_rule)
        remove_rule = QPushButton('Usuń zaznaczoną'); remove_rule.clicked.connect(self._remove_normalization_rule); nor.addWidget(remove_rule)
        reset_rules = QPushButton('Przywróć domyślne'); reset_rules.clicked.connect(self._reset_normalization_rules); nor.addWidget(reset_rules); nor.addStretch(1); nol.addLayout(nor)
        self.normalization_preview = QLabel(''); self.normalization_preview.setObjectName('FilenamePreview'); self.normalization_preview.setWordWrap(True); nol.addWidget(self.normalization_preview)
        self.normalization_table.itemChanged.connect(self._update_normalization_preview); self.normalize_names.toggled.connect(self._update_normalization_preview); self._update_normalization_preview()
        self.section_layouts['naming'].addWidget(normalization)

        organization = QFrame(); organization.setObjectName('FolderOrganizationCard')
        fl = QVBoxLayout(organization); fl.setContentsMargins(16, 14, 16, 14); fl.setSpacing(8)
        ftitle = QLabel('Organizacja folderu GOTOWE'); ftitle.setStyleSheet('font-size:13pt;font-weight:750;color:#65d8cf;'); fl.addWidget(ftitle)
        fdesc = QLabel('Opcjonalnie twórz jeden poziom podfolderów. Domyślnie wszystko trafia bezpośrednio do GOTOWE.'); fdesc.setWordWrap(True); fdesc.setObjectName('MutedText'); fl.addWidget(fdesc)
        genre_rule = QLabel('Przy organizacji według gatunku używany jest pierwszy gatunek z listy, np. Trance, Progressive, Vocal → GOTOWE\\Trance.'); genre_rule.setWordWrap(True); genre_rule.setObjectName('MutedText'); fl.addWidget(genre_rule)
        self.folder_org_buttons: dict[str, QRadioButton] = {}
        self.folder_org_buttons['none'] = QRadioButton('Bez podfolderów')
        self.folder_org_buttons['artist'] = QRadioButton('Według wykonawcy')
        self.folder_org_buttons['genre'] = QRadioButton('Według gatunku')
        self.folder_org_group = QButtonGroup(self); self.folder_org_group.setExclusive(True)
        examples = {
            'none': '<b style="color:#65d8cf">GOTOWE</b>\\4 Strings - Take Me Away (Dave Darell Remix) (2009) [132bpm].mp3',
            'artist': 'GOTOWE\\<b style="color:#65d8cf">4 Strings</b>\\4 Strings - Take Me Away (Dave Darell Remix) (2009) [132bpm].mp3',
            'genre': 'GOTOWE\\<b style="color:#65d8cf">Trance</b>\\4 Strings - Take Me Away (Dave Darell Remix) (2009) [132bpm].mp3',
        }
        active = cfg.folder_organization if cfg.folder_organization in examples else 'none'
        for key, example in examples.items():
            row = QFrame(); row.setObjectName('FolderChoiceRow'); row.setProperty('selected', key == active)
            rl = QVBoxLayout(row); rl.setContentsMargins(11, 8, 11, 8); rl.setSpacing(3)
            radio = self.folder_org_buttons[key]; radio.setChecked(key == active); self.folder_org_group.addButton(radio)
            radio.toggled.connect(self._update_folder_preview); rl.addWidget(radio)
            sample = QLabel(example); sample.setObjectName('FolderOptionExample'); sample.setTextFormat(Qt.TextFormat.RichText); sample.setWordWrap(True); rl.addWidget(sample)
            fl.addWidget(row)
        preview_head = QLabel('PODGLĄD DOCELOWEJ ŚCIEŻKI'); preview_head.setObjectName('FieldHeading'); fl.addWidget(preview_head)
        self.folder_preview = QLabel(''); self.folder_preview.setObjectName('FolderStructurePreview'); self.folder_preview.setWordWrap(True); self.folder_preview.setTextFormat(Qt.TextFormat.RichText); fl.addWidget(self.folder_preview)
        self._update_folder_preview(); self.section_layouts['naming'].addWidget(organization)

        recognition = QFrame(); recognition.setObjectName('OnlineRecognitionCard')
        rol = QVBoxLayout(recognition); rol.setContentsMargins(16, 14, 16, 14); rol.setSpacing(9)
        rotitle = QLabel('Zachowanie rozpoznawania'); rotitle.setStyleSheet('font-size:13pt;font-weight:750;color:#57d8ff;'); rol.addWidget(rotitle)
        rodesc = QLabel('Ustaw, czy ALO ma automatycznie rozpocząć rozpoznawanie po zakończeniu skanowania.')
        rodesc.setWordWrap(True); rodesc.setObjectName('MutedText'); rol.addWidget(rodesc)
        self.auto = QCheckBox('Po skanie automatycznie uruchom rozpoznawanie online')
        self.auto.setChecked(cfg.auto_identify_after_scan); rol.addWidget(self.auto)
        self.section_layouts['online'].addWidget(recognition)

        backup = QFrame(); backup.setObjectName('BackupCard')
        bal = QVBoxLayout(backup); bal.setContentsMargins(16, 14, 16, 14); bal.setSpacing(8)
        batitle = QLabel('Kopia bezpieczeństwa ALO'); batitle.setStyleSheet('font-size:13pt;font-weight:750;color:#7eb4ff;'); bal.addWidget(batitle)
        badesc = QLabel('Kopia obejmuje bazę ALO i konfigurację programu. Pliki muzyczne nie są kopiowane.')
        badesc.setWordWrap(True); badesc.setObjectName('MutedText'); bal.addWidget(badesc)
        bar = QHBoxLayout(); make_backup = QPushButton('Utwórz kopię'); make_backup.clicked.connect(self.backup_requested); bar.addWidget(make_backup)
        restore_backup = QPushButton('Przywróć kopię'); restore_backup.clicked.connect(self.restore_backup_requested); bar.addWidget(restore_backup); bar.addStretch(1); bal.addLayout(bar)
        self.section_layouts['advanced'].addWidget(backup)

        online = QFrame(); online.setObjectName('IntegrationCard'); self.integration_card = online
        ol = QVBoxLayout(online); ol.setContentsMargins(18, 16, 18, 18); ol.setSpacing(15)
        info = QLabel('Każde źródło działa niezależnie. Klucze są przechowywane lokalnie i pozostają maskowane w interfejsie.')
        info.setWordWrap(True); info.setObjectName('MutedText'); ol.addWidget(info)
        self.provider_cards: dict[str, QFrame] = {}
        self.provider_names: dict[str, QLabel] = {}

        self.acoustid = QLineEdit(cfg.acoustid_key); self.acoustid.setEchoMode(QLineEdit.EchoMode.Password); self.acoustid.setPlaceholderText('Application API Key')
        ac_card = QFrame(); ac_card.setObjectName('ProviderCard'); ac_card.setProperty('providerKind', 'acoustid'); ac_card.setMinimumHeight(116); ac = QVBoxLayout(ac_card); ac.setContentsMargins(14, 12, 14, 12); ac.setSpacing(8); ac.addWidget(_provider_accent('acoustid', '#57d8ff', ac_card))
        ach = QHBoxLayout(); ach.setSpacing(10); ach.addWidget(_icon_label('fingerprint', '#57d8ff', 24))
        ac_text = QVBoxLayout(); ac_name = QLabel('AcoustID'); ac_name.setObjectName('ProviderName'); ac_name.setProperty('providerColor', '#57d8ff'); ac_name.setStyleSheet('color:#57d8ff;'); ac_desc = QLabel('Rozpoznawanie utworów na podstawie fingerprintu audio.'); ac_desc.setObjectName('MutedText'); ac_desc.setWordWrap(True); ac_text.addWidget(ac_name); ac_text.addWidget(ac_desc); ach.addLayout(ac_text, 1)
        self.acoustid_status = QLabel(''); self.acoustid_status.setObjectName('ProviderStatusBadge'); ach.addWidget(self.acoustid_status); ac.addLayout(ach)
        self.acoustid.setObjectName('ProviderSecretField'); ac.addWidget(self.acoustid)
        acr = QHBoxLayout(); ah = QPushButton('Jak zdobyć klucz?'); ah.setIcon(alo_icon('help', '#b8c6d2', 16)); ah.clicked.connect(lambda: self.help_requested.emit('Konfiguracja AcoustID i Discogs')); aw = QPushButton('Otwórz stronę'); aw.setIcon(alo_icon('external', '#83cfff', 16)); aw.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://acoustid.org/new-application'))); acr.addWidget(ah); acr.addWidget(aw); acr.addStretch(1); ac.addLayout(acr); self.provider_cards['acoustid'] = ac_card; self.provider_names['acoustid'] = ac_name; ol.addWidget(ac_card)

        self.discogs = QLineEdit(cfg.discogs_token); self.discogs.setEchoMode(QLineEdit.EchoMode.Password); self.discogs.setPlaceholderText('Personal Access Token')
        dc_card = QFrame(); dc_card.setObjectName('ProviderCard'); dc_card.setProperty('providerKind', 'discogs'); dc_card.setMinimumHeight(116); dc = QVBoxLayout(dc_card); dc.setContentsMargins(14, 12, 14, 12); dc.setSpacing(8); dc.addWidget(_provider_accent('discogs', '#43d17d', dc_card))
        dch = QHBoxLayout(); dch.setSpacing(10); dch.addWidget(_icon_label('disc', '#43d17d', 24))
        dc_text = QVBoxLayout(); dc_name = QLabel('Discogs'); dc_name.setObjectName('ProviderName'); dc_name.setProperty('providerColor', '#43d17d'); dc_name.setStyleSheet('color:#43d17d;'); dc_desc = QLabel('Wersja, remix, rok, gatunek i informacje o wydaniu.'); dc_desc.setObjectName('MutedText'); dc_desc.setWordWrap(True); dc_text.addWidget(dc_name); dc_text.addWidget(dc_desc); dch.addLayout(dc_text, 1)
        self.discogs_status = QLabel(''); self.discogs_status.setObjectName('ProviderStatusBadge'); dch.addWidget(self.discogs_status); dc.addLayout(dch)
        self.discogs.setObjectName('ProviderSecretField'); dc.addWidget(self.discogs)
        dcr = QHBoxLayout(); dh = QPushButton('Jak zdobyć klucz?'); dh.setIcon(alo_icon('help', '#b8c6d2', 16)); dh.clicked.connect(lambda: self.help_requested.emit('Konfiguracja AcoustID i Discogs')); dw = QPushButton('Otwórz stronę'); dw.setIcon(alo_icon('external', '#7ee7a5', 16)); dw.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://www.discogs.com/settings/developers'))); dcr.addWidget(dh); dcr.addWidget(dw); dcr.addStretch(1); dc.addLayout(dcr); self.provider_cards['discogs'] = dc_card; self.provider_names['discogs'] = dc_name; ol.addWidget(dc_card)

        self.mb_contact = QLineEdit(cfg.musicbrainz_contact); self.mb_contact.setVisible(False)
        mb = QFrame(); mb.setObjectName('ProviderCard'); mb.setProperty('providerKind', 'musicbrainz'); mb.setMinimumHeight(116); ml = QVBoxLayout(mb); ml.setContentsMargins(14, 12, 14, 12); ml.setSpacing(8); ml.addWidget(_provider_accent('musicbrainz', '#b86cff', mb))
        mbh = QHBoxLayout(); mbh.setSpacing(10); mbh.addWidget(_icon_label('brain', '#b86cff', 24))
        mb_text = QVBoxLayout(); mb_name = QLabel('MusicBrainz'); mb_name.setObjectName('ProviderName'); mb_name.setProperty('providerColor', '#b86cff'); mb_name.setStyleSheet('color:#b86cff;'); mb_desc = QLabel('Utwór, wykonawca, album i identyfikatory nagrania.'); mb_desc.setObjectName('MutedText'); mb_desc.setWordWrap(True); mb_text.addWidget(mb_name); mb_text.addWidget(mb_desc); mbh.addLayout(mb_text, 1)
        self.musicbrainz_status = QLabel('Nie wymaga klucza API'); self.musicbrainz_status.setObjectName('ProviderStatusBadge'); self.musicbrainz_status.setProperty('providerState', 'no-key'); mbh.addWidget(self.musicbrainz_status); ml.addLayout(mbh)
        mb_actions = QHBoxLayout(); mb_web = QPushButton('Otwórz stronę'); mb_web.setIcon(alo_icon('external', '#d09bff', 16)); mb_web.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://musicbrainz.org/'))); mb_actions.addWidget(mb_web); mb_actions.addStretch(1); ml.addLayout(mb_actions); self.provider_cards['musicbrainz'] = mb; self.provider_names['musicbrainz'] = mb_name; ol.addWidget(mb)

        apple = QFrame(); apple.setObjectName('ProviderCard'); apple.setProperty('providerKind', 'apple'); apple.setMinimumHeight(116); apl = QVBoxLayout(apple); apl.setContentsMargins(14, 12, 14, 12); apl.setSpacing(8); apl.addWidget(_provider_accent('apple', '#ff6670', apple))
        aph = QHBoxLayout(); aph.setSpacing(10); aph.addWidget(_icon_label('music', '#ff6670', 24))
        apple_text = QVBoxLayout(); apple_name = QLabel('Apple / iTunes'); apple_name.setObjectName('ProviderName'); apple_name.setProperty('providerColor', '#ff6670'); apple_name.setStyleSheet('color:#ff6670;'); apple_desc = QLabel('Katalog, album, rok, gatunek i propozycje okładek.'); apple_desc.setObjectName('MutedText'); apple_desc.setWordWrap(True); apple_text.addWidget(apple_name); apple_text.addWidget(apple_desc); aph.addLayout(apple_text, 1)
        self.apple_status = QLabel('Nie wymaga klucza API'); self.apple_status.setObjectName('ProviderStatusBadge'); self.apple_status.setProperty('providerState', 'no-key'); aph.addWidget(self.apple_status); apl.addLayout(aph)
        apple_actions = QHBoxLayout(); apple_web = QPushButton('Otwórz stronę'); apple_web.setIcon(alo_icon('external', '#ff8892', 16)); apple_web.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://music.apple.com/pl/browse'))); apple_actions.addWidget(apple_web); apple_actions.addStretch(1); apl.addLayout(apple_actions); self.provider_cards['apple'] = apple; self.provider_names['apple'] = apple_name; ol.addWidget(apple)

        self.acoustid.textChanged.connect(self._update_provider_statuses)
        self.discogs.textChanged.connect(self._update_provider_statuses)
        self._update_provider_statuses()

        api_save_row = QHBoxLayout(); self.save_api_button = QPushButton('Zapisz klucze'); self.save_api_button.setObjectName('SectionSaveButton'); self.save_api_button.clicked.connect(self._save_api); api_save_row.addWidget(self.save_api_button)
        self.api_saved_label = QLabel('Klucze zapisane'); self.api_saved_label.setObjectName('SavedNotice'); self.api_saved_label.setVisible(False); api_save_row.addWidget(self.api_saved_label); api_save_row.addStretch(1); ol.addLayout(api_save_row)
        attribution = QLabel('This application uses Discogs’ API but is not affiliated with, sponsored or endorsed by Discogs. “Discogs” is a trademark of Zink Media, LLC.')
        attribution.setWordWrap(True); attribution.setObjectName('FinePrint'); ol.addWidget(attribution)
        self.section_layouts['integrations'].addWidget(online)

        reset_card = QFrame(); reset_card.setObjectName('SafeDefaultsCard')
        reset_layout = QHBoxLayout(reset_card); reset_layout.setContentsMargins(16, 12, 16, 12); reset_layout.setSpacing(12)
        reset_copy = QVBoxLayout(); reset_copy.setSpacing(3)
        reset_title = QLabel('Ustawienia domyślne'); reset_title.setStyleSheet('font-weight:700;'); reset_copy.addWidget(reset_title)
        reset_note = QLabel('Przywróć bezpieczne preferencje bez usuwania biblioteki, utworów ani kluczy API.')
        reset_note.setWordWrap(True); reset_note.setObjectName('MutedText'); reset_copy.addWidget(reset_note)
        reset_layout.addLayout(reset_copy, 1)
        self.restore_defaults_button = QPushButton('Przywróć ustawienia domyślne')
        self.restore_defaults_button.setObjectName('RestoreDefaultsAction')
        self.restore_defaults_button.setIcon(alo_icon('restore', '#9fc9d8', 17))
        self.restore_defaults_button.clicked.connect(self._restore_defaults)
        reset_layout.addWidget(self.restore_defaults_button)
        self.section_layouts['advanced'].addWidget(reset_card)

        full_reset_card = QFrame(); full_reset_card.setObjectName('FullResetCard'); full_reset_card.setProperty('settingsSection', 'advanced')
        full_reset_layout = QHBoxLayout(full_reset_card); full_reset_layout.setContentsMargins(16, 12, 16, 12); full_reset_layout.setSpacing(12)
        full_reset_copy = QVBoxLayout(); full_reset_copy.setSpacing(3)
        full_reset_title = QLabel('Resetuj ALO do czystego stanu'); full_reset_title.setStyleSheet('font-weight:700;color:#ff8b83;'); full_reset_copy.addWidget(full_reset_title)
        full_reset_note = QLabel('Usuwa bazy i ustawienia ALO, ale nie usuwa plików muzycznych z dysku.')
        full_reset_note.setWordWrap(True); full_reset_note.setObjectName('MutedText'); full_reset_copy.addWidget(full_reset_note)
        full_reset_layout.addLayout(full_reset_copy, 1)
        self.full_reset_button = QPushButton('Resetuj ALO do czystego stanu')
        self.full_reset_button.setObjectName('RemoveLibraryAction')
        self.full_reset_button.setIcon(alo_icon('warning', '#ff8b83', 17))
        self.full_reset_button.clicked.connect(self.full_reset_requested)
        full_reset_layout.addWidget(self.full_reset_button)
        self.section_layouts['advanced'].addWidget(full_reset_card)

        save_row = QHBoxLayout(); self.saved_label = QLabel('Ustawienia zapisane'); self.saved_label.setObjectName('SavedNotice'); self.saved_label.setVisible(False)
        save = QPushButton('Zapisz ustawienia'); save.setObjectName('Primary'); save.clicked.connect(self._save)
        save_row.addWidget(save); save_row.addWidget(self.saved_label); save_row.addStretch(1); lay.addLayout(save_row)

        footer = QFrame(); footer.setObjectName('ContactFooter')
        cl = QVBoxLayout(footer); cl.setContentsMargins(10, 8, 10, 8); cl.setSpacing(2)
        version_label = QLabel(f'ALO Music v{__version__} • 2026'); version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter); cl.addWidget(version_label)
        powered = QLabel('Powered by Damian'); powered.setObjectName('ContactAuthor'); powered.setAlignment(Qt.AlignmentFlag.AlignHCenter); cl.addWidget(powered)
        cr = QHBoxLayout(); cr.addStretch(1); contact_label = QLabel('Kontakt:'); contact_label.setObjectName('ContactLabel'); cr.addWidget(contact_label)
        contact_link = QLabel('<a href="https://github.com/DamianPPD/ALO-Music-Public/issues">GitHub Issues</a>'); contact_link.setObjectName('ContactEmail'); contact_link.setOpenExternalLinks(True); contact_link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.TextSelectableByMouse); cr.addWidget(contact_link); cr.addStretch(1); cl.addLayout(cr)
        lay.addWidget(footer)
        lay.addStretch(1)
        scroll.setWidget(content); self.scroll = scroll; root.addWidget(scroll)

    @staticmethod
    def _make_settings_section(name: str, title: str, description: str, icon_name: str, accent: str):
        section = QFrame(); section.setObjectName('SettingsSection'); section.setProperty('sectionName', name)
        outer = QVBoxLayout(section); outer.setContentsMargins(14, 13, 14, 14); outer.setSpacing(10)
        heading = QHBoxLayout(); heading.setSpacing(8)
        heading.addWidget(_icon_label(icon_name, accent, 20))
        title_label = QLabel(title); title_label.setObjectName('SettingsSectionTitle'); title_label.setStyleSheet(f'color:{accent};')
        heading.addWidget(title_label, 1); outer.addLayout(heading)
        description_label = QLabel(description); description_label.setObjectName('SettingsSectionDescription'); description_label.setWordWrap(True)
        outer.addWidget(description_label)
        body = QVBoxLayout(); body.setContentsMargins(0, 2, 0, 0); body.setSpacing(10); outer.addLayout(body)
        return section, body

    def _open_path(self, path: Path):
        path = Path(path)
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _add_section_divider(self, layout: QVBoxLayout):
        divider = QFrame(); divider.setObjectName('SettingsSectionDivider'); divider.setFixedHeight(2); layout.addWidget(divider)

    def _path_row(self, layout: QVBoxLayout, label: str, path: Path, accent: str):
        box = QFrame(); box.setObjectName('PathRow')
        row = QHBoxLayout(box); row.setContentsMargins(12, 7, 12, 7); row.setSpacing(8)
        lab = QLabel(label); lab.setStyleSheet(f'font-weight:700;color:{accent};'); lab.setMinimumWidth(165)
        parent = html.escape(str(Path(path).parent))
        name = html.escape(Path(path).name)
        val = QLabel(f'<span style="color:#8391a0">{parent}\\</span><b style="color:{accent}">{name}</b>')
        val.setTextFormat(Qt.TextFormat.RichText); val.setWordWrap(True); val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        open_button = QPushButton('Otwórz'); open_button.setObjectName('PathOpenButton'); open_button.setEnabled(Path(path).exists()); open_button.clicked.connect(lambda _=False, p=Path(path): self._open_path(p))
        row.addWidget(lab); row.addWidget(val, 1); row.addWidget(open_button); layout.addWidget(box)

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                SettingsPage._clear_layout(child_layout)

    def _rebuild_location_rows(self):
        if not hasattr(self, 'locations_layout'):
            return
        self._clear_layout(self.locations_layout)
        settings = self.app_settings
        ll = self.locations_layout
        available = settings.library.root.exists() and settings.library.root.is_dir()
        status_row = QHBoxLayout(); status_row.setSpacing(8)
        self.library_status_icon = QLabel(); self.library_status_icon.setObjectName('LibraryAvailabilityIcon')
        status_color = '#43d17d' if available else '#ffb84d'
        status_name = 'status' if available else 'warning'
        self.library_status_icon.setPixmap(alo_icon(status_name, status_color, 18).pixmap(18, 18))
        self.library_status_icon.setFixedSize(22, 22); self.library_status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_row.addWidget(self.library_status_icon)
        status_text = 'Biblioteka dostępna' if available else 'Biblioteka niedostępna'
        self.library_status_label = QLabel(ui_text(self, status_text))
        self.library_status_label.setObjectName('LibraryAvailabilityStatus')
        self.library_status_label.setProperty('available', available)
        self.library_status_label.setStyleSheet(f'color:{status_color};font-weight:700;')
        status_row.addWidget(self.library_status_label); status_row.addStretch(1); ll.addLayout(status_row)

        location_row = QHBoxLayout(); location_row.setSpacing(10)
        self.library_path_label = QLabel(str(settings.library.root)); self.library_path_label.setObjectName('LibraryLocationPath')
        self.library_path_label.setToolTip(str(settings.library.root)); self.library_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.library_path_label.setWordWrap(True); location_row.addWidget(self.library_path_label, 1)
        self.change_library_button = QPushButton(ui_text(self, 'Zmień lokalizację')); self.change_library_button.setObjectName('ChangeLibraryLocationAction')
        self.change_library_button.setIcon(alo_icon('folder_open', '#8ecfe6', 17))
        self.change_library_button.clicked.connect(self.change_library_location_requested); location_row.addWidget(self.change_library_button)
        ll.addLayout(location_row)

    def refresh_main_settings(self, settings: AppSettings):
        self.app_settings = settings
        self._rebuild_location_rows()

    def _save_language(self):
        current = AppPreferences.from_store(self.store)
        prefs = AppPreferences(
            language=str(self.language_combo.currentData() or 'pl'),
            theme='dark',
            normalize_names=current.normalize_names,
            name_rules=current.name_rules,
        )
        prefs.save(self.store)
        self.language_saved_label.setVisible(True)
        QTimer.singleShot(2200, lambda: self.language_saved_label.setVisible(False))
        self.preferences_saved.emit(prefs)

    def _update_provider_statuses(self, *_):
        for field, badge in (
            (self.acoustid, self.acoustid_status),
            (self.discogs, self.discogs_status),
        ):
            configured = bool(field.text().strip())
            badge.setText(ui_text(self, 'Skonfigurowano' if configured else 'Brak klucza'))
            badge.setProperty('providerState', 'ready' if configured else 'missing')
            badge.style().unpolish(badge)
            badge.style().polish(badge)

    def _save_api(self):
        current = ProviderSettings.from_store(self.store)
        ProviderSettings(
            acoustid_key=self.acoustid.text().strip(),
            discogs_token=self.discogs.text().strip(),
            musicbrainz_contact=self.mb_contact.text().strip() or 'personal-use',
            auto_identify_after_scan=self.auto.isChecked(),
            filename_template=current.filename_template,
            contact_email=current.contact_email,
            folder_organization=current.folder_organization,
        ).save(self.store)
        self._update_provider_statuses()
        self.api_saved_label.setVisible(True)
        QTimer.singleShot(2200, lambda: self.api_saved_label.setVisible(False))
        self.provider_saved.emit()

    def _filename_fields_changed(self, *_):
        if getattr(self, '_updating_filename_controls', False): return
        enabled = {key for key, check in self.filename_checks.items() if check.isChecked()}
        self._updating_filename_controls = True; self.filename_template.setText(template_from_filename_fields(enabled)); self._updating_filename_controls = False; self._update_filename_preview()

    def _filename_template_changed(self, *_):
        if not getattr(self, '_updating_filename_controls', False):
            fields = filename_fields_from_template(self.filename_template.text()); self._updating_filename_controls = True
            for key, check in self.filename_checks.items(): check.setChecked(key in fields or key in {'Artist', 'Title'})
            self._updating_filename_controls = False
        self._update_filename_preview()

    def _reset_filename_format(self):
        self.filename_template.setText(DEFAULT_FILENAME_TEMPLATE)

    def _update_filename_preview(self):
        sample = TrackRecord(path=Path('sample.mp3'), artist='4 Strings', title='Take Me Away (Dave Darell Remix)', album='Take Me Away', year='2009', genre='Trance', bpm=132)
        template = self.filename_template.text().strip() or DEFAULT_FILENAME_TEMPLATE
        self.filename_preview.setText(ui_text(self, 'Podgląd: ') + propose_filename(sample, template=template))

    def _selected_folder_organization(self) -> str:
        for key, button in self.folder_org_buttons.items():
            if button.isChecked():
                return key
        return 'none'

    def _update_folder_preview(self, *_):
        if not hasattr(self, 'folder_org_buttons'):
            return
        mode = self._selected_folder_organization()
        filename = '4 Strings - Take Me Away (Dave Darell Remix) (2009) [132bpm].mp3'
        ready = Path(self.app_settings.library.ready)
        base = html.escape(str(ready.parent))
        ready_name = html.escape(ready.name)
        root = f'<span style="color:#8391a0">{base}\\</span><b style="color:#65d8cf">{ready_name}</b>'
        if mode == 'artist':
            target = f'{root}\\<b style="color:#65d8cf">4 Strings</b>\\{html.escape(filename)}'
        elif mode == 'genre':
            target = f'{root}\\<b style="color:#65d8cf">Trance</b>\\{html.escape(filename)}'
        else:
            target = f'{root}\\{html.escape(filename)}'
        self.folder_preview.setText(ui_text(self, 'Przykład: ') + target)
        for key, button in self.folder_org_buttons.items():
            row = button.parentWidget()
            if row is not None:
                row.setProperty('selected', key == mode); row.style().unpolish(row); row.style().polish(row)

    def _load_normalization_rules(self, rules):
        self.normalization_table.blockSignals(True)
        self.normalization_table.setRowCount(0)
        for rule in rules:
            row = self.normalization_table.rowCount(); self.normalization_table.insertRow(row)
            enabled = QTableWidgetItem(''); enabled.setFlags(enabled.flags() | Qt.ItemFlag.ItemIsUserCheckable); enabled.setCheckState(Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked)
            find = QTableWidgetItem(rule.find); replacement = QTableWidgetItem(rule.replacement)
            self.normalization_table.setItem(row, 0, enabled); self.normalization_table.setItem(row, 1, find); self.normalization_table.setItem(row, 2, replacement)
        self.normalization_table.blockSignals(False)

    def _normalization_rules(self) -> tuple[NameNormalizationRule, ...]:
        rules = []
        for row in range(self.normalization_table.rowCount()):
            enabled_item = self.normalization_table.item(row, 0); find_item = self.normalization_table.item(row, 1); replace_item = self.normalization_table.item(row, 2)
            find = (find_item.text() if find_item else '').strip(); replacement = (replace_item.text() if replace_item else '').strip()
            if not find:
                continue
            enabled = enabled_item is None or enabled_item.checkState() == Qt.CheckState.Checked
            rules.append(NameNormalizationRule(find, replacement, enabled))
        return tuple(rules) or default_name_rules()

    def _add_normalization_rule(self):
        row = self.normalization_table.rowCount(); self.normalization_table.insertRow(row)
        enabled = QTableWidgetItem(''); enabled.setFlags(enabled.flags() | Qt.ItemFlag.ItemIsUserCheckable); enabled.setCheckState(Qt.CheckState.Checked)
        self.normalization_table.setItem(row, 0, enabled); self.normalization_table.setItem(row, 1, QTableWidgetItem('')); self.normalization_table.setItem(row, 2, QTableWidgetItem(''))
        self.normalization_table.setCurrentCell(row, 1); self.normalization_table.editItem(self.normalization_table.item(row, 1))

    def _edit_normalization_rule(self):
        row = self.normalization_table.currentRow()
        if row < 0:
            return
        enabled_item = self.normalization_table.item(row, 0)
        find_item = self.normalization_table.item(row, 1)
        replace_item = self.normalization_table.item(row, 2)

        dialog = QDialog(self)
        dialog.setWindowTitle('Edytuj regułę normalizacji')
        dialog.setMinimumWidth(460)
        root = QVBoxLayout(dialog); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(12)
        form = QFormLayout(); form.setSpacing(10)
        enabled = QCheckBox('Włączona')
        enabled.setChecked(enabled_item is None or enabled_item.checkState() == Qt.CheckState.Checked)
        find_edit = QLineEdit((find_item.text() if find_item else '').strip())
        replace_edit = QLineEdit((replace_item.text() if replace_item else '').strip())
        find_edit.setMinimumHeight(36); replace_edit.setMinimumHeight(36)
        form.addRow('Znajdź:', find_edit); form.addRow('Zamień na:', replace_edit); form.addRow('', enabled)
        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Zapisz')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Anuluj')
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); root.addWidget(buttons)
        apply_static_language(dialog, str(self.language_combo.currentData() or 'pl'))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not find_edit.text().strip():
            QMessageBox.warning(self, ui_text(self, 'Brak reguły'), ui_text(self, 'Pole „Znajdź” nie może być puste.'))
            return
        enabled_item.setCheckState(Qt.CheckState.Checked if enabled.isChecked() else Qt.CheckState.Unchecked)
        find_item.setText(find_edit.text().strip())
        replace_item.setText(replace_edit.text().strip())
        self._update_normalization_preview()

    def _remove_normalization_rule(self):
        row = self.normalization_table.currentRow()
        if row >= 0:
            self.normalization_table.removeRow(row); self._update_normalization_preview()

    def _reset_normalization_rules(self):
        self._load_normalization_rules(default_name_rules()); self._update_normalization_preview()

    def _update_normalization_preview(self, *_):
        if not hasattr(self, 'normalization_preview'):
            return
        from audio_library_organizer.metadata.normalization import normalize_music_text
        sample = 'dj alpha feat beta (extended club mix)'
        result = normalize_music_text(sample, self._normalization_rules()) if self.normalize_names.isChecked() else sample
        self.normalization_preview.setText(ui_text(self, f'Podgląd: {sample}  →  {result}'))

    def create_restore_defaults_dialog(self) -> RestoreDefaultsDialog:
        dialog = RestoreDefaultsDialog(self)
        apply_static_language(dialog, str(self.language_combo.currentData() or 'pl'))
        return dialog

    def _restore_defaults(self):
        dialog = self.create_restore_defaults_dialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        restore_safe_defaults(self.store)
        cfg = ProviderSettings.from_store(self.store)
        prefs = AppPreferences.from_store(self.store)
        self.filename_template.setText(cfg.filename_template)
        self.normalize_names.setChecked(prefs.normalize_names)
        self._load_normalization_rules(prefs.name_rules)
        self.folder_org_buttons.get(cfg.folder_organization, self.folder_org_buttons['none']).setChecked(True)
        self.auto.setChecked(cfg.auto_identify_after_scan)
        self._update_filename_preview()
        self._update_normalization_preview()
        self._update_folder_preview()
        self.saved_label.setText(ui_text(self, 'Przywrócono ustawienia domyślne'))
        self.saved_label.setVisible(True)
        QTimer.singleShot(3500, lambda: self.saved_label.setVisible(False))
        self.provider_saved.emit()
        self.preferences_saved.emit(prefs)

    def _save(self):
        ProviderSettings(
            acoustid_key=self.acoustid.text().strip(), discogs_token=self.discogs.text().strip(),
            musicbrainz_contact=self.mb_contact.text().strip() or 'personal-use', auto_identify_after_scan=self.auto.isChecked(),
            filename_template=self.filename_template.text().strip() or DEFAULT_FILENAME_TEMPLATE,
            contact_email='', folder_organization=self._selected_folder_organization(),
        ).save(self.store)
        prefs = AppPreferences(
            language=str(self.language_combo.currentData() or 'pl'),
            theme='dark',
            normalize_names=self.normalize_names.isChecked(),
            name_rules=self._normalization_rules(),
        )
        prefs.save(self.store)
        self.saved_label.setVisible(True); self.saved_label.setText(ui_text(self, 'Ustawienia zapisane'))
        QTimer.singleShot(3500, lambda: self.saved_label.setVisible(False)); self.provider_saved.emit(); self.preferences_saved.emit(prefs)


class StartNavButton(QPushButton):
    """One icon family and a short colour transition, without moving tabs."""

    def __init__(self, label: str, icon_name: str, parent=None):
        super().__init__(label, parent)
        self._icon_name = icon_name
        self._icon_color = QColor('#d8e1e5')
        self._hovered = False
        self.setIconSize(QSize(20, 20))
        self.setIcon(start_icon(icon_name, self._icon_color.name(), 20))
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(150)
        self._fade.valueChanged.connect(self._paint_icon_color)
        self.toggled.connect(self._refresh_color)

    def _paint_icon_color(self, color):
        self._icon_color = QColor(color)
        self.setIcon(start_icon(self._icon_name, self._icon_color.name(), 20))

    def _refresh_color(self, *_):
        target = QColor('#4cde96' if self.isChecked() or self._hovered else '#d8e1e5')
        self._fade.stop()
        if self.isChecked():
            self._paint_icon_color(target)
            return
        self._fade.setStartValue(self._icon_color)
        self._fade.setEndValue(target)
        self._fade.start()

    def enterEvent(self, event):
        self._hovered = True
        self._refresh_color()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._refresh_color()
        super().leaveEvent(event)


def _read_menu_snapshot(repository, library_root):
    """Worker-only fresh read; never dereference MainWindow on a pool thread."""
    snapshot = repository.file_check_snapshot()
    return (snapshot.read_context(library_root), tuple(snapshot.tracks),
            {tid: cached.evaluation for tid, cached in snapshot.cached})


class MainWindow(QMainWindow):
    def __init__(self, app_settings: AppSettings, qt_settings: QSettings, parent=None):
        super().__init__(parent)
        self.main_settings = app_settings
        self.qt_settings = qt_settings
        self.preferences = AppPreferences.from_store(qt_settings)
        self.library_registry = LibraryRegistry.from_store(qt_settings, app_settings)
        self.main_settings = self.library_registry.main_settings
        self.app_settings = self.library_registry.settings_for(self.library_registry.active)
        self.setWindowTitle('ALO Music — Audio Library Organizer')
        self.setWindowIcon(QIcon(str(asset_path('alo.ico'))))
        self.resize(1500, 900)
        self.app_settings.library.ensure_created()
        self.repository = LibraryRepository(self.app_settings.library.database); self.repository.initialize()
        self.availability = self.repository.sync_availability()
        self.service = LibraryService(self.app_settings, self.repository)
        self.change_history = ChangeHistory(library_id=self.repository.library_id)
        self._identification_generation = 0
        self._read_context = None
        self._thread = None; self._worker = None; self._pending_auto_identify = False; self._operation_kind = 'idle'; self._identification_was_cancelled = False; self._active_scan_source_dirs = None
        self._identification_closing = False
        self._active_metadata_editor = None
        self._file_check_generation = 0
        self._file_check_context = None
        self._file_check_repository = None
        self._file_check_closing = False
        self._output_operation = None
        self._output_session = {}
        self._output_baseline_evals = {}
        self._output_watcher = QFileSystemWatcher(self)
        self._output_watcher.fileChanged.connect(self._output_watch_changed)
        self._output_watcher.directoryChanged.connect(self._output_watch_changed)
        self.last_reconciliation_result = None
        self._adoption_dialog = None
        self._adoption_view_context = None
        QApplication.instance().aboutToQuit.connect(self._stop_file_check_on_quit)

        central = QWidget(); self.setCentralWidget(central)
        self.statusBar().hide()
        outer = QVBoxLayout(central); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        top_nav = QFrame(); top_nav.setObjectName('TopNav')
        nav = QHBoxLayout(top_nav); nav.setContentsMargins(18, 8, 18, 8); nav.setSpacing(8)
        brand_wrap = QWidget(); brand_lay = QHBoxLayout(brand_wrap); brand_lay.setContentsMargins(0, 0, 8, 0); brand_lay.setSpacing(9)
        brand_icon = QLabel(); pix = QPixmap(str(asset_path('alo_icon.png')))
        if not pix.isNull(): brand_icon.setPixmap(pix.scaled(42, 42, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand_icon.setFixedSize(44, 44); brand_lay.addWidget(brand_icon)
        brand_text = QVBoxLayout(); brand_text.setSpacing(0)
        brand_name = QLabel('ALO Music'); brand_name.setObjectName('BrandName')
        brand_ver = QLabel(f'v{__version__} • 2026'); brand_ver.setObjectName('BrandVersion')
        brand_text.addWidget(brand_name); brand_text.addWidget(brand_ver); brand_lay.addLayout(brand_text)
        brand_wrap.setFixedWidth(205); nav.addWidget(brand_wrap)
        self.nav_buttons = []
        self.nav_icon_ids = ('nav_start', 'nav_library', 'nav_duplicates', 'nav_folders', 'nav_help', 'nav_settings')
        for icon_name, (label, index) in zip(self.nav_icon_ids, [('Start', 0), ('Biblioteka', 1), ('Duplikaty', 2), ('Foldery z zaznaczonych utworów', 3), ('Pomoc', 4), ('Ustawienia', 5)]):
            btn = StartNavButton(label, icon_name); btn.setObjectName('TopNavButton'); btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, i=index: self._navigate(i)); self.nav_buttons.append(btn)
            nav.addWidget(btn)
        nav.addStretch(1)
        self.manage_libraries_nav = QPushButton('Biblioteki'); self.manage_libraries_nav.setObjectName('ManageLibrariesNavAction')
        self.manage_libraries_nav.setIcon(start_icon('folder', '#aeb9c4', 18))
        self.manage_libraries_nav.setIconSize(QSize(17, 17))
        self.manage_libraries_nav.setToolTip('Zarządzaj bibliotekami ALO'); self.manage_libraries_nav.clicked.connect(self._open_library_manager); nav.addWidget(self.manage_libraries_nav)
        outer.addWidget(top_nav)

        self.action_frame = QFrame(); self.action_frame.setObjectName('ToolbarFrame')
        action = QHBoxLayout(self.action_frame); action.setContentsMargins(10, 7, 10, 7); action.setSpacing(6)

        workflow_group = QFrame(); workflow_group.setObjectName('WorkflowToolbarGroup')
        workflow = QHBoxLayout(workflow_group); workflow.setContentsMargins(4, 3, 4, 3); workflow.setSpacing(4)
        self.scan_btn = QPushButton('1. Skanuj foldery'); self.scan_btn.setObjectName('Primary'); self.scan_btn.clicked.connect(self._scan_button_clicked)
        self.identify_btn = QPushButton('2. Rozpoznaj utwory online'); self.identify_btn.setObjectName('IdentifyOnlineAction'); self.identify_btn.clicked.connect(self._identify_button_clicked)
        self.review_btn = QPushButton('3. Sprawdź w Bibliotece'); self.review_btn.setObjectName('ReviewAction'); self.review_btn.clicked.connect(self._check_library_clicked)
        self.export_btn = QPushButton('4. Utwórz pliki wynikowe'); self.export_btn.setObjectName('ExportAction'); self.export_btn.clicked.connect(self.export_library)
        step_arrow_1 = _icon_label('chevron-right', '#6d7c88', 15); step_arrow_1.setObjectName('WorkflowStepArrow')
        step_arrow_2 = _icon_label('chevron-right', '#6d7c88', 15); step_arrow_2.setObjectName('WorkflowStepArrow')
        step_arrow_3 = _icon_label('chevron-right', '#6d7c88', 15); step_arrow_3.setObjectName('WorkflowStepArrow')
        workflow.addWidget(self.scan_btn); workflow.addWidget(step_arrow_1); workflow.addWidget(self.identify_btn); workflow.addWidget(step_arrow_2); workflow.addWidget(self.review_btn); workflow.addWidget(step_arrow_3); workflow.addWidget(self.export_btn)
        action.addWidget(workflow_group)

        workflow_separator = QFrame(); workflow_separator.setObjectName('WorkflowToolbarSeparator'); workflow_separator.setFixedWidth(1); workflow_separator.setMinimumHeight(32)
        action.addWidget(workflow_separator)
        self.action_icon_ids = [
            (self.scan_btn, 'scan'),
            (self.identify_btn, 'search'),
            (self.review_btn, 'review'),
            (self.export_btn, 'export'),
        ]
        self.action_icon_colors = {
            self.scan_btn: '#dbe8e2',
            self.identify_btn: '#dbe8e2',
            self.review_btn: '#dbe8e2',
            self.export_btn: '#dbe8e2',
        }
        self.action_visual_roles = {
            self.scan_btn: 'scan',
            self.identify_btn: 'identify',
            self.review_btn: 'review',
            self.export_btn: 'export',
        }
        for button, icon_name in self.action_icon_ids:
            button.setIcon(start_icon(icon_name, self.action_icon_colors[button], 23))
            button.setIconSize(QSize(23, 23))
            self._apply_workflow_button_style(button, active=False)

        self.scan_btn.setToolTip('Odczytaj tagi, długość, jakość, BPM i fingerprint')
        self.identify_btn.setToolTip('Uzupełnij dane z MusicBrainz i Apple/iTunes oraz opcjonalnie AcoustID i Discogs')
        self.review_btn.setToolTip('Sprawdź metadane, okładki i duplikaty przed utworzeniem plików')
        self.export_btn.setToolTip('Utwórz kopie w bibliotece docelowej i wykonaj techniczną kontrolę kopii')
        self.action_buttons = [self.scan_btn, self.identify_btn, self.review_btn, self.export_btn]
        self.operation_frame = QFrame(); self.operation_frame.setObjectName('OperationFrame'); self.operation_frame.setProperty('operationKind', 'idle')
        self.operation_frame.setParent(self.action_frame)
        self.operation_frame.setMinimumWidth(410)
        self.operation_frame.setMaximumWidth(460)
        op = QVBoxLayout(self.operation_frame); op.setContentsMargins(8, 4, 8, 4); op.setSpacing(1)
        op_head = QHBoxLayout(); op_head.setSpacing(3)
        self.operation_icon = QLabel(); self.operation_icon.setObjectName('OperationIcon'); self.operation_icon.setFixedSize(19, 19); self.operation_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); self.operation_icon.setPixmap(start_icon('status_ring', '#8fa1b3', 17).pixmap(17, 17)); op_head.addWidget(self.operation_icon)
        op_title = QLabel('BIEŻĄCA OPERACJA'); op_title.setObjectName('OperationHeading'); op_head.addWidget(op_title)
        self.operation_state_icon = QLabel(); self.operation_state_icon.setObjectName('OperationStateIcon'); self.operation_state_icon.setFixedSize(19, 19); self.operation_state_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); self.operation_state_icon.setPixmap(start_icon('check_circle', '#67e495', 17).pixmap(17, 17)); op_head.addWidget(self.operation_state_icon)
        self.operation_title = QLabel('GOTOWY'); self.operation_title.setObjectName('OperationKindTitle'); op_head.addWidget(self.operation_title)
        self.adoption_btn = QToolButton(self.operation_frame)
        self.adoption_btn.setText('Przypisz wynik…'); self.adoption_btn.hide()
        self.adoption_btn.clicked.connect(self._open_legacy_adoption)
        op_head.addStretch(1); op_head.addWidget(self.adoption_btn); op.addLayout(op_head)
        self.operation_status = QLabel('Wybierz etap pracy'); self.operation_status.setObjectName('OperationStatus')
        self.operation_status.setWordWrap(False); self.operation_status.setToolTip(self.operation_status.text()); op.addWidget(self.operation_status)
        self.progress = QProgressBar(); self.progress.setObjectName('StartOperationProgress'); self.progress.setRange(0, 1); self.progress.setValue(1); self.progress.setVisible(False); op.addWidget(self.progress)
        action.addSpacing(30)
        action.addStretch(2)
        action.addWidget(self.operation_frame, 1)
        action.addSpacing(10)
        action.addStretch(1)
        outer.addWidget(self.action_frame)

        content = QFrame(); content.setObjectName('ContentArea')
        content_lay = QVBoxLayout(content); content_lay.setContentsMargins(16, 12, 16, 8)
        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(self.app_settings)
        self.dashboard.set_library_name(self.library_registry.active.name)
        self.dashboard.refresh_requested.connect(self.start_scan)
        if hasattr(self.dashboard, 'sources'):
            self.new_files_btn = self.dashboard.sources.add_button
            self.dashboard.context_refresh_requested.connect(self._refresh_start_context)
        else:
            self.new_files_btn = QPushButton('+ Dodaj źródło', self.dashboard)
            self.new_files_btn.hide()
        self.new_files_btn.clicked.connect(self._add_new_files)
        self.player = PlayerBar()
        self.player.track_activated.connect(self._activate_player_track)
        self.library = LibraryPage()
        self.player.track_changed.connect(self.library.set_playing_track)
        self.library.play_requested.connect(lambda track: self.player.load_track(track, autoplay=True, source_label='Biblioteka'))
        self.library.queue_next_requested.connect(lambda track: self.player.queue_next(track, source_label='Biblioteka'))
        self.library.manual_field_requested.connect(self._apply_manual_field)
        self.library.edit_requested.connect(self._edit_metadata)
        self.library.approve_requested.connect(self._approve_track)
        self.library.review_requested.connect(lambda track: self._set_ready_from_editor(track, False))
        self.library.context_notice.connect(self._show_operation)
        self.library.set_context_provider(self._library_context_snapshot,
                                          worker_reader=self._library_context_reader)
        self.library.context_playlist_requested.connect(self._export_context_playlist)
        self.library.context_collection_requested.connect(self._create_context_collection)
        self.library.undo_requested.connect(self._undo_last_change)
        self.library.create_collection_requested.connect(self._create_collection_from_tracks)
        self.library.playlist_requested.connect(self._export_playlist)
        self.library.set_history_provider(self.change_history.history_for)
        self.duplicates = DuplicatesPage(self.player); self.duplicates.decision_requested.connect(self._duplicate_decision); self.duplicates.edit_track_requested.connect(self._edit_duplicate_track)
        self.collections = CollectionsPage(self._collections_library_for_active())
        self.collections.add_from_library_requested.connect(lambda: self._navigate(1))
        self.collections.play_requested.connect(lambda track: self.player.load_track(track, autoplay=True, source_label='Foldery z zaznaczonych utworów'))
        self.collections.playlist_requested.connect(self._export_playlist)
        self.help = HelpCenter(); self.settings_page = SettingsPage(self.main_settings, qt_settings)
        self.settings_page.help_requested.connect(self._open_help_topic)
        self.settings_page.provider_saved.connect(self._settings_saved)
        self.settings_page.preferences_saved.connect(self._apply_preferences)
        self.settings_page.manage_libraries_requested.connect(self._open_library_manager)
        self.settings_page.change_library_location_requested.connect(self._change_main_library_location)
        self.settings_page.backup_requested.connect(self._create_backup)
        self.settings_page.restore_backup_requested.connect(self._restore_backup)
        self.settings_page.full_reset_requested.connect(self._reset_alo_to_clean_state)
        for page in (self.dashboard, self.library, self.duplicates, self.collections, self.help, self.settings_page): self.stack.addWidget(page)
        content_lay.addWidget(self.stack, 1); outer.addWidget(content, 1); outer.addWidget(self.player)
        self._apply_preferences(self.preferences)
        self._update_library_nav_action()
        self._navigate(0); self.refresh_data()

    def _t(self, text: str) -> str:
        return ui_text(self, text)

    def _collections_library_for_active(self):
        return self.app_settings.library

    def _update_library_nav_action(self):
        profile = self.library_registry.active
        self.manage_libraries_nav.setText(tr('library.manage', self.preferences.language))
        destination = profile.library_root
        tip = 'Manage libraries' if self.preferences.language == 'en' else 'Zarządzaj bibliotekami'
        self.manage_libraries_nav.setToolTip(f'{self._t(profile.name)}\n{destination}\n{tip}')

    def _apply_preferences(self, prefs: AppPreferences):
        self.preferences = AppPreferences(
            language=prefs.language,
            theme='dark',
            normalize_names=prefs.normalize_names,
            name_rules=prefs.name_rules,
        )
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(style_for_theme('dark'))
        apply_static_language(self, self.preferences.language)
        nav_keys = ('nav.start', 'nav.library', 'nav.duplicates', 'nav.collections', 'nav.help', 'nav.settings')
        for button, key in zip(self.nav_buttons, nav_keys):
            button.setText(tr(key, self.preferences.language))
        if self._thread is None:
            self._refresh_workflow_button_texts()
        self._update_library_nav_action()
        apply_static_language(self.settings_page, self.preferences.language)
        for page in (self.dashboard, self.library, self.duplicates, self.collections):
            apply_static_language(page, self.preferences.language)
        if hasattr(self.dashboard, 'refresh_language'):
            self.dashboard.refresh_language()
        self._refresh_start_context()
        self.help.set_language(self.preferences.language)
        self.player.refresh_language()
        if hasattr(self, '_last_ui_summary'):
            self.dashboard.set_summary(self._last_ui_summary)
            self.dashboard.set_health(self._last_ui_health)
        self.library.refresh(preserve_order=True)
        self.duplicates.set_tracks(self.library._tracks)
        if hasattr(self, '_operation_source'):
            kind, title, detail = self._operation_source
            status_source = getattr(self, '_operation_status_source', None)
            self._set_operation_state(kind, title, detail)
            if status_source is not None:
                self._show_operation(status_source)

    def _open_library_manager(self):
        dialog = LibraryManagerDialog(self.library_registry, self)
        self._library_manager = dialog
        dialog.activate_requested.connect(self._activate_library_profile)
        dialog.registry_changed.connect(self._library_registry_changed)
        dialog.restart_requested.connect(self._restart_library_profile)
        apply_static_language(dialog, self.preferences.language)
        dialog.exec()
        self._library_manager = None

    def _change_main_library_location(self):
        """Point the main profile at a validated folder without moving old data."""
        if self._thread is not None:
            QMessageBox.warning(self, self._t('Operacja w toku'), self._t('Najpierw zakończ bieżącą operację.'))
            return
        folder = QFileDialog.getExistingDirectory(
            self,
            self._t('Wybierz nową lokalizację biblioteki'),
            str(self.main_settings.library.root),
        )
        if not folder:
            return
        new_root = Path(folder).expanduser().resolve()
        if new_root == self.main_settings.library.root:
            return
        try:
            updated = AppSettings(self.main_settings.source_dirs, LibraryPaths(new_root))
            self.library_registry.validate_database_location(new_root, exclude_profile_id='main')
            for profile in self.library_registry.profiles:
                if profile.kind == 'library':
                    profile_root = Path(profile.library_root).resolve()
                    if new_root == profile_root or profile_root in new_root.parents or new_root in profile_root.parents:
                        raise ValueError(self._t('Wybrana lokalizacja koliduje z inną biblioteką ALO.'))
                for source_dir in profile.source_dirs:
                    source_root = Path(source_dir).resolve()
                    if new_root == source_root or source_root in new_root.parents or new_root in source_root.parents:
                        raise ValueError(self._t('Wybrana lokalizacja koliduje ze źródłem skanowania ALO.'))
        except ValueError as exc:
            QMessageBox.warning(self, self._t('Nieprawidłowy folder'), self._t(str(exc)))
            return

        confirmation = QMessageBox.question(
            self,
            self._t('Zmienić lokalizację biblioteki?'),
            (
                f'{self._t("ALO przełączy Bibliotekę główną na wybrany folder:")}\n\n'
                f'{new_root}\n\n'
                f'{self._t("Ta operacja nie przenosi ani nie usuwa plików z dotychczasowej lokalizacji. ")}'
                f'{self._t("Jeśli chcesz zachować tamte dane w nowym miejscu, skopiuj je osobno przed przełączeniem.")}'
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            updated.library.ensure_created()
            candidate_repository = LibraryRepository(updated.library.database)
            candidate_repository.initialize()
            candidate_availability = candidate_repository.sync_availability()
        except (OSError, ValueError, sqlite3.Error, MigrationError) as exc:
            QMessageBox.warning(self, self._t('Nie można użyć lokalizacji biblioteki'), self._t(str(exc)))
            return

        self.library_registry.update_main_settings(updated)
        self.main_settings = self.library_registry.main_settings
        save_app_settings(self.qt_settings, self.main_settings)
        self.library_registry.save(self.qt_settings)
        self.settings_page.refresh_main_settings(self.main_settings)
        apply_static_language(self.settings_page, self.preferences.language)
        if self.library_registry.active.profile_id == 'main':
            self._rebind_active_profile(
                self.library_registry.active,
                repository=candidate_repository,
                availability=candidate_availability,
            )
        self._show_operation('Zmieniono lokalizację biblioteki głównej.')

    def _library_registry_changed(self):
        self.library_registry.save(self.qt_settings)
        self.settings_page.refresh_main_settings(self.library_registry.main_settings)
        apply_static_language(self.settings_page, self.preferences.language)

    def _reset_alo_to_clean_state(self):
        if self._thread is not None:
            QMessageBox.warning(self, self._t('Operacja w toku'), self._t('Najpierw zakończ bieżącą operację.'))
            return
        if self.preferences.language == 'en':
            text = (
                'Reset ALO to a clean state?\n\n'
                'This removes registered libraries, ALO databases, scan history and saved settings.\n'
                'Music files on disk will NOT be deleted.\n\n'
                'After restart ALO will behave like a fresh installation.'
            )
            title = 'Reset ALO'
        else:
            text = (
                'Zresetować ALO do czystego stanu?\n\n'
                'Zostaną usunięte zapisane biblioteki, bazy ALO, historia skanowania i ustawienia programu.\n'
                'Pliki muzyczne na dysku NIE zostaną usunięte.\n\n'
                'Po ponownym uruchomieniu ALO zachowa się jak świeża instalacja.'
            )
            title = 'Resetuj ALO do czystego stanu'
        answer = QMessageBox.question(
            self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = reset_alo_state(self.qt_settings, self.main_settings, self.library_registry)
        if getattr(self, '_library_manager', None) is not None:
            self._library_manager.accept()
            self._library_manager = None
        message = (
            f'ALO has been reset. Removed {result.databases_removed} local database(s).\n\n'
            'Music files were not changed. Start ALO again to choose a language and create a library.'
            if self.preferences.language == 'en' else
            f'ALO zostało zresetowane. Usunięto {result.databases_removed} lokalne bazy.\n\n'
            'Pliki muzyczne nie zostały zmienione. Uruchom ALO ponownie, aby wybrać język i utworzyć bibliotekę.'
        )
        QMessageBox.information(self, title, message)
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _activate_library_profile(self, profile_id: str):
        if self._thread is not None:
            QMessageBox.warning(self, self._t('Operacja w toku'), self._t('Najpierw zakończ bieżącą operację.'))
            return
        editor = getattr(self, '_active_metadata_editor', None)
        if editor is not None and editor.has_unsaved_changes():
            QMessageBox.warning(
                self,
                self._t('Niezapisane zmiany'),
                self._t('Najpierw zapisz lub odrzuć zmiany w otwartym edytorze metadanych.'),
            )
            return
        try:
            profile = self.library_registry.activate(profile_id)
        except KeyError:
            return
        except (OSError, ValueError, sqlite3.Error, MigrationError) as exc:
            QMessageBox.warning(self, self._t('Nie można użyć lokalizacji biblioteki'), self._t(str(exc)))
            return
        self.library_registry.save(self.qt_settings)
        self._rebind_active_profile(profile)
        if getattr(self, '_library_manager', None) is not None:
            self._library_manager.refresh()
            apply_static_language(self._library_manager, self.preferences.language)

    def _restart_library_profile(self, profile_id: str):
        if profile_id != self.library_registry.active.profile_id:
            return
        profile = self.library_registry.find(profile_id)
        if profile is None:
            return
        self._rebind_active_profile(profile)
        self._show_operation(f'Biblioteka „{profile.name}” została wyzerowana. Możesz dodać nowe pliki do skanowania.')

    def _rebind_active_profile(self, profile, *, repository=None, availability=None):
        self._invalidate_output_states()
        self._identification_generation += 1
        if isinstance(self._worker, (IdentificationWorker, AudioIdentificationWorker)):
            self._worker.cancel()
        self._file_check_generation += 1
        if isinstance(self._worker, FileReconciliationWorker):
            self._worker.cancel()
        self._file_check_context = None
        self.last_reconciliation_result = None
        self.adoption_btn.hide()
        self._adoption_view_context = None
        if self._adoption_dialog is not None:
            self._adoption_dialog.close()
            self._adoption_dialog = None
        self.app_settings = self.library_registry.settings_for(profile)
        if repository is None:
            repository = LibraryRepository(self.app_settings.library.database)
            repository.initialize()
        self.repository = repository
        self.availability = self.repository.sync_availability() if availability is None else availability
        self.service = LibraryService(self.app_settings, self.repository)
        self.change_history = ChangeHistory(library_id=self.repository.library_id)
        self.library.set_history_provider(self.change_history.history_for)
        self.dashboard.set_library(self.app_settings, profile.name)
        self.collections.set_library(self._collections_library_for_active())
        self._update_library_nav_action()
        self.refresh_data()
        self._show_operation(f'Aktywna biblioteka: {profile.name}')

    def _export_playlist(self, paths):
        selected_count = len(paths or [])
        paths = [Path(p) for p in (paths or []) if Path(p).is_file()]
        if not paths:
            QMessageBox.information(self, self._t('Brak plików'), self._t('Nie ma plików do zapisania w playliście.'))
            return
        base = self._collections_library_for_active().custom_folders
        default = base / 'playlista.m3u8'
        dialog = CreationNameDialog('playlist', selected_count, self, initial_target=default, available_count=len(paths))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target = dialog.target_path()
        if target.suffix.lower() != '.m3u8':
            target = target.with_suffix('.m3u8')
        try:
            result = write_m3u8(target, paths, relative=True)
        except OSError as exc:
            QMessageBox.critical(self, self._t('Nie można zapisać playlisty'), self._t(str(exc))); return
        self._show_operation(f'Utworzono playlistę: {result.name}')
        CreationResultDialog('playlist', result.stem, len(paths), result, self).exec()

    def _export_context_playlist(self, request):
        token, paths = request
        if self.library._context_tracks(token) is None or not paths:
            return
        default = self.app_settings.library.custom_folders / 'playlista.m3u8'
        dialog = CreationNameDialog('playlist', len(paths), self, initial_target=default)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target = dialog.target_path()
        if target.suffix.lower() != '.m3u8':
            target = target.with_suffix('.m3u8')
        # The dialog is not an authorization cache: recheck on the worker again.
        self.library.run_context_command(token, 'playlist', (str(target),), self._context_playlist_written)

    def _context_playlist_written(self, result, error):
        if error:
            QMessageBox.critical(self, self._t('Nie można zapisać playlisty'), self._t(error))
            return
        path, count = result
        self._show_operation(f'Utworzono playlistę: {path.name}')
        CreationResultDialog('playlist', path.stem, count, path, self).exec()

    def _create_context_collection(self, request):
        token, tracks = request
        if self.library._context_tracks(token) is None or not tracks:
            return
        dialog = CreationNameDialog('folder', len(tracks), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name_edit.text()
        if not name.strip():
            return
        self.library.run_context_command(token, 'collection', (self.app_settings.library, name.strip()),
                                         self._context_collection_planned)

    def _context_collection_planned(self, plan, error):
        if error:
            QMessageBox.warning(self, self._t('Nie można utworzyć folderu'), self._t(error))
            return
        if not plan.items or self._thread is not None:
            return
        self._start_collection_plan(plan)

    def _backup_settings_payload(self) -> dict[str, object]:
        return {
            'version': __version__,
            'language': self.preferences.language,
            'theme': self.preferences.theme,
            'normalize_names': self.preferences.normalize_names,
            'name_rules': [rule.to_dict() for rule in self.preferences.name_rules],
            'main_source_dirs': [str(p) for p in self.main_settings.source_dirs],
            'main_library_root': str(self.main_settings.library.root),
            'profiles': [p.to_dict() for p in self.library_registry.profiles if p.kind == 'library'],
        }

    def _create_backup(self):
        default = self.main_settings.library.reports / f'ALO_backup_{datetime.now():%Y%m%d_%H%M%S}.alo-backup.zip'
        filename, _ = QFileDialog.getSaveFileName(self, self._t('Utwórz kopię bezpieczeństwa ALO'), str(default), self._t('Kopia ALO (*.zip)'))
        if not filename:
            return
        try:
            profile_databases = {
                profile.profile_id: Path(profile.library_root) / '.alo' / 'library.sqlite3'
                for profile in self.library_registry.profiles if profile.kind == 'library'
            }
            target = create_alo_backup(
                Path(filename), database_path=self.main_settings.library.database,
                settings_payload=self._backup_settings_payload(), profile_databases=profile_databases,
            )
        except OSError as exc:
            QMessageBox.critical(self, self._t('Błąd kopii bezpieczeństwa'), self._t(str(exc))); return
        QMessageBox.information(self, self._t('Kopia utworzona'), self._t(f'Zapisano kopię ALO bez plików muzycznych:\n{target}'))

    def _restore_backup(self):
        filename, _ = QFileDialog.getOpenFileName(self, self._t('Wybierz kopię bezpieczeństwa ALO'), str(self.main_settings.library.reports), self._t('Kopia ALO (*.zip)'))
        if not filename:
            return
        path = Path(filename)
        try:
            info = inspect_alo_backup(path)
        except Exception as exc:
            QMessageBox.critical(self, self._t('Nieprawidłowa kopia'), self._t(str(exc))); return
        answer = QMessageBox.question(
            self, self._t('Przywróć bazę ALO'),
            self._t('Przywrócenie zastąpi bazę Biblioteki głównej danymi z kopii. Pliki muzyczne nie zostaną zmienione. Kontynuować?'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            restore_database_from_backup(path, self.main_settings.library.database)
        except Exception as exc:
            QMessageBox.critical(self, self._t('Nie można przywrócić kopii'), self._t(str(exc))); return
        settings = info.get('settings') if isinstance(info, dict) else None
        if isinstance(settings, dict):
            language = str(settings.get('language') or self.preferences.language)
            theme = str(settings.get('theme') or self.preferences.theme)
            raw_rules = settings.get('name_rules') or []
            rules = tuple(NameNormalizationRule.from_dict(item) for item in raw_rules if isinstance(item, dict)) or self.preferences.name_rules
            prefs = AppPreferences(language=language, theme=theme, normalize_names=bool(settings.get('normalize_names', True)), name_rules=rules)
            prefs.save(self.qt_settings); self._apply_preferences(prefs)
            profiles = [item for item in (settings.get('profiles') or []) if isinstance(item, dict)]
            if profiles:
                self.qt_settings.setValue('libraries/profiles', json.dumps(profiles, ensure_ascii=False))
                self.qt_settings.setValue('libraries/active', 'main')
                destinations = {
                    str(item.get('profile_id')): Path(str(item.get('library_root'))) / '.alo' / 'library.sqlite3'
                    for item in profiles if item.get('profile_id') and item.get('library_root')
                }
                restore_profile_databases_from_backup(path, destinations)
                self.library_registry = LibraryRegistry.from_store(self.qt_settings, self.main_settings)
        self.library_registry.activate('main')
        self._rebind_active_profile(self.library_registry.active)
        QMessageBox.information(self, self._t('Kopia przywrócona'), self._t('Przywrócono bazę Biblioteki głównej, dostępne bazy profili i ustawienia z kopii. Pliki muzyczne pozostały bez zmian.'))

    def _set_operation_state(self, kind: str, title: str, detail: str = ''):
        self._operation_source = (kind, title, detail)
        icons = {
            'idle': ('check_circle', '#67e495'), 'scan': ('spinner', '#55dca0'),
            'online': ('spinner', '#55dca0'), 'review': ('spinner', '#55dca0'),
            'export': ('spinner', '#55dca0'), 'done': ('check_circle', '#67e495'),
            'error': ('warning', '#ff6b6b'),
        }
        self._operation_kind = kind
        icon_name, icon_color = icons.get(kind, icons['idle'])
        self.operation_state_icon.setPixmap(start_icon(icon_name, icon_color, 17).pixmap(17, 17))
        self.operation_title.setText(self._t(title))
        if detail:
            self._operation_status_source = detail
            self.operation_status.setText(self._t(detail))
            self.operation_status.setToolTip(self.operation_status.text())
        self.operation_frame.setProperty('operationKind', kind)
        self.operation_frame.style().unpolish(self.operation_frame)
        self.operation_frame.style().polish(self.operation_frame)
        self.operation_frame.update()

    def _set_button_running(self, button: QPushButton, running: bool):
        button.setProperty('running', running)
        button.style().unpolish(button); button.style().polish(button); button.update()

    def _scan_button_clicked(self):
        if self._thread is not None:
            if self._operation_kind == 'scan':
                self.cancel_current_scan()
            return
        if not self.app_settings.source_dirs:
            self._add_new_files()
            return
        self.start_scan()

    def _identify_button_clicked(self):
        if self._thread is not None:
            if self._operation_kind == 'online':
                self.cancel_current_identification()
            return
        self.start_identification()

    def _add_new_files(self):
        if self._thread is not None:
            return
        profile = self.library_registry.active
        folder = QFileDialog.getExistingDirectory(
            self, self._t('Wybierz folder z nowymi plikami'),
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not folder:
            return
        source = Path(folder).resolve()
        try:
            updated_profile = self.library_registry.add_source_dir(profile.profile_id, source)
            updated = self.library_registry.settings_for(updated_profile)
        except ValueError as exc:
            QMessageBox.warning(self, self._t('Nieprawidłowy folder'), self._t(str(exc))); return
        self.app_settings = updated
        self.service.settings = updated
        self.library_registry.save(self.qt_settings)
        if updated_profile.kind == 'main':
            self.main_settings = updated
            save_app_settings(self.qt_settings, updated)
            self.settings_page.refresh_main_settings(updated)
            apply_static_language(self.settings_page, self.preferences.language)
        if getattr(self, '_library_manager', None) is not None:
            self._library_manager.refresh()
        self.start_scan(source_dirs=(source,), new_files=True)

    def _navigate(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons): button.setChecked(i == index)
        if self._thread is None:
            self._set_action_highlight(self.review_btn if index == 1 else None)

    def _workflow_button_style(self, role: str, active: bool = False) -> str:
        bg = '#102b21' if active else '#0c1920'
        border = '#42d992' if active else '#315048'
        return (
            'QPushButton {'
            f'background:{bg}; border:1px solid {border}; color:#eef7f2;'
            'border-radius:8px; min-height:36px; padding:6px 10px; font-weight:750;'
            '}'
            'QPushButton:hover {'
            'background:#173428; border:1px solid #51e59e; color:#ffffff;'
            '}'
            'QPushButton:pressed {'
            'background:#1c4530; border:1px solid #57e6a2;'
            '}'
            'QPushButton:disabled {'
            'background:#111820; border:1px solid #27343d; color:#65737d;'
            '}'
        )

    @staticmethod
    def _workflow_cancel_style() -> str:
        return (
            'QPushButton {'
            'background:#32181c; border:1px solid #e45f68; color:#ffe4e6;'
            'border-radius:9px; min-height:32px; padding:9px 18px; font-weight:800;'
            '}'
            'QPushButton:hover {'
            'background:#4a1c22; border:1px solid #ff7b84; color:#ffffff;'
            '}'
            'QPushButton:pressed {'
            'background:#541d24; border:1px solid #ff8b93; color:#ffffff;'
            '}'
            'QPushButton:disabled {'
            'background:#2b171a; border:1px solid #a94850; color:#d9a8ac;'
            '}'
        )

    def _apply_workflow_button_style(self, button, *, active: bool) -> None:
        if button.objectName() in {'CancelScanAction', 'CancelOnlineAction'}:
            button.setStyleSheet(self._workflow_cancel_style())
        else:
            role = self.action_visual_roles.get(button, 'identify')
            button.setStyleSheet(self._workflow_button_style(role, active=active))

    def _set_action_highlight(self, active_button=None):
        icon_lookup = dict(self.action_icon_ids)
        for button in self.action_buttons:
            active = button is active_button
            button.setProperty('operationActive', active)
            icon_name = icon_lookup.get(button)
            if icon_name is not None:
                base = '#4de398' if active else self.action_icon_colors.get(button, '#c7d2da')
                button.setIcon(start_icon(icon_name, base, 23))
            self._apply_workflow_button_style(button, active=active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _open_review(self):
        if self._thread is None:
            self._set_action_highlight(self.review_btn)
            self._set_operation_state('review', 'WERYFIKACJA W BIBLIOTECE', 'Sprawdź utwory oznaczone jako DO SPRAWDZENIA.')
        self._navigate(1)

    def _check_library_clicked(self):
        """Only an explicit button click starts disk checks; review stays intact."""
        if isinstance(self._worker, FileReconciliationWorker):
            self._worker.cancel()
            return
        self._open_review()
        if self._thread is not None or self._file_check_closing:
            return
        self._invalidate_output_states()
        library_id = self.library_registry.active.library_id
        operation_id = str(uuid4())
        self._file_check_generation += 1
        self._file_check_context = (library_id, operation_id, self._file_check_generation)
        self._file_check_repository = self.repository
        self.last_reconciliation_result = None
        self.adoption_btn.hide()
        if self._adoption_dialog is not None:
            self._adoption_dialog.close()
            self._adoption_dialog = None
        self._pending_auto_identify = False
        paths = self.app_settings.library
        from audio_library_organizer.jobs.output_session import OutputCheckOperation, output_policy
        selected = self.library._selected_tracks()
        self._output_operation = OutputCheckOperation(library_id, operation_id,
            self._file_check_generation, output_policy(ProviderSettings.from_store(self.qt_settings)),
            selected[0].track_id if len(selected) == 1 else None)
        thread = QThread(self)
        worker = FileReconciliationWorker(self.repository, library_id=library_id,
            operation_id=operation_id, managed_roots=(paths.ready, paths.review, paths.not_selected),
            library_root=paths.root, known_libraries=self._known_adoption_libraries(),
            output_operation=self._output_operation)
        worker.moveToThread(thread)
        self._thread, self._worker = thread, worker
        self._set_operation_state('review', 'WERYFIKACJA W BIBLIOTECE', 'Sprawdzanie plików…')
        self._set_busy(True, kind='check')
        self.review_btn.setText('Cancel check' if self.preferences.language == 'en' else 'Anuluj sprawdzanie')
        thread.started.connect(worker.run)
        worker.progress.connect(self._file_check_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._file_check_finished, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._file_check_failed, Qt.ConnectionType.QueuedConnection)
        # quit() is thread-safe; shutdown must not depend on GUI event dispatch.
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._file_check_thread_done)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _file_check_matches(self, library_id, operation_id):
        return (not self._file_check_closing and self._file_check_context ==
                (library_id, operation_id, self._file_check_generation)
                and self._file_check_repository is self.repository
                and library_id == self.library_registry.active.library_id)

    @Slot(str, str, int, int, str)
    def _file_check_progress(self, library_id, operation_id, current, total, name):
        if not self._file_check_matches(library_id, operation_id):
            return
        self.progress.setRange(0, max(1, total)); self.progress.setValue(current)
        self._show_operation(f'Check {current}/{total}: {name}' if self.preferences.language == 'en'
                             else f'Sprawdzanie {current}/{total}: {name}')

    @Slot(object)
    def _file_check_finished(self, result):
        if not self._file_check_matches(result.library_id, result.operation_id):
            return
        self.last_reconciliation_result = result
        self._accept_output_delivery(result)
        summary = result.summary
        if self.preferences.language == 'en':
            text = (f'{"Check cancelled" if result.cancelled else "Check complete"}: '
                    f'{summary.present} present, {summary.missing} missing, {summary.offline} offline; '
                    f'{summary.new_sources} new candidates, {summary.possible_moves} possible moves. '
                    'Review metadata in the Library.')
        else:
            text = (f'{"Kontrola anulowana" if result.cancelled else "Kontrola zakończona"}: '
                    f'dostępne {summary.present}, brakujące {summary.missing}, offline {summary.offline}; '
                    f'nowi kandydaci {summary.new_sources}, możliwe przeniesienia {summary.possible_moves}. '
                    'Metadane możesz przeglądać w Bibliotece.')
        self._show_operation(text)
        inventory = result.adoption_inventory
        if inventory is not None and not result.cancelled and any(p.locator for p in inventory.proposals):
            self.adoption_btn.setText('Assign output…' if self.preferences.language == 'en' else 'Przypisz wynik…')
            self.adoption_btn.show()

    def _known_adoption_libraries(self):
        """Describe every configured profile without disk probes on the GUI thread."""
        return tuple(KnownLibrary(str(profile.library_root),
            str(profile.library_root / '.alo' / 'library.sqlite3'), profile.library_id)
            for profile in self.library_registry.profiles)

    def _invalidate_output_states(self, track_id=None):
        """Revoke only new session evidence; leave independent baseline states."""
        operation = self._output_operation
        request = operation.current_request() if operation is not None else None
        if operation is not None and (track_id is None or request is None or request.track_id == track_id):
            operation.invalidate()
        for tid in tuple(self._output_session):
            if track_id is None or tid == track_id:
                self._output_session.pop(tid)
        if not self._output_session:
            paths = self._output_watcher.files() + self._output_watcher.directories()
            if paths:
                self._output_watcher.removePaths(paths)
        if hasattr(self, 'library') and self._read_context is not None:
            merged = dict(self._output_baseline_evals)
            merged.update({tid: d.pending.evaluation for tid, d in self._output_session.items()})
            self.library.set_file_state_evaluations(self._read_context.library_id, merged)
            self.library.refresh(preserve_order=True)

    @Slot(str)
    def _output_watch_changed(self, path):
        # Additional invalidation, NEVER the acceptance-time identity proof.
        for tid, delivery in tuple(self._output_session.items()):
            material_paths = (delivery.source_locator, delivery.managed_locator,
                str(Path(delivery.source_locator).parent), str(Path(delivery.managed_locator).parent))
            if path in material_paths:
                self._invalidate_output_states(tid)
                continue
            database_paths = (str(self.repository.database_path.parent), *tuple(
                str(self.repository.database_path) + suffix for suffix in ('', '-wal', '-journal')))
            if path in database_paths:
                # SQLite's own cache/checkpoint/journal activity is not a
                # metadata edit. Keep evidence only after fresh validation.
                from audio_library_organizer.jobs.output_session import context_matches, material_matches, output_policy, database_safe
                operation = self._output_operation
                request = operation.current_request() if operation is not None else None
                try:
                    if not database_safe(delivery):
                        self._invalidate_output_states(tid)
                        continue
                    current = self.repository.adopted_assessment_snapshot(tid, timeout=0.0)
                    if (request is not None and request.generation == self._file_check_generation
                            and request.policy_revision == output_policy(ProviderSettings.from_store(self.qt_settings))
                            and context_matches(delivery, current, request) and material_matches(delivery)):
                        journals = [str(self.repository.database_path) + suffix for suffix in ('', '-wal', '-journal')]
                        missing = [p for p in journals if p not in self._output_watcher.files() and Path(p).exists()]
                        if not missing or not self._output_watcher.addPaths(missing):
                            continue
                except (sqlite3.Error, OSError, ValueError, RuntimeError):
                    pass
                self._invalidate_output_states(tid)
            elif path in delivery.watch_paths:
                self._invalidate_output_states(tid)

    def _accept_output_delivery(self, result):
        from audio_library_organizer.jobs.output_session import context_matches, material_matches, output_policy, database_safe
        delivery = result.output_delivery
        operation = self._output_operation
        if (delivery is None or operation is None or result.cancelled
                or delivery.root != str(self.app_settings.library.root)
                or delivery.database_locator != str(self.repository.database_path) or not database_safe(delivery)):
            return
        request = operation.current_request()
        if (request is None or request.generation != self._file_check_generation
                or request.policy_revision != output_policy(ProviderSettings.from_store(self.qt_settings))
                or not self._file_check_matches(request.library_id, request.operation_id)):
            return
        # Register first; then check actual local metadata, not a queued watcher.
        paths = delivery.watch_paths
        if self._output_watcher.addPaths(list(paths)):
            self._output_watcher.removePaths(self._output_watcher.files() + self._output_watcher.directories())
            return
        journals = [str(self.repository.database_path) + suffix for suffix in ('-wal', '-journal')]
        journals = [p for p in journals if Path(p).exists()]
        if journals and self._output_watcher.addPaths(journals):
            self._output_watcher.removePaths(self._output_watcher.files() + self._output_watcher.directories())
            return
        try:
            current = self.repository.adopted_assessment_snapshot(request.track_id, timeout=0.0)
            if not context_matches(delivery, current, request) or not material_matches(delivery):
                return
            self._output_session[request.track_id] = delivery
            self.refresh_data()
        except (sqlite3.Error, OSError, ValueError, RuntimeError):
            self._output_session.pop(request.track_id, None)
        finally:
            if not self._output_session:
                watches = self._output_watcher.files() + self._output_watcher.directories()
                if watches:
                    self._output_watcher.removePaths(watches)

    def _output_evaluations(self, snapshot):
        from audio_library_organizer.jobs.output_session import context_matches, material_matches, output_policy, database_safe
        from audio_library_organizer.storage.repository import AdoptedAssessmentSnapshot
        from audio_library_organizer.domain.file_state import FileState
        merged = dict(self._output_baseline_evals)
        tracks = {t.track_id: t for t in snapshot.tracks}
        policy = output_policy(ProviderSettings.from_store(self.qt_settings))
        operation = self._output_operation
        request = operation.current_request() if operation is not None else None
        for tid, delivery in tuple(self._output_session.items()):
            current = AdoptedAssessmentSnapshot(snapshot.library_id, tracks.get(tid),
                snapshot.sources, snapshot.managed_bindings)
            if (request is None or request.generation != self._file_check_generation
                    or request.policy_revision != policy or not context_matches(delivery, current, request)
                    or not database_safe(delivery) or not material_matches(delivery)):
                self._output_session.pop(tid)
                continue
            baseline = merged.get(tid)
            if baseline is None or baseline.state not in (FileState.CONFLICT, FileState.MANAGED_FILE_MISSING):
                merged[tid] = delivery.pending.evaluation
        return merged

    def _open_legacy_adoption(self):
        if self._thread is not None or self.last_reconciliation_result is None:
            return
        inventory = self.last_reconciliation_result.adoption_inventory
        if inventory is None or inventory.cancelled or inventory.library_id != self.library_registry.active.library_id:
            return
        if self._adoption_dialog is not None:
            self._adoption_dialog.close()
        self._adoption_view_context = (inventory.library_id, self._file_check_generation, self.repository,
                                      str(self.app_settings.library.root), self._known_adoption_libraries())
        dialog = LegacyAdoptionDialog(inventory, self, language=self.preferences.language)
        self._adoption_dialog = dialog
        dialog.approve_requested.connect(self._start_legacy_adoption)
        dialog.open()

    @Slot(str)
    def _start_legacy_adoption(self, proposal_id):
        context = self._adoption_view_context
        dialog = self._adoption_dialog
        if (self._thread is not None or context is None or dialog is None or self._file_check_closing
                or context[:4] != (self.library_registry.active.library_id, self._file_check_generation,
                                  self.repository, str(self.app_settings.library.root))
                or context[4] != self._known_adoption_libraries()
                or self.last_reconciliation_result is None
                or dialog.inventory is not self.last_reconciliation_result.adoption_inventory):
            return
        proposal = next((p for p in dialog.inventory.proposals if p.proposal_id == proposal_id), None)
        if proposal is None or not proposal.can_adopt:
            return
        operation_id = str(uuid4())
        self._file_check_generation += 1
        self._file_check_context = (context[0], operation_id, self._file_check_generation)
        self._file_check_repository = self.repository
        thread = QThread(self)
        worker = LegacyAdoptionWorker(self.repository, proposal_id=proposal_id, library_id=context[0],
            operation_id=operation_id, library_root=context[3], known_libraries=context[4])
        worker.moveToThread(thread)
        self._thread, self._worker = thread, worker
        self._set_busy(True, kind='check')
        self.adoption_btn.setEnabled(False)
        thread.started.connect(worker.adopt)
        worker.finished.connect(self._legacy_adoption_finished, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._file_check_failed, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._file_check_thread_done)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(object)
    def _legacy_adoption_finished(self, result):
        if not self._file_check_matches(result.library_id, result.operation_id):
            return
        self.last_reconciliation_result = None
        self._adoption_view_context = None
        self.adoption_btn.hide()
        if self._adoption_dialog is not None:
            self._adoption_dialog.close()
            self._adoption_dialog = None
        self.refresh_data()
        self._show_operation('Output assignment saved. Music unchanged.' if self.preferences.language == 'en'
                             else 'Zapisano przypisanie pliku wynikowego. Muzyka pozostała nietknięta.')

    @Slot(str, str, str)
    def _file_check_failed(self, library_id, operation_id, message):
        if self._file_check_matches(library_id, operation_id):
            self._show_operation(message)
            if self._adoption_dialog is not None:
                self._adoption_dialog.operation_failed(message)

    @Slot()
    def _file_check_thread_done(self):
        # finished precedes the thread's deferred-delete cleanup. Releasing a
        # Python-owned worker before that cleanup can delete it from the GUI.
        if self._thread is not None:
            self._thread.wait()
        self._thread = None; self._worker = None
        self._file_check_context = None; self._file_check_repository = None
        if self._file_check_closing:
            self.close()
            return
        self._set_busy(False)
        self.adoption_btn.setEnabled(True)
        self._set_action_highlight(self.review_btn if self.stack.currentIndex() == 1 else None)

    @Slot()
    def _stop_file_check_on_quit(self):
        if isinstance(self._worker, (IdentificationWorker, AudioIdentificationWorker)):
            self._identification_closing = True
            self._identification_generation += 1
            self._worker.cancel()
            self._thread.quit()
            self._thread.wait()
        if isinstance(self._worker, FileReconciliationWorker):
            self._file_check_closing = True
            self._file_check_generation += 1
            self._worker.cancel()
            self._thread.quit()
            self._thread.wait()

    def _open_help_topic(self, title: str):
        self._navigate(4)
        self.help.show_topic(title)

    def _settings_saved(self):
        self._invalidate_output_states()
        self.refresh_data()

    def _activate_player_track(self, track):
        self._navigate(1)
        self._select_saved_track(track)

    def _select_saved_track(self, track):
        if track.track_id:
            self.library.select_track(track)
        else:
            self.library.select_track_by_path(track.path)

    def _create_collection_from_tracks(self, tracks):
        available = [track for track in tracks if track.is_available and Path(track.path).is_file()]
        if not available:
            QMessageBox.warning(self, self._t('Brak dostępnych plików'), self._t('Żaden z zaznaczonych plików nie jest obecnie dostępny.'))
            return
        dialog = CreationNameDialog('folder', len(tracks), self, available_count=len(available))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name_edit.text()
        if not name.strip():
            return
        try:
            plan = build_collection_plan(self._collections_library_for_active(), name.strip(), available)
        except ValueError as exc:
            QMessageBox.warning(self, self._t('Nie można utworzyć folderu'), self._t(str(exc))); return
        if self._thread is not None:
            return
        self._start_collection_plan(plan)

    def _start_collection_plan(self, plan):
        if not plan.items:
            QMessageBox.warning(self, self._t('Brak dostępnych plików'), self._t('Żaden z zaznaczonych plików nie jest obecnie dostępny.'))
            return
        self._collection_dialog_target = (plan.items[0].destination_dir, len(plan.items))
        self._set_operation_state('export', 'TWORZENIE FOLDERU Z ZAZNACZONYCH UTWORÓW', f'Kopiowanie {len(plan.items)} zaznaczonych utworów…')
        self._set_busy(True, f'Tworzenie folderu „{plan.items[0].destination_dir.name}”…', kind='collection')
        thread = QThread(self); worker = ExportWorker(plan); worker.moveToThread(thread)
        thread.started.connect(worker.run); worker.progress.connect(self._export_progress); worker.finished.connect(self._collection_finished); worker.failed.connect(self._job_failed)
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit); thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater); thread.finished.connect(self._thread_done)
        self._thread = thread; self._worker = worker; thread.start()

    def _collection_finished(self, result):
        self.collections.refresh()
        copied = len(result.copied)
        destination, planned = getattr(self, '_collection_dialog_target', None) or (result.copied[0].parent if result.copied else None, result.planned)
        self._collection_dialog_target = None
        success = result.status == 'success'
        dialog = CreationResultDialog('folder', destination.name if destination is not None else '—', copied, destination, self,
            outcome=result.status, expected_count=planned,
            errors=(*result.errors, *result.verification_errors, result.fatal_error, *result.cleanup_warnings))
        self._set_operation_state('done' if success else 'error', dialog.windowTitle(), dialog.count_label.text())
        dialog.exec()

    def _apply_manual_field(self, tracks, field_name: str, value, lock: bool):
        current = [self.repository.get_track(t.track_id) for t in tracks]
        current = [t for t in current if t is not None]
        self.change_history.record(current, f'Zmiana pola {field_name}')
        for track in current:
            before = deepcopy(track)
            apply_manual_field([track], field_name, value, lock=lock)
            self._commit_track_metadata(before, track)
        self.refresh_data(); self._show_operation(f'Zmieniono {field_name} dla {len(tracks)} utworów. Ręczna wartość jest chroniona przed automatycznym nadpisaniem.')

    def _open_metadata_editor(self, track, *, duplicate_context: bool = False):
        navigation_tracks = (
            self.duplicates.current_group_tracks()
            if duplicate_context else self.library.visible_tracks()
        )
        if not navigation_tracks:
            navigation_tracks = [track]

        def path_key(item):
            return track_identity(item, self.repository.library_id)

        wanted = path_key(track)
        current_index = next(
            (index for index, candidate in enumerate(navigation_tracks) if path_key(candidate) == wanted),
            -1,
        )
        if current_index < 0:
            navigation_tracks = [track, *navigation_tracks]
            current_index = 0

        previous_geometry = None
        try:
            while 0 <= current_index < len(navigation_tracks):
                current_track = navigation_tracks[current_index]
                dialog = MetadataEditorDialog(
                    current_track, self,
                    filename_template=ProviderSettings.from_store(self.qt_settings).filename_template,
                    player_bar=self.player,
                    genre_suggestions=GenreSettings.from_store(self.qt_settings).suggestions(),
                    normalize_names=self.preferences.normalize_names,
                    name_rules=self.preferences.name_rules,
                    navigation_index=current_index,
                    navigation_total=len(navigation_tracks),
                    read_context=self._read_context,
                )
                if previous_geometry is not None:
                    dialog.setGeometry(previous_geometry)
                dialog.save_requested.connect(
                    lambda editor, target=current_track: self._save_metadata_from_editor(
                        target, editor, duplicate_context=duplicate_context
                    )
                )
                dialog.ready_requested.connect(
                    lambda editor, ready, target=current_track: self._set_ready_from_editor(
                        target, ready, duplicate_context=duplicate_context, editor=editor
                    )
                )
                dialog.online_scan_requested.connect(
                    lambda editor, target=current_track: self._start_single_track_identification(target, editor)
                )
                dialog.audio_scan_requested.connect(
                    lambda editor, target=current_track: self._start_audio_identification(target, editor)
                )
                dialog.audio_source_confirmed.connect(
                    lambda editor, previous, target=current_track: self._save_audio_source(target, previous)
                )
                apply_static_language(dialog, self.preferences.language)
                dialog.refresh_audio_language()
                self._active_metadata_editor = dialog
                dialog.exec()
                previous_geometry = dialog.geometry()
                delta = dialog.navigation_delta
                self._active_metadata_editor = None
                dialog.deleteLater()
                if not delta:
                    break
                current_index += delta
                if not duplicate_context:
                    self.library.select_track(navigation_tracks[current_index])
        finally:
            self._active_metadata_editor = None

    @staticmethod
    def _copy_track_state(target: TrackRecord, source: TrackRecord) -> None:
        for field_name in TrackRecord.__dataclass_fields__:
            setattr(target, field_name, deepcopy(getattr(source, field_name)))

    def _fresh_metadata_target(self, track):
        if track.track_id is None:
            # Existing standalone editor callers register their record on save.
            self.repository.upsert_track(track)
        current = self.repository.get_track(track.track_id)
        if current is None:
            raise ValueError('Metadata record no longer exists.')
        self._copy_track_state(track, current)
        return deepcopy(current)

    def _commit_track_metadata(self, before, track):
        saved = self.repository.save_metadata(track.track_id, metadata_changes(before, track),
            expected_revision=metadata_revision(before), library_id=self.change_history.library_id)
        self._copy_track_state(track, saved)
        self._invalidate_output_states(track.track_id)

    def _identification_context_current(self, repository, library_id, generation):
        return (isValid(self) and not self._identification_closing and self.repository is repository
                and self.repository.library_id == library_id
                and generation == self._identification_generation)

    def _editor_request_current(self, repository, library_id, editor, request, generation):
        return (self._identification_context_current(repository, library_id, generation) and isValid(editor)
                and self._active_metadata_editor in (None, editor)
                and editor.accepts_async_result(request))

    def _start_single_track_identification(self, track: TrackRecord, editor: MetadataEditorDialog):
        if self._thread is not None:
            QMessageBox.information(self, self._t('Operacja w toku'), self._t('Najpierw zakończ bieżącą operację.'))
            return
        if editor.has_unsaved_changes():
            QMessageBox.warning(
                self, self._t('Niezapisane zmiany'),
                self._t('Najpierw zapisz albo anuluj zmiany w tym utworze, a potem uruchom rozpoznawanie online.'),
            )
            return
        if editor.online_locked():
            QMessageBox.information(
                self, self._t('Rozpoznawanie zablokowane'),
                self._t('Ten utwór jest zablokowany przed rozpoznawaniem online. Odblokuj go, aby wykonać skan.'),
            )
            return
        editor.set_online_scan_busy(True)
        self._identification_generation += 1
        generation = self._identification_generation
        repository, library_id = self.repository, self.repository.library_id
        request = editor.begin_async_request(ReadPurpose.METADATA_EDITOR_READ)
        self._set_action_highlight(self.identify_btn)
        self._set_operation_state('online', 'ROZPOZNAWANIE JEDNEGO UTWORU', f'Online: {track.filename}')
        self._set_busy(True, f'Rozpoznawanie online tylko: {track.filename}', kind='online')
        job = IdentificationJob(self.repository, self._build_identifier(), tracks=[track], force=True)
        thread = QThread(self); worker = IdentificationWorker(job); worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda current, total, name: self._identify_progress(current, total, name)
                                if self._editor_request_current(repository, library_id, editor, request, generation) else None)
        worker.finished.connect(lambda result, t=track, e=editor: self._single_track_identification_finished(result, t, e)
                                if self._editor_request_current(repository, library_id, e, request, generation) else None)
        worker.failed.connect(lambda message, e=editor: self._single_track_identification_failed(message, e)
                              if self._editor_request_current(repository, library_id, e, request, generation) else None)
        editor.finished.connect(worker._cancelled.set)
        editor.destroyed.connect(worker._cancelled.set)
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater); thread.finished.connect(self._thread_done)
        thread.finished.connect(lambda: editor.set_online_scan_busy(False)
                                if isValid(editor) and not editor._read_closed else None)
        self._thread = thread; self._worker = worker; thread.start()

    def _single_track_identification_finished(self, result, track: TrackRecord, editor: MetadataEditorDialog):
        fresh = self.repository.get_track(track.track_id)
        if fresh is not None:
            self._copy_track_state(track, fresh)
        editor.apply_online_result(track)
        self.refresh_data()
        self.library.select_track(track)
        if result.errors:
            detail = f'Rozpoznawanie {track.filename}: błąd providerów — sprawdź komunikat w danych utworu.'
            self._set_operation_state('error', 'ROZPOZNAWANIE WYMAGA UWAGI', detail)
        elif result.certain:
            self._set_operation_state('done', 'UTWÓR ROZPOZNANY ONLINE', f'{track.filename}: wysokie dopasowanie.')
        elif result.probable:
            self._set_operation_state('done', 'UTWÓR SPRAWDZONY ONLINE', f'{track.filename}: dopasowanie wymaga kontroli.')
        else:
            self._set_operation_state('done', 'UTWÓR SPRAWDZONY ONLINE', f'{track.filename}: brak pewnego dopasowania.')

    def _single_track_identification_failed(self, message: str, editor: MetadataEditorDialog):
        editor.set_online_scan_busy(False)
        self._job_failed(message)

    def _start_audio_identification(self, track: TrackRecord, editor: MetadataEditorDialog) -> None:
        if self._thread is not None:
            editor.show_audio_error('Najpierw zakończ bieżącą operację.')
            return
        editor.start_audio_lookup(wait_for_thread=True)
        self._identification_generation += 1
        generation = self._identification_generation
        repository, library_id = self.repository, self.repository.library_id
        request = editor.begin_async_request(ReadPurpose.AUDIO_IDENTIFICATION)
        cfg = ProviderSettings.from_store(self.qt_settings)
        job = AudioIdentification(AcoustIDClient(cfg.acoustid_key),
                                  musicbrainz_client=MusicBrainzClient(cfg.musicbrainz_contact),
                                  read_context=self._read_context if track.track_id else None)
        thread = QThread(self)
        worker = AudioIdentificationWorker(job, track)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        current = lambda: self._editor_request_current(repository, library_id, editor, request, generation)
        worker.phase.connect(lambda phase: editor.set_audio_phase(phase) if current() else None)
        def finished(hits):
            if current():
                editor._audio_candidates_request = request
                editor.show_audio_candidates(hits)
        worker.finished.connect(finished)
        worker.failed.connect(lambda message: editor.show_audio_error(message) if current() else None)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_done)
        thread.finished.connect(lambda: editor.finish_audio_lookup() if isValid(editor) and not editor._read_closed else None)
        editor.finished.connect(worker._cancelled.set)
        editor.destroyed.connect(worker._cancelled.set)
        self._thread = thread
        self._worker = worker
        self._set_busy(True, self._t('Rozpoznawanie po audio…'), kind='audio')
        thread.start()

    def _save_audio_source(self, track: TrackRecord, previous: TrackRecord) -> None:
        if previous.track_id is None:
            self.repository.upsert_track(previous)
            track.track_id = previous.track_id
        current = self.repository.get_track(track.track_id)
        if current is None:
            return
        changes = metadata_changes(previous, track)
        try:
            saved = self.repository.save_metadata(track.track_id, changes,
                expected_revision=metadata_revision(previous), library_id=self.change_history.library_id,
                expected_source=(str(previous.path), previous.source_id, previous.source_relative_path),
                expected_material_revision=source_material_revision(previous))
        except ValueError:
            self._copy_track_state(track, current)
            return
        self.change_history.record([previous], 'Zatwierdzenie źródła audio')
        self._copy_track_state(track, saved)
        self._invalidate_output_states(track.track_id)
        self.refresh_data()
        self.library.select_track(track)

    def _save_metadata_from_editor(self, track, dialog, *, duplicate_context: bool = False):
        if dialog._read_closed or dialog.library_id not in ('', self.repository.library_id):
            return
        before = self._fresh_metadata_target(track)
        self.change_history.record([track], 'Edycja metadanych w Duplikatach' if duplicate_context else 'Edycja metadanych')
        sources = dialog.source_selections()
        for field_name, value in dialog.values().items():
            apply_manual_field([track], field_name, value, lock=True, source=sources.get(field_name, 'Ręcznie'))
        cover_update = dialog.cover_save_state()
        if cover_update is not None:
            track.manual_cover_path = cover_update['manual_cover_path']
            track.cover_choice = cover_update['cover_choice']
            track.cover_art_url = cover_update['cover_art_url']
            track.has_cover = cover_update['has_cover']
        set_online_locked(track, dialog.online_locked())
        if duplicate_context:
            self._keep_edited_duplicate(track)
        self._commit_track_metadata(before, track)
        self.refresh_data()
        self.library.select_track(track)
        if duplicate_context:
            self._show_operation(f'Zapisano metadane i ustawiono ZACHOWAJ: {track.filename}')
        else:
            result = library_status_text(track)
            self._show_operation(f'Metadane zapisane • Status: {result}')

    @staticmethod
    def _keep_edited_duplicate(selected):
        apply_duplicate_decision(selected, 'keep')

    def _set_ready_from_editor(self, track, ready: bool, *, duplicate_context: bool = False, editor=None):
        if editor is not None and (editor._read_closed or editor.library_id not in ('', self.repository.library_id)):
            return
        before = self._fresh_metadata_target(track)
        self.change_history.record([track], 'Oznaczenie jako GOTOWE' if ready else 'Odznaczenie jako GOTOWE')
        if ready:
            approve_as_ready(track)
        else:
            track.status = 'review'
            track.locked_fields.add('__status__')
        if duplicate_context and 'duplicate_primary' not in track.locked_fields:
            apply_duplicate_decision(track, 'keep')
            if not ready:
                track.status = 'review'
                track.locked_fields.add('__status__')
        self._commit_track_metadata(before, track)
        self.refresh_data()
        # refresh_data() already restores the selected row, visual order and scroll position.
        # Do not re-select and center the row after a status change from the metadata editor.
        dialog_status = 'GOTOWE' if ready and track.status == 'ready' else 'DO SPRAWDZENIA'
        self._show_operation(f'{track.filename}: {dialog_status}')

    def _edit_metadata(self, track):
        self._open_metadata_editor(track, duplicate_context=False)

    def _approve_track(self, track):
        before = self._fresh_metadata_target(track)
        self.change_history.record([track], 'Zatwierdzenie jako GOTOWE')
        approve_as_ready(track); self._commit_track_metadata(before, track); self.refresh_data()
        self._show_operation(f'Ręcznie zatwierdzono jako GOTOWE: {track.filename}')

    def _duplicate_decision(self, track, decision: str):
        before = self._fresh_metadata_target(track)
        labels = {
            'keep': 'ZACHOWAJ', 'duplicate': 'DUPLIKAT', 'not_selected': 'NIE WYBIERAM', 'review': 'DO SPRAWDZENIA',
        }
        self.change_history.record([track], f"Decyzja w Duplikatach: {labels.get(decision, decision)}")
        apply_duplicate_decision(track, decision)
        self._commit_track_metadata(before, track)
        self.refresh_data()
        result = library_status_text(track)
        self._show_operation(f"{track.filename}: wybrano {labels.get(decision, decision)} → Biblioteka: {result}.")

    def _edit_duplicate_track(self, selected):
        self._open_metadata_editor(selected, duplicate_context=True)

    def _undo_last_change(self):
        tracks = self.repository.list_tracks()
        before = {t.track_id: deepcopy(t) for t in tracks}
        action = self.change_history.undo_last(tracks, library_id=self.repository.library_id)
        if action is None:
            self._show_operation('Brak ręcznych zmian do cofnięcia w tej sesji.')
            return
        for track in tracks:
            key = track_identity(track, self.repository.library_id)
            if key in action.path_keys:
                self._commit_track_metadata(before[track.track_id], track)
        self.refresh_data()
        self._show_operation(f'Cofnięto: {action.description}')

    def cancel_current_identification(self):
        if isinstance(self._worker, IdentificationWorker):
            self._worker.cancel()
            self.identify_btn.setEnabled(False)
            self.identify_btn.setText('Anulowanie rozpoznawania…')
            self.identify_btn.setIcon(start_icon('cancel', '#ff7a84', 20))
            self._set_operation_state('online', 'ANULOWANIE ROZPOZNAWANIA', 'Bieżące zapytanie zostanie dokończone; kolejne nie będą wysyłane.')

    def cancel_current_scan(self):
        if isinstance(self._worker, ScanWorker):
            self._worker.cancel(); self.scan_btn.setEnabled(False); self.scan_btn.setText('Anulowanie skanowania…'); self.scan_btn.setIcon(start_icon('cancel', '#ff7a84', 20)); self.scan_btn.setObjectName('CancelScanAction'); self.scan_btn.style().unpolish(self.scan_btn); self.scan_btn.style().polish(self.scan_btn)
            self._set_operation_state('scan', 'ANULOWANIE SKANOWANIA', 'Zatrzymanie nastąpi bezpiecznie po zakończeniu bieżącego pliku…')

    def _sync_availability(self):
        self.availability = self.repository.sync_availability()
        return self.repository.list_tracks(available_only=True)

    def _library_context_snapshot(self):
        snapshot = self.repository.file_check_snapshot()
        return (snapshot.read_context(self.app_settings.library.root), list(snapshot.tracks),
                {tid: cached.evaluation for tid, cached in snapshot.cached})

    def _library_context_reader(self):
        # Called on GUI: capture repository/root now. No QObject goes to worker.
        return partial(_read_menu_snapshot, self.repository, str(self.app_settings.library.root))

    def refresh_data(self):
        snapshot = self.repository.file_check_snapshot()
        self._read_context = snapshot.read_context(self.app_settings.library.root)
        self.player.set_read_context(self._read_context)
        self.library.set_read_context(self._read_context)
        self.duplicates.library_id = snapshot.library_id
        all_tracks = list(snapshot.tracks)
        tracks = all_tracks
        cfg = ProviderSettings.from_store(self.qt_settings)
        template = cfg.filename_template
        for track in tracks:
            proposed = propose_filename(track, template=template)
            if track.proposed_filename != proposed:
                before = deepcopy(track)
                track.proposed_filename = proposed
                try:
                    self._commit_track_metadata(before, track)
                except ValueError:
                    fresh = self.repository.get_track(track.track_id)
                    if fresh is not None:
                        self._copy_track_state(track, fresh)
        self._output_baseline_evals = {tid: cached.evaluation for tid, cached in snapshot.cached}
        self.library.set_file_state_evaluations(snapshot.library_id, self._output_evaluations(snapshot))
        self.player.reconcile_tracks(tracks)
        summary = build_operation_summary(tracks)
        health = build_library_health(all_tracks)
        self._last_ui_summary, self._last_ui_health = summary, health
        self.dashboard.set_summary(summary); self.dashboard.set_health(health)
        self.library.set_tracks(tracks); self.duplicates.set_tracks(tracks); self.collections.refresh()
        for page in (self.dashboard, self.library, self.duplicates, self.collections):
            apply_static_language(page, self.preferences.language)
        self._refresh_start_context()
        duplicate_label = tr('nav.duplicates', self.preferences.language)
        duplicate_groups = duplicate_group_count(tracks)
        if duplicate_groups:
            self.nav_buttons[2].setText(f"{duplicate_label} ({duplicate_groups})")
        else:
            self.nav_buttons[2].setText(duplicate_label)
        self.nav_buttons[2].setProperty('hasItems', duplicate_groups > 0)
        self.nav_buttons[2].style().unpolish(self.nav_buttons[2]); self.nav_buttons[2].style().polish(self.nav_buttons[2])

    def _refresh_start_context(self):
        if hasattr(self.dashboard, 'sources'):
            self.dashboard.sources.set_registry(self.library_registry, self.qt_settings)
            self.dashboard.set_folder_organization(ProviderSettings.from_store(self.qt_settings).folder_organization)

    def _show_operation(self, text: str):
        self._operation_status_source = text
        self.operation_status.setText(self._t(text))
        self.operation_status.setToolTip(self.operation_status.text())

    def _refresh_workflow_button_texts(self):
        language = self.preferences.language
        self.scan_btn.setText(f"1. {tr('action.scan', language)}")
        if self._identification_was_cancelled:
            self.identify_btn.setText(f"2. {tr('action.resume_online', language)}")
        else:
            self.identify_btn.setText(f"2. {tr('action.identify_online', language)}")
        self.review_btn.setText(f"3. {tr('action.review', language)}")
        self.export_btn.setText(f"4. {tr('action.export', language)}")
        self.new_files_btn.setText(self._t('+ Dodaj źródło').removeprefix('+ '))
        self.new_files_btn.setToolTip(self._t('Wybierz folder z nowymi plikami'))

    def _set_busy(self, busy: bool, message: str = '', *, kind: str | None = None):
        active_kind = kind or self._operation_kind
        scan_running = busy and active_kind == 'scan'
        online_running = busy and active_kind == 'online'
        export_running = busy and active_kind == 'export'

        self.scan_btn.setEnabled((not busy) or scan_running)
        self.identify_btn.setEnabled((not busy) or online_running)
        self.new_files_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy)
        self.review_btn.setEnabled(True)

        scan_idle = f"1. {tr('action.scan', self.preferences.language)}"
        scan_cancel = 'Cancel scan' if self.preferences.language == 'en' else 'Anuluj skanowanie'
        self.scan_btn.setText(scan_cancel if scan_running else scan_idle)
        self.scan_btn.setIcon(start_icon('cancel' if scan_running else 'scan', '#ff7a84' if scan_running else '#dbe8e2', 23))
        self.scan_btn.setObjectName('CancelScanAction' if scan_running else 'Primary')
        self._apply_workflow_button_style(self.scan_btn, active=scan_running)
        self.scan_btn.style().unpolish(self.scan_btn); self.scan_btn.style().polish(self.scan_btn)
        if online_running:
            self.identify_btn.setText(tr('action.cancel_online', self.preferences.language))
        elif self._identification_was_cancelled:
            self.identify_btn.setText(f"2. {tr('action.resume_online', self.preferences.language)}")
        else:
            self.identify_btn.setText(f"2. {tr('action.identify_online', self.preferences.language)}")
        self.identify_btn.setObjectName('CancelOnlineAction' if online_running else 'IdentifyOnlineAction')
        self.identify_btn.setIcon(start_icon('cancel' if online_running else 'recognize', '#ff7a84' if online_running else '#dbe8e2', 23))
        self._apply_workflow_button_style(self.identify_btn, active=online_running)
        self.identify_btn.style().unpolish(self.identify_btn); self.identify_btn.style().polish(self.identify_btn)
        export_running_text = 'Creating files…' if self.preferences.language == 'en' else 'Tworzenie plików…'
        self.export_btn.setText(export_running_text if export_running else f"4. {tr('action.export', self.preferences.language)}")
        self.review_btn.setText(f"3. {tr('action.review', self.preferences.language)}")
        self.new_files_btn.setText(self._t('+ Dodaj źródło').removeprefix('+ '))
        self._set_button_running(self.scan_btn, scan_running)
        self._set_button_running(self.identify_btn, online_running)
        self._set_button_running(self.export_btn, export_running)

        self.progress.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1); self.progress.setValue(1)
        if message:
            self._show_operation(message)

    def start_scan(self, source_dirs=None, new_files: bool = False):
        if self._thread is not None: return
        self._active_scan_source_dirs = source_dirs
        cfg = ProviderSettings.from_store(self.qt_settings); self._pending_auto_identify = cfg.auto_identify_after_scan
        self._set_action_highlight(self.scan_btn)
        self._set_operation_state('scan', 'NOWE PLIKI' if new_files else 'SKANOWANIE', 'Analiza tylko wskazanego folderu…' if new_files else 'Odczyt tagów, BPM, jakości i fingerprintów…')
        thread = QThread(self); worker = ScanWorker(self.service, source_dirs=source_dirs); worker.moveToThread(thread)
        self._thread = thread; self._worker = worker; self._set_busy(True, 'Skanowanie: odczyt tagów, BPM, jakości i fingerprintów…', kind='scan')
        thread.started.connect(worker.run); worker.progress.connect(self._scan_progress); worker.track_ready.connect(self._scan_track_ready)
        worker.finished.connect(self._scan_finished); worker.failed.connect(self._job_failed)
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater); thread.finished.connect(self._thread_done); thread.start()

    def _scan_progress(self, current: int, total: int, name: str):
        self.progress.setVisible(True); self.progress.setRange(0, max(1, total)); self.progress.setValue(current)
        self._show_operation(f'Skanowanie {current}/{total}: {name}')

    def _scan_track_ready(self, current: int, total: int, _track):
        every = 1 if total <= 50 else (5 if total <= 250 else 20)
        if should_refresh_live_scan(current, total, every=every): self.refresh_data()

    def _scan_finished(self, result):
        self.availability = self.repository.sync_availability()
        if not result.cancelled:
            active_id = self.library_registry.active.profile_id
            for source_text, file_count in getattr(result, 'source_counts', ()):
                self.library_registry.record_scan(active_id, Path(source_text), file_count)
            self.library_registry.save(self.qt_settings)
            if getattr(self, '_library_manager', None) is not None:
                self._library_manager.refresh()
        self._active_scan_source_dirs = None
        self.refresh_data(); report = self.app_settings.library.reports / f'skan_{datetime.now():%Y%m%d_%H%M%S}.csv'; export_csv(self.repository.list_tracks(), report)
        if result.cancelled: self._pending_auto_identify = False
        prefix = 'Skan anulowany' if result.cancelled else 'Skan zakończony'
        summary_text = f'{prefix}: {result.scanned} przeanalizowano, {result.skipped_unchanged} bez zmian, błędy: {result.errors}.'
        self._set_operation_state('done', 'SKANOWANIE ZAKOŃCZONE' if not result.cancelled else 'SKANOWANIE ANULOWANE', summary_text)

    def _thread_done(self):
        self._thread = None; self._worker = None; self._set_busy(False)
        if self._identification_closing:
            self._pending_auto_identify = False
            self.close()
            return
        if self._pending_auto_identify:
            self._pending_auto_identify = False; self.start_identification()
            return
        self._set_action_highlight(self.review_btn if self.stack.currentIndex() == 1 else None)

    def _job_failed(self, message: str):
        self._pending_auto_identify = False; self._set_operation_state('error', 'BŁĄD OPERACJI', message); QMessageBox.critical(self, self._t('Błąd'), self._t(message))

    def _build_identifier(self):
        cfg = ProviderSettings.from_store(self.qt_settings)
        mb = MusicBrainzClient(cfg.musicbrainz_contact)
        acoustid = AcoustIDClient(cfg.acoustid_key) if cfg.acoustid_key else None
        discogs = DiscogsClient(cfg.discogs_token) if cfg.discogs_token else None
        itunes = ITunesSearchClient()
        return IdentificationService(acoustid=acoustid, musicbrainz=mb, discogs=discogs, itunes=itunes)

    def start_identification(self):
        if self._thread is not None: return
        tracks = self._sync_availability()
        if not tracks: QMessageBox.information(self, self._t('Brak plików'), self._t('Najpierw uruchom skanowanie folderów.')); return
        self._set_action_highlight(self.identify_btn)
        self._set_operation_state('online', 'ROZPOZNAWANIE ONLINE', 'MusicBrainz i Apple/iTunes działają bez klucza. AcoustID i Discogs są używane, jeśli je skonfigurowano.')
        self._set_busy(True, 'Rozpoznawanie online — może potrwać, ponieważ bazy mają limity zapytań…', kind='online')
        job = IdentificationJob(self.repository, self._build_identifier(), tracks=tracks)
        self._identification_generation += 1
        generation = self._identification_generation
        repository, library_id = self.repository, self.repository.library_id
        current = lambda: self._identification_context_current(repository, library_id, generation)
        thread = QThread(self); worker = IdentificationWorker(job); worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda done, total, name: self._identify_progress(done, total, name) if current() else None)
        worker.finished.connect(lambda result: self._identify_finished(result) if current() else None)
        worker.failed.connect(lambda message: self._job_failed(message) if current() else None)
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit); thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater); thread.finished.connect(self._thread_done)
        self._thread = thread; self._worker = worker; thread.start()

    def _identify_progress(self, current: int, total: int, name: str):
        self.progress.setVisible(True); self.progress.setRange(0, max(1, total)); self.progress.setValue(current)
        self._show_operation(f'Rozpoznawanie online {current}/{total}: {name}')

    def _identify_finished(self, result):
        self._identification_was_cancelled = bool(getattr(result, 'cancelled', False))
        self.refresh_data(); report = self.app_settings.library.reports / f'rozpoznanie_{datetime.now():%Y%m%d_%H%M%S}.csv'; export_csv(self.repository.list_tracks(), report)
        title = 'ROZPOZNAWANIE ANULOWANE' if self._identification_was_cancelled else 'ROZPOZNAWANIE ZAKOŃCZONE'
        skipped = f' Pominięto zablokowane: {result.skipped_locked}.' if getattr(result, 'skipped_locked', 0) else ''
        self._set_operation_state('done', title, f'Pewne {result.certain}, prawdopodobne {result.probable}, niepewne {result.uncertain}, błędy {result.errors}.{skipped}')

    def export_library(self):
        if self._thread is not None:
            return
        tracks = self._sync_availability()
        if not tracks:
            QMessageBox.information(self, self._t('Brak plików'), self._t('Najpierw przeskanuj bibliotekę.'))
            return
        summary = build_operation_summary(tracks)
        if export_needs_library_review(summary):
            box = ExportReviewWarning(summary['review'], self, language=self.preferences.language)
            review_button, continue_button = box.review_button, box.continue_button
            box.exec()
            if box.clickedButton() is review_button:
                self._open_review()
                return
            if box.clickedButton() is not continue_button:
                return
        cfg = ProviderSettings.from_store(self.qt_settings)
        plan = ExportPlan.from_tracks(deepcopy(tracks), self.app_settings.library, folder_organization=cfg.folder_organization)
        metrics = plan.preview_metrics()
        if not confirm_bulk_copy(self, {**plan.summary, **metrics}, examples=plan.preview_lines(6),
                                 folder_organization=cfg.folder_organization, plan=plan):
            return
        if self._thread is not None:
            return
        self._set_action_highlight(self.export_btn)
        self._set_operation_state('export', 'TWORZENIE PLIKÓW', 'Kopiowanie, zapis metadanych i techniczna kontrola kopii…')
        self._set_busy(True, 'Tworzenie plików i techniczna kontrola kopii…', kind='export')
        self._export_plan = plan
        self._export_library = self.app_settings.library
        self._export_language = self.preferences.language
        self._export_metrics = metrics
        self._export_started = perf_counter()
        self._export_result = None
        self._export_stop_requested = False
        self._export_dialog = ExportProgressDialog(len(plan.items), self, language=self._export_language)
        self._export_dialog.stop_requested.connect(self._request_export_stop)
        thread = QThread(self)
        worker = ExportWorker(plan, adoption_repository=self.repository,
            library_root=self._export_library.root, known_libraries=self._known_adoption_libraries())
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._export_progress, Qt.ConnectionType.QueuedConnection)
        worker.phase.connect(self._export_event, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._export_finished, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._export_failed, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._export_thread_done, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        self._export_dialog.show()
        thread.start()

    @Slot(int, int, str)
    def _export_progress(self, current: int, total: int, name: str):
        self.progress.setVisible(True); self.progress.setRange(0, max(1, total)); self.progress.setValue(current)
        self._show_operation(f'Tworzenie plików i kontrola techniczna {current}/{total}: {name}')

    @Slot(object)
    def _export_event(self, event):
        dialog = getattr(self, '_export_dialog', None)
        if dialog is not None:
            dialog.update_event(event)

    @Slot()
    def _request_export_stop(self):
        if not isinstance(self._worker, ExportWorker):
            return
        self._export_stop_requested = True
        self._worker.cancel()
        dialog = getattr(self, '_export_dialog', None)
        if dialog is not None:
            dialog.request_stop()

    @Slot(object)
    def _export_finished(self, result):
        # A result is not a QThread completion barrier. Keep ownership until
        # thread.finished, then join the final native teardown before any dialog.
        self._export_result = result

    @Slot(str)
    def _export_failed(self, message):
        self._export_result = ExportResult((), (), planned=len(self._export_plan.items),
            elapsed_seconds=perf_counter() - self._export_started, fatal_error=message,
            cancelled=self._export_stop_requested)

    @Slot()
    def _export_thread_done(self):
        thread = self._thread
        if thread is not None:
            thread.wait()  # finished was received; never wait on an active file.
        self._thread, self._worker = None, None
        dialog = self._export_dialog
        self._export_dialog = None
        dialog.finish()
        dialog.deleteLater()
        result = self._export_result or ExportResult((), (), planned=len(self._export_plan.items),
            elapsed_seconds=perf_counter() - self._export_started, fatal_error='Worker ended without a result.')
        from dataclasses import replace
        result = replace(result, cancelled=result.cancelled or self._export_stop_requested,
                         elapsed_seconds=max(result.elapsed_seconds, perf_counter() - self._export_started))
        self._set_busy(False)
        self._pending_auto_identify = False
        self._set_action_highlight(self.review_btn if self.stack.currentIndex() == 1 else None)
        plan, library = self._export_plan, self._export_library
        tracks = [item.track for item in plan.items]
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid4().hex[:8]
        report_errors, verification_report = [], None
        # Preserve existing reports and add every failed/unprocessed plan item
        # to the copy audit. One failed report must not hide the other results.
        reports = (
            (export_verification_csv, (result, library.reports / f'weryfikacja_kopii_{stamp}.csv'), {'plan': plan}),
            (export_csv, (tracks, library.reports / f'eksport_{stamp}.csv'), {}),
            (export_session_html, (tracks, library.reports / f'raport_sesji_{stamp}.html'), {'language': self._export_language}),
        )
        for writer, args, kwargs in reports:
            try:
                path = writer(*args, **kwargs)
                if writer is export_verification_csv:
                    verification_report = path
            except Exception as exc:
                prefix = 'Report error' if self._export_language == 'en' else 'Błąd raportu'
                report_errors.append(f'{prefix}: {exc}')
        summary = ExportSummaryDialog(result, plan, library.root, verification_report, self,
            metrics=self._export_metrics, report_errors=report_errors, language=self._export_language)
        if self._export_language == 'en':
            title = {'success': 'CREATION COMPLETED', 'problems': 'CREATION NEEDS ATTENTION', 'cancelled': 'CREATION STOPPED'}[summary.outcome]
            detail = f'Created and verified: {result.created}/{result.planned}. Remaining: {result.remaining}. Errors: {result.failed}.'
        else:
            title = {'success': 'TWORZENIE ZAKOŃCZONE', 'problems': 'TWORZENIE WYMAGA UWAGI', 'cancelled': 'TWORZENIE ZATRZYMANE'}[summary.outcome]
            detail = f'Utworzono i zweryfikowano: {result.created}/{result.planned}. Pozostało: {result.remaining}. Błędy: {result.failed}.'
        self._set_operation_state('done', title, detail)
        try:
            summary.exec()
        finally:
            summary.deleteLater()

    def closeEvent(self, event):
        if isinstance(self._worker, ExportWorker):
            self._request_export_stop()
            event.ignore()
            return
        self.library.cancel_context_actions()
        if isinstance(self._worker, (IdentificationWorker, AudioIdentificationWorker)):
            self._identification_closing = True
            self._identification_generation += 1
            self._pending_auto_identify = False
            self._worker.cancel()
            event.ignore()
            return
        if isinstance(self._worker, FileReconciliationWorker):
            self._file_check_closing = True
            self._file_check_generation += 1
            self._worker.cancel()
            event.ignore()
            return
        self.library.cancel_context_actions(closing=True)
        super().closeEvent(event)
