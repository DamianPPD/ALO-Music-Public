from __future__ import annotations

import html
from pathlib import Path
import shutil

from PySide6.QtCore import Qt, QUrl, Signal, QRectF
from PySide6.QtGui import QBrush, QColor, QCursor, QDesktopServices, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from audio_library_organizer.domain.settings import AppSettings
from audio_library_organizer.ui.icons import alo_icon, start_icon
from audio_library_organizer.ui.i18n import ui_text, language_for
from audio_library_organizer.ui.widgets import StatCard
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.scan_sources import ScanSourcesWidget

START_PANEL_ICON_COLOR = '#628fb0'


class StudioHero(QFrame):
    """Display the approved panorama with its audio equipment in the crop."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('StartStudioHero')
        self.artwork_path = asset_path('start_studio.png')
        self._artwork = QPixmap(str(self.artwork_path))
        self.setFixedHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setClipPath(self._rounded_path(bounds))
        painter.fillRect(bounds, QColor('#0b151c'))
        if not self._artwork.isNull():
            # Crop the supplied panorama to the low hero without stretching it.
            # The artwork strip is centred vertically in the source image.
            source_width = self._artwork.width()
            source_height = min(self._artwork.height(), source_width * bounds.height() / bounds.width())
            source_top = min(self._artwork.height() - source_height,
                             max(0.0, self._artwork.height() * .46 - source_height / 2))
            source = QRectF(0, source_top, source_width, source_height)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(bounds, self._artwork, source)
        gradient = QLinearGradient(bounds.topLeft(), bounds.topRight())
        gradient.setColorAt(0, QColor(2, 10, 16, 95))
        gradient.setColorAt(0.38, QColor(2, 10, 16, 35))
        gradient.setColorAt(0.60, QColor(2, 10, 16, 8))
        gradient.setColorAt(1, QColor(2, 10, 16, 0))
        painter.fillRect(bounds, QBrush(gradient))
        painter.setClipping(False)
        painter.setPen(QColor('#294550'))
        painter.drawRoundedRect(bounds, 10, 10)

    @staticmethod
    def _rounded_path(bounds):
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRoundedRect(bounds, 10, 10)
        return path


class DashboardStatCard(StatCard):
    clicked = Signal()

    def __init__(self, title: str, value: str = '0', parent=None, *, accent: str = '#4a91ff'):
        super().__init__(title, value, parent, accent=accent)
        self.setObjectName('DashboardStatCard')
        self.setStyleSheet(
            f'QFrame#DashboardStatCard {{ background:#0e1a22; border:1px solid {accent}; '
            f'border-top:2px solid {accent}; '
            'border-radius:9px; } QLabel { background:transparent; border:0; }'
        )
        self.setFixedHeight(92)
        layout = self.layout()
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(3)
        layout.removeWidget(self.value_label)
        caption = layout.takeAt(0).widget()
        icon_name = {'Utwory': 'music_note', 'Do sprawdzenia': 'warning',
                     'Duplikaty': 'duplicates', 'Brak okładki': 'cover'}[title]
        self.stat_icon = QLabel()
        self.stat_icon.setPixmap(start_icon(icon_name, accent, 32).pixmap(32, 32))
        self.stat_icon.setFixedSize(52, 54)
        self.stat_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stat_icon.setStyleSheet(f'background:{QColor(accent).darker(500).name()}; border:1px solid {QColor(accent).darker(270).name()}; border-radius:9px;')
        row = QHBoxLayout()
        row.setSpacing(13)
        row.addWidget(self.stat_icon)
        text_column = QVBoxLayout()
        text_column.setSpacing(1)
        text_column.addWidget(self.value_label)
        text_column.addWidget(caption)
        row.addLayout(text_column)
        row.addStretch(1)
        layout.insertLayout(0, row)
        self.value_label.setStyleSheet(f'font-size:25pt;font-weight:800;border:0;color:{accent};')
        self._accent = accent
        self._decoration = {'Utwory': 'equalizer', 'Do sprawdzenia': 'checklist',
                            'Duplikaty': 'layers', 'Brak okładki': 'covers'}[title]
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip('Kliknij, aby otworzyć ten widok w Bibliotece')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() < 300:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._accent)
        color.setAlpha(66)
        painter.setPen(QPen(color, 1.5))
        fill = QColor(self._accent)
        fill.setAlpha(12)
        painter.setBrush(fill)
        x = self.width() - 98
        if self._decoration == 'equalizer':
            gradient = QLinearGradient(0, 22, 0, 70)
            bright = QColor(self._accent)
            bright.setAlpha(88)
            dim = QColor(self._accent)
            dim.setAlpha(35)
            gradient.setColorAt(0, dim)
            gradient.setColorAt(.5, bright)
            gradient.setColorAt(1, dim)
            painter.setPen(Qt.PenStyle.NoPen)
            for index, height in enumerate((13, 20, 27, 39, 28, 17, 34, 43, 29, 19, 35, 25, 15)):
                px = x + 5 + index * 6
                painter.setBrush(QBrush(gradient))
                painter.drawRoundedRect(QRectF(px, 46 - height / 2, 3.5, height), 1.6, 1.6)
        elif self._decoration == 'checklist':
            painter.drawRoundedRect(QRectF(x + 15, 19, 65, 60), 5, 5)
            painter.drawRoundedRect(QRectF(x + 33, 15, 29, 9), 3, 3)
            for offset in (34, 48, 62):
                painter.drawRoundedRect(QRectF(x + 24, offset, 7, 7), 1, 1)
                painter.drawLine(x + 25, offset + 3, x + 27, offset + 5)
                painter.drawLine(x + 27, offset + 5, x + 31, offset)
                painter.drawLine(x + 40, offset + 3, x + 69, offset + 3)
        elif self._decoration == 'layers':
            for dx, dy in ((5, 37), (19, 28), (33, 19)):
                painter.drawRoundedRect(QRectF(x + dx, dy, 53, 49), 4, 4)
                painter.drawLine(x + dx + 10, dy + 13, x + dx + 35, dy + 13)
                painter.drawLine(x + dx + 10, dy + 20, x + dx + 28, dy + 20)
        else:
            for dx, dy in ((5, 38), (19, 29), (33, 20)):
                painter.drawRoundedRect(QRectF(x + dx, dy, 54, 48), 4, 4)
            painter.drawEllipse(QRectF(x + 64, 30, 6, 6))
            painter.drawLine(x + 42, 58, x + 53, 44)
            painter.drawLine(x + 53, 44, x + 63, 53)
            painter.drawLine(x + 63, 53, x + 70, 46)
            painter.drawLine(x + 70, 46, x + 78, 58)


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


class LibraryStructureList(QWidget):
    """Draw the quiet tree connector behind the six location rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('LibraryStructureList')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.rows = []

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.rows:
            return
        root, *children = self.rows
        if not children:
            return
        centers = [row.geometry().center().y() for row in children]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#365568'), 1))
        painter.drawLine(8, root.geometry().bottom() + 1, 8, centers[-1])
        for row, center in zip(children, centers):
            connector_accent = row.property('connectorAccent')
            painter.setPen(QPen(QColor(connector_accent or '#365568'), 1))
            painter.drawLine(8, center, row.x() - 1, center)
            painter.setBrush(QColor(connector_accent or START_PANEL_ICON_COLOR))
            painter.drawEllipse(QRectF(5, center - 3, 6, 6))
        painter.end()


