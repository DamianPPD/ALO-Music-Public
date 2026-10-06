from __future__ import annotations

from html import escape
from pathlib import Path
from weakref import ref

from PySide6.QtCore import Qt, Signal, QUrl, QStringListModel, QItemSelectionModel, QSignalBlocker, QEvent, QTimer, QRect, QSize
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPixmap, QColor, QBrush, QPen, QPainter, QDesktopServices, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QTableView, QLabel,
    QSplitter, QFrame, QPushButton, QInputDialog, QMessageBox, QAbstractItemView,
    QHeaderView, QScrollArea, QGridLayout, QMenu, QCompleter,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QLayout, QSizePolicy, QApplication,
)

from audio_library_organizer import __version__
from audio_library_organizer import crash_debug
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.duplicates.families import group_version_families
from audio_library_organizer.metadata.artwork import extract_embedded_cover
from audio_library_organizer.metadata.online_lock import is_online_locked
from audio_library_organizer.ui.state import (
    library_status_text, library_status_presentation, track_matches_quick_filter,
    display_bpm, effective_status, review_severity, track_matches_library_filters,
)
from audio_library_organizer.ui.widgets import ClickableCoverLabel, show_cover_preview
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.genre_input import build_genre_suggestions
from audio_library_organizer.ui.i18n import ui_text, localized_no_cover_name, tr, language_for
from audio_library_organizer.ui.icons import alo_icon, library_icon


PLAYING_ROLE = int(Qt.ItemDataRole.UserRole) + 1
VISUAL_ORDER_ROLE = int(Qt.ItemDataRole.UserRole) + 2
STATUS_ACCENT_ROLE = int(Qt.ItemDataRole.UserRole) + 3
STATUS_BACKGROUND_ROLE = int(Qt.ItemDataRole.UserRole) + 4
PLAYING_BACKGROUND = QColor('#142b23')
PLAYING_ACCENT = QColor('#4cb68a')
SELECTED_BACKGROUND = QColor('#203038')
SELECTED_ACCENT = QColor('#65b5c0')


def _paint_library_checkbox(painter, square, state, hovered=False):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor('#b9c3cb' if hovered else '#929ca5'), 1.4))
    painter.setBrush(QBrush(QColor('#172128')))
    painter.drawRoundedRect(square, 3, 3)
    painter.setPen(QPen(QColor('#edf0f2'), 2.1))
    if state == Qt.CheckState.PartiallyChecked:
        painter.drawLine(square.left() + 4, square.center().y(), square.right() - 4, square.center().y())
    elif state == Qt.CheckState.Checked:
        painter.drawLine(square.left() + 3, square.center().y(), square.center().x() - 1, square.bottom() - 4)
        painter.drawLine(square.center().x() - 1, square.bottom() - 4, square.right() - 3, square.top() + 4)
    painter.restore()


