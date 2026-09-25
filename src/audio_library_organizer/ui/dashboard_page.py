from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import html
from pathlib import Path
import shutil

from PySide6.QtCore import Qt, QSettings, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QResizeEvent
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from audio_library_organizer.domain.settings import AppSettings
from audio_library_organizer.ui.icons import alo_icon
from audio_library_organizer.ui.i18n import ui_text, language_for
from audio_library_organizer.ui.widgets import StatCard


class DashboardStatCard(StatCard):
    clicked = Signal()

    def __init__(self, title: str, value: str = '0', parent=None, *, accent: str = '#4a91ff'):
        super().__init__(title, value, parent, accent=accent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip('Kliknij, aby otworzyć ten widok w Bibliotece')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ElidedPathLabel(QLabel):
    """A selectable path label that keeps long Windows paths inside its card."""

    def __init__(self, path: Path, accent: str, parent=None):
        super().__init__(parent)
        self._full_path = str(path)
        self._accent = accent
        self.setObjectName('QuickAccessPath')
        self.setProperty('pathAccent', accent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setToolTip(self._full_path)

    def set_path(self, path: Path) -> None:
        self._full_path = str(path)
        self.setToolTip(self._full_path)
        self._refresh_text()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        width = max(80, self.contentsRect().width())
        path = Path(self._full_path)
        terminal = path.name or self._full_path
        parent = str(path.parent)
        separator = '\\' if '\\' in self._full_path else '/'
        reserved = self.fontMetrics().horizontalAdvance(terminal + separator) + 8
        visible_parent = self.fontMetrics().elidedText(
            parent,
            Qt.TextElideMode.ElideMiddle,
            max(24, width - reserved),
        )
        self.setText(
            f'<span style="color:#8fa7b4">{html.escape(visible_parent + separator)}</span>'
            f'<span style="color:{self._accent};font-weight:650">{html.escape(terminal)}</span>'
        )


class QuickAccessCard(QFrame):
    def __init__(self, title: str, path: Path, icon_name: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName('QuickAccessCard')
        self.setProperty('accentColor', accent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(120)
        self.path = Path(path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        self.title_icon = QLabel()
        self.title_icon.setObjectName('QuickAccessIcon')
        self.title_icon.setPixmap(alo_icon(icon_name, '#d9e8ef', 19).pixmap(19, 19))
        self.title_icon.setFixedSize(23, 23)
        self.title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.addWidget(self.title_icon)
        self.title_label = QLabel(title)
        self.title_label.setObjectName('QuickAccessTitle')
        heading.addWidget(self.title_label, 1)
        self.availability = QLabel('')
        self.availability.setObjectName('QuickAccessAvailability')
        heading.addWidget(self.availability)
        layout.addLayout(heading)

        self.path_label = ElidedPathLabel(self.path, accent)
        layout.addWidget(self.path_label)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.open_button = QPushButton('Otwórz folder')
        self.open_button.setObjectName('QuickAccessOpen')
        self.open_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.open_button.setIcon(alo_icon('folder_open', '#d9e8ef', 15))
        self.open_button.setToolTip('Otwórz folder w Eksploratorze')
        self.copy_button = QPushButton('Kopiuj ścieżkę')
        self.copy_button.setObjectName('QuickAccessCopy')
        self.copy_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.copy_button.setIcon(alo_icon('copy', '#98afbd', 14))
        self.copy_button.setToolTip('Kopiuj ścieżkę')
        actions.addWidget(self.open_button)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.open_button.clicked.connect(self._open_folder)
        self.copy_button.clicked.connect(self._copy_path)
        self.set_path(path)

    def set_path(self, path: Path) -> None:
        self.path = Path(path)
        self.path_label.set_path(self.path)
        available = self.path.is_dir()
        self.availability.setText(ui_text(self, 'Dostępna' if available else 'Niedostępna'))
        self.availability.setProperty('available', available)
        self.availability.style().unpolish(self.availability)
        self.availability.style().polish(self.availability)
        self.open_button.setEnabled(available)

    def _open_folder(self) -> None:
        if self.path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def _copy_path(self) -> None:
        QApplication.clipboard().setText(str(self.path))


class DashboardPage(QWidget):
    refresh_requested = Signal()
    quick_view_requested = Signal(str)

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._library_root = Path(settings.library.root)
        self._summary: dict[str, int] = {}
        self._health: dict[str, object] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)

        self.dashboard_title = QLabel('Biblioteka główna')
        self.dashboard_title.setStyleSheet('font-size:22pt;font-weight:750;')
        root.addWidget(self.dashboard_title)

        path_bar = QFrame()
        path_bar.setObjectName('SessionCard')
        path_layout = QHBoxLayout(path_bar)
        path_layout.setContentsMargins(12, 8, 12, 8)
        path_layout.setSpacing(8)
        folder_icon = QLabel()
        folder_icon.setPixmap(alo_icon('folder', '#62d6f5', 20).pixmap(20, 20))
        folder_icon.setFixedSize(24, 24)
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path_layout.addWidget(folder_icon)
        self.library_label = QLabel(str(settings.library.root))
        self.library_label.setObjectName('MutedText')
        self.library_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.library_label.setToolTip(str(settings.library.root))
        path_layout.addWidget(self.library_label, 1)
        self.open_folder_button = QPushButton('Otwórz folder')
        self.open_folder_button.setObjectName('LibrarySecondaryAction')
        self.open_folder_button.clicked.connect(self._open_library_folder)
        path_layout.addWidget(self.open_folder_button)
        root.addWidget(path_bar)

        cards_layout = QGridLayout()
        cards_layout.setHorizontalSpacing(10)
        cards_layout.setVerticalSpacing(0)
        self.cards = {
            'total': DashboardStatCard('Utwory', accent='#7f8da1'),
            'review': DashboardStatCard('Do sprawdzenia', accent='#ffb84d'),
            'duplicate': DashboardStatCard('Duplikaty', accent='#b987ff'),
            'missing_covers': DashboardStatCard('Brak okładki', accent='#63b3ed'),
        }
        for column, key in enumerate(('total', 'review', 'duplicate', 'missing_covers')):
            cards_layout.addWidget(self.cards[key], 0, column)
        root.addLayout(cards_layout)

        self.cards['total'].clicked.connect(lambda: self.quick_view_requested.emit('all'))
        self.cards['review'].clicked.connect(lambda: self.quick_view_requested.emit('review'))
        self.cards['duplicate'].clicked.connect(lambda: self.quick_view_requested.emit('duplicate'))
        self.cards['missing_covers'].clicked.connect(lambda: self.quick_view_requested.emit('no_cover'))

        self.last_scan_label = QLabel('Ostatnie skanowanie: brak danych')
        self.last_scan_label.setObjectName('MutedText')
        self.last_scan_label.setWordWrap(True)
        root.addWidget(self.last_scan_label)

        quick_header = QHBoxLayout()
        quick_title_icon = QLabel()
        quick_title_icon.setPixmap(alo_icon('folder_open', '#62d6f5', 20).pixmap(20, 20))
        quick_title_icon.setFixedSize(24, 24)
        quick_header.addWidget(quick_title_icon)
        quick_title = QLabel('Szybki dostęp')
        quick_title.setObjectName('DashboardSectionTitle')
        quick_header.addWidget(quick_title)
        quick_header.addStretch(1)
        root.addLayout(quick_header)

        self.quick_access_host = QWidget()
        self.quick_access_layout = QGridLayout(self.quick_access_host)
        self.quick_access_layout.setContentsMargins(0, 0, 0, 14)
        self.quick_access_layout.setHorizontalSpacing(10)
        self.quick_access_layout.setVerticalSpacing(10)
        self.location_cards: dict[str, QuickAccessCard] = {}
        self._location_order = ('root', 'ready', 'review', 'not_selected', 'custom_folders', 'reports')
        self._create_location_cards(settings)
        root.addWidget(self.quick_access_host)

        root.addSpacing(10)
        self.statistics_separator = QFrame()
        self.statistics_separator.setObjectName('DashboardStatisticsSeparator')
        self.statistics_separator.setMinimumHeight(42)
        separator_layout = QHBoxLayout(self.statistics_separator)
        separator_layout.setContentsMargins(0, 9, 0, 9)
        separator_layout.setSpacing(8)
        left_line = QFrame()
        left_line.setObjectName('DashboardStatisticsLine')
        left_line.setFrameShape(QFrame.Shape.HLine)
        separator_layout.addWidget(left_line, 1)
        self.statistics_separator_icon = QLabel()
        self.statistics_separator_icon.setObjectName('DashboardStatisticsIcon')
        self.statistics_separator_icon.setPixmap(alo_icon('report', '#75bfff', 17).pixmap(17, 17))
        self.statistics_separator_icon.setFixedSize(20, 20)
        self.statistics_separator_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        separator_layout.addWidget(self.statistics_separator_icon)
        self.statistics_separator_title = QLabel('Statystyki biblioteki')
        self.statistics_separator_title.setObjectName('DashboardStatisticsTitle')
        separator_layout.addWidget(self.statistics_separator_title)
        right_line = QFrame()
        right_line.setObjectName('DashboardStatisticsLine')
        right_line.setFrameShape(QFrame.Shape.HLine)
        separator_layout.addWidget(right_line, 4)
        root.addWidget(self.statistics_separator)

        stats_frame = QFrame()
        stats_frame.setObjectName('LibraryHealthCard')
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(14, 11, 14, 11)
        stats_layout.setSpacing(8)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(10)
        stats_grid.setVerticalSpacing(8)
        stat_labels = [
            ('covers', 'OKŁADKI'),
            ('online', 'ROZPOZNANE ONLINE'),
            ('missing', 'BRAKUJĄCE PLIKI'),
            ('suspicious', 'PODEJRZANE DANE'),
            ('size', 'ROZMIAR BIBLIOTEKI'),
            ('free_space', 'WOLNE MIEJSCE'),
        ]
        self.stats_values: dict[str, QLabel] = {}
        for index, (key, label) in enumerate(stat_labels):
            box = QFrame()
            box.setObjectName('WorkflowMiniStep')
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(10, 7, 10, 7)
            box_layout.setSpacing(2)
            heading = QLabel(label)
            heading.setObjectName('FieldHeading')
            value = QLabel('—')
            value.setStyleSheet('font-size:12pt;font-weight:750;')
            box_layout.addWidget(heading)
            box_layout.addWidget(value)
            self.stats_values[key] = value
            stats_grid.addWidget(box, index // 3, index % 3)
        stats_layout.addLayout(stats_grid)
        root.addWidget(stats_frame)

        self.attention_frame = QFrame()
        self.attention_frame.setObjectName('MissingFilesBanner')
        attention_layout = QHBoxLayout(self.attention_frame)
        attention_layout.setContentsMargins(12, 9, 12, 9)
        attention_layout.setSpacing(10)
        attention_title = QLabel('Wymaga uwagi')
        attention_title.setStyleSheet('font-weight:800;')
        attention_layout.addWidget(attention_title)
        self.attention_text = QLabel('')
        self.attention_text.setWordWrap(True)
        attention_layout.addWidget(self.attention_text, 1)
        self.attention_frame.setVisible(False)
        root.addWidget(self.attention_frame)

        root.addStretch(1)
        self._load_last_scan()

    def _library_storage_key(self) -> str:
        normalized = str(self._library_root.resolve()).casefold().encode('utf-8', errors='replace')
        digest = hashlib.sha1(normalized).hexdigest()[:16]
        return f'dashboard/last_scan/{digest}'

    def _save_last_scan(self, when: datetime) -> None:
        store = QSettings()
        store.setValue(self._library_storage_key(), when.isoformat(timespec='seconds'))
        store.sync()

    def _load_last_scan(self) -> None:
        raw = QSettings().value(self._library_storage_key(), '')
        if not raw:
            self.last_scan_label.setText(ui_text(self, 'Ostatnie skanowanie: brak danych'))
            self.last_scan_label.setToolTip('')
            return
        try:
            when = datetime.fromisoformat(str(raw))
        except ValueError:
            self.last_scan_label.setText(ui_text(self, 'Ostatnie skanowanie: brak danych'))
            self.last_scan_label.setToolTip('')
            return
        self._show_last_scan_time(when)

    def _show_last_scan_time(self, when: datetime) -> None:
        today = datetime.now().date()
        if when.date() == today:
            moment = f'{"today" if language_for(self) == "en" else "dzisiaj"}, {when:%H:%M}'
        elif when.date() == today - timedelta(days=1):
            moment = f'{"yesterday" if language_for(self) == "en" else "wczoraj"}, {when:%H:%M}'
        else:
            moment = when.strftime('%d.%m.%Y, %H:%M')
        self.last_scan_label.setText(f'{ui_text(self, "Ostatnie skanowanie:")} {moment}')

    def _open_library_folder(self) -> None:
        target = self._library_root if self._library_root.exists() else self._library_root.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    @staticmethod
    def _location_specs(settings: AppSettings) -> tuple[tuple[str, str, Path, str, str], ...]:
        library = settings.library
        return (
            ('root', 'Biblioteka główna', library.root, 'library', '#58c9f3'),
            ('ready', 'Pliki wynikowe / GOTOWE', library.ready, 'check_library', '#55d98b'),
            ('review', 'Do sprawdzenia', library.review, 'warning', '#f0b44d'),
            ('not_selected', 'Niewybrane', library.not_selected, 'folder', '#b987ff'),
            ('custom_folders', 'Moje pliki MP3', library.custom_folders, 'add_tracks', '#50d1c4'),
            ('reports', 'Raporty', library.reports, 'report', '#75bfff'),
        )

    def _create_location_cards(self, settings: AppSettings) -> None:
        for key, title, path, icon_name, accent in self._location_specs(settings):
            self.location_cards[key] = QuickAccessCard(title, path, icon_name, accent, self.quick_access_host)
        self._reflow_locations()

    def _update_location_cards(self, settings: AppSettings) -> None:
        for key, _title, path, _icon_name, _accent in self._location_specs(settings):
            self.location_cards[key].set_path(path)

    def _reflow_locations(self) -> None:
        width = self.width()
        columns = 3 if width >= 1100 else 2 if width >= 720 else 1
        for index, key in enumerate(self._location_order):
            self.quick_access_layout.addWidget(self.location_cards[key], index // columns, index % columns)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'location_cards'):
            self._reflow_locations()

    def set_library(self, settings: AppSettings, library_name: str | None = None):
        self._library_root = Path(settings.library.root)
        self._last_scan_tooltip_source = ''
        self.library_label.setText(str(settings.library.root))
        self.library_label.setToolTip(str(settings.library.root))
        self._update_location_cards(settings)
        if library_name:
            self.set_library_name(library_name)
        self._load_last_scan()
        if self._health:
            self._update_statistics()

    def set_library_name(self, name: str):
        self.dashboard_title.setText(ui_text(self, name or 'Biblioteka główna'))

    def set_last_scan_summary(self, text: str):
        now = datetime.now()
        self._last_scan_tooltip_source = text
        self._save_last_scan(now)
        self._show_last_scan_time(now)
        self.last_scan_label.setToolTip(ui_text(self, text or ''))

    def refresh_language(self) -> None:
        self._load_last_scan()
        self.last_scan_label.setToolTip(ui_text(self, getattr(self, '_last_scan_tooltip_source', '')))
        for card in self.location_cards.values():
            card.set_path(card.path)
        self._update_attention()

    def set_summary(self, summary: dict[str, int]):
        self._summary = dict(summary)
        self.cards['total'].set_value(int(summary.get('total', 0)))
        self.cards['review'].set_value(int(summary.get('review', 0)))
        self.cards['duplicate'].set_value(int(summary.get('duplicate', 0)))
        self._update_attention()

    def set_health(self, health: dict[str, object]):
        self._health = dict(health)
        self.cards['missing_covers'].set_value(int(health.get('missing_covers', 0)))
        self._update_statistics()
        self._update_attention()

    def _update_statistics(self) -> None:
        available = int(self._health.get('available', self._summary.get('total', 0)))
        missing_covers = int(self._health.get('missing_covers', 0))
        covers = max(0, available - missing_covers)
        cover_percent = (covers / available * 100.0) if available else 0.0
        self.stats_values['covers'].setText(f'{covers} / {available} ({cover_percent:.0f}%)')

        online_checked = int(self._health.get('online_checked', 0))
        online_percent = float(self._health.get('online_percent', 0.0))
        if available and online_percent <= 0.0 and online_checked:
            online_percent = online_checked / available * 100.0
        self.stats_values['online'].setText(f'{online_checked} / {available} ({online_percent:.0f}%)')

        self.stats_values['missing'].setText(str(int(self._health.get('missing', 0))))
        self.stats_values['suspicious'].setText(str(int(self._health.get('suspicious', 0))))

        size = int(self._health.get('size_bytes', 0))
        if size >= 1024 ** 3:
            size_text = f'{size / (1024 ** 3):.2f} GB'
        elif size >= 1024 ** 2:
            size_text = f'{size / (1024 ** 2):.1f} MB'
        else:
            size_text = f'{size / 1024:.1f} KB' if size else '0 MB'
        self.stats_values['size'].setText(size_text)

        free_label = self.stats_values['free_space']
        try:
            target = self._library_root if self._library_root.exists() else self._library_root.parent
            free_gb = shutil.disk_usage(target).free / (1024 ** 3)
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

    def _update_attention(self) -> None:
        review = int(self._summary.get('review', 0))
        duplicate = int(self._summary.get('duplicate', 0))
        missing_covers = int(self._health.get('missing_covers', 0))
        missing = int(self._health.get('missing', 0))

        parts: list[str] = []
        if review:
            parts.append(ui_text(self, f'{review} do sprawdzenia'))
        if duplicate:
            parts.append(ui_text(self, f'{duplicate} grup duplikatów'))
        if missing_covers:
            parts.append(ui_text(self, f'{missing_covers} bez okładki'))
        if missing:
            parts.append(ui_text(self, f'{missing} brakujących plików'))

        self.attention_text.setText(' • '.join(parts))
        self.attention_frame.setVisible(bool(parts))