class LibraryFolderButton(QPushButton):
    """Keep the folder action text separate from its trailing chevron."""

    def __init__(self, parent=None):
        super().__init__('Otwórz folder', parent)
        self.setObjectName('QuickAccessOpen')
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._chevron = QLabel(self)
        self._chevron.setObjectName('StartFolderChevron')
        self._chevron.setFixedSize(12, 12)
        self._chevron.setPixmap(alo_icon('chevron-right', START_PANEL_ICON_COLOR, 12).pixmap(12, 12))
        self._chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._chevron.move(self.width() - self._chevron.width() - 9,
                           (self.height() - self._chevron.height()) // 2)


class LibraryLocationRow(QFrame):
    def __init__(self, title: str, path: Path, icon_name: str, accent: str, parent=None, *, is_root: bool = False):
        super().__init__(parent)
        self.setObjectName('LibraryLocationRow')
        self.setProperty('accentColor', accent)
        self.setProperty('isRoot', is_root)
        self.setStyleSheet(f'QFrame#LibraryLocationRow {{ border-left:{5 if is_root else 3}px solid {accent}; }}')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setFixedHeight(72 if is_root else 64)
        self.path = Path(path)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(9)
        self.title_icon = QLabel()
        self.title_icon.setObjectName('QuickAccessIcon')
        self.title_icon.setPixmap(start_icon(icon_name, accent, 20).pixmap(20, 20))
        self.title_icon.setFixedSize(24, 24)
        self.title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_icon)
        text_column = QVBoxLayout()
        text_column.setSpacing(3)
        self.title_label = QLabel(title)
        self.title_label.setObjectName('QuickAccessTitle')
        title_row = QHBoxLayout(); title_row.setSpacing(7)
        title_row.addWidget(self.title_label)
        self.detail_label = QLabel('')
        self.detail_label.setObjectName('StartFolderOrganization')
        self.detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.detail_label.hide()
        title_row.addWidget(self.detail_label)
        title_row.addStretch(1)
        text_column.addLayout(title_row)
        self.path_label = ElidedPathLabel(self.path, accent)
        text_column.addWidget(self.path_label)
        layout.addLayout(text_column, 1)
        self.open_button = LibraryFolderButton(self)
        layout.addWidget(self.open_button)

        self.open_button.clicked.connect(self._open_folder)
        self.set_path(path)

    def set_path(self, path: Path) -> None:
        self.path = Path(path)
        self.path_label.set_path(self.path)
        self.refresh_availability()

    def refresh_availability(self) -> bool:
        available = self.path.is_dir()
        self.open_button.setEnabled(available)
        self.open_button.setProperty('available', available)
        self.open_button.style().unpolish(self.open_button)
        self.open_button.style().polish(self.open_button)
        self.open_button.setToolTip(ui_text(self, 'Otwórz folder w Eksploratorze' if available else 'Niedostępna'))
        self.open_button.setAccessibleDescription(ui_text(self, 'Dostępna' if available else 'Niedostępna'))
        self.open_button.update()
        return available

    def _open_folder(self) -> None:
        if self.refresh_availability():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