class LibraryCheckHeader(QHeaderView):
    """Tri-state checkbox for the currently visible Library rows."""

    def __init__(self, page):
        super().__init__(Qt.Orientation.Horizontal, page.table)
        self._page = ref(page)
        self._check_hovered = False
        self.setMouseTracking(True)

    def checkState(self):
        page = self._page()
        if page is None:
            return Qt.CheckState.Unchecked
        keys = {page._path_key(track) for track in page.visible_tracks()}
        checked = page._visible_checked_paths()
        if not keys or not checked:
            return Qt.CheckState.Unchecked
        if keys <= checked:
            return Qt.CheckState.Checked
        return Qt.CheckState.PartiallyChecked

    def toggleVisibleChecks(self):
        page = self._page()
        if page is not None:
            page._toggle_visible_checks()

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        if logical_index == 0:
            square = QRect(rect.center().x() - 8, rect.center().y() - 8, 16, 16)
            _paint_library_checkbox(painter, square, self.checkState(), self._check_hovered)

    def mouseMoveEvent(self, event):
        hovered = self.logicalIndexAt(event.position().toPoint()) == 0
        if hovered != self._check_hovered:
            self._check_hovered = hovered
            self.updateSection(0)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._check_hovered = False
        self.updateSection(0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.logicalIndexAt(event.position().toPoint()) == 0:
            self.toggleVisibleChecks()
            event.accept()
            return
        super().mousePressEvent(event)


class StableTableView(QTableView):
    """Keeps status visible and limits keyboard navigation to vertical rows."""

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        super().scrollTo(index, hint)
        self.horizontalScrollBar().setValue(0)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event.accept()
            self.horizontalScrollBar().setValue(0)
            return
        super().keyPressEvent(event)
        self.horizontalScrollBar().setValue(0)


class LibraryRowDelegate(QStyledItemDelegate):
    """Thin playing/selection outlines, with neutral checks."""

    @staticmethod
    def _check_state(index):
        value = index.data(Qt.ItemDataRole.CheckStateRole)
        # PySide may return an enum after setData and an int after setCheckState.
        return Qt.CheckState.Unchecked if value is None else Qt.CheckState(value)

    def editorEvent(self, event, model, option, index):
        if index.column() == 0 and event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            checked = self._check_state(index) == Qt.CheckState.Checked
            state = Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
            model.setData(index, state.value, Qt.ItemDataRole.CheckStateRole)
            return True
        return super().editorEvent(event, model, option, index)

    def paint(self, painter, option, index):
        clean = QStyleOptionViewItem(option)
        self.initStyleOption(clean, index)
        clean.state &= ~QStyle.StateFlag.State_HasFocus
        selected = bool(clean.state & QStyle.StateFlag.State_Selected)
        playing = bool(index.data(PLAYING_ROLE))
        if index.column() == 0:
            clean.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        if index.column() == 1:
            # Keep DisplayRole for sorting; show the icon and accessible tooltip.
            clean.text = ''
            clean.icon = QIcon()
            clean.features &= ~(QStyleOptionViewItem.ViewItemFeature.HasDisplay
                                | QStyleOptionViewItem.ViewItemFeature.HasDecoration)
        if selected or playing:
            clean.state &= ~QStyle.StateFlag.State_Selected
            background = SELECTED_BACKGROUND if selected else PLAYING_BACKGROUND
            clean.backgroundBrush = QBrush(background)
            painter.save()
            painter.fillRect(option.rect, background)
            painter.restore()
        elif clean.backgroundBrush.style() != Qt.BrushStyle.NoBrush:
            # QSS item rules may omit the model's background brush.
            painter.save()
            painter.fillRect(option.rect, clean.backgroundBrush)
            painter.restore()
        style = clean.widget.style() if clean.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, clean, painter, clean.widget)
        if index.column() == 1:
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            if icon is not None:
                square = QRect(option.rect.center().x() - 8, option.rect.center().y() - 8, 16, 16)
                icon.paint(painter, square, Qt.AlignmentFlag.AlignCenter, QIcon.Mode.Normal)
        if index.column() == 0:
            square = QRect(option.rect.center().x() - 8, option.rect.center().y() - 8, 16, 16)
            _paint_library_checkbox(painter, square, self._check_state(index),
                                    bool(clean.state & QStyle.StateFlag.State_MouseOver))
        accent = index.data(STATUS_ACCENT_ROLE)
        if selected or playing:
            painter.save()
            painter.setClipRect(option.rect)
            painter.setPen(QPen(PLAYING_ACCENT if playing else SELECTED_ACCENT, 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            row_rect = option.rect
            if isinstance(clean.widget, QTableView):
                row_rect = clean.widget.visualRect(index.siblingAtColumn(0)).united(
                    clean.widget.visualRect(index.siblingAtColumn(index.model().columnCount() - 1)))
            # One rectangle inside the viewport; never over the row-number header.
            painter.drawRect(row_rect.adjusted(1, 1, -2, -2))
            painter.restore()
        if index.column() == 0 and accent is not None and not selected and not playing:
            painter.save()
            painter.setPen(QPen(accent, 1.0))
            painter.drawLine(option.rect.left() + 1, option.rect.top() + 2,
                             option.rect.left() + 1, option.rect.bottom() - 2)
            painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(38, size.height()) if index.column() == 1 else size


class LibraryPage(QWidget):
    play_requested = Signal(object)
    track_selected = Signal(object)
    manual_field_requested = Signal(object, str, object, bool)
    edit_requested = Signal(object)
    approve_requested = Signal(object)
    undo_requested = Signal()
    create_collection_requested = Signal(object)
    playlist_requested = Signal(object)
    queue_next_requested = Signal(object)

    HEADERS = ['', 'Status', 'Wykonawca', 'Tytuł', 'Rok', 'Gatunek', 'BPM', 'Długość', 'Jakość', 'Format']
    CATEGORY_ICONS = {
        'all': 'all_tracks', 'ready': 'ready', 'duplicate': 'duplicates',
        'review': 'review', 'not_selected': 'unselected', 'no_cover': 'no_cover',
        'no_year': 'no_year',
    }
    CATEGORY_COLORS = {
        'all': '#bdcbd3', 'ready': '#6de6a5', 'duplicate': '#bd9bf7',
        'review': '#f4bd75', 'not_selected': '#bdcbd3',
        'no_cover': '#bdcbd3', 'no_year': '#bdcbd3',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('LibraryPage')
        self._tracks: list[TrackRecord] = []
        self._cover_pixmap = QPixmap()
        self._cover_note = ''
        self._cover_network = QNetworkAccessManager(self)
        self._cover_request_serial = 0
        self._history_provider = None
        self._playing_path: str | None = None
        self._version_family_by_path: dict[str, list[TrackRecord]] = {}
        self._checked_paths: set[str] = set()
        self._syncing_checks = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        filters = QVBoxLayout(); filters.setSpacing(5)
        self._filters_top = QHBoxLayout(); self._filters_top.setSpacing(8)
        self._filters_bottom = QHBoxLayout(); self._filters_bottom.setSpacing(8)
        filters.addLayout(self._filters_top); filters.addLayout(self._filters_bottom)
        self.search = QLineEdit(); self.search.setPlaceholderText('Szukaj: wykonawca, tytuł, album…')
        self.search.setMinimumWidth(170); self.search.setMaximumWidth(560)
        self.genre_filter = QLineEdit(); self.genre_filter.setPlaceholderText('Gatunki, np. Trance, Vocal')
        self.genre_filter.setMinimumWidth(160); self.genre_filter.setMaximumWidth(420)
        self.genre_filter.setToolTip('Wpisz kilka gatunków po przecinku. Utwór musi zawierać wszystkie podane gatunki.')
        self._genre_filter_model = QStringListModel([], self)
        self._genre_filter_completer = QCompleter(self._genre_filter_model, self); self._genre_filter_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive); self._genre_filter_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.genre_filter.setCompleter(self._genre_filter_completer)
        self.bpm_min = QLineEdit(); self.bpm_min.setPlaceholderText('BPM od')
        self.bpm_max = QLineEdit(); self.bpm_max.setPlaceholderText('BPM do')
        self.bpm_min.ensurePolished()
        bpm_width = max(84, self.bpm_min.fontMetrics().horizontalAdvance('BPM from') + 28)
        self.bpm_min.setFixedWidth(bpm_width); self.bpm_max.setFixedWidth(bpm_width)
        self.status = QComboBox(); self.status.setFixedWidth(190)
        self.status.addItem(library_icon('all_tracks', '#8fe9ad', 18), 'Wszystkie utwory', 'all')
        all_index = self.status.findData('all')
        self.status.insertSeparator(self.status.count())
        for label, key in [
            ('Gotowe', 'ready'), ('Duplikaty', 'duplicate'),
            ('Do sprawdzenia', 'review'), ('Nie wybieram', 'not_selected'),
        ]:
            self.status.addItem(library_icon(self.CATEGORY_ICONS[key], '#bdcbd3', 18), label, key)
        self.status.insertSeparator(self.status.count())
        for label, key in [('Brak okładki', 'no_cover'), ('Brak roku', 'no_year')]:
            self.status.addItem(library_icon(self.CATEGORY_ICONS[key], '#bdcbd3', 18), label, key)
        if all_index >= 0:
            self.status.setCurrentIndex(all_index)
        self.status.highlighted.connect(self._paint_category_icons)
        self.status.currentIndexChanged.connect(self._paint_category_icons)
        self.status.view().installEventFilter(self)
        self._paint_category_icons()

        self.format_filter = QComboBox()
        self.format_filter.setObjectName('LibraryFormatFilter')
        self.format_filter.setFixedWidth(160)
        self.format_filter.setToolTip(ui_text(self, 'Filtruj według formatu pliku'))
        self._sync_format_options()

        self.collection_btn = QPushButton('Utwórz folder z zaznaczonych', self); self.collection_btn.setObjectName('LibraryCollectionAction'); self.collection_btn.setIcon(library_icon('folder_add', '#cbd8df', 18)); self.collection_btn.clicked.connect(self._request_collection)
        self.playlist_btn = QPushButton('Utwórz playlistę', self); self.playlist_btn.setObjectName('LibraryPlaylistAction'); self.playlist_btn.setIcon(library_icon('playlist', '#cbd8df', 18)); self.playlist_btn.clicked.connect(self._request_playlist)

        self._toolbar_top = QHBoxLayout(); self._toolbar_top.setSpacing(8)
        self.view_state_label = QLabel('')
        self.view_state_label.setObjectName('LibraryViewState')
        self.view_state_label.setTextFormat(Qt.TextFormat.RichText)
        self.view_state_label.setWordWrap(False)
        self.view_state_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.reset_view_btn = QPushButton('Resetuj widok')
        self.reset_view_btn.setObjectName('LibrarySecondaryAction')
        self.reset_view_btn.setIcon(library_icon('reset', '#cbd8df', 18))
        self.reset_view_btn.clicked.connect(self._reset_view)
        self.reset_view_btn.setToolTip(ui_text(self, 'Resetuj widok'))
        self._layout_filters(self.width())
        root.addLayout(filters)
        self.selected_count = QLabel('')
        self.selected_count.setObjectName('LibrarySelectedCount')
        self.selected_count.hide()
        for button in (self.collection_btn, self.playlist_btn):
            button.setMinimumHeight(34)
            button.setMaximumHeight(34)
            button.setToolTip(ui_text(self, button.text()))
        self.playlist_btn.setToolTip(ui_text(self, 'Utwórz playlistę z zaznaczonych utworów'))
        for widget in (self.collection_btn, self.playlist_btn, self.selected_count):
            self._toolbar_top.addWidget(widget)
        self._toolbar_top.addWidget(self.view_state_label, 1)
        root.addLayout(self._toolbar_top)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.table = StableTableView()
        self.table.setHorizontalHeader(LibraryCheckHeader(self))
        self.table.installEventFilter(self)
        self.table.setItemDelegate(LibraryRowDelegate(self.table))
        self.table.setMouseTracking(True)
        self.table.setIconSize(QSize(16, 16))
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.setShowGrid(False)
        self.model = QStandardItemModel(0, len(self.HEADERS)); self.model.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setModel(self.model)
        self.model.itemChanged.connect(self._on_check_item_changed)
        header = self.table.horizontalHeader(); header.setStretchLastSection(False)
        for col in (0, 1, 4, 6, 7, 9): header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        for col in (2, 5, 8): header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 36); self._ensure_status_column_width()
        self.table.setColumnWidth(2, 165); self.table.setColumnWidth(4, 62)
        self.table.setColumnWidth(5, 150); self.table.setColumnWidth(6, 62); self.table.setColumnWidth(7, 76)
        self.table.setColumnWidth(8, 125); self.table.setColumnWidth(9, 72)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._play_selected)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        # Do not coerce currentIndex to column 0 on click. That was the cause of the visual "jump".
        self.split.addWidget(self.table)

        self.detail = QFrame(); self.detail.setObjectName('DetailPanel'); self.detail.setMinimumWidth(640); self.detail.setMaximumWidth(940)
        detail_outer = QVBoxLayout(self.detail); detail_outer.setContentsMargins(0, 0, 0, 0); detail_outer.setSpacing(0)
        header = QFrame(); header.setObjectName('LibraryDetailHeader'); header.setFixedHeight(50)
        header_row = QHBoxLayout(header); header_row.setContentsMargins(12, 8, 12, 8); header_row.setSpacing(8)
        self.detail_title_icon = QWidget(); self.detail_title_icon.setObjectName('LibraryDetailHeaderIcon')
        self.detail_title_icon.setFixedWidth(29)
        mark_layout = QHBoxLayout(self.detail_title_icon); mark_layout.setContentsMargins(0, 0, 0, 0)
        mark = QLabel(); mark.setObjectName('LibrarySectionMark'); mark.setFixedSize(20, 7)
        mark_layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self.detail_title_icon)
        self.detail_title = QLabel('Szczegóły utworu'); self.detail_title.setObjectName('LibraryDetailTitle')
        header_row.addWidget(self.detail_title); header_row.addStretch(1)
        self.details_btn = QPushButton('Zwiń szczegóły', self); self.details_btn.setObjectName('DetailsToggle')
        self.details_btn.setCheckable(True); self.details_btn.setChecked(True); self.details_btn.setFixedHeight(34)
        self.details_btn.setMinimumWidth(150)
        self.details_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.details_btn.setIcon(library_icon('collapse', '#aec4d3', 16)); self.details_btn.setIconSize(QSize(16, 16))
        self.details_btn.setToolTip(ui_text(self, 'Zwiń szczegóły'))
        self.details_btn.clicked.connect(self._toggle_details)
        detail_outer.addWidget(header)

        self.detail_scroll = QScrollArea(); self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); detail_root = QVBoxLayout(body)
        detail_root.setContentsMargins(10, 8, 10, 8); detail_root.setSpacing(8)
        detail_root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.detail_section_marks = []
        self.detail_section_titles = []

        self.version_family_card = QFrame(); self.version_family_card.setObjectName('VersionFamilyCard')
        self.version_family_card.hide()
        family_layout = QVBoxLayout(self.version_family_card); family_layout.setContentsMargins(0, 0, 0, 2); family_layout.setSpacing(0)
        family_head, self.family_toggle = self._detail_section_header('Rodzina wersji', disclosure=True)
        family_layout.addWidget(family_head)
        self.version_family_rows = QWidget(); self.version_family_rows.setObjectName('LibraryFamilyRows')
        self.version_family_rows_layout = QVBoxLayout(self.version_family_rows)
        self.version_family_rows_layout.setContentsMargins(8, 1, 8, 2); self.version_family_rows_layout.setSpacing(0)
        family_layout.addWidget(self.version_family_rows)
        self.family_toggle.clicked.connect(self._toggle_family)
        detail_root.addWidget(self.version_family_card)

        summary_row = QHBoxLayout(); summary_row.setContentsMargins(0, 0, 0, 0); summary_row.setSpacing(13)
        self.cover = ClickableCoverLabel('Brak okładki'); self.cover.setObjectName('LibraryDetailCover')
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter); self.cover.setFixedSize(218, 218)
        self.cover.clicked.connect(self._show_cover_preview)
        summary_row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)

        self.completeness_card = QFrame(); self.completeness_card.setObjectName('LibraryCompletenessCard')
        self.completeness_card.setProperty('state', 'incomplete')
        completeness_layout = QVBoxLayout(self.completeness_card)
        completeness_layout.setContentsMargins(12, 12, 12, 11); completeness_layout.setSpacing(9)
        completeness_top = QHBoxLayout(); completeness_top.setSpacing(7)
        self.completeness_icon = QLabel(); self.completeness_icon.setObjectName('LibraryCompletenessIcon')
        self.completeness_icon.setFixedSize(16, 16)
        self.completeness_icon.setPixmap(library_icon('status_review', '#ff927c', 16).pixmap(16, 16))
        completeness_top.addWidget(self.completeness_icon)
        self.completeness_title = QLabel('Dane niekompletne'); self.completeness_title.setObjectName('LibraryCompletenessTitle')
        self.completeness_title.setWordWrap(False)
        completeness_top.addWidget(self.completeness_title, 1)
        self.completeness_count = QLabel('0/6'); self.completeness_count.setObjectName('LibraryCompletenessCount')
        completeness_top.addWidget(self.completeness_count)
        completeness_layout.addLayout(completeness_top)
        separator = QFrame(); separator.setObjectName('LibraryDetailSeparator'); separator.setFixedHeight(1)
        completeness_layout.addWidget(separator)
        fields_row = QHBoxLayout(); fields_row.setContentsMargins(0, 0, 0, 0); fields_row.setSpacing(4)
        self.completeness_fields = {}
        self.completeness_field_icons = {}
        self._completeness_glyphs = {
            'artist': 'artist', 'title': 'music_note', 'year': 'calendar',
            'genre': 'tag', 'bpm': 'waveform', 'album': 'album',
        }
        for key, title in (('artist', 'Wykonawca'), ('title', 'Tytuł / wersja'),
                           ('year', 'Rok'), ('genre', 'Gatunek'), ('bpm', 'BPM'), ('album', 'Album')):
            if key == 'album':
                album_separator = QFrame(); album_separator.setObjectName('LibraryCompletenessAlbumSeparator')
                album_separator.setFixedSize(1, 108)
                fields_row.addWidget(album_separator, 0, Qt.AlignmentFlag.AlignVCenter)
            field = QFrame(); field.setObjectName('LibraryCompletenessFieldRow')
            field.setProperty('complete', False); field.setProperty('optional', key == 'album')
            field.setMinimumHeight(125)
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(3, 10, 3, 10); field_layout.setSpacing(8)
            field_layout.addStretch(1)
            icon = QLabel(); icon.setObjectName('LibraryCompletenessFieldIcon')
            icon.setFixedSize(32, 32)
            field_color = '#e5b86a' if key == 'album' else '#ff927c'
            icon.setPixmap(library_icon(self._completeness_glyphs[key], field_color, 32).pixmap(32, 32))
            field_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
            label = QLabel(title); label.setObjectName('LibraryCompletenessField')
            label.setProperty('complete', False); label.setProperty('optional', key == 'album')
            label.setWordWrap(True); label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            if key == 'title':
                label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                label.setMinimumWidth(44)
            field_layout.addWidget(label)
            field_layout.addStretch(1)
            fields_row.addWidget(field, 1)
            self.completeness_fields[key] = label
            self.completeness_field_icons[key] = icon
        completeness_layout.addLayout(fields_row, 1)
        summary_row.addWidget(self.completeness_card, 1)
        summary_row.setAlignment(self.completeness_card, Qt.AlignmentFlag.AlignTop)
        self.completeness_card.setMinimumHeight(218)
        summary_host = QWidget(); summary_host.setObjectName('LibrarySummary')
        summary_host.setMinimumHeight(218); summary_host.setLayout(summary_row)
        detail_root.addWidget(summary_host)

        self.detail_labels: dict[str, QLabel] = {}

        track_card = QFrame(); track_card.setObjectName('LibraryTrackDataCard')
        data_layout = QVBoxLayout(track_card); data_layout.setContentsMargins(0, 0, 0, 7); data_layout.setSpacing(0)
        data_head, _ = self._detail_section_header('Dane utworu'); data_layout.addWidget(data_head)
        data_layout.addSpacing(2)
        for key, title, icon in (('artist', 'Wykonawca', 'artist'),
                                 ('title', 'Tytuł / wersja', 'music_note'),
                                 ('album', 'Album / Release', 'album')):
            data_layout.addWidget(self._detail_value_row(key, title, icon))
        metrics = QHBoxLayout(); metrics.setContentsMargins(6, 5, 6, 0); metrics.setSpacing(0)
        for index, (key, title, icon) in enumerate((('year', 'Rok', 'calendar'),
                                                   ('bpm', 'BPM', 'waveform'),
                                                   ('genre', 'Gatunek', 'tag'))):
            if index:
                divider = QFrame(); divider.setObjectName('LibraryMetricDivider'); divider.setFixedWidth(1)
                metrics.addWidget(divider)
            metrics.addWidget(self._detail_metric(key, title, icon, centered=True), 1)
        data_layout.addLayout(metrics)
        detail_root.addWidget(track_card)

        self.technical_panel = QFrame(); self.technical_panel.setObjectName('LibraryTechnicalCard')
        technical_layout = QVBoxLayout(self.technical_panel)
        technical_layout.setContentsMargins(0, 0, 0, 7); technical_layout.setSpacing(5)
        technical_head, _ = self._detail_section_header('Dane techniczne')
        technical_layout.addWidget(technical_head)
        first_row = QHBoxLayout(); first_row.setContentsMargins(6, 3, 6, 0); first_row.setSpacing(0)
        for index, (key, title, icon) in enumerate((('format', 'Format', 'file_format'),
                                                   ('bitrate', 'Bitrate', 'waveform'),
                                                   ('sample_rate', 'Sample rate', 'waveform'),
                                                   ('channels', 'Kanały', 'channels'))):
            if index:
                divider = QFrame(); divider.setObjectName('LibraryMetricDivider'); divider.setFixedWidth(1)
                first_row.addWidget(divider)
            first_row.addWidget(self._detail_metric(key, title, icon), 1)
        technical_layout.addLayout(first_row)
        second_row = QHBoxLayout(); second_row.setContentsMargins(6, 2, 6, 0); second_row.setSpacing(0)
        for index, (key, title, icon) in enumerate((('duration', 'Czas trwania', 'clock'),
                                                   ('size', 'Rozmiar pliku', 'file_size'))):
            if index:
                divider = QFrame(); divider.setObjectName('LibraryMetricDivider'); divider.setFixedWidth(1)
                second_row.addWidget(divider)
            second_row.addWidget(self._detail_metric(key, title, icon), 1)
        technical_layout.addLayout(second_row)
        detail_root.addWidget(self.technical_panel)
        detail_root.addStretch(1)
        self.detail_scroll.setWidget(body); detail_outer.addWidget(self.detail_scroll, 1)

        actions_bar = QFrame(); actions_bar.setObjectName('PinnedDetailActions')
        actions = QHBoxLayout(actions_bar); actions.setContentsMargins(14, 10, 14, 10); actions.setSpacing(0)
        self.detail_edit = QPushButton('Edytuj metadane'); self.detail_edit.setObjectName('LibraryDetailEdit')
        self.detail_edit.setIcon(library_icon('metadata_edit', '#a5f3c1', 22)); self.detail_edit.setIconSize(QSize(22, 22))
        self.detail_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.detail_edit.setToolTip(ui_text(self, 'Edytuj metadane'))
        self.detail_edit.clicked.connect(self._edit_current)
        actions.addWidget(self.detail_edit)
        self.detail_actions = actions_bar
        detail_outer.addWidget(actions_bar)
        self.split.addWidget(self.detail); self.split.setSizes([960, 640])
        self._expanded_detail_sizes = [960, 640]
        self._toolbar_top.addWidget(self.details_btn, 0, Qt.AlignmentFlag.AlignRight)
        root.addWidget(self.split, 1)

        self.search.textChanged.connect(self._filters_changed)
        self.genre_filter.textChanged.connect(self._filters_changed)
        self.bpm_min.textChanged.connect(self._filters_changed)
        self.bpm_max.textChanged.connect(self._filters_changed)
        self.status.currentIndexChanged.connect(self._filters_changed)
        self.format_filter.currentIndexChanged.connect(self._filters_changed)
        self.table.selectionModel().selectionChanged.connect(self._show_detail)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._update_view_state_label)
        self._update_view_state_label()
        self._update_selection_count()

    def _detail_section_header(self, title: str, *, disclosure: bool = False):
        host = QFrame(); host.setObjectName('LibrarySectionHeader')
        row = QHBoxLayout(host); row.setContentsMargins(12, 6, 10, 6); row.setSpacing(8)
        mark = QLabel(); mark.setObjectName('LibrarySectionMark'); mark.setFixedSize(20, 7)
        row.addWidget(mark); self.detail_section_marks.append(mark)
        heading = QPushButton(title) if disclosure else QLabel(title)
        heading.setObjectName('LibrarySectionTitle')
        if disclosure:
            heading.setCheckable(True); heading.setChecked(True)
        row.addWidget(heading, 1); self.detail_section_titles.append(heading)
        if disclosure:
            self.family_arrow = QPushButton(); self.family_arrow.setObjectName('LibraryFamilyArrow')
            self.family_arrow.setIcon(library_icon('collapse', '#a8bdca', 15))
            self.family_arrow.setIconSize(QSize(15, 15)); self.family_arrow.setFixedSize(24, 22)
            self.family_arrow.clicked.connect(heading.click)
            row.addWidget(self.family_arrow)
        return host, heading

    def _detail_value_row(self, key: str, title: str, icon: str) -> QFrame:
        host = QFrame(); host.setObjectName('LibraryValueRow')
        row = QHBoxLayout(host); row.setContentsMargins(12, 8, 12, 8); row.setSpacing(8)
        glyph = QLabel(); glyph.setObjectName('LibraryFieldIcon')
        glyph.setPixmap(library_icon(icon, '#8babc0', 17).pixmap(17, 17)); row.addWidget(glyph)
        label = QLabel(title); label.setObjectName('LibraryFieldName'); label.setFixedWidth(123); row.addWidget(label)
        value = QLabel('—'); value.setObjectName('LibraryFieldValue'); value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(value, 1); self.detail_labels[key] = value
        return host

    def _detail_metric(self, key: str, title: str, icon: str, *, centered: bool = False) -> QWidget:
        host = QWidget(); host.setObjectName('LibraryMetric')
        if centered:
            host.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            column = QVBoxLayout(host); column.setContentsMargins(7, 8, 7, 8); column.setSpacing(2)
            heading = QHBoxLayout(); heading.setSpacing(5)
            heading.addStretch(1)
            glyph = QLabel(); glyph.setObjectName('LibraryFieldIcon')
            glyph.setPixmap(library_icon(icon, '#8babc0', 16).pixmap(16, 16)); heading.addWidget(glyph)
            label = QLabel(title); label.setObjectName('LibraryMetricName'); heading.addWidget(label)
            heading.addStretch(1); column.addLayout(heading)
            value = QLabel('—'); value.setObjectName('LibraryMetricValue'); value.setWordWrap(True)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            column.addWidget(value)
            self.detail_labels[key] = value
            return host
        row = QHBoxLayout(host); row.setContentsMargins(7, 8, 7, 8); row.setSpacing(5)
        glyph = QLabel(); glyph.setObjectName('LibraryFieldIcon')
        glyph.setPixmap(library_icon(icon, '#8babc0', 16).pixmap(16, 16)); row.addWidget(glyph)
        stack = QVBoxLayout(); stack.setSpacing(1)
        label = QLabel(title); label.setObjectName('LibraryMetricName'); stack.addWidget(label)
        value = QLabel('—'); value.setObjectName('LibraryMetricValue'); value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        stack.addWidget(value); row.addLayout(stack, 1)
        self.detail_labels[key] = value
        return host

    def resizeEvent(self, event):
        if hasattr(self, '_filters_top'):
            self._layout_filters(event.size().width())
        super().resizeEvent(event)

    def _layout_filters(self, width: int):
        compact = width < 1260
        if compact == getattr(self, '_filters_compact', None):
            return
        self._filters_compact = compact
        widgets = (self.search, self.genre_filter, self.bpm_min, self.bpm_max,
                   self.status, self.format_filter, self.reset_view_btn)
        for widget in widgets:
            self._filters_top.removeWidget(widget)
            self._filters_bottom.removeWidget(widget)
        for layout in (self._filters_top, self._filters_bottom):
            while layout.takeAt(0):
                pass
        if compact:
            for widget in widgets[:4]:
                self._filters_top.addWidget(widget, 2 if widget is self.search else 1 if widget is self.genre_filter else 0)
            for widget in widgets[4:]:
                self._filters_bottom.addWidget(widget)
            self._filters_bottom.addStretch(1)
        else:
            for widget in widgets:
                self._filters_top.addWidget(widget, 2 if widget is self.search else 1 if widget is self.genre_filter else 0)
        legend = getattr(self, '_status_legend_button', None)
        if legend is not None:
            self._filters_top.addWidget(legend, 0, Qt.AlignmentFlag.AlignRight)

    def set_history_provider(self, provider):
        self._history_provider = provider

    def _paint_category_icons(self, hovered_index: int = -1):
        selected = self.status.currentData()
        self.status.setStyleSheet('color: #6de6a5;')
        for key, icon_name in self.CATEGORY_ICONS.items():
            index = self.status.findData(key)
            if index < 0:
                continue
            active = key == selected
            color = '#6de6a5' if active or index == hovered_index else self.CATEGORY_COLORS[key]
            self.status.setItemIcon(index, library_icon(icon_name, color, 18))
            item = self.status.model().item(index)
            if item is not None:
                item.setForeground(QBrush(QColor(color)))
                item.setBackground(QBrush(QColor('#173c2d')) if active or index == hovered_index else QBrush())

    @staticmethod
    def _format_of(track: TrackRecord) -> str:
        return track.path.suffix.lstrip('.').upper() or '—'

    def _sync_format_options(self):
        chosen = self.format_filter.currentData() or ''
        formats = sorted({self._format_of(track) for track in self._tracks} - {'—'})
        with QSignalBlocker(self.format_filter):
            self.format_filter.clear()
            caption = ui_text(self, 'Format') + ': '
            self.format_filter.addItem(caption + ui_text(self, 'Wszystkie'), '')
            for value in formats:
                self.format_filter.addItem(caption + value, value)
            index = self.format_filter.findData(chosen)
            self.format_filter.setCurrentIndex(max(0, index))
        self._update_format_accent()

    def _update_format_accent(self):
        active = bool(self.format_filter.currentData())
        self.format_filter.setProperty('formatActive', active)
        self.format_filter.style().unpolish(self.format_filter)
        self.format_filter.style().polish(self.format_filter)

    def _on_check_item_changed(self, item):
        if self._syncing_checks or item.column() != 0:
            return
        key = self._path_key(item.data(Qt.ItemDataRole.UserRole))
        if key is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_paths.add(key)
        else:
            self._checked_paths.discard(key)
        self._update_selection_count()

    def _visible_checked_paths(self) -> set[str]:
        return {self._path_key(item.data(Qt.ItemDataRole.UserRole))
                for row in range(self.model.rowCount())
                if (item := self.model.item(row, 0)) is not None
                and item.checkState() == Qt.CheckState.Checked
                and item.data(Qt.ItemDataRole.UserRole) is not None}

    def _update_selection_count(self):
        visible = {self._path_key(track) for track in self.visible_tracks()}
        self._checked_paths.intersection_update(visible)
        changed_rows = []
        with QSignalBlocker(self.model):
            for row in range(self.model.rowCount()):
                item = self.model.item(row, 0)
                key = self._path_key(item.data(Qt.ItemDataRole.UserRole))
                state = Qt.CheckState.Checked if key in self._checked_paths else Qt.CheckState.Unchecked
                if item.checkState() != state:
                    item.setCheckState(state)
                    changed_rows.append(row)
        # Batch changes suppress dataChanged; notify row views as well as the header.
        if changed_rows:
            self._syncing_checks = True
            try:
                self.model.dataChanged.emit(self.model.index(min(changed_rows), 0), self.model.index(max(changed_rows), 0),
                                            [int(Qt.ItemDataRole.CheckStateRole)])
            finally:
                self._syncing_checks = False
        count = len(self._checked_paths)
        self.selected_count.setText(f'{ui_text(self, "Zaznaczono:")} {count}')
        self.selected_count.setVisible(count > 0)
        self.collection_btn.setEnabled(count > 0)
        self.playlist_btn.setEnabled(count > 0)
        self.table.viewport().update()
        self.table.horizontalHeader().viewport().update()

    def _filters_changed(self, *_):
        self._checked_paths.clear()
        self.refresh(clear_checks=True)
        self.table.selectionModel().clearSelection()

    def _toggle_visible_checks(self):
        visible = {self._path_key(track) for track in self.visible_tracks()}
        if not visible:
            return
        self._checked_paths = set() if visible <= self._checked_paths else visible
        self._update_selection_count()

    def _ensure_status_column_width(self) -> None:
        """Fit the header and a centered 16 px icon, including after view restore."""
        text_width = self.table.horizontalHeader().fontMetrics().horizontalAdvance(ui_text(self, 'Status'))
        required = max(58, text_width + 26)
        if self.table.columnWidth(1) != required:
            self.table.setColumnWidth(1, required)

    def eventFilter(self, watched, event):
        handled = super().eventFilter(watched, event)
        if watched is getattr(self, 'table', None) and event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
            QEvent.Type.StyleChange,
        }:
            QTimer.singleShot(0, self, self._ensure_status_column_width)
        if watched is self.status.view() and event.type() == QEvent.Type.Hide:
            self._paint_category_icons()
        return handled

    def set_tracks(self, tracks: list[TrackRecord]):
        self._tracks = tracks
        self._checked_paths.clear()
        self._sync_format_options()
        self._version_family_by_path = {}
        for family in group_version_families(tracks):
            for member in family:
                try:
                    key = str(Path(member.path).resolve()).casefold()
                except OSError:
                    key = str(member.path).casefold()
                self._version_family_by_path[key] = family
        self._update_genre_suggestions()
        self.refresh(preserve_order=True, clear_checks=True)
        self.table.selectionModel().clearSelection()

    @staticmethod
    def _path_key(track: TrackRecord | None) -> str | None:
        if track is None:
            return None
        try:
            return str(Path(track.path).resolve()).casefold()
        except OSError:
            return str(track.path).casefold()

    def _capture_view_state(self) -> dict:
        header = self.table.horizontalHeader()
        selection = self.table.selectionModel()
        selected_paths: list[str] = []
        visual_order: list[str] = []
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            track = item.data(Qt.ItemDataRole.UserRole) if item else None
            key = self._path_key(track)
            if key is not None:
                visual_order.append(key)
        if selection is not None:
            for index in selection.selectedRows(0):
                item = self.model.item(index.row(), 0)
                track = item.data(Qt.ItemDataRole.UserRole) if item else None
                key = self._path_key(track)
                if key is not None:
                    selected_paths.append(key)
        return {
            'sort_column': header.sortIndicatorSection(),
            'sort_order': header.sortIndicatorOrder(),
            'vertical_scroll': self.table.verticalScrollBar().value(),
            'horizontal_scroll': self.table.horizontalScrollBar().value(),
            'current_path': self._path_key(self._current_track()),
            'selected_paths': selected_paths,
            'visual_order': visual_order,
            'column_widths': [self.table.columnWidth(col) for col in range(self.model.columnCount())],
        }

    def _restore_view_state(self, state: dict):
        widths = state.get('column_widths') or []
        for col, width in enumerate(widths):
            if col < self.model.columnCount() and width > 0:
                self.table.setColumnWidth(col, int(width))
        self._ensure_status_column_width()

        wanted = set(state.get('selected_paths') or [])
        current_path = state.get('current_path')
        selection = self.table.selectionModel()
        if selection is not None:
            selection.clearSelection()
            current_index = None
            for row in range(self.model.rowCount()):
                item = self.model.item(row, 0)
                track = item.data(Qt.ItemDataRole.UserRole) if item else None
                key = self._path_key(track)
                index = self.model.index(row, 0)
                if key in wanted:
                    selection.select(
                        index,
                        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                    )
                if key == current_path:
                    current_index = index
            if current_index is not None:
                selection.setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.NoUpdate)
                self._show_detail()

        self.table.verticalScrollBar().setValue(int(state.get('vertical_scroll', 0)))
        self.table.horizontalScrollBar().setValue(int(state.get('horizontal_scroll', 0)))

    def _update_view_state_label(self, *_):
        header = self.table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        if 0 <= sort_column < len(self.HEADERS):
            sort_name = ui_text(self, self.HEADERS[sort_column])
        else:
            sort_name = ui_text(self, self.HEADERS[0])
        arrow = '↑' if header.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder else '↓'

        language = language_for(self)
        filters: list[tuple[str, str]] = []
        status_text = self.status.currentText().strip()
        if (self.status.currentData() or 'all') != 'all':
            color = {'review': '#d8a23a', 'error': '#f34d64', 'problem': '#f34d64',
                     'ready': '#84cfa6', 'duplicate': '#b6a0ce'}.get(
                self.status.currentData(), '#a5b2bd')
            filters.append((status_text, color))
        if self.search.text().strip():
            filters.append((f'{tr("library.view.search", language)} {self.search.text().strip()}', '#a5b2bd'))
        if self.genre_filter.text().strip():
            filters.append((f'{tr("library.view.genre", language)} {self.genre_filter.text().strip()}', '#b6a0ce'))
        if self.bpm_min.text().strip() or self.bpm_max.text().strip():
            bpm_from = self.bpm_min.text().strip() or '—'
            bpm_to = self.bpm_max.text().strip() or '—'
            filters.append((f'BPM {bpm_from}–{bpm_to}', '#a5b2bd'))
        if self.format_filter.currentData():
            filters.append((f'{ui_text(self, "Format")}: {self.format_filter.currentData()}', '#85bdd6'))
        if not filters:
            filters.append((tr('library.view.none', language), '#a5b2bd'))
        sort_label = tr('library.view.sort', language)
        filters_label = tr('library.view.filters', language)
        sort_value = f'{sort_name} {arrow}'
        filter_text = ' · '.join(value for value, _ in filters)
        filter_html = ' · '.join(f'<span style="color:{color}">{escape(value)}</span>'
                                 for value, color in filters)
        self.view_state_label.setText(
            f'{escape(sort_label)} <span style="color:#65b5c0;font-weight:600">{escape(sort_value)}</span>'
            f' &nbsp; • &nbsp; {escape(filters_label)} {filter_html}')
        tooltip = f'{sort_label} {sort_value}   •   {filters_label} {filter_text}'
        self.view_state_label.setToolTip(f'<qt><span style="white-space:pre-wrap">{escape(tooltip)}</span></qt>')

    def _reset_view(self):
        self._checked_paths.clear()
        blockers = [
            QSignalBlocker(self.search), QSignalBlocker(self.genre_filter),
            QSignalBlocker(self.bpm_min), QSignalBlocker(self.bpm_max), QSignalBlocker(self.status),
            QSignalBlocker(self.format_filter),
        ]
        self.search.clear()
        self.genre_filter.clear()
        self.bpm_min.clear()
        self.bpm_max.clear()
        all_index = self.status.findData('all')
        if all_index >= 0:
            self.status.setCurrentIndex(all_index)
        self.format_filter.setCurrentIndex(0)
        del blockers
        self._paint_category_icons()
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.verticalScrollBar().setValue(0)
        self.refresh(clear_checks=True)
        self.table.selectionModel().clearSelection()

    def refresh(self, *_, preserve_order: bool = False, clear_checks: bool = False):
        checked = set() if clear_checks else self._checked_paths.copy()
        self._sync_format_options()
        view_state = self._capture_view_state()
        text = self.search.text().casefold().strip()
        wanted = self.status.currentData() or 'all'
        wanted_format = self.format_filter.currentData() or ''
        previous_order = view_state.get('visual_order') or []
        order_map = {key: index for index, key in enumerate(previous_order)} if preserve_order else {}
        sort_order = view_state.get('sort_order', Qt.SortOrder.AscendingOrder)
        next_order = len(order_map)
        visible_keys = set()

        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        for track in self._tracks:
            if not track_matches_quick_filter(track, wanted):
                continue
            if wanted_format and self._format_of(track) != wanted_format:
                continue
            if not track_matches_library_filters(track, genres_text=self.genre_filter.text(), bpm_min=self.bpm_min.text(), bpm_max=self.bpm_max.text()):
                continue
            hay = ' '.join(filter(None, [track.artist, track.title, track.album, track.genre, track.filename])).casefold()
            if text and text not in hay:
                continue
            duration = '' if track.duration_seconds is None else f'{int(track.duration_seconds)//60}:{int(track.duration_seconds)%60:02d}'
            quality = ' · '.join(x for x in [track.codec or '', f'{track.bitrate_kbps} kb/s' if track.bitrate_kbps else ''] if x)
            presentation = library_status_presentation(track)
            is_playing = self._track_is_playing(track)
            status_text = ui_text(self, library_status_text(track))
            values = [
                '', status_text, track.artist or '', track.title or '', track.year or '', track.genre or '',
                display_bpm(track.bpm), duration, quality, self._format_of(track),
            ]
            items = [QStandardItem(str(value)) for value in values]
            status = effective_status(track)
            problem = status == 'error' or (status == 'review' and review_severity(track) == 'critical')
            tint, row_accent = None, None
            if problem:
                icon_name, icon_color, tint = 'status_problem', '#f34d64', '#23181d'
                row_accent = QColor('#bc3d50')
            elif status == 'review':
                icon_name, icon_color, tint = 'status_review', '#d8a23a', '#1b1b18'
                row_accent = QColor('#b8862f')
            else:
                icon_name = {'ready': 'status_ready', 'duplicate': 'duplicates', 'not_selected': 'cancel'}.get(status, 'info')
                icon_color = '#35d893' if status == 'ready' else presentation.accent
            icon_factory = library_icon if problem or status in {'ready', 'review'} else alo_icon
            items[1].setIcon(icon_factory(icon_name, icon_color, 16))
            key = self._path_key(track)
            visible_keys.add(key)
            order_index = order_map.get(key)
            if order_index is None:
                order_index = next_order
                next_order += 1
            stable_sort_value = order_index if sort_order == Qt.SortOrder.AscendingOrder else -order_index
            for item in items:
                item.setEditable(False)
                item.setData(is_playing, PLAYING_ROLE)
                item.setData(stable_sort_value, VISUAL_ORDER_ROLE)
                item.setData(row_accent, STATUS_ACCENT_ROLE)
                if tint is not None:
                    item.setBackground(QBrush(QColor(tint)))
                item.setData(item.background(), STATUS_BACKGROUND_ROLE)
            items[0].setCheckable(True)
            items[0].setCheckState(Qt.CheckState.Checked if key in checked else Qt.CheckState.Unchecked)
            items[3].setToolTip(track.title or '')
            items[2].setToolTip(track.artist or '')
            items[0].setData(track, Qt.ItemDataRole.UserRole)
            if is_playing:
                playing_background = QBrush(PLAYING_BACKGROUND)
                for item in items:
                    item.setBackground(playing_background)
            items[1].setToolTip(self._playing_status_tooltip(track, is_playing))
            items[1].setData(items[1].toolTip(), Qt.ItemDataRole.AccessibleTextRole)
            self.model.appendRow(items)

        self._checked_paths = checked & visible_keys
        preserve_existing_order = bool(order_map)
        if preserve_existing_order:
            self.model.setSortRole(VISUAL_ORDER_ROLE)
        self.table.setSortingEnabled(True)
        if preserve_existing_order:
            # The refresh has now restored the visual order. Future explicit
            # header clicks sort by the visible cell values again.
            self.model.setSortRole(Qt.ItemDataRole.DisplayRole)
        self._restore_view_state(view_state)
        self._show_detail()
        self._update_selection_count()
        self._update_format_accent()
        self._update_view_state_label()

    def _track_is_playing(self, track: TrackRecord) -> bool:
        if not self._playing_path:
            return False
        try:
            return str(Path(track.path).resolve()).casefold() == self._playing_path
        except OSError:
            return str(track.path).casefold() == self._playing_path

    def set_playing_track(self, track: TrackRecord | None):
        new_path = self._path_key(track)
        if new_path == self._playing_path:
            return
        old_path = self._playing_path
        self._playing_path = new_path
        # This notification can arrive inside QTableView.doubleClicked. Keep
        # its model items and active indexes alive throughout that event.
        self._update_playing_row_state(old_path, new_path)

    def _playing_status_tooltip(self, track: TrackRecord, is_playing: bool) -> str:
        status = effective_status(track)
        problem = status == 'error' or (status == 'review' and review_severity(track) == 'critical')
        caption = ui_text(self, 'PROBLEM' if problem else library_status_text(track))
        if is_playing:
            caption += ' • ' + ui_text(self, 'TERAZ GRA')
        if is_online_locked(track):
            caption += ' • ' + ui_text(self, 'Zablokowany przed ponownym rozpoznaniem online')
        elif not is_playing and 'duplicate_primary' in track.locked_fields:
            caption += ' • ' + ui_text(self, 'Ten plik został przez Ciebie wybrany w zakładce Duplikaty.')
        return caption

    def _update_playing_row_state(self, old_path: str | None, new_path: str | None):
        changed_rows = []
        with QSignalBlocker(self.model):
            for row in range(self.model.rowCount()):
                track = self.model.item(row, 0).data(Qt.ItemDataRole.UserRole)
                key = self._path_key(track)
                if key not in {old_path, new_path}:
                    continue
                is_playing = key == new_path
                for column in range(self.model.columnCount()):
                    item = self.model.item(row, column)
                    item.setData(is_playing, PLAYING_ROLE)
                    item.setBackground(QBrush(PLAYING_BACKGROUND) if is_playing
                                       else item.data(STATUS_BACKGROUND_ROLE))
                status_item = self.model.item(row, 1)
                status_item.setToolTip(self._playing_status_tooltip(track, is_playing))
                status_item.setData(status_item.toolTip(), Qt.ItemDataRole.AccessibleTextRole)
                changed_rows.append(row)
        # Batch role changes repaint only affected rows. Suppress checkbox
        # reconciliation for these notifications; their check state is untouched.
        previous_syncing = self._syncing_checks
        self._syncing_checks = True
        try:
            for row in changed_rows:
                self.model.dataChanged.emit(self.model.index(row, 0),
                                            self.model.index(row, self.model.columnCount() - 1),
                                            [PLAYING_ROLE, int(Qt.ItemDataRole.BackgroundRole),
                                             int(Qt.ItemDataRole.ToolTipRole), int(Qt.ItemDataRole.AccessibleTextRole)])
        finally:
            self._syncing_checks = previous_syncing

    def _current_track(self):
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        item = self.model.item(idx.row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _play_selected(self, _index=None):
        track = self._current_track()
        if track:
            crash_debug.record('library.play.request', **crash_debug.track_context(track.path))
            self.play_requested.emit(track)

    def _show_detail(self, *_):
        t = self._current_track()
        if not t:
            return
        crash_debug.record('library.selection.enter', **crash_debug.track_context(t.path))
        self.track_selected.emit(t)
        self.detail_labels['artist'].setText(t.artist or '—')
        self.detail_labels['title'].setText(t.title or '—')
        self.detail_labels['album'].setText(t.album or '—')
        self.detail_labels['year'].setText(t.year or '—')
        self.detail_labels['bpm'].setText(display_bpm(t.bpm) or '—')
        self.detail_labels['genre'].setText(t.genre or '—')
        self.detail_labels['format'].setText(self._format_of(t))
        self.detail_labels['bitrate'].setText(f'{t.bitrate_kbps} kb/s' if t.bitrate_kbps else '—')
        self.detail_labels['sample_rate'].setText(f'{t.sample_rate_hz / 1000:g} kHz' if t.sample_rate_hz else '—')
        self.detail_labels['channels'].setText(ui_text(self, 'Stereo' if t.channels == 2 else 'Mono') if t.channels in (1, 2) else str(t.channels or '—'))
        self.detail_labels['duration'].setText('—' if t.duration_seconds is None else f'{int(t.duration_seconds)//60}:{int(t.duration_seconds)%60:02d}')
        self.detail_labels['size'].setText('—' if not t.size_bytes else f'{t.size_bytes / (1024 * 1024):.1f} MB')

        try:
            family_key = str(Path(t.path).resolve()).casefold()
        except OSError:
            family_key = str(t.path).casefold()
        family = self._version_family_by_path.get(family_key, [])
        self.version_family_card.setVisible(len(family) > 1)
        if len(family) > 1:
            self.family_toggle.setText(f'{ui_text(self, "Rodzina wersji")} ({len(family)} {ui_text(self, "utwory")})')
            while self.version_family_rows_layout.count():
                item = self.version_family_rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for member in family:
                row = QFrame(); row.setObjectName('LibraryFamilyRow')
                row.setProperty('current', member is t)
                contents = QHBoxLayout(row); contents.setContentsMargins(10, 4, 10, 4); contents.setSpacing(7)
                indicator = QLabel('◉' if member is t else '○'); indicator.setObjectName('LibraryFamilyIndicator')
                contents.addWidget(indicator)
                title = QLabel(member.title or member.filename); title.setObjectName('LibraryFamilyTitle')
                title.setWordWrap(True); contents.addWidget(title, 1)
                duration = '—' if member.duration_seconds is None else f'{int(member.duration_seconds)//60}:{int(member.duration_seconds)%60:02d}'
                contents.addWidget(QLabel(duration))
                if member is t:
                    marker = QLabel(ui_text(self, '(aktualnie)')); marker.setObjectName('LibraryFamilyCurrent')
                    contents.addWidget(marker)
                self.version_family_rows_layout.addWidget(row)

        complete = {
            'artist': bool(t.artist), 'title': bool(t.title), 'album': bool(t.album),
            'year': bool(t.year), 'bpm': t.bpm is not None, 'genre': bool(t.genre),
        }
        self.completeness_count.setText(f'{sum(complete.values())}/6')
        state = ('complete' if all(complete.values()) else
                 'partial' if all(complete[key] for key in ('artist', 'title', 'year', 'genre', 'bpm')) else 'incomplete')
        self.completeness_title.setText(tr(f'library.details.{state}', language_for(self)))
        self.completeness_card.setProperty('state', state)
        self.completeness_card.setProperty('complete', all(complete.values()))
        glyph, color = {'complete': ('status_ready', '#2de1ac'),
                        'partial': ('empty_check', '#e5b86a'),
                        'incomplete': ('status_review', '#ff927c')}[state]
        self.completeness_icon.setPixmap(library_icon(glyph, color, 16).pixmap(16, 16))
        for widget in (self.completeness_card, self.completeness_title, self.completeness_count):
            widget.style().unpolish(widget); widget.style().polish(widget)
        for key, label in self.completeness_fields.items():
            label.setText(ui_text(self, {
                'artist': 'Wykonawca', 'title': 'Tytuł / wersja', 'album': 'Album',
                'year': 'Rok', 'bpm': 'BPM', 'genre': 'Gatunek',
            }[key]))
            color = '#84e8c4' if complete[key] else '#e5b86a' if key == 'album' else '#ff927c'
            field_icon = library_icon(self._completeness_glyphs[key], color, 32)
            self.completeness_field_icons[key].setPixmap(field_icon.pixmap(32, 32))
            label.setProperty('complete', complete[key])
            field = label.parentWidget()
            field.setProperty('complete', complete[key])
            field.style().unpolish(field); field.style().polish(field)
            label.style().unpolish(label); label.style().polish(label)
        self._load_cover(t)
        crash_debug.record('library.selection.done', **crash_debug.track_context(t.path))

    @staticmethod
    def _external_cover_url(track: TrackRecord) -> str | None:
        if track.cover_art_url:
            return track.cover_art_url
        if track.musicbrainz_release_id:
            return f'https://coverartarchive.org/release/{track.musicbrainz_release_id}/front-500'
        return None

    def _load_cover(self, track: TrackRecord):
        self._cover_request_serial += 1; serial = self._cover_request_serial
        choice = (track.cover_choice or 'auto').casefold()
        if choice == 'placeholder':
            self._set_cover_pixmap(QPixmap(str(asset_path(localized_no_cover_name(self)))), 'Brak potwierdzonej okładki — grafika zastępcza ALO Music.')
            return
        if track.manual_cover_path and Path(track.manual_cover_path).is_file() and choice in {'auto', 'manual'}:
            self._set_cover_pixmap(QPixmap(track.manual_cover_path), 'Okładka wybrana ręcznie.')
            return
        if choice != 'source':
            external_url = self._external_cover_url(track)
            if external_url:
                self._cover_pixmap = QPixmap(); self.cover.setPixmap(QPixmap()); self.cover.setText(ui_text(self, 'Ładowanie…'))
                self._load_remote_cover(track, external_url, serial); return
        self._show_source_cover_fallback(track, 'Okładka źródłowa / zapasowa.')

    def _load_remote_cover(self, track: TrackRecord, url: str, serial: int):
        request = QNetworkRequest(QUrl(url)); request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f'ALO Music/{__version__}')
        reply = self._cover_network.get(request); reply.finished.connect(lambda r=reply, t=track, s=serial: self._remote_cover_finished(r, t, s))

    def _remote_cover_finished(self, reply: QNetworkReply, track: TrackRecord, serial: int):
        try:
            if serial != self._cover_request_serial or self._current_track() is not track:
                return
            if reply.error() == QNetworkReply.NetworkError.NoError:
                pix = QPixmap(); pix.loadFromData(bytes(reply.readAll()))
                if not pix.isNull():
                    self._set_cover_pixmap(pix, 'Okładka pobrana z dopasowanego wydania.'); return
            self._show_source_cover_fallback(track, 'Nie udało się pobrać okładki zewnętrznej — użyta zostanie źródłowa lub zastępcza.')
        finally:
            reply.deleteLater()

    def _show_source_cover_fallback(self, track: TrackRecord, note: str):
        pix = QPixmap(); embedded = extract_embedded_cover(track.path)
        if embedded:
            pix.loadFromData(embedded[0]); self._set_cover_pixmap(pix, note); return
        self._set_cover_pixmap(QPixmap(str(asset_path(localized_no_cover_name(self)))), 'Brak potwierdzonej okładki — grafika zastępcza ALO Music.')

    def _set_cover_pixmap(self, pix: QPixmap, note: str):
        self._cover_pixmap = pix; self._cover_note = note
        if pix.isNull():
            self.cover.setPixmap(QPixmap()); self.cover.setText(ui_text(self, 'Brak okładki'))
        else:
            self.cover.setText(''); self.cover.setPixmap(pix.scaled(218, 218, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.cover.setToolTip(ui_text(self, note or 'Kliknij okładkę, aby powiększyć'))

    def _show_cover_preview(self):
        show_cover_preview(self, self._cover_pixmap, title=ui_text(self, 'Powiększona okładka'), note=ui_text(self, self._cover_note))

    def _toggle_details(self, checked: bool):
        if not checked and self.detail.isVisible():
            self._expanded_detail_sizes = self.split.sizes()
        self.detail.setVisible(checked)
        caption = 'Zwiń szczegóły' if checked else 'Rozwiń szczegóły'
        self.details_btn.setText(ui_text(self, caption))
        self.details_btn.setToolTip(ui_text(self, caption))
        self.details_btn.setProperty('_alo_pl_text', caption)
        self.details_btn.setProperty('_alo_pl_tooltip', caption)
        self.details_btn.setIcon(library_icon('collapse' if checked else 'expand', '#aec4d3', 16))
        if checked:
            self.split.setSizes(self._expanded_detail_sizes)
        else:
            self.split.setSizes([self.split.width(), 0])

    def _toggle_family(self, checked: bool):
        self.version_family_rows.setVisible(checked)
        self.family_arrow.setIcon(library_icon('collapse' if checked else 'expand', '#a8bdca', 15))

    def select_track_by_path(self, path: Path) -> bool:
        target = str(Path(path).resolve()).casefold()
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0); candidate = item.data(Qt.ItemDataRole.UserRole) if item else None
            if candidate is not None and str(Path(candidate.path).resolve()).casefold() == target:
                self.table.clearSelection(); index = self.model.index(row, 0)
                self.table.setCurrentIndex(index); self.table.selectRow(row); self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
                if not self.details_btn.isChecked():
                    self.details_btn.setChecked(True); self._toggle_details(True)
                self._show_detail()
                return True
        return False

    def select_track(self, track: TrackRecord):
        target = str(Path(track.path).resolve()).casefold()
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0); candidate = item.data(Qt.ItemDataRole.UserRole) if item else None
            if candidate is not None and str(Path(candidate.path).resolve()).casefold() == target:
                self.table.clearSelection(); index = self.model.index(row, 0); self.table.setCurrentIndex(index); self.table.selectRow(row)
                self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
                if not self.details_btn.isChecked():
                    self.details_btn.setChecked(True); self._toggle_details(True)
                return True
        return False

    def _selected_tracks(self) -> list[TrackRecord]:
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()}); tracks: list[TrackRecord] = []
        for row in rows:
            item = self.model.item(row, 0)
            if item is not None:
                track = item.data(Qt.ItemDataRole.UserRole)
                if track is not None:
                    tracks.append(track)
        return tracks

    def _checked_tracks(self) -> list[TrackRecord]:
        return [self.model.item(row, 0).data(Qt.ItemDataRole.UserRole)
                for row in range(self.model.rowCount())
                if self.model.item(row, 0).checkState() == Qt.CheckState.Checked]

    def visible_tracks(self) -> list[TrackRecord]:
        """Return tracks in the exact filtered/sorted order shown to the user."""
        tracks: list[TrackRecord] = []
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            track = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if track is not None:
                tracks.append(track)
        return tracks

    def genre_suggestions(self) -> list[str]:
        return build_genre_suggestions([track.genre for track in self._tracks])

    def _update_genre_suggestions(self):
        self._genre_filter_model.setStringList(self.genre_suggestions())

    def _request_playlist(self):
        tracks = self._checked_tracks()
        if not tracks:
            QMessageBox.information(self, ui_text(self, 'Brak zaznaczenia'), ui_text(self, 'Zaznacz utwory, które mają trafić do playlisty.'))
            return
        self.playlist_requested.emit([track.path for track in tracks])

    def _show_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if index.isValid():
            self.table.selectRow(index.row())
        track = self._current_track()
        if track is None:
            return
        menu = QMenu(self)
        play = menu.addAction(library_icon('play', '#cbd8df', 18), ui_text(self, 'Odtwórz'))
        play_next = menu.addAction(library_icon('next', '#cbd8df', 18), ui_text(self, 'Odtwórz jako następny'))
        edit = menu.addAction(library_icon('metadata_edit', '#9af0b6', 18), ui_text(self, 'Edytuj metadane'))
        menu.addSeparator()
        folder = menu.addAction(library_icon('folder', '#cbd8df', 18), ui_text(self, 'Dodaj do folderów z zaznaczonych utworów'))
        playlist = menu.addAction(library_icon('playlist', '#cbd8df', 18), ui_text(self, 'Utwórz playlistę z zaznaczonych'))
        menu.addSeparator()
        reveal = menu.addAction(library_icon('folder', '#cbd8df', 18), ui_text(self, 'Pokaż w Eksploratorze'))
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is play:
            self.play_requested.emit(track)
        elif chosen is play_next:
            self.queue_next_requested.emit(track)
        elif chosen is edit:
            self.edit_requested.emit(track)
        elif chosen is folder:
            tracks = self._checked_tracks() or [track]
            self.create_collection_requested.emit(tracks)
        elif chosen is playlist:
            tracks = self._checked_tracks() or [track]
            self.playlist_requested.emit([t.path for t in tracks])
        elif chosen is reveal:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(track.path.parent)))

    def _edit_current(self):
        track = self._current_track()
        if not track:
            QMessageBox.information(self, ui_text(self, 'Brak zaznaczenia'), ui_text(self, 'Najpierw zaznacz utwór w bibliotece.')); return
        self.edit_requested.emit(track)

    def _request_collection(self):
        tracks = self._checked_tracks()
        if not tracks:
            QMessageBox.information(self, ui_text(self, 'Brak zaznaczenia'), ui_text(self, 'Zaznacz utwory, które mają trafić do nowego folderu.'))
            return
        self.create_collection_requested.emit(tracks)

    def _edit_selected_genre(self):
        tracks = self._selected_tracks()
        if not tracks:
            QMessageBox.information(self, ui_text(self, 'Brak zaznaczenia'), ui_text(self, 'Zaznacz jeden lub wiele utworów w tabeli.')); return
        current = tracks[0].genre or ''
        value, ok = QInputDialog.getText(self, ui_text(self, 'Zmień gatunek'), ui_text(self, f'Nowy gatunek dla {len(tracks)} utworów:'), text=current)
        if ok and value.strip():
            self.manual_field_requested.emit(tracks, 'genre', value.strip(), True)
