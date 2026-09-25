from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl, QStringListModel, QItemSelectionModel, QSignalBlocker, QEvent, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPixmap, QColor, QBrush, QPen, QAction, QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QTableView, QLabel,
    QSplitter, QFrame, QPushButton, QInputDialog, QMessageBox, QAbstractItemView,
    QHeaderView, QScrollArea, QGridLayout, QMenu, QCompleter,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle,
)

from audio_library_organizer import __version__
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.duplicates.families import group_version_families
from audio_library_organizer.metadata.artwork import extract_embedded_cover
from audio_library_organizer.metadata.online_lock import is_online_locked
from audio_library_organizer.ui.state import (
    identification_summary, metadata_completeness, library_status_text,
    library_status_presentation, track_matches_quick_filter,
    display_bpm, effective_status, track_matches_library_filters,
)
from audio_library_organizer.ui.widgets import ClickableCoverLabel, show_cover_preview
from audio_library_organizer.ui.confidence import ConfidenceWidget
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.genre_input import build_genre_suggestions
from audio_library_organizer.ui.i18n import ui_text, localized_no_cover_name
from audio_library_organizer.ui.icons import alo_icon


PLAYING_ROLE = int(Qt.ItemDataRole.UserRole) + 1
VISUAL_ORDER_ROLE = int(Qt.ItemDataRole.UserRole) + 2
PLAYING_BACKGROUND = QColor('#153a42')
PLAYING_ACCENT = QColor('#31d7c8')


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
    """Draw a persistent playing-row highlight without native cell focus outlines."""

    def paint(self, painter, option, index):
        clean = QStyleOptionViewItem(option)
        clean.state &= ~QStyle.StateFlag.State_HasFocus
        playing = bool(index.data(PLAYING_ROLE))
        if playing:
            clean.state &= ~QStyle.StateFlag.State_Selected
            painter.save()
            painter.fillRect(option.rect, PLAYING_BACKGROUND)
            painter.restore()
        super().paint(painter, clean, index)
        if playing:
            painter.save()
            painter.setPen(QPen(PLAYING_ACCENT, 2.0))
            painter.drawLine(option.rect.left(), option.rect.top() + 1, option.rect.right(), option.rect.top() + 1)
            painter.drawLine(option.rect.left(), option.rect.bottom() - 1, option.rect.right(), option.rect.bottom() - 1)
            if index.column() == 0:
                painter.drawLine(option.rect.left() + 1, option.rect.top(), option.rect.left() + 1, option.rect.bottom())
            painter.restore()


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

    HEADERS = ['Status', 'Wykonawca', 'Tytuł', 'Rok', 'Gatunek', 'BPM', 'Długość', 'Jakość']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: list[TrackRecord] = []
        self._cover_pixmap = QPixmap()
        self._cover_note = ''
        self._cover_network = QNetworkAccessManager(self)
        self._cover_request_serial = 0
        self._history_provider = None
        self._playing_path: str | None = None
        self._version_family_by_path: dict[str, list[TrackRecord]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        filters = QHBoxLayout(); filters.setSpacing(8)
        self.search = QLineEdit(); self.search.setPlaceholderText('Szukaj: wykonawca, tytuł, album…')
        self.search.setMinimumWidth(280); self.search.setMaximumWidth(560)
        self.genre_filter = QLineEdit(); self.genre_filter.setPlaceholderText('Gatunki, np. Trance, Vocal')
        self.genre_filter.setMinimumWidth(220); self.genre_filter.setMaximumWidth(420)
        self.genre_filter.setToolTip('Wpisz kilka gatunków po przecinku. Utwór musi zawierać wszystkie podane gatunki.')
        self._genre_filter_model = QStringListModel([], self)
        self._genre_filter_completer = QCompleter(self._genre_filter_model, self); self._genre_filter_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive); self._genre_filter_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.genre_filter.setCompleter(self._genre_filter_completer)
        self.bpm_min = QLineEdit(); self.bpm_min.setPlaceholderText('BPM od'); self.bpm_min.setFixedWidth(72)
        self.bpm_max = QLineEdit(); self.bpm_max.setPlaceholderText('BPM do'); self.bpm_max.setFixedWidth(72)
        self.status = QComboBox(); self.status.setFixedWidth(190)
        # The default library view is always first and visually distinct.
        self.status.addItem(alo_icon('library', '#8fe9ad', 15), 'Wszystkie utwory', 'all')
        all_index = self.status.findData('all')
        if all_index >= 0:
            item = self.status.model().item(all_index)
            if item is not None:
                self.status.model().item(all_index).setData(QBrush(QColor('#173c2d')), Qt.ItemDataRole.BackgroundRole)
                item.setForeground(QBrush(QColor('#8fe9ad')))
                font = item.font(); font.setBold(True); item.setFont(font)
        self.status.insertSeparator(self.status.count())
        for icon_name, color, label, key in [
            ('status', '#43d17d', 'Gotowe', 'ready'),
            ('duplicates', '#b987ff', 'Duplikaty', 'duplicate'),
            ('warning', '#ffb84d', 'Do sprawdzenia', 'review'),
            ('cancel', '#9aa8b3', 'Nie wybieram', 'not_selected'),
        ]:
            self.status.addItem(alo_icon(icon_name, color, 15), label, key)
        self.status.insertSeparator(self.status.count())
        for label, key in [
            ('Brak okładki', 'no_cover'), ('Brak roku', 'no_year'),
        ]:
            self.status.addItem(label, key)
        if all_index >= 0:
            self.status.setCurrentIndex(all_index)

        self.edit_genre = QPushButton('Gatunek dla zaznaczonych'); self.edit_genre.setIcon(alo_icon('edit', '#b8c8d2', 16)); self.edit_genre.clicked.connect(self._edit_selected_genre)
        self.select_all_btn = QPushButton('Zaznacz wszystko'); self.select_all_btn.setObjectName('LibrarySecondaryAction'); self.select_all_btn.clicked.connect(self._select_all_visible)
        self.collection_btn = QPushButton('Utwórz folder z zaznaczonych'); self.collection_btn.setObjectName('LibraryCollectionAction'); self.collection_btn.setIcon(alo_icon('folder', '#70d9f2', 16)); self.collection_btn.clicked.connect(self._request_collection)
        self.playlist_btn = QPushButton('Utwórz playlistę (.m3u8)'); self.playlist_btn.setObjectName('LibraryPlaylistAction'); self.playlist_btn.setIcon(alo_icon('add_tracks', '#9bd2ff', 16)); self.playlist_btn.clicked.connect(self._request_playlist)
        self.details_btn = QPushButton('Szczegóły utworu'); self.details_btn.setObjectName('DetailsToggle'); self.details_btn.setIcon(alo_icon('info', '#71d7ef', 16))
        self.details_btn.setCheckable(True); self.details_btn.clicked.connect(self._toggle_details)

        filters.addWidget(self.search)
        filters.addWidget(self.genre_filter)
        filters.addWidget(self.bpm_min)
        filters.addWidget(self.bpm_max)
        filters.addWidget(self.status)
        filters.addWidget(self.edit_genre)
        filters.addWidget(self.select_all_btn)
        filters.addWidget(self.collection_btn)
        filters.addWidget(self.playlist_btn)
        filters.addStretch(0)
        filters.addWidget(self.details_btn)
        root.addLayout(filters)

        view_controls = QHBoxLayout(); view_controls.setSpacing(8)
        self.view_state_label = QLabel('')
        self.view_state_label.setObjectName('LibraryViewState')
        self.view_state_label.setWordWrap(False)
        self.reset_view_btn = QPushButton('Resetuj widok')
        self.reset_view_btn.setObjectName('LibrarySecondaryAction')
        self.reset_view_btn.clicked.connect(self._reset_view)
        view_controls.addWidget(self.view_state_label, 1)
        view_controls.addWidget(self.reset_view_btn)
        root.addLayout(view_controls)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.table = StableTableView()
        self.table.installEventFilter(self)
        self.table.setItemDelegate(LibraryRowDelegate(self.table))
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
        header = self.table.horizontalHeader(); header.setStretchLastSection(False)
        for col in (0, 3, 5, 6): header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        for col in (1, 4, 7): header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._ensure_status_column_width(); self.table.setColumnWidth(1, 165); self.table.setColumnWidth(3, 62)
        self.table.setColumnWidth(4, 150); self.table.setColumnWidth(5, 62); self.table.setColumnWidth(6, 76); self.table.setColumnWidth(7, 125)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._play_selected)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        # Do not coerce currentIndex to column 0 on click. That was the cause of the visual "jump".
        self.split.addWidget(self.table)

        self.detail = QFrame(); self.detail.setObjectName('DetailPanel'); self.detail.setMinimumWidth(640); self.detail.setMaximumWidth(940)
        detail_outer = QVBoxLayout(self.detail); detail_outer.setContentsMargins(0, 0, 0, 0); detail_outer.setSpacing(0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); detail_root = QVBoxLayout(body); detail_root.setContentsMargins(8, 6, 8, 6); detail_root.setSpacing(6)
        dtitle = QLabel('Szczegóły utworu'); dtitle.setStyleSheet('font-size:14pt;font-weight:750;'); detail_root.addWidget(dtitle)
        self.quick_file_info = QLabel(''); self.quick_file_info.setObjectName('QuickFileInfo'); self.quick_file_info.setWordWrap(True); detail_root.addWidget(self.quick_file_info)

        self.version_family_card = QFrame(); self.version_family_card.setObjectName('VersionFamilyCard'); self.version_family_card.setVisible(False)
        family_layout = QVBoxLayout(self.version_family_card); family_layout.setContentsMargins(10, 7, 10, 7); family_layout.setSpacing(3)
        family_title = QLabel('Rodzina wersji'); family_title.setObjectName('VersionFamilyHeading'); family_layout.addWidget(family_title)
        self.version_family_label = QLabel(''); self.version_family_label.setObjectName('VersionFamilyText'); self.version_family_label.setWordWrap(True); family_layout.addWidget(self.version_family_label)
        detail_root.addWidget(self.version_family_card)

        summary_row = QHBoxLayout(); summary_row.setSpacing(10)
        cover_box = QVBoxLayout(); cover_box.setSpacing(4)
        self.cover = ClickableCoverLabel('Brak okładki'); self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter); self.cover.setFixedSize(196, 196)
        self.cover.setStyleSheet('background:#0b0e13;border:1px solid #2c3442;border-radius:10px;color:#758195;')
        self.cover.clicked.connect(self._show_cover_preview)
        cover_box.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignHCenter)
        self.cover_caption = QLabel('Kliknij okładkę, aby powiększyć'); self.cover_caption.setWordWrap(True); self.cover_caption.setObjectName('MutedText'); self.cover_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_caption.setMaximumWidth(196); cover_box.addWidget(self.cover_caption)
        cover_host = QWidget(); cover_host.setLayout(cover_box); summary_row.addWidget(cover_host, 0)

        self.review_box = QFrame(); self.review_box.setObjectName('ReviewReasonCard')
        review_lay = QVBoxLayout(self.review_box); review_lay.setContentsMargins(10, 8, 10, 8); review_lay.setSpacing(4)
        self.confirmed_heading = QLabel('POTWIERDZONE'); self.confirmed_heading.setObjectName('ConfirmedHeading')
        self.confirmed_label = QLabel('—'); self.confirmed_label.setWordWrap(True); self.confirmed_label.setObjectName('ConfirmedText')
        self.missing_heading = QLabel('BRAKI'); self.missing_heading.setObjectName('MissingHeading')
        self.missing_label = QLabel('—'); self.missing_label.setWordWrap(True); self.missing_label.setObjectName('MissingText')
        self.complete_label = QLabel(''); self.complete_label.setWordWrap(True); self.complete_label.setObjectName('CompleteText'); self.complete_label.setVisible(False)
        review_lay.addWidget(self.confirmed_heading); review_lay.addWidget(self.confirmed_label)
        review_lay.addWidget(self.missing_heading); review_lay.addWidget(self.missing_label); review_lay.addWidget(self.complete_label); review_lay.addStretch(1)
        summary_row.addWidget(self.review_box, 1)
        detail_root.addLayout(summary_row)

        self.detail_labels: dict[str, QLabel] = {}

        primary = QFrame(); primary.setObjectName('PrimaryMetadataCard')
        pg = QGridLayout(primary); pg.setContentsMargins(8, 5, 8, 5); pg.setHorizontalSpacing(12); pg.setVerticalSpacing(2)
        primary_title = QLabel('DANE GŁÓWNE'); primary_title.setObjectName('MetadataSectionTitle'); pg.addWidget(primary_title, 0, 0, 1, 4)
        primary_fields = [
            ('artist', 'WYKONAWCA', 1, 0, 1, 4),
            ('title', 'TYTUŁ / WERSJA', 3, 0, 1, 4),
            ('year', 'ROK', 5, 0, 1, 1), ('bpm', 'BPM', 5, 1, 1, 1), ('genre', 'GATUNEK', 5, 2, 1, 2),
        ]
        self._add_detail_fields(pg, primary_fields)
        detail_root.addWidget(primary)

        additional = QFrame(); additional.setObjectName('AdditionalMetadataCard')
        ag = QGridLayout(additional); ag.setContentsMargins(8, 5, 8, 5); ag.setHorizontalSpacing(12); ag.setVerticalSpacing(2)
        additional_title = QLabel('DANE DODATKOWE'); additional_title.setObjectName('MetadataSectionTitleOptional'); ag.addWidget(additional_title, 0, 0, 1, 4)
        additional_fields = [
            ('album', 'ALBUM / RELEASE', 1, 0, 1, 2), ('discogs', 'DISCOGS URL', 1, 2, 1, 2),
            ('comment', 'KOMENTARZ', 3, 0, 1, 4),
        ]
        self._add_detail_fields(ag, additional_fields)
        detail_root.addWidget(additional)

        match_box = QFrame(); match_box.setObjectName('MatchInfoCard'); match_box.setProperty('lowConfidence', False)
        self.match_box = match_box
        mg = QGridLayout(match_box); mg.setContentsMargins(8, 7, 8, 7); mg.setHorizontalSpacing(12); mg.setVerticalSpacing(4)
        confidence_head = QLabel('PEWNOŚĆ'); confidence_head.setObjectName('DetailFieldHeading'); mg.addWidget(confidence_head, 0, 0)
        self.confidence_widget = ConfidenceWidget(None, match_box); mg.addWidget(self.confidence_widget, 1, 0)
        sources_head = QLabel('ŹRÓDŁA DANYCH'); sources_head.setObjectName('DetailFieldHeading'); mg.addWidget(sources_head, 0, 1)
        sources = QLabel('—'); sources.setWordWrap(True); sources.setObjectName('DetailFieldValue'); mg.addWidget(sources, 1, 1); self.detail_labels['sources'] = sources
        reasons_head = QLabel('DOPASOWANIE'); reasons_head.setObjectName('DetailFieldHeading'); mg.addWidget(reasons_head, 2, 0, 1, 2)
        reasons = QLabel('—'); reasons.setWordWrap(True); reasons.setObjectName('DetailFieldValue'); mg.addWidget(reasons, 3, 0, 1, 2); self.detail_labels['reasons'] = reasons
        detail_root.addWidget(match_box)

        history_box = QFrame(); history_box.setObjectName('HistoryCard')
        hl = QVBoxLayout(history_box); hl.setContentsMargins(8, 5, 8, 5); hl.setSpacing(2)
        self.history_heading = QLabel('HISTORIA ZMIAN W SESJI'); self.history_heading.setObjectName('DetailFieldHeading'); hl.addWidget(self.history_heading)
        self.history_label = QLabel('Brak ręcznych zmian.'); self.history_label.setWordWrap(True); self.history_label.setObjectName('MutedText'); hl.addWidget(self.history_label)
        detail_root.addWidget(history_box)

        self.technical_toggle = QPushButton('DANE TECHNICZNE'); self.technical_toggle.setObjectName('DisclosureButton'); self.technical_toggle.setIcon(alo_icon('settings', '#82b8cf', 16)); self.technical_toggle.setCheckable(True); self.technical_toggle.clicked.connect(self._toggle_technical)
        detail_root.addWidget(self.technical_toggle)
        self.technical_panel = QFrame(); self.technical_panel.setObjectName('TechnicalPanel'); self.technical_panel.setVisible(False)
        tg = QGridLayout(self.technical_panel); tg.setContentsMargins(8, 5, 8, 5); tg.setHorizontalSpacing(12); tg.setVerticalSpacing(2)
        technical_fields = [
            ('duration', 'DŁUGOŚĆ', 0, 0, 1, 1), ('size', 'ROZMIAR PLIKU', 0, 1, 1, 1),
            ('quality', 'JAKOŚĆ', 2, 0, 1, 2), ('path', 'PLIK ŹRÓDŁOWY', 4, 0, 1, 2), ('hash', 'SHA-256', 6, 0, 1, 2),
        ]
        self._add_detail_fields(tg, technical_fields, technical=True)
        detail_root.addWidget(self.technical_panel)
        detail_root.addStretch(1)
        scroll.setWidget(body); detail_outer.addWidget(scroll, 1)

        actions_bar = QFrame(); actions_bar.setObjectName('PinnedDetailActions')
        actions = QHBoxLayout(actions_bar); actions.setContentsMargins(12, 9, 12, 9); actions.setSpacing(8)
        self.undo = QPushButton('Cofnij ostatnią zmianę'); self.undo.setIcon(alo_icon('undo', '#a9bac4', 17)); self.undo.clicked.connect(self.undo_requested.emit)
        edit = QPushButton('Edytuj metadane'); edit.setIcon(alo_icon('edit', '#75dff8', 17)); edit.clicked.connect(self._edit_current)
        self.approve = QPushButton('ZATWIERDŹ JAKO GOTOWE'); self.approve.setObjectName('ApproveButton'); self.approve.setIcon(alo_icon('status', '#e9fff1', 17)); self.approve.clicked.connect(self._approve_current)
        actions.addWidget(self.undo); actions.addStretch(1); actions.addWidget(edit); actions.addWidget(self.approve)
        detail_outer.addWidget(actions_bar)

        self.split.addWidget(self.detail); self.split.setSizes([840, 720]); self.detail.setVisible(False)
        root.addWidget(self.split, 1)

        self.search.textChanged.connect(self.refresh)
        self.genre_filter.textChanged.connect(self.refresh)
        self.bpm_min.textChanged.connect(self.refresh)
        self.bpm_max.textChanged.connect(self.refresh)
        self.status.currentIndexChanged.connect(self.refresh)
        self.table.selectionModel().selectionChanged.connect(self._show_detail)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._update_view_state_label)
        self._update_view_state_label()

    def _add_detail_fields(self, grid: QGridLayout, specs, *, technical: bool = False):
        for key, label, row, col, row_span, col_span in specs:
            heading = QLabel(label); heading.setObjectName('DetailFieldHeading')
            value = QLabel('—'); value.setObjectName('DetailFieldValue')
            value.setWordWrap(key not in {'hash'}); value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
            value.setOpenExternalLinks(True)
            grid.addWidget(heading, row, col, row_span, col_span)
            grid.addWidget(value, row + 1, col, row_span, col_span)
            self.detail_labels[key] = value
            if technical and key == 'hash':
                value.setTextFormat(Qt.TextFormat.PlainText); value.setToolTip('Pełny SHA-256')

    def set_history_provider(self, provider):
        self._history_provider = provider

    def _ensure_status_column_width(self) -> None:
        """Keep the full status label visible with its icon at larger DPI/font sizes."""
        text_width = self.table.fontMetrics().horizontalAdvance('DO SPRAWDZENIA')
        icon_width = max(15, self.table.iconSize().width())
        required = max(176, text_width + icon_width + 36)
        if self.table.columnWidth(0) < required:
            self.table.setColumnWidth(0, required)

    def eventFilter(self, watched, event):
        handled = super().eventFilter(watched, event)
        if watched is getattr(self, 'table', None) and event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
            QEvent.Type.StyleChange,
        }:
            QTimer.singleShot(0, self._ensure_status_column_width)
        return handled

    def set_tracks(self, tracks: list[TrackRecord]):
        self._tracks = tracks
        self._version_family_by_path = {}
        for family in group_version_families(tracks):
            for member in family:
                try:
                    key = str(Path(member.path).resolve()).casefold()
                except OSError:
                    key = str(member.path).casefold()
                self._version_family_by_path[key] = family
        self._update_genre_suggestions()
        self.refresh(preserve_order=True)

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

        filters: list[str] = []
        status_text = self.status.currentText().strip()
        if (self.status.currentData() or 'all') != 'all':
            filters.append(status_text)
        if self.search.text().strip():
            filters.append(f'Szukaj: {self.search.text().strip()}')
        if self.genre_filter.text().strip():
            filters.append(f'Gatunek: {self.genre_filter.text().strip()}')
        if self.bpm_min.text().strip() or self.bpm_max.text().strip():
            bpm_from = self.bpm_min.text().strip() or '—'
            bpm_to = self.bpm_max.text().strip() or '—'
            filters.append(f'BPM {bpm_from}–{bpm_to}')
        filter_text = ' · '.join(filters) if filters else 'brak'
        self.view_state_label.setText(ui_text(self, f'Sortowanie: {sort_name} {arrow}   •   Filtry: {filter_text}'))

    def _reset_view(self):
        blockers = [
            QSignalBlocker(self.search), QSignalBlocker(self.genre_filter),
            QSignalBlocker(self.bpm_min), QSignalBlocker(self.bpm_max), QSignalBlocker(self.status),
        ]
        self.search.clear()
        self.genre_filter.clear()
        self.bpm_min.clear()
        self.bpm_max.clear()
        all_index = self.status.findData('all')
        if all_index >= 0:
            self.status.setCurrentIndex(all_index)
        del blockers
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.verticalScrollBar().setValue(0)
        self.refresh()

    def refresh(self, *_, preserve_order: bool = False):
        view_state = self._capture_view_state()
        text = self.search.text().casefold().strip()
        wanted = self.status.currentData() or 'all'
        previous_order = view_state.get('visual_order') or []
        order_map = {key: index for index, key in enumerate(previous_order)} if preserve_order else {}
        sort_order = view_state.get('sort_order', Qt.SortOrder.AscendingOrder)
        next_order = len(order_map)

        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        for track in self._tracks:
            if not track_matches_quick_filter(track, wanted):
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
            locked_online = is_online_locked(track)
            values = [
                status_text, track.artist or '', track.title or '', track.year or '', track.genre or '',
                display_bpm(track.bpm), duration, quality,
            ]
            items = [QStandardItem(str(value)) for value in values]
            status_icons = {'ready': 'status', 'duplicate': 'duplicates', 'review': 'warning', 'not_selected': 'cancel'}
            items[0].setIcon(alo_icon('lock' if locked_online else status_icons.get(effective_status(track), 'info'), presentation.accent, 15))
            key = self._path_key(track)
            order_index = order_map.get(key)
            if order_index is None:
                order_index = next_order
                next_order += 1
            stable_sort_value = order_index if sort_order == Qt.SortOrder.AscendingOrder else -order_index
            for item in items:
                item.setEditable(False)
                item.setData(is_playing, PLAYING_ROLE)
                item.setData(stable_sort_value, VISUAL_ORDER_ROLE)
            items[2].setToolTip(track.title or '')
            items[1].setToolTip(track.artist or '')
            # Only Status is colored by default. The playing track overrides the full row.
            items[0].setBackground(QBrush(QColor(presentation.background)))
            items[0].setForeground(QBrush(QColor(presentation.accent)))
            font = items[0].font(); font.setBold(True); items[0].setFont(font)
            items[0].setData(track, Qt.ItemDataRole.UserRole)
            items[0].setToolTip(status_text)
            if is_playing:
                playing_background = QBrush(PLAYING_BACKGROUND)
                for item in items:
                    item.setBackground(playing_background)
                tooltip = f'{status_text} • {ui_text(self, "TERAZ GRA")}'
                if is_online_locked(track):
                    tooltip += ' • ' + ui_text(self, 'Zablokowany przed ponownym rozpoznaniem online')
                items[0].setToolTip(tooltip)
            elif is_online_locked(track):
                items[0].setToolTip(f'{status_text} • {ui_text(self, "Zablokowany przed ponownym rozpoznaniem online")}')
            elif 'duplicate_primary' in track.locked_fields:
                items[0].setToolTip(f'{status_text} • {ui_text(self, "Ten plik został przez Ciebie wybrany w zakładce Duplikaty.")}')
            self.model.appendRow(items)

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
        self._update_view_state_label()

    def _track_is_playing(self, track: TrackRecord) -> bool:
        if not self._playing_path:
            return False
        try:
            return str(Path(track.path).resolve()).casefold() == self._playing_path
        except OSError:
            return str(track.path).casefold() == self._playing_path

    def set_playing_track(self, track: TrackRecord | None):
        if track is None:
            new_path = None
        else:
            try:
                new_path = str(Path(track.path).resolve()).casefold()
            except OSError:
                new_path = str(track.path).casefold()
        if new_path == self._playing_path:
            return
        self._playing_path = new_path
        # Rebuild only the lightweight table model so TERAZ GRA follows the
        # shared player without changing the selected row or visual order.
        self.refresh(preserve_order=True)

    def _current_track(self):
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        item = self.model.item(idx.row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _play_selected(self, _index=None):
        track = self._current_track()
        if track:
            self.play_requested.emit(track)

    def _show_detail(self, *_):
        t = self._current_track()
        if not t:
            return
        self.track_selected.emit(t)
        self.detail_labels['artist'].setText(t.artist or '—')
        self.detail_labels['title'].setText(t.title or '—')
        self.detail_labels['album'].setText(t.album or '—')
        self.detail_labels['year'].setText(t.year or '—')
        self.detail_labels['bpm'].setText(display_bpm(t.bpm) or '—')
        self.detail_labels['genre'].setText(t.genre or '—')
        self.detail_labels['path'].setText(str(t.path))
        self.detail_labels['duration'].setText('—' if t.duration_seconds is None else f'{int(t.duration_seconds)//60}:{int(t.duration_seconds)%60:02d}')
        self.detail_labels['size'].setText('—' if not t.size_bytes else f'{t.size_bytes / (1024 * 1024):.2f} MB')
        self.detail_labels['quality'].setText(f'{t.codec or "?"} · {t.bitrate_kbps or "?"} kb/s · {t.sample_rate_hz or "?"} Hz · {t.channels or "?"} {ui_text(self, "kanały")}')
        low_confidence = bool(t.confidence is not None and t.confidence < 0.65)
        self.match_box.setProperty('lowConfidence', low_confidence)
        self.match_box.style().unpolish(self.match_box); self.match_box.style().polish(self.match_box); self.match_box.update()
        info = identification_summary(t)
        self.confidence_widget.set_value(t.confidence)
        self.detail_labels['sources'].setText(ui_text(self, info['sources'])); self.detail_labels['reasons'].setText(ui_text(self, info['reasons']))
        self.detail_labels['discogs'].setText(f'<a href="{t.discogs_url}">{t.discogs_url}</a>' if t.discogs_url else '—')
        self.detail_labels['comment'].setText((t.comment or '—').replace('\n', '<br>'))
        hash_text = '—' if not t.sha256 else f'{t.sha256[:12]}…{t.sha256[-12:]}'
        self.detail_labels['hash'].setText(hash_text); self.detail_labels['hash'].setToolTip(t.sha256 or '')
        history = self._history_provider(t) if self._history_provider else []
        self.history_label.setText('\n'.join(f'• {ui_text(self, entry)}' for entry in history) if history else ui_text(self, 'Brak ręcznych zmian.'))

        try:
            family_key = str(Path(t.path).resolve()).casefold()
        except OSError:
            family_key = str(t.path).casefold()
        family = self._version_family_by_path.get(family_key, [])
        self.version_family_card.setVisible(len(family) > 1)
        if family:
            lines = []
            for member in family:
                duration = '—' if member.duration_seconds is None else f'{int(member.duration_seconds)//60}:{int(member.duration_seconds)%60:02d}'
                marker = ui_text(self, 'Teraz: ') if member is t else '       '
                lines.append(f'{marker}{member.title or member.filename}  —  {duration}')
            self.version_family_label.setText(ui_text(self, f'Rodzina wersji: {len(family)} utwory') + '\n' + '\n'.join(lines))
        else:
            self.version_family_label.setText('')

        completeness = metadata_completeness(t)
        self.confirmed_label.setText('\n'.join(ui_text(self, value) for value in completeness['confirmed_core']) or '—')
        missing = list(completeness['missing_core'])
        self.review_box.setProperty('hasMissing', bool(missing))
        self.review_box.style().unpolish(self.review_box); self.review_box.style().polish(self.review_box)
        self.missing_heading.setVisible(bool(missing)); self.missing_label.setVisible(bool(missing)); self.complete_label.setVisible(not missing)
        if missing:
            self.missing_label.setText('\n'.join(ui_text(self, value) for value in missing)); self.complete_label.setText('')
        else:
            self.complete_label.setText(ui_text(self, 'Dane główne kompletne — nie musisz niczego uzupełniać.'))

        status = effective_status(t)
        self.approve.setEnabled(status not in {'duplicate', 'not_selected'})
        self.approve.setText(ui_text(self, 'GOTOWE' if status == 'ready' else 'ZATWIERDŹ JAKO GOTOWE'))
        self._load_cover(t)
        if status == 'review' and not self.detail.isVisible():
            self.details_btn.setChecked(True); self._toggle_details(True)

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
                self.cover_caption.setText(ui_text(self, 'Pobieranie podglądu zewnętrznej okładki…'))
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
            self.cover.setText(''); self.cover.setPixmap(pix.scaled(196, 196, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.cover_caption.setText(ui_text(self, note or 'Kliknij okładkę, aby powiększyć'))

    def _show_cover_preview(self):
        show_cover_preview(self, self._cover_pixmap, title=ui_text(self, 'Powiększona okładka'), note=ui_text(self, self._cover_note))

    def _toggle_details(self, checked: bool):
        self.detail.setVisible(checked)
        self.details_btn.setText(ui_text(self, 'Ukryj szczegóły' if checked else 'Szczegóły utworu'))
        if checked:
            self.split.setSizes([820, 740])

    def _toggle_technical(self, checked: bool):
        self.technical_panel.setVisible(checked)
        self.technical_toggle.setText('UKRYJ DANE TECHNICZNE' if checked else 'DANE TECHNICZNE')

    def select_track_by_path(self, path: Path) -> bool:
        target = str(Path(path).resolve()).casefold()
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0); candidate = item.data(Qt.ItemDataRole.UserRole) if item else None
            if candidate is not None and str(Path(candidate.path).resolve()).casefold() == target:
                self.table.clearSelection(); index = self.model.index(row, 0)
                self.table.setCurrentIndex(index); self.table.selectRow(row); self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
                if not self.detail.isVisible():
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
                if not self.detail.isVisible():
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
        tracks = self._selected_tracks()
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
        play = menu.addAction(alo_icon('play', '#72e0a4', 16), ui_text(self, 'Odtwórz'))
        play_next = menu.addAction(alo_icon('forward', '#9bc4d4', 16), ui_text(self, 'Odtwórz jako następny'))
        edit = menu.addAction(alo_icon('edit', '#73d8ef', 16), ui_text(self, 'Edytuj metadane'))
        menu.addSeparator()
        folder = menu.addAction(alo_icon('folder', '#7cdff4', 16), ui_text(self, 'Dodaj do Moje foldery MP3'))
        playlist = menu.addAction(alo_icon('add_tracks', '#9bd2ff', 16), ui_text(self, 'Utwórz playlistę z zaznaczonych'))
        menu.addSeparator()
        reveal = menu.addAction(alo_icon('folder_open', '#b8c8d2', 16), ui_text(self, 'Pokaż w Eksploratorze'))
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is play:
            self.play_requested.emit(track)
        elif chosen is play_next:
            self.queue_next_requested.emit(track)
        elif chosen is edit:
            self.edit_requested.emit(track)
        elif chosen is folder:
            tracks = self._selected_tracks() or [track]
            self.create_collection_requested.emit(tracks)
        elif chosen is playlist:
            tracks = self._selected_tracks() or [track]
            self.playlist_requested.emit([t.path for t in tracks])
        elif chosen is reveal:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(track.path.parent)))

    def _edit_current(self):
        track = self._current_track()
        if not track:
            QMessageBox.information(self, ui_text(self, 'Brak zaznaczenia'), ui_text(self, 'Najpierw zaznacz utwór w bibliotece.')); return
        self.edit_requested.emit(track)

    def _approve_current(self):
        track = self._current_track()
        if not track or effective_status(track) in {'duplicate', 'not_selected'}:
            return
        completeness = metadata_completeness(track)
        missing = list(completeness['missing_core'])
        if missing:
            self.review_box.setProperty('hasMissing', True)
            self.review_box.style().unpolish(self.review_box); self.review_box.style().polish(self.review_box)
            QMessageBox.warning(
                self, ui_text(self, 'Brak wymaganych danych'),
                ui_text(self, 'Nie można oznaczyć jako GOTOWE — uzupełnij wymagane pola: ') + ', '.join(ui_text(self, field) for field in missing),
            )
            return
        self.approve_requested.emit(track)

    def _select_all_visible(self):
        self.table.selectAll()

    def _request_collection(self):
        tracks = self._selected_tracks()
        if not tracks:
            QMessageBox.information(self, ui_text(self, 'Brak zaznaczenia'), ui_text(self, 'Zaznacz utwory, które mają trafić do nowego folderu MP3.'))
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