class DashboardPage(QWidget):
    refresh_requested = Signal()
    quick_view_requested = Signal(str)
    context_refresh_requested = Signal()

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._library_root = Path(settings.library.root)
        self._summary: dict[str, int] = {}
        self._health: dict[str, object] = {}
        self._folder_organization = 'none'

        viewport_layout = QVBoxLayout(self)
        viewport_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName('StartScroll')
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        viewport_layout.addWidget(self.scroll)
        body = QWidget()
        body.setObjectName('StartContent')
        self.scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(12, 7, 12, 6)
        root.setSpacing(7)

        self.hero = StudioHero(body)
        hero_text = QVBoxLayout(self.hero)
        hero_text.setContentsMargins(110, 32, 18, 25)
        hero_text.setSpacing(0)
        hero_brand = QLabel('<span>ALO</span> <span style="color:#4cde96">Music</span>')
        hero_brand.setObjectName('StartHeroBrand')
        hero_text.addWidget(hero_brand)
        hero_text.addSpacing(2)
        self.hero_subtitle = QLabel('Audio Library Organizer')
        self.hero_subtitle.setObjectName('StartHeroSubtitle')
        subtitle_font = self.hero_subtitle.font()
        subtitle_font.setPixelSize(12)
        subtitle_font.setLetterSpacing(subtitle_font.SpacingType.AbsoluteSpacing, 1.1)
        self.hero_subtitle.setFont(subtitle_font)
        hero_text.addWidget(self.hero_subtitle)
        hero_text.addSpacing(8)
        self.hero_title = QLabel('Twoja kolekcja. Pełna kontrola.')
        self.hero_title.setObjectName('StartHeroTitle')
        self.hero_title.setWordWrap(True)
        hero_text.addWidget(self.hero_title)
        hero_text.addSpacing(5)
        self.hero_description = QLabel('Porządkuj • uzupełniaj • analizuj')
        self.hero_description.setObjectName('StartHeroDescription')
        hero_text.addWidget(self.hero_description)
        hero_text.addStretch(1)
        root.addWidget(self.hero)

        cards_layout = QGridLayout()
        cards_layout.setHorizontalSpacing(10)
        cards_layout.setVerticalSpacing(0)
        self.cards = {
            'total': DashboardStatCard('Utwory', accent='#67baff'),
            'review': DashboardStatCard('Do sprawdzenia', accent='#ffb84d'),
            'duplicate': DashboardStatCard('Duplikaty', accent='#b987ff'),
            'missing_covers': DashboardStatCard('Brak okładki', accent='#63b3ed'),
        }
        for column, key in enumerate(('total', 'review', 'duplicate', 'missing_covers')):
            cards_layout.addWidget(self.cards[key], 0, column)
        root.addLayout(cards_layout)
        root.addSpacing(8)

        self.cards['total'].clicked.connect(lambda: self.quick_view_requested.emit('all'))
        self.cards['review'].clicked.connect(lambda: self.quick_view_requested.emit('review'))
        self.cards['duplicate'].clicked.connect(lambda: self.quick_view_requested.emit('duplicate'))
        self.cards['missing_covers'].clicked.connect(lambda: self.quick_view_requested.emit('no_cover'))

        self.attention_line = QWidget(body)
        self.attention_line.setObjectName('StartAttentionLine')
        attention_layout = QHBoxLayout(self.attention_line)
        attention_layout.setContentsMargins(0, 0, 0, 0); attention_layout.setSpacing(7)
        attention_icon = QLabel()
        attention_icon.setObjectName('StartAttentionIcon')
        attention_icon.setPixmap(start_icon('warning', '#ff6b6b', 16).pixmap(16, 16))
        attention_icon.setFixedSize(18, 18)
        attention_layout.addWidget(attention_icon)
        self.attention_text = QLabel('')
        self.attention_text.setObjectName('StartAttentionText')
        self.attention_text.setWordWrap(False)
        self.attention_text.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        attention_layout.addWidget(self.attention_text, 1)
        self.attention_line.hide()
        root.addWidget(self.attention_line)
        root.addSpacing(12)

        self.library_panels_host = QWidget()
        self.library_panels_host.setObjectName('StartLibraryPanels')
        self.library_panels_layout = QGridLayout(self.library_panels_host)
        self.library_panels_layout.setContentsMargins(0, 0, 0, 0)
        self.library_panels_layout.setSpacing(12)
        self.structure_panel, structure_layout = self._create_library_panel(
            'Struktura biblioteki', 'Główna biblioteka i powiązane lokalizacje robocze.')
        self.status_panel, status_layout = self._create_library_panel(
            'Stan biblioteki', 'Podsumowanie zawartości i analiz biblioteki.', compact_header=True)
        self.sources_panel, sources_layout = self._create_library_panel(
            'Źródła skanowania', 'Foldery dodane do skanowania biblioteki.')
        self.sources_panel.setFixedHeight(300)
        self.sources = ScanSourcesWidget(self.sources_panel)
        sources_layout.addWidget(self.sources, 1)
        self.right_column = QWidget(self.library_panels_host)
        right_layout = QVBoxLayout(self.right_column)
        right_layout.setContentsMargins(0, 0, 0, 0); right_layout.setSpacing(10)
        right_layout.addWidget(self.sources_panel)
        right_layout.addWidget(self.status_panel)

        self.quick_access_host = LibraryStructureList(self.structure_panel)
        self.quick_access_layout = QGridLayout(self.quick_access_host)
        self.quick_access_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_access_layout.setColumnMinimumWidth(0, 26)
        self.quick_access_layout.setColumnStretch(1, 1)
        self.quick_access_layout.setHorizontalSpacing(0)
        self.quick_access_layout.setVerticalSpacing(7)
        self.quick_access_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.location_cards: dict[str, LibraryLocationRow] = {}
        self._location_order = ('root', 'ready', 'review', 'not_selected', 'custom_folders', 'reports')
        self._create_location_cards(settings)
        structure_layout.addWidget(self.quick_access_host, 1)

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(5)
        self.stats_grid.setVerticalSpacing(4)
        self.stats_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        stat_labels = [
            ('covers', 'Utwory z okładką'),
            ('online', 'Utwory rozpoznane online'),
            ('size', 'Rozmiar biblioteki'),
            ('missing', 'Brakujące pliki'),
            ('suspicious', 'Metadane do sprawdzenia'),
            ('free_space', 'Wolne miejsce na dysku'),
        ]
        self._metric_order = tuple(key for key, _label in stat_labels)
        self.metric_cards = {}
        self.stats_values: dict[str, QLabel] = {}
        self.stats_progress = {}
        for index, (key, label) in enumerate(stat_labels):
            wide = key in {'covers', 'online'}
            box = QFrame()
            box.setObjectName('StartLibraryMetric')
            box.setProperty('metricKind', key)
            box.setFixedHeight(40 if wide else 36)
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(7, 5, 7, 5)
            box_layout.setSpacing(6)
            icon = QLabel()
            icon_name = {'covers': 'cover', 'online': 'cloud', 'suspicious': 'document_warning',
                         'size': 'database', 'missing': 'document_x', 'free_space': 'disk'}[key]
            icon.setObjectName('StartMetricIcon')
            icon.setPixmap(start_icon(icon_name, START_PANEL_ICON_COLOR, 14).pixmap(14, 14))
            icon.setFixedSize(18, 18)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box_layout.addWidget(icon)
            heading = QLabel(label)
            heading.setObjectName('StartMetricHeading')
            heading.setWordWrap(True)
            value = QLabel('—')
            value.setObjectName('StartMetricValue')
            value.setStyleSheet('font-size:11pt;font-weight:750;')
            if wide:
                box_layout.addWidget(heading, 1)
                value_column = QVBoxLayout()
                value_column.setSpacing(3)
                value_column.addWidget(value)
                from PySide6.QtWidgets import QProgressBar
                progress = QProgressBar()
                progress.setObjectName('StartMetricProgress')
                progress.setProperty('metricKind', key)
                progress.setRange(0, 100)
                progress.setTextVisible(False)
                value_column.addWidget(progress)
                box_layout.addLayout(value_column, 1)
                self.stats_progress[key] = progress
            else:
                box_layout.addWidget(heading, 1)
                box_layout.addWidget(value)
            self.stats_values[key] = value
            self.metric_cards[key] = box
            if wide:
                self.stats_grid.addWidget(box, index, 0, 1, 2)
            else:
                self.stats_grid.addWidget(box, 2 + (index - 2) // 2, (index - 2) % 2)

        status_layout.addLayout(self.stats_grid)
        root.addWidget(self.library_panels_host)
        self._reflow_panels()

        self.set_folder_organization('none')

    def _create_library_panel(self, title: str, subtitle: str, *, compact_header: bool = False):
        panel = QFrame(self.library_panels_host)
        panel.setObjectName('StartLibraryPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 6 if compact_header else 10, 12, 10)
        layout.setSpacing(5 if compact_header else 9)
        if compact_header:
            layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        header = QHBoxLayout()
        header.setSpacing(9)
        mark = QLabel()
        mark.setObjectName('LibrarySectionMark')
        mark.setFixedSize(20, 7)
        header.addWidget(mark)
        text = QVBoxLayout()
        text.setSpacing(1 if compact_header else 3)
        heading = QLabel(title)
        heading.setObjectName('StartPanelTitle')
        note = QLabel(subtitle)
        note.setObjectName('StartPanelSubtitle')
        note.setWordWrap(True)
        text.addWidget(heading)
        text.addWidget(note)
        header.addLayout(text, 1)
        layout.addLayout(header)
        return panel, layout

    def set_folder_organization(self, mode: str) -> None:
        self._folder_organization = mode if mode in {'none', 'artist', 'genre'} else 'none'
        text = {'none': 'Bez podfolderów', 'artist': 'Według wykonawcy', 'genre': 'Według gatunku'}[self._folder_organization]
        label = self.location_cards['ready'].detail_label
        label.setText('(' + ui_text(self, text) + ')')
        label.show()

    @staticmethod
    def _location_specs(settings: AppSettings) -> tuple[tuple[str, str, Path, str, str], ...]:
        library = settings.library
        return (
            ('root', 'Biblioteka główna', library.root, 'folder_root', '#58c9f3'),
            ('ready', 'Pliki wynikowe / GOTOWE', library.ready, 'folder_check', '#55d98b'),
            ('review', 'Do sprawdzenia', library.review, 'folder_warning', '#f0b44d'),
            ('not_selected', 'Niewybrane', library.not_selected, 'folder_x', '#e675a2'),
            ('custom_folders', 'Foldery z zaznaczonych utworów', library.custom_folders, 'folder_selected', '#8d9ba6'),
            ('reports', 'Raporty', library.reports, 'folder_report', '#50c9da'),
        )

    def _create_location_cards(self, settings: AppSettings) -> None:
        for index, (key, title, path, icon_name, accent) in enumerate(self._location_specs(settings)):
            card = LibraryLocationRow(title, path, icon_name, accent, self.quick_access_host, is_root=key == 'root')
            if key == 'custom_folders':
                card.setProperty('connectorAccent', accent)
            self.location_cards[key] = card
            self.quick_access_layout.addWidget(card, index, 0 if key == 'root' else 1, 1, 2 if key == 'root' else 1)
        self.quick_access_host.rows = list(self.location_cards.values())

    def _update_location_cards(self, settings: AppSettings) -> None:
        for key, _title, path, _icon_name, _accent in self._location_specs(settings):
            self.location_cards[key].set_path(path)

    def _reflow_panels(self) -> None:
        two_columns = self.width() >= 1050
        self.library_panels_layout.addWidget(self.structure_panel, 0, 0)
        self.library_panels_layout.addWidget(self.right_column, 0 if two_columns else 1, 1 if two_columns else 0)
        self.library_panels_layout.setColumnStretch(0, 63 if two_columns else 1)
        self.library_panels_layout.setColumnStretch(1, 37 if two_columns else 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'hero_title'):
            self.hero_title.setMaximumWidth(min(600, max(330, int(self.width() * .42))))
        if hasattr(self, 'library_panels_host'):
            self._reflow_panels()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_locations()
        self.context_refresh_requested.emit()
        self.sources.refresh()

    def refresh_locations(self) -> None:
        for card in self.location_cards.values():
            card.refresh_availability()

    def set_library(self, settings: AppSettings, library_name: str | None = None):
        self._library_root = Path(settings.library.root)
        self._update_location_cards(settings)
        if library_name:
            self.set_library_name(library_name)
        self.sources.refresh()
        if self._health:
            self._update_statistics()

    def set_library_name(self, name: str):
        # MainWindow keeps this callback when switching the active library.
        # Its root path is displayed only in the structure panel now.
        self._library_name = name or 'Biblioteka główna'

    def refresh_language(self) -> None:
        self.set_folder_organization(self._folder_organization)
        self.sources.refresh()
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
        self.refresh_locations()
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
        self.stats_progress['covers'].setValue(round(cover_percent))

        online_checked = int(self._health.get('online_checked', 0))
        online_percent = float(self._health.get('online_percent', 0.0))
        if available and online_percent <= 0.0 and online_checked:
            online_percent = online_checked / available * 100.0
        self.stats_values['online'].setText(f'{online_checked} / {available} ({online_percent:.0f}%)')
        self.stats_progress['online'].setValue(round(online_percent))

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
                free_label.setStyleSheet('font-size:11pt;font-weight:750;color:#ff6b6b;')
            elif free_gb < 20:
                free_label.setStyleSheet('font-size:11pt;font-weight:750;color:#ffb84d;')
            else:
                free_label.setStyleSheet('font-size:11pt;font-weight:750;')
        except OSError:
            free_label.setText('—')
            free_label.setStyleSheet('font-size:11pt;font-weight:750;')

    def _update_attention(self) -> None:
        review = int(self._summary.get('review', 0))
        missing_covers = int(self._health.get('missing_covers', 0))
        text = f'Wymaga uwagi: {review} utworów wymaga sprawdzenia metadanych • {missing_covers} utworów nie ma okładki'
        self.attention_text.setText(ui_text(self, text))
        self.attention_line.setVisible(bool(review or missing_covers))
