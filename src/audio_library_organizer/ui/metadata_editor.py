from __future__ import annotations

from copy import copy, deepcopy
from pathlib import Path

from PySide6.QtCore import Property, Qt, QTimer, QUrl, Signal, QRegularExpression, QSize, QRectF
from PySide6.QtGui import QAction, QPixmap, QIcon, QColor, QPainter, QPen, QRegularExpressionValidator, QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from audio_library_organizer import __version__
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.artwork import extract_embedded_cover
from audio_library_organizer.metadata.naming import DEFAULT_FILENAME_TEMPLATE, normalize_title_case, propose_filename
from audio_library_organizer.metadata.normalization import normalize_music_text, is_valid_year_text
from audio_library_organizer.domain.preferences import default_name_rules
from audio_library_organizer.metadata.online_lock import is_online_locked
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.icons import editor_icon
from audio_library_organizer.ui.state import display_bpm, metadata_completeness, effective_status, library_status_presentation, review_severity
from audio_library_organizer.ui.confidence import ConfidenceWidget
from audio_library_organizer.ui.player import CompactPlayerBar
from audio_library_organizer.ui.widgets import ClickableCoverLabel, SelectableElidedLineEdit, show_cover_preview
from audio_library_organizer.ui.genre_input import GenreChipInput
from audio_library_organizer.ui.i18n import ui_text, language_for, apply_static_language, localized_no_cover_name


class MissingCompleteGraphic(QWidget):
    """Small document/check illustration used only by the BRAKI empty state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(58, 48)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor('#5a6876')); pen.setWidthF(1.8); painter.setPen(pen)
        painter.setBrush(QColor('#131d24'))
        painter.drawRoundedRect(11, 4, 34, 39, 6, 6)
        line_pen = QPen(QColor('#7d8d9b')); line_pen.setWidthF(1.5); painter.setPen(line_pen)
        painter.drawLine(18, 14, 36, 14); painter.drawLine(18, 21, 33, 21); painter.drawLine(18, 28, 30, 28)
        check_pen = QPen(QColor('#43d17d')); check_pen.setWidthF(3.2); check_pen.setCapStyle(Qt.PenCapStyle.RoundCap); painter.setPen(check_pen)
        painter.drawLine(30, 35, 35, 39); painter.drawLine(35, 39, 46, 28)


class MissingEmptyState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        box = QVBoxLayout(self); box.setContentsMargins(0, 2, 0, 2); box.setSpacing(1)
        graphic = MissingCompleteGraphic(self); box.addWidget(graphic, 0, Qt.AlignmentFlag.AlignHCenter)
        title = QLabel('Dane kompletne'); title.setObjectName('MissingEmptyTitle'); title.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(title)
        subtitle = QLabel('Wszystkie wymagane pola są uzupełnione'); subtitle.setObjectName('MissingEmptySubtitle'); subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(subtitle)


def _section_header(text: str, icon_name: str, *, compact: bool = False) -> QWidget:
    host = QWidget()
    host.setObjectName('EditorSectionHeader')
    host.setStyleSheet('background:transparent;')
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 1)
    row.setSpacing(7)
    icon = QLabel()
    icon_size = 16 if compact else 17
    icon.setStyleSheet('background:transparent;')
    icon.setPixmap(editor_icon(icon_name, '#5fd5f2', icon_size).pixmap(icon_size, icon_size))
    icon.setFixedSize(icon_size + 2, icon_size + 2)
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label = QLabel(text)
    label.setObjectName('EditorSectionTitle')
    row.addWidget(icon)
    row.addWidget(label)
    row.addStretch(1)
    return host


def _set_editor_button_icon(button, name: str, color: str, size: int) -> None:
    button.setIcon(editor_icon(name, color, size))
    button.setIconSize(QSize(size, size))
    button.setProperty('iconStyle', 'thin')


def _color_dot_icon(color: str, size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    margin = 1.5
    painter.drawEllipse(QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    painter.end()
    return QIcon(pm)


class SourceMenuTextLabel(QLabel):
    """Plain menu text whose color is not replaced by QMenu's action palette."""

    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self._display_color = QColor(color)

    def display_color(self) -> str:
        return self._display_color.name()

    def set_display_color(self, color: str) -> None:
        self._display_color = QColor(color)
        self.update()

    displayColor = Property(str, display_color, set_display_color)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self._display_color)
        painter.setFont(self.font())
        painter.drawText(
            self.contentsRect(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )


class SourceMenuOption(QWidget):
    """Partially colored source option used inside per-field menus."""

    activated = Signal()

    def __init__(self, provider: str, value: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName('SourceMenuOption')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 10, 5)
        row.setSpacing(6)
        dot = QLabel()
        dot.setObjectName('SourceMenuDot')
        dot.setPixmap(_color_dot_icon(color, 10).pixmap(10, 10))
        dot.setFixedSize(10, 10)
        name = SourceMenuTextLabel(provider, color)
        name.setObjectName('SourceMenuProvider')
        name_font = name.font()
        name_font.setBold(True)
        name.setFont(name_font)
        detail = SourceMenuTextLabel(value, '#c8d3da')
        detail.setObjectName('SourceMenuValue')
        separator = SourceMenuTextLabel('—', '#c8d3da')
        separator.setObjectName('SourceMenuSeparator')
        row.addWidget(dot)
        row.addWidget(name)
        row.addWidget(separator)
        row.addWidget(detail, 1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class EditorCloseGuardDialog(QDialog):
    """ALO-styled close warning with explicit save/return/discard decisions."""

    def __init__(self, items: list[tuple[str, str]], *, has_unsaved_changes: bool, allow_close: bool = True, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self.decision = 'return'
        self.setObjectName('EditorCloseGuardDialog')
        self.setWindowTitle('Sprawdź przed zamknięciem')
        self.setModal(True)
        self.setMinimumWidth(500)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        icon = QLabel()
        icon.setObjectName('CloseGuardHeaderIcon')
        icon.setPixmap(editor_icon('warning', '#ffc14f', 24).pixmap(24, 24))
        icon.setFixedSize(28, 28)
        title = QLabel('Przed zamknięciem sprawdź ten utwór')
        title.setObjectName('CloseGuardTitle')
        head.addWidget(icon)
        head.addWidget(title, 1)
        root.addLayout(head)

        note = QLabel('ALO wykryło elementy, które mogą wymagać Twojej decyzji:')
        note.setObjectName('CloseGuardNote')
        note.setWordWrap(True)
        root.addWidget(note)

        issues = QFrame()
        issues.setObjectName('CloseGuardIssues')
        issues_layout = QVBoxLayout(issues)
        issues_layout.setContentsMargins(10, 8, 10, 8)
        issues_layout.setSpacing(6)
        for severity, text in self.items:
            line = QFrame()
            line.setObjectName('CloseGuardIssue')
            line.setProperty('severity', severity)
            line_layout = QHBoxLayout(line)
            line_layout.setContentsMargins(7, 5, 7, 5)
            line_layout.setSpacing(8)
            color = '#ff776d' if severity == 'critical' else '#ffc14f'
            marker = QLabel()
            marker.setPixmap(editor_icon('warning', color, 16).pixmap(16, 16))
            marker.setFixedSize(18, 18)
            label = QLabel(ui_text(self, text))
            label.setObjectName('CloseGuardIssueText')
            label.setProperty('severity', severity)
            label.setWordWrap(True)
            line_layout.addWidget(marker)
            line_layout.addWidget(label, 1)
            issues_layout.addWidget(line)
        root.addWidget(issues)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.return_button = QPushButton('Wróć do edycji')
        self.return_button.setObjectName('CloseReturnAction')
        _set_editor_button_icon(self.return_button, 'chevron-left', '#c7d3da', 17)
        self.return_button.clicked.connect(self.reject)
        actions.addWidget(self.return_button)
        actions.addStretch(1)
        if has_unsaved_changes:
            self.discard_button = QPushButton('Odrzuć zmiany')
            self.discard_button.setObjectName('CloseDiscardAction')
            _set_editor_button_icon(self.discard_button, 'close', '#e7a09a', 17)
            self.discard_button.clicked.connect(lambda: self._finish('discard'))
            actions.addWidget(self.discard_button)
            self.save_button = QPushButton('Zapisz i zamknij')
            self.save_button.setObjectName('CloseSaveAction')
            _set_editor_button_icon(self.save_button, 'save', '#e8fbff', 17)
            self.save_button.clicked.connect(lambda: self._finish('save'))
            actions.addWidget(self.save_button)
            self.save_button.setDefault(True)
        elif allow_close:
            self.close_button = QPushButton('Zamknij mimo ostrzeżeń')
            self.close_button.setObjectName('CloseDespiteWarningsAction')
            _set_editor_button_icon(self.close_button, 'close', '#e7c58b', 17)
            self.close_button.clicked.connect(lambda: self._finish('close'))
            actions.addWidget(self.close_button)
        root.addLayout(actions)
        apply_static_language(self, language_for(self))

    def _finish(self, decision: str) -> None:
        self.decision = decision
        self.accept()


class MetadataEditorDialog(QDialog):
    """Shared metadata editor used from Library and Duplicates.

    The dialog keeps a working copy of form state. ``Zapisz zmiany`` emits a
    synchronous save request but deliberately keeps the window open, so the
    user can compare provider values and continue editing.
    """

    save_requested = Signal(object)
    ready_requested = Signal(object, bool)
    online_scan_requested = Signal(object)
    navigation_requested = Signal(int)

    CORE_FIELDS = ('artist', 'title', 'year', 'genre', 'bpm')
    SOURCE_LABELS = {
        'Tag': 'TAG',
        'Discogs': 'DISCOGS',
        'MusicBrainz': 'MUSICBRAINZ',
        'Apple / iTunes': 'APPLE',
        'Ręcznie': 'RĘCZNIE',
        'Analiza audio': '≋ ANALIZA',
        'Nazwa pliku': 'NAZWA',
        'Przywrócone': 'TAG',
    }
    SOURCE_KINDS = {
        'Tag': 'tag',
        'Przywrócone': 'tag',
        'Discogs': 'discogs',
        'MusicBrainz': 'musicbrainz',
        'Apple / iTunes': 'apple',
        'Ręcznie': 'manual',
        'Analiza audio': 'analysis',
        'Nazwa pliku': 'filename',
    }
    SOURCE_ORDER = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', 'Analiza audio', 'Nazwa pliku')
    SOURCE_COLORS = {
        'Tag': '#5ca3ff',
        'Discogs': '#43d17d',
        'MusicBrainz': '#b36cff',
        'Apple / iTunes': '#ff6670',
        'Analiza audio': '#ef5b64',
        'Nazwa pliku': '#9aa6b2',
        'Ręcznie': '#ffb84d',
    }

    COVER_OPTIONS = (
        ('source', 'OBECNA'),
        ('external', 'POBRANA'),
        ('manual', 'WŁASNA'),
        ('placeholder', 'BRAK OKŁADKI'),
    )

    def __init__(self, track: TrackRecord, parent=None, *, filename_template: str = DEFAULT_FILENAME_TEMPLATE, player_bar=None, genre_suggestions=(), normalize_names: bool = True, name_rules=None, navigation_index: int = 0, navigation_total: int = 1):
        super().__init__(parent)
        self.track = track
        self.navigation_total = max(1, int(navigation_total))
        self.navigation_index = max(0, min(int(navigation_index), self.navigation_total - 1))
        self.navigation_delta = 0
        self.filename_template = filename_template
        self.normalize_names = bool(normalize_names)
        self.name_rules = tuple(name_rules or default_name_rules())
        self.genre_suggestions = tuple(genre_suggestions or ())
        self.manual_cover_path = track.manual_cover_path
        self.cover_choice = track.cover_choice or 'auto'
        self.mark_ready = effective_status(track) == 'ready'
        self.has_saved_changes = False
        self._force_closing = False
        self._suspend_tracking = True
        self._filename_manual = bool(track.filename_override)
        self._online_scan_busy = False
        self._undo_stack: list[dict[str, object]] = []
        self._field_widgets: dict[str, QLineEdit | QTextEdit] = {}
        self._source_buttons: dict[str, QToolButton] = {}
        self._field_status_icons: dict[str, QLabel] = {}
        self._field_value_shells: dict[str, QFrame] = {}
        self._current_sources = dict(track.field_sources or {})
        self._source_values = deepcopy(track.field_source_values or {})
        self._cover_network = QNetworkAccessManager(self)
        self._cover_request_serial = 0
        self._cover_candidate_states: dict[str, str] = {}
        self._cover_pending_replies: set[QNetworkReply] = set()
        self._cover_reply_timers: dict[QNetworkReply, QTimer] = {}
        self._cover_labels: dict[str, ClickableCoverLabel] = {}
        self._cover_buttons: dict[str, QPushButton] = {}
        self._cover_pixmaps: dict[str, QPixmap] = {}
        self._cover_notes: dict[str, str] = {}
        self._initial_values = self._track_value_map(track)
        self._ensure_current_source_values()
        self.finished.connect(lambda _result: self._cancel_pending_cover_requests())

        self.setWindowTitle('Edytuj metadane')
        available = self.screen().availableGeometry()
        target_width = min(1680, max(760, round(available.width() * 0.98)))
        target_height = min(1040, max(680, round(available.height() * 0.96)))
        self.resize(min(target_width, available.width()), min(target_height, available.height()))
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(9)

        heading_row = QHBoxLayout()
        heading_row.setSpacing(8)
        self.editor_heading_icon = QLabel()
        self.editor_heading_icon.setObjectName('EditorHeadingIcon')
        self.editor_heading_icon.setPixmap(editor_icon('edit', '#62d9f3', 23).pixmap(23, 23))
        self.editor_heading_icon.setFixedSize(27, 27)
        self.editor_heading_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading_row.addWidget(self.editor_heading_icon)
        heading = QLabel('Edytuj metadane przed zatwierdzeniem')
        heading.setObjectName('EditorHeadingTitle')
        heading.setStyleSheet('font-size:16pt;font-weight:750;')
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        self.dirty_notice = QLabel('Niezapisane zmiany')
        self.dirty_notice.setObjectName('UnsavedNotice')
        self.dirty_notice.setVisible(False)
        heading_row.addWidget(self.dirty_notice)
        self.saved_notice = QLabel('Zapisano')
        self.saved_notice.setObjectName('SavedNotice')
        self.saved_notice.setVisible(False)
        heading_row.addWidget(self.saved_notice)
        self.file_counter = QLabel(f'Plik {self.navigation_index + 1} z {self.navigation_total}')
        self.file_counter.setObjectName('EditorFileCounter')
        heading_row.addWidget(self.file_counter)
        self.previous_file_button = QPushButton('')
        self.previous_file_button.setObjectName('EditorPreviousFileButton')
        self.previous_file_button.setAccessibleName('Poprzedni plik')
        self.previous_file_button.setToolTip('Przejdź do poprzedniego pliku')
        self.previous_file_button.setFixedSize(34, 30)
        _set_editor_button_icon(self.previous_file_button, 'chevron-left', '#bcd6e1', 17)
        self.previous_file_button.setEnabled(self.navigation_index > 0)
        self.previous_file_button.clicked.connect(lambda: self._request_navigation(-1))
        heading_row.addWidget(self.previous_file_button)
        self.next_file_button = QPushButton('')
        self.next_file_button.setObjectName('EditorNextFileButton')
        self.next_file_button.setAccessibleName('Następny plik')
        self.next_file_button.setToolTip('Przejdź do następnego pliku')
        self.next_file_button.setFixedSize(34, 30)
        _set_editor_button_icon(self.next_file_button, 'chevron-right', '#bcd6e1', 17)
        self.next_file_button.setEnabled(self.navigation_index + 1 < self.navigation_total)
        self.next_file_button.clicked.connect(lambda: self._request_navigation(1))
        heading_row.addWidget(self.next_file_button)
        root.addLayout(heading_row)

        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName('MetadataContentScroll')
        self.content_scroll.setStyleSheet('''
            QScrollBar:vertical { background:#101920; width:10px; margin:0; border:0; }
            QScrollBar::handle:vertical { background:#46606b; min-height:36px; border-radius:5px; }
            QScrollBar::handle:vertical:hover { background:#39b89c; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; border:0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
        ''')
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content_scroll.setMinimumHeight(180)
        content_host = QWidget()
        content = QVBoxLayout(content_host)
        content.setContentsMargins(0, 0, 6, 0)
        content.setSpacing(9)
        self.content_scroll.setWidget(content_host)
        root.addWidget(self.content_scroll, 1)

        note = QLabel('Zmiany są zapisywane w bibliotece ALO i dotyczą kopii wynikowej. Oryginalny plik pozostaje nietknięty.')
        note.setWordWrap(True)
        note.setObjectName('MutedText')
        content.addWidget(note)

        self.online_lock = QPushButton('')
        self.online_lock.setObjectName('OnlineLockButton')
        self.online_lock.setCheckable(True)
        self.online_lock.setChecked(is_online_locked(track))
        self.online_lock.setFixedWidth(38)
        self.online_lock.setAccessibleName('Blokada rozpoznawania online')
        self.online_lock.toggled.connect(self._on_online_lock_toggled)

        # Pasek bieżącego utworu + akcje online, zgodny z hierarchią głównej referencji.
        pre_online = QFrame()
        pre_online.setObjectName('PreOnlineSnapshotCard')
        pol = QHBoxLayout(pre_online)
        pol.setContentsMargins(12, 7, 10, 7)
        pol.setSpacing(9)
        self.track_header_icon = QLabel()
        self.track_header_icon.setObjectName('TrackHeaderIcon')
        self.track_header_icon.setPixmap(editor_icon('music', '#57d8f4', 19).pixmap(19, 19))
        self.track_header_icon.setFixedSize(22, 22)
        self.track_header_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pol.addWidget(self.track_header_icon)
        self.track_header_title = SelectableElidedLineEdit(track.path.name)
        self.track_header_title.setObjectName('TrackHeaderTitle')
        pol.addWidget(self.track_header_title, 1)
        self.pre_online_summary = self.track_header_title
        duration = max(0, int(track.duration_seconds or 0))
        technical_values = (
            ('track_header_bpm', f'{display_bpm(track.bpm) or "—"} BPM'),
            ('track_header_duration', f'{duration // 60:02d}:{duration % 60:02d}'),
            ('track_header_format', (track.codec or track.path.suffix.lstrip('.') or '—').upper()),
        )
        for attribute, value in technical_values:
            separator = QLabel('|')
            separator.setObjectName('TrackHeaderSeparator')
            pol.addWidget(separator)
            technical = QLabel(value)
            technical.setObjectName('TrackHeaderTechnical')
            technical.setAlignment(Qt.AlignmentFlag.AlignCenter)
            setattr(self, attribute, technical)
            pol.addWidget(technical)
        pol.addSpacing(18)
        self.scan_online_button = QPushButton('Rozpoznaj online')
        self.scan_online_button.setObjectName('SingleTrackOnlineButton')
        self.scan_online_button.setProperty('actionRole', 'primary')
        _set_editor_button_icon(self.scan_online_button, 'search', '#e9fdff', 19)
        self.scan_online_button.setToolTip('Uruchom rozpoznawanie online tylko dla tego utworu.')
        self.scan_online_button.clicked.connect(lambda: self.online_scan_requested.emit(self))
        pol.addWidget(self.scan_online_button)
        self.restore_pre_online_button = QPushButton('Przywróć dane sprzed online')
        self.restore_pre_online_button.setObjectName('RestoreOnlineButton')
        self.restore_pre_online_button.setProperty('actionRole', 'secondary')
        _set_editor_button_icon(self.restore_pre_online_button, 'undo', '#dce8ef', 18)
        self.restore_pre_online_button.setEnabled(bool(track.pre_online_metadata))
        self.restore_pre_online_button.clicked.connect(self._restore_pre_online_fields)
        pol.addWidget(self.restore_pre_online_button)
        self.online_lock.setProperty('actionRole', 'tool')
        pol.addWidget(self.online_lock)
        for online_action in (self.scan_online_button, self.restore_pre_online_button, self.online_lock):
            online_action.setFixedHeight(36)
        self._update_online_lock_button()
        content.addWidget(pre_online)
        self.set_online_scan_busy(False)

        self.suspicious_warning = QLabel('Duża różnica względem danych sprzed online — sprawdź wykonawcę i tytuł przed zatwierdzeniem.')
        self.suspicious_warning.setObjectName('SuspiciousOnlineWarning')
        self.suspicious_warning.setWordWrap(True)
        self.suspicious_warning.setVisible(any('Duża różnica' in reason for reason in track.match_reasons))
        content.addWidget(self.suspicious_warning)

        # Główna przestrzeń: edytowalne metadane, kompaktowy status oraz okładki.
        workspace = QHBoxLayout()
        workspace.setSpacing(10)

        metadata = self.metadata_card = QFrame()
        metadata.setObjectName('PrimaryMetadataCard')
        metadata.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        form = QFormLayout(metadata)
        form.setContentsMargins(10, 8, 10, 8)
        form.setVerticalSpacing(5)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        metadata_head = _section_header('Metadane utworu', 'metadata')
        form.addRow(metadata_head)

        self.artist = QLineEdit(track.artist or '')
        self.title = QLineEdit(track.title or '')
        self.year = QLineEdit(track.year or '')
        self.year.setPlaceholderText('np. 2009')
        self.year.setMaxLength(4)
        self.year.setValidator(QRegularExpressionValidator(QRegularExpression(r'\d{0,4}'), self.year))
        self.genre = GenreChipInput(track.genre or '', suggestions=self.genre_suggestions, max_items=3)
        self.genre.setToolTip('Wybierz z podpowiedzi albo wpisz własny gatunek. Pierwszy gatunek jest główny.')
        self.bpm = QLineEdit('' if track.bpm is None else display_bpm(track.bpm))
        self.album = QLineEdit(track.album or '')
        self.discogs_url = QLineEdit(track.discogs_url or '')
        self.comment = QTextEdit(track.comment or '')
        self.comment.setMaximumHeight(66)
        self.comment.setPlaceholderText('Dodaj komentarz…')

        for field_name, label, widget in (
            ('artist', 'Wykonawca', self.artist),
            ('title', 'Tytuł / wersja', self.title),
            ('year', 'Rok', self.year),
            ('genre', 'Gatunek', self.genre),
            ('bpm', 'BPM', self.bpm),
            ('album', 'Album / Release', self.album),
        ):
            form.addRow(self._field_label(label), self._field_input(field_name, widget))

        url_host = QWidget()
        url_row = QHBoxLayout(url_host)
        url_row.setContentsMargins(0, 0, 0, 0)
        url_row.setSpacing(5)
        url_row.addWidget(self._field_input('discogs_url', self.discogs_url), 1)
        self.open_url_button = QPushButton('Otwórz')
        self.open_url_button.setObjectName('OpenMetadataUrlButton')
        _set_editor_button_icon(self.open_url_button, 'external', '#8edcf1', 16)
        self.open_url_button.setToolTip('Otwórz adres w domyślnej przeglądarce')
        self.open_url_button.clicked.connect(self._open_metadata_url)
        url_row.addWidget(self.open_url_button)
        form.addRow(self._field_label('Discogs URL'), url_host)
        form.addRow(self._field_label('Komentarz'), self._field_input('comment', self.comment))
        workspace.addWidget(metadata, 5)

        status_host = self.status_recognition_column = QFrame()
        status_host.setObjectName('StatusRecognitionColumn')
        status_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        status_col = QVBoxLayout(status_host)
        status_col.setContentsMargins(0, 0, 0, 0)
        status_col.setSpacing(7)

        status_card = self.status_card = QFrame()
        status_card.setObjectName('MetadataStatusCompact')
        status_box = QVBoxLayout(status_card)
        status_box.setContentsMargins(10, 8, 10, 8)
        status_box.setSpacing(4)
        status_title = _section_header('Status pliku', 'status', compact=True)
        status_box.addWidget(status_title)
        self.status_labels = {}
        self.status_icons = {}
        self.status_rows = {}
        for field_name, label in (
            ('artist', 'Wykonawca'),
            ('title', 'Tytuł / wersja'),
            ('bpm', 'BPM'),
            ('cover', 'Okładka'),
            ('year', 'Rok'),
            ('genre', 'Gatunek'),
        ):
            row_frame = QFrame()
            row_frame.setObjectName('MetadataStatusRow')
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(5, 2, 5, 2)
            row_layout.setSpacing(7)
            icon = QLabel('')
            icon.setObjectName('MetadataStatusIcon')
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setFixedSize(18, 18)
            item = QLabel(label)
            item.setObjectName('MetadataStatusText')
            row_layout.addWidget(icon)
            row_layout.addWidget(item, 1)
            self.status_icons[field_name] = icon
            self.status_labels[field_name] = item
            self.status_rows[field_name] = row_frame
            status_box.addWidget(row_frame)
        status_col.addWidget(status_card, 3)

        recognition = self.recognition_card = QFrame()
        recognition.setObjectName('RecognitionInfoCompact')
        ril = QVBoxLayout(recognition)
        ril.setContentsMargins(10, 8, 10, 8)
        ril.setSpacing(5)
        ri_title = _section_header('Informacje o rozpoznaniu', 'info', compact=True)
        ril.addWidget(ri_title)
        self.recognition_values = {}
        for key, label in (
            ('source', 'Główne źródło'),
            ('fields', 'Rozpoznane pola'),
            ('duration', 'Długość'),
            ('bitrate', 'Bitrate'),
        ):
            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            name = QLabel(label)
            name.setObjectName('RecognitionFieldName')
            value = QLabel('—')
            value.setObjectName('RecognitionFieldValue')
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            line.addWidget(name)
            line.addStretch(1)
            line.addWidget(value)
            ril.addLayout(line)
            self.recognition_values[key] = value

        confidence_row = QHBoxLayout()
        confidence_row.setContentsMargins(0, 2, 0, 0)
        confidence_label = QLabel('Pewność')
        confidence_label.setObjectName('RecognitionFieldName')
        confidence_row.addWidget(confidence_label)
        confidence_row.addStretch(1)
        self.recognition_confidence = QLabel('—')
        self.recognition_confidence.setObjectName('RecognitionConfidencePercent')
        confidence_row.addWidget(self.recognition_confidence)
        ril.addLayout(confidence_row)
        self.recognition_bar = QProgressBar()
        self.recognition_bar.setObjectName('RecognitionConfidenceBar')
        self.recognition_bar.setRange(0, 100)
        self.recognition_bar.setTextVisible(False)
        self.recognition_bar.setFixedHeight(6)
        ril.addWidget(self.recognition_bar)
        status_col.addWidget(recognition, 2)
        workspace.addWidget(status_host, 2)

        gallery = self.cover_gallery = QFrame()
        gallery.setObjectName('CoverGallery')
        gallery.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        gl = QVBoxLayout(gallery)
        gl.setContentsMargins(10, 8, 10, 8)
        gl.setSpacing(6)
        gh = _section_header('Okładka (wybierana z listy)', 'image')
        gl.addWidget(gh)

        cover_top = QHBoxLayout()
        cover_top.setSpacing(10)

        cover_main_col = QVBoxLayout()
        cover_main_col.setSpacing(7)
        self.cover_main_preview = ClickableCoverLabel('Brak okładki')
        self.cover_main_preview.setObjectName('CoverMainPreview')
        self.cover_main_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_main_preview.setFixedSize(248, 248)
        self.cover_main_preview.clicked.connect(self._preview_selected_cover)
        self.cover_selected_badge = QLabel('', self.cover_main_preview)
        self.cover_selected_badge.setObjectName('CoverSelectedBadge')
        self.cover_selected_badge.setPixmap(editor_icon('status', '#f2fff8', 17).pixmap(17, 17))
        self.cover_selected_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_selected_badge.setFixedSize(24, 24)
        self.cover_selected_badge.move(216, 216)
        cover_main_col.addWidget(self.cover_main_preview, 0, Qt.AlignmentFlag.AlignLeft)

        self.choose_cover_button = QPushButton('Dodaj')
        self.choose_cover_button.setObjectName('CoverSmallAction')
        _set_editor_button_icon(self.choose_cover_button, 'upload', '#d9e6ee', 17)
        self.choose_cover_button.setToolTip('Wybierz własny plik okładki')
        self.choose_cover_button.clicked.connect(self._choose_cover)
        self.search_cover_button = QPushButton('Szukaj okładki online')
        self.search_cover_button.setObjectName('CoverSmallAction')
        _set_editor_button_icon(self.search_cover_button, 'search', '#d9e6ee', 17)
        self.search_cover_button.setToolTip('Odśwież propozycje okładek przez ponowne rozpoznanie online')
        self.search_cover_button.clicked.connect(lambda: self.online_scan_requested.emit(self))
        cover_top.addLayout(cover_main_col, 0)

        cover_side = QVBoxLayout()
        cover_side.setSpacing(6)
        proposals_head = QHBoxLayout()
        proposals_head.setSpacing(6)
        self.cover_proposal_count = QLabel('Propozycje (0)')
        self.cover_proposal_count.setObjectName('CoverProposalsHeading')
        self.cover_proposal_count.setMaximumHeight(24)
        proposals_head.addWidget(self.cover_proposal_count)
        proposals_head.addStretch(1)
        self.show_more_covers_button = QPushButton('Pokaż więcej')
        self.show_more_covers_button.setObjectName('CoverShowMoreAction')
        self.show_more_covers_button.setVisible(False)
        self.show_more_covers_button.clicked.connect(self._show_all_cover_proposals)
        proposals_head.addWidget(self.show_more_covers_button)
        cover_side.addLayout(proposals_head)

        self.cover_proposals_host = QFrame()
        self.cover_proposals_host.setObjectName('CoverProposalsHost')
        self.cover_proposals_grid = QGridLayout(self.cover_proposals_host)
        self.cover_proposals_grid.setContentsMargins(7, 7, 7, 7)
        self.cover_proposals_grid.setHorizontalSpacing(6)
        self.cover_proposals_grid.setVerticalSpacing(6)
        self.cover_proposals_grid.setColumnMinimumWidth(0, 90)
        self.cover_proposals_grid.setColumnMinimumWidth(1, 90)
        self.cover_proposals_host.setMinimumWidth(200)
        cover_side.addWidget(self.cover_proposals_host, 0, Qt.AlignmentFlag.AlignTop)

        cover_top.addLayout(cover_side, 1)
        gl.addLayout(cover_top)
        gl.addStretch(1)

        cover_actions = QWidget()
        cover_actions.setObjectName('CoverActions')
        cover_actions_row = QHBoxLayout(cover_actions)
        cover_actions_row.setContentsMargins(0, 2, 0, 0)
        cover_actions_row.setSpacing(7)
        cover_actions_row.addWidget(self.choose_cover_button)
        cover_actions_row.addStretch(1)
        cover_actions_row.addWidget(self.search_cover_button)
        gl.addWidget(cover_actions)

        self._cover_candidate_urls: dict[str, str] = {}
        self._cover_candidate_pixmaps: dict[str, QPixmap] = {}
        self._cover_proposal_labels: dict[str, ClickableCoverLabel] = {}
        self._cover_proposals_expanded = False
        self._selected_cover_key = 'placeholder'
        self._selected_external_url = track.cover_art_url
        workspace.addWidget(gallery, 4)
        workspace.setStretch(0, 5)
        workspace.setStretch(1, 2)
        workspace.setStretch(2, 4)
        content.addLayout(workspace)

        naming = QFrame()
        naming.setObjectName('FilenamePreviewCard')
        nl = QVBoxLayout(naming)
        nl.setContentsMargins(10, 6, 10, 6)
        nl.setSpacing(3)
        name_row = QHBoxLayout()
        name_icon = QLabel()
        name_icon.setStyleSheet('background:transparent;')
        name_icon.setPixmap(editor_icon('metadata', '#78a9c6', 15).pixmap(15, 15))
        name_icon.setFixedSize(17, 17)
        name_row.addWidget(name_icon)
        nh = QLabel('Nazwa wynikowa')
        nh.setObjectName('DetailFieldHeading')
        name_row.addWidget(nh)
        self.filename_override = QLineEdit(propose_filename(track, template=self.filename_template))
        self.filename_override.setObjectName('ResultFilenameEdit')
        self.filename_override.setToolTip('Możesz zmienić tę nazwę ręcznie — edytowana wersja zostanie zapisana.')
        name_row.addWidget(self.filename_override, 1)
        restore_name = QPushButton('Przywróć nazwę z metadanych')
        restore_name.setObjectName('RestoreFilenameButton')
        _set_editor_button_icon(restore_name, 'undo', '#cdd9e2', 16)
        restore_name.clicked.connect(self._restore_auto_filename)
        name_row.addWidget(restore_name)
        nl.addLayout(name_row)
        fname_note = QLabel('Opcjonalnie: edytuj nazwę tego pliku. Jeśli ją zmienisz, właśnie ta nazwa zostanie zapisana.')
        fname_note.setObjectName('MetadataHintText')
        fname_note.setWordWrap(True)
        fname_note.setStyleSheet('color:#596773; font-size:8pt; font-style:italic; padding:2px 3px;')
        nl.addWidget(fname_note)
        content.addWidget(naming)

        comparison = QFrame()
        comparison.setObjectName('SourceComparisonCard')
        comparison_layout = QVBoxLayout(comparison)
        comparison_layout.setContentsMargins(8, 6, 8, 6)
        comparison_layout.setSpacing(4)
        compare_head = QHBoxLayout()
        compare_title = _section_header('Porównanie źródeł  (pomocniczo)', 'database', compact=True)
        compare_head.addWidget(compare_title)
        self.source_legend_button = QToolButton()
        self.source_legend_button.setObjectName('SourceLegendInfoButton')
        self.source_legend_button.setText('')
        self.source_legend_button.setIcon(editor_icon('info', '#8ed9eb', 16))
        self.source_legend_button.setIconSize(QSize(16, 16))
        self.source_legend_button.setProperty('iconStyle', 'thin')
        self.source_legend_button.setToolTip('Legenda źródeł — kliknij')
        self.source_legend_button.setAccessibleName('Legenda źródeł')
        legend_menu = QMenu(self.source_legend_button)
        legend_menu.setObjectName('SourceLegendMenu')
        legend_menu.addSection('Legenda źródeł')
        legend_rows = (
            ('Tag', 'TAG', 'dane zapisane w pliku'),
            ('Discogs', 'Discogs', 'wydanie, wersja/remix, rok i gatunek'),
            ('MusicBrainz', 'MusicBrainz', 'identyfikacja nagrania i wydań'),
            ('Apple / iTunes', 'Apple', 'katalog Apple / iTunes bez klucza API'),
            ('Ręcznie', 'RĘCZNIE', 'wartość wpisana ręcznie'),
            ('Analiza audio', 'ANALIZA', 'wartość wykryta z audio'),
            ('Nazwa pliku', 'NAZWA', 'wartość odczytana z nazwy pliku'),
        )
        legend_colors = dict(self.SOURCE_COLORS)
        legend_colors.setdefault('Ręcznie', '#ffb84d')
        for source_key, source, description in legend_rows:
            action = QWidgetAction(legend_menu)
            option = SourceMenuOption(
                source,
                description,
                legend_colors.get(source_key, '#8a96a8'),
                legend_menu,
            )
            action.setDefaultWidget(option)
            legend_menu.addAction(action)
        self.source_legend_button.setMenu(legend_menu)
        self.source_legend_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        compare_head.addWidget(self.source_legend_button)
        compare_head.addStretch(1)
        comparison_layout.addLayout(compare_head)

        self.source_table = QTableWidget(0, 6)
        self.source_table.setObjectName('SourceComparisonTable')
        self.source_table.setHorizontalHeaderLabels(('Źródło', 'Tytuł / wersja', 'Wykonawca', 'Rok', 'Gatunek', 'Akcja'))
        self.source_table.verticalHeader().setVisible(False)
        self.source_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.source_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.source_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.source_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_table.setAlternatingRowColors(True)
        self.source_table.setIconSize(QSize(12, 12))
        self.source_table.setWordWrap(False)
        self.source_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.source_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.source_table.verticalHeader().setDefaultSectionSize(31)
        self.source_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header = self.source_table.horizontalHeader()
        header.setFixedHeight(27)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 130)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 58)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 126)
        comparison_layout.addWidget(self.source_table)
        comparison.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        content.addWidget(comparison)

        self.compact_player = None
        if player_bar is not None:
            self.compact_player = CompactPlayerBar(player_bar, track, self)
            root.addWidget(self.compact_player)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.undo_button = QPushButton('Cofnij ostatnią zmianę')
        self.undo_button.setObjectName('EditorSecondaryAction')
        _set_editor_button_icon(self.undo_button, 'undo', '#dce7ee', 18)
        self.undo_button.setToolTip('Cofa ostatnią zmianę w całym edytorze, także przywrócenie danych sprzed online.')
        self.undo_button.clicked.connect(self._undo_editor_change)

        self.online_lock.setIconSize(QSize(18, 18))

        self.save_button = QPushButton('Zapisz zmiany')
        self.save_button.setObjectName('SaveMetadataButton')
        _set_editor_button_icon(self.save_button, 'save', '#dce7ee', 18)
        self.save_button.clicked.connect(self._request_save)

        self.status_button = QPushButton('')
        self.status_button.setObjectName('CurrentStatusButton')
        self.status_button.setProperty('iconStyle', 'thin')
        self.status_button.setIconSize(QSize(18, 18))
        self.status_button.clicked.connect(self._toggle_ready)

        self.footer_buttons = [self.undo_button, self.status_button, self.save_button]
        for action_button in self.footer_buttons:
            action_button.setMinimumHeight(40)
        buttons.addWidget(self.undo_button)
        buttons.addStretch(1)
        buttons.addWidget(self.status_button)
        buttons.addWidget(self.save_button)
        root.addLayout(buttons)

        self._load_cover_gallery()
        self._refresh_source_comparison()
        self._connect_edit_tracking()
        self.discogs_url.textChanged.connect(self._refresh_url_action)
        self._suspend_tracking = False
        self._refresh_all()
        self._saved_state = self._capture_editor_state()
        self._last_observed_state = deepcopy(self._saved_state)
        self._update_ready_button()
        self._refresh_url_action()

    @staticmethod
    def _track_value_map(track: TrackRecord) -> dict[str, object]:
        return {
            'artist': track.artist or '',
            'title': track.title or '',
            'album': track.album or '',
            'year': track.year or '',
            'genre': track.genre or '',
            'bpm': '' if track.bpm is None else display_bpm(track.bpm),
            'discogs_url': track.discogs_url or '',
            'comment': track.comment or '',
        }

    def _ensure_current_source_values(self) -> None:
        values = self._track_value_map(self.track)
        for field_name, value in values.items():
            source = self._current_sources.get(field_name, '')
            if source and value not in ('', None):
                self._source_values.setdefault(field_name, {}).setdefault(source, value)
        if self.track.discogs_url:
            self._source_values.setdefault('discogs_url', {}).setdefault('Discogs', self.track.discogs_url)
            self._current_sources.setdefault('discogs_url', 'Discogs')

    def _field_label(self, label: str) -> QLabel:
        text = QLabel(label + ':')
        text.setObjectName('MetadataFieldLabel')
        return text

    def _field_input(self, field_name: str, widget: QLineEdit | QTextEdit) -> QWidget:
        self._field_widgets[field_name] = widget
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)

        value_shell = QFrame()
        value_shell.setObjectName('MetadataValueShell')
        value_row = QHBoxLayout(value_shell)
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(0)
        value_row.addWidget(widget, 1)
        indicator = QLabel()
        indicator.setObjectName('MetadataFieldWarning')
        indicator.setFixedSize(20, 20)
        indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        indicator.hide()
        self._field_status_icons[field_name] = indicator
        value_row.addWidget(indicator)
        self._field_value_shells[field_name] = value_shell
        row.addWidget(value_shell, 1)
        badge = QToolButton()
        badge.setObjectName('MetadataSourceBadge')
        badge.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        badge.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        badge.setToolTip('Kliknij, aby porównać dostępne wartości z różnych źródeł.')
        self._source_buttons[field_name] = badge
        row.addWidget(badge)
        self._rebuild_source_menu(field_name)
        self._refresh_source_badge(field_name)
        return host

    def _rebuild_source_menu(self, field_name: str) -> None:
        button = self._source_buttons.get(field_name)
        if button is None:
            return
        menu = QMenu(button)
        candidates = self._source_values.get(field_name, {})
        candidates = {name: value for name, value in candidates.items() if name != 'Ręcznie'}
        ordered = [name for name in self.SOURCE_ORDER if name in candidates]
        ordered += [name for name in candidates if name not in ordered]
        if not ordered:
            empty = QAction(ui_text(self, 'Brak alternatywnych danych'), menu)
            empty.setEnabled(False)
            menu.addAction(empty)
        else:
            for source in ordered:
                value = candidates[source]
                text = self._display_source_value(field_name, value)
                if len(text) > 72:
                    text = text[:69] + '…'
                action = QWidgetAction(menu)
                color = self.SOURCE_COLORS.get(source, '#9aa8b2')
                option = SourceMenuOption(ui_text(self, self.SOURCE_LABELS.get(source, source.upper())), text, color, menu)
                select_source = lambda f=field_name, s=source, m=menu: (
                    self._select_source_value(f, s), m.close()
                )
                option.activated.connect(select_source)
                action.triggered.connect(lambda _checked=False, callback=select_source: callback())
                action.setDefaultWidget(option)
                menu.addAction(action)
        button.setMenu(menu)

    def _display_source_value(self, field_name: str, value) -> str:
        if field_name == 'bpm':
            return display_bpm(value) or '—'
        return str(value or '—')

    def _source_kind(self, source: str) -> str:
        return self.SOURCE_KINDS.get(source, 'filename' if source else 'none')

    def _refresh_source_badge(self, field_name: str) -> None:
        source = self._current_sources.get(field_name, '')
        button = self._source_buttons.get(field_name)
        widget = self._field_widgets.get(field_name)
        if button is not None:
            button.setText(ui_text(self, self.SOURCE_LABELS.get(source, source.upper() if source else 'ŹRÓDŁO')))
            source_color = self.SOURCE_COLORS.get(source, '#aeb8c2')
            button.setIcon(_color_dot_icon(source_color))
            button.setIconSize(QSize(10, 10))
            button.setProperty('sourceColor', source_color)
            button.setProperty('sourceKind', self._source_kind(source))
            button.setStyleSheet(f'color:{source_color};')
            button.style().unpolish(button)
            button.style().polish(button)
        if widget is not None:
            widget.setProperty('sourceKind', self._source_kind(source))
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _focus_manual_field(self, field_name: str) -> None:
        widget = self._field_widgets.get(field_name)
        if widget is not None:
            widget.setFocus()

    def _select_source_value(self, field_name: str, source: str) -> None:
        candidates = self._source_values.get(field_name, {})
        if source not in candidates:
            return
        self._push_undo_state()
        self._suspend_tracking = True
        try:
            self._set_widget_value(field_name, candidates[source])
            self._current_sources[field_name] = source
        finally:
            self._suspend_tracking = False
        self._refresh_source_badge(field_name)
        self._refresh_all()
        self._refresh_source_comparison()
        self._observe_state()

    def _set_widget_value(self, field_name: str, value) -> None:
        widget = self._field_widgets[field_name]
        text = self._display_source_value(field_name, value)
        if isinstance(widget, QTextEdit):
            widget.setPlainText('' if text == '—' else text)
        else:
            widget.setText('' if text == '—' else text)

    def _connect_edit_tracking(self) -> None:
        for field_name, widget in self._field_widgets.items():
            if isinstance(widget, QLineEdit) or hasattr(widget, 'textEdited'):
                widget.textEdited.connect(lambda _text='', f=field_name: self._on_user_field_edit(f))
                widget.textChanged.connect(self._refresh_all)
            else:
                widget.textChanged.connect(lambda f=field_name: self._on_text_edit_changed(f))
        self.filename_override.textEdited.connect(self._on_filename_user_edit)
        self.filename_override.textChanged.connect(self._refresh_all)

    def _on_text_edit_changed(self, field_name: str) -> None:
        if self._suspend_tracking:
            return
        self._on_user_field_edit(field_name)

    def _on_user_field_edit(self, field_name: str) -> None:
        if self._suspend_tracking:
            return
        if self._last_observed_state is not None:
            self._undo_stack.append(deepcopy(self._last_observed_state))
        self._current_sources[field_name] = 'Ręcznie'
        self._refresh_source_badge(field_name)
        self._refresh_all()
        self._observe_state()

    def _on_filename_user_edit(self, _text: str = '') -> None:
        if self._suspend_tracking:
            return
        if self._last_observed_state is not None:
            self._undo_stack.append(deepcopy(self._last_observed_state))
        self._filename_manual = True
        self._refresh_all()
        self._observe_state()

    def _update_online_lock_button(self) -> None:
        locked = self.online_lock.isChecked()
        self.online_lock.setText('')
        self.online_lock.setToolTip(ui_text(self,
            'Dane chronione przed ponownym rozpoznaniem online'
            if locked else 'Rozpoznawanie online odblokowane'
        ))
        _set_editor_button_icon(
            self.online_lock,
            'lock' if locked else 'unlock',
            '#ff6973' if locked else '#78cfff',
            18,
        )
        self.online_lock.setProperty('lockedOnline', locked)
        self.online_lock.style().unpolish(self.online_lock)
        self.online_lock.style().polish(self.online_lock)
        if hasattr(self, 'scan_online_button'):
            self.scan_online_button.setEnabled(not locked and not self._online_scan_busy)

    def set_online_scan_busy(self, busy: bool) -> None:
        self._online_scan_busy = bool(busy)
        if not hasattr(self, 'scan_online_button'):
            return
        self.scan_online_button.setText(ui_text(self, 'Rozpoznawanie…' if busy else 'Rozpoznaj online'))
        _set_editor_button_icon(self.scan_online_button, 'search', '#91a4b0' if busy else '#dce8ef', 18)
        self.scan_online_button.setEnabled(not busy and not self.online_lock.isChecked())
        self.previous_file_button.setEnabled(not busy and self.navigation_index > 0)
        self.next_file_button.setEnabled(not busy and self.navigation_index + 1 < self.navigation_total)

    def apply_online_result(self, track: TrackRecord) -> None:
        """Refresh the open editor from the just-saved single-track online result."""
        self.track = track
        self._suspend_tracking = True
        try:
            self.manual_cover_path = track.manual_cover_path
            self.cover_choice = track.cover_choice or 'auto'
            self._selected_external_url = track.cover_art_url
            self.mark_ready = effective_status(track) == 'ready'
            self._current_sources = dict(track.field_sources or {})
            self._source_values = deepcopy(track.field_source_values or {})
            self._ensure_current_source_values()
            values = self._track_value_map(track)
            for field_name, value in values.items():
                if field_name in self._field_widgets:
                    self._set_widget_value(field_name, value)
            self._filename_manual = bool(track.filename_override)
            self.filename_override.setText(track.filename_override or propose_filename(track, template=self.filename_template))
            self.track_header_title.setText(track.path.name)
            duration = max(0, int(track.duration_seconds or 0))
            self.track_header_bpm.setText(f'{display_bpm(track.bpm) or "—"} BPM')
            self.track_header_duration.setText(f'{duration // 60:02d}:{duration % 60:02d}')
            self.track_header_format.setText((track.codec or track.path.suffix.lstrip('.') or '—').upper())
            self.restore_pre_online_button.setEnabled(bool(track.pre_online_metadata))
            self.online_lock.setChecked(is_online_locked(track))
            self._refresh_recognition_info()
            self.suspicious_warning.setVisible(any('Duża różnica' in reason for reason in track.match_reasons))
            for field_name in self._field_widgets:
                self._rebuild_source_menu(field_name)
                self._refresh_source_badge(field_name)
            self._load_cover_gallery()
            self._refresh_source_comparison()
        finally:
            self._suspend_tracking = False
        self._initial_values = self._track_value_map(track)
        self._undo_stack.clear()
        self._refresh_all()
        self._saved_state = deepcopy(self._capture_editor_state())
        self._last_observed_state = deepcopy(self._saved_state)
        self.dirty_notice.setVisible(False)
        self._update_ready_button()
        self._refresh_url_action()
        self.set_online_scan_busy(False)

    def _on_online_lock_toggled(self, _checked: bool) -> None:
        self._update_online_lock_button()
        if self._suspend_tracking:
            return
        if self._last_observed_state is not None:
            self._undo_stack.append(deepcopy(self._last_observed_state))
        self._refresh_dirty_state()
        self._observe_state()

    def _push_undo_state(self) -> None:
        self._undo_stack.append(deepcopy(self._capture_editor_state()))

    def _observe_state(self) -> None:
        self._last_observed_state = deepcopy(self._capture_editor_state())

    def _capture_editor_state(self) -> dict[str, object]:
        return {
            'values': {field: self._widget_text(widget) for field, widget in self._field_widgets.items()},
            'sources': deepcopy(self._current_sources),
            'filename': self.filename_override.text(),
            'filename_manual': self._filename_manual,
            'manual_cover_path': self.manual_cover_path,
            'cover_choice': self.cover_choice,
            'selected_cover_key': getattr(self, '_selected_cover_key', self.cover_choice),
            'selected_external_url': getattr(self, '_selected_external_url', self.track.cover_art_url),
            'ready': self.mark_ready,
            'online_locked': self.online_lock.isChecked(),
        }

    def _apply_editor_state(self, state: dict[str, object]) -> None:
        self._suspend_tracking = True
        try:
            for field_name, value in (state.get('values') or {}).items():
                if field_name in self._field_widgets:
                    widget = self._field_widgets[field_name]
                    if isinstance(widget, QTextEdit):
                        widget.setPlainText(str(value or ''))
                    else:
                        widget.setText(str(value or ''))
            self._current_sources = deepcopy(state.get('sources') or {})
            self.filename_override.setText(str(state.get('filename') or ''))
            self._filename_manual = bool(state.get('filename_manual'))
            self.manual_cover_path = state.get('manual_cover_path') or None
            self.cover_choice = str(state.get('cover_choice') or 'auto')
            self._selected_cover_key = str(state.get('selected_cover_key') or self.cover_choice)
            self._selected_external_url = state.get('selected_external_url') or self.track.cover_art_url
            self.mark_ready = bool(state.get('ready'))
            self.online_lock.setChecked(bool(state.get('online_locked')))
            self._update_online_lock_button()
            for field_name in self._field_widgets:
                self._refresh_source_badge(field_name)
            target_cover = self._selected_cover_key
            if target_cover in self._cover_candidate_pixmaps:
                self._select_cover_choice(target_cover, allow_unavailable=True, record_undo=False)
        finally:
            self._suspend_tracking = False
        self._refresh_all()
        self._observe_state()
        self._update_ready_button()

    def _widget_text(self, widget: QLineEdit | QTextEdit) -> str:
        return widget.toPlainText() if isinstance(widget, QTextEdit) else widget.text()

    def _undo_editor_change(self) -> None:
        if not self._undo_stack:
            return
        state = self._undo_stack.pop()
        self._apply_editor_state(state)

    def _restore_pre_online_fields(self) -> None:
        data = self.track.pre_online_metadata or {}
        if not data:
            return
        self._push_undo_state()
        self._suspend_tracking = True
        try:
            for field_name in ('artist', 'title', 'album', 'year', 'genre', 'bpm'):
                if field_name not in self._field_widgets or field_name not in data:
                    continue
                value = data.get(field_name)
                self._set_widget_value(field_name, value)
                source = self._local_source_for_value(field_name, value)
                self._current_sources[field_name] = source
                self._refresh_source_badge(field_name)
        finally:
            self._suspend_tracking = False
        self._filename_manual = False
        self._refresh_all()
        self._observe_state()

    def _local_source_for_value(self, field_name: str, value) -> str:
        candidates = self._source_values.get(field_name, {})
        for source in ('Tag', 'Nazwa pliku', 'Analiza audio'):
            if source in candidates and str(candidates[source]) == str(value):
                return source
        return 'Tag'

    def _refresh_all(self, *_):
        self._update_filename_preview()
        self._refresh_required_fields()
        self._refresh_status_summary()
        self._refresh_recognition_info()
        self._refresh_change_highlights()
        self._refresh_dirty_state()

    def _refresh_required_fields(self) -> None:
        for field_name in self.CORE_FIELDS:
            widget = self._field_widgets[field_name]
            missing = not bool(self._widget_text(widget).strip())
            widget.setProperty('missingRequired', missing)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            inner_edit = getattr(widget, 'edit', None)
            if inner_edit is not None:
                inner_edit.setProperty('missingRequired', missing)
                inner_edit.style().unpolish(inner_edit)
                inner_edit.style().polish(inner_edit)
            shell = self._field_value_shells.get(field_name)
            if shell is not None:
                shell.setProperty('missingRequired', missing)
                shell.style().unpolish(shell)
                shell.style().polish(shell)

    def _refresh_status_summary(self) -> None:
        preview = self._preview_track()
        values = {
            'artist': bool(preview.artist),
            'title': bool(preview.title),
            'bpm': preview.bpm is not None,
            'cover': self.selected_cover_available(),
            'year': bool(preview.year),
            'genre': bool(preview.genre),
        }
        for field_name, label in (
            ('artist', 'Wykonawca'),
            ('title', 'Tytuł / wersja'),
            ('bpm', 'BPM'),
            ('cover', 'Okładka'),
            ('year', 'Rok'),
            ('genre', 'Gatunek'),
        ):
            widget = self.status_labels.get(field_name)
            icon = self.status_icons.get(field_name)
            row = self.status_rows.get(field_name)
            if widget is None or icon is None or row is None:
                continue
            ok = values[field_name]
            if ok:
                icon_name, icon_color, kind = 'status', '#35df89', 'ok'
            elif field_name in {'artist', 'title'}:
                icon_name, icon_color, kind = 'alert_circle', '#ff665e', 'critical'
            else:
                icon_name, icon_color, kind = 'alert_circle', '#ffc85b', 'warning'
            widget.setText(ui_text(self, label))
            icon.setText('')
            icon.setPixmap(editor_icon(icon_name, icon_color, 18).pixmap(18, 18))
            for element in (widget, icon, row):
                element.setProperty('statusKind', kind)
                element.style().unpolish(element)
                element.style().polish(element)
            if kind == 'ok':
                icon.setStyleSheet('background:transparent; border:0;')
                widget.setStyleSheet('color:#63e39a; font-weight:760;')
                row.setStyleSheet('background:transparent; border:0;')
            elif kind == 'warning':
                icon.setStyleSheet('background:transparent; border:0;')
                widget.setStyleSheet('color:#f5b64f; font-weight:820;')
                row.setStyleSheet('background:transparent; border:0;')
            elif kind == 'critical':
                icon.setStyleSheet('background:transparent; border:0;')
                widget.setStyleSheet('color:#ff8179; font-weight:820;')
                row.setStyleSheet('background:transparent; border:0;')

        # Przy polach pokazujemy wyłącznie ostrzeżenia. Poprawne wartości nie
        # dostają drugiej, konkurującej z panelem statusu zielonej ikony.
        for field_name, indicator in self._field_status_icons.items():
            status = self.status_icons.get(field_name)
            if status is not None:
                field_kind = status.property('statusKind')
            else:
                missing = field_name in self.CORE_FIELDS and not bool(self._widget_text(self._field_widgets[field_name]).strip())
                field_kind = 'critical' if missing and field_name in {'artist', 'title'} else 'warning' if missing else 'ok'
            problematic = field_kind in {'warning', 'critical'}
            color = '#ff665e' if field_kind == 'critical' else '#ffc85b'
            indicator.setText('')
            indicator.setPixmap(editor_icon('alert_circle', color, 16).pixmap(16, 16) if problematic else QPixmap())
            indicator.setProperty('statusKind', field_kind)
            indicator.setVisible(problematic)
            indicator.style().unpolish(indicator)
            indicator.style().polish(indicator)
            indicator.setToolTip(ui_text(self, 'Dane kompletne' if not problematic else 'Brak danych'))

    def _refresh_recognition_info(self) -> None:
        values = self._preview_track()
        present = sum(bool(value) for value in (values.artist, values.title, values.year, values.genre, values.bpm))
        source = self._current_sources.get('title') or self._current_sources.get('artist') or '—'
        source_display = {
            'Tag': 'TAG',
            'Apple / iTunes': 'Apple',
            'Analiza audio': 'Analiza audio',
            'Nazwa pliku': 'Nazwa pliku',
            'Ręcznie': 'Ręcznie',
        }.get(source, source)
        duration = '—'
        if self.track.duration_seconds is not None:
            total = int(round(self.track.duration_seconds))
            duration = f'{total // 60:02d}:{total % 60:02d}'
        bitrate = f'{self.track.bitrate_kbps} kb/s' if self.track.bitrate_kbps else '—'
        self.recognition_values['source'].setText(ui_text(self, source_display))
        source_color = self.SOURCE_COLORS.get(source, '#d5e2e8')
        self.recognition_values['source'].setProperty('sourceColor', source_color)
        self.recognition_values['source'].setStyleSheet(
            f'color:{source_color}; background:transparent; font-weight:700;'
        )
        self.recognition_values['fields'].setText(f'{present}/5')
        self.recognition_values['duration'].setText(duration)
        self.recognition_values['bitrate'].setText(bitrate)
        if self.track.confidence is None:
            percent = None
            kind = 'none'
        else:
            percent = max(0, min(100, round(float(self.track.confidence) * 100)))
            kind = 'high' if percent >= 90 else ('medium' if percent >= 65 else 'low')
        self.recognition_confidence.setText('—' if percent is None else f'{percent}%')
        self.recognition_bar.setValue(percent or 0)
        for element in (self.recognition_confidence, self.recognition_bar):
            element.setProperty('confidenceKind', kind)
            element.style().unpolish(element)
            element.style().polish(element)

    def _refresh_current_status_banner(self) -> None:
        # Status jest celowo prezentowany tylko na dolnym przycisku edytora.
        return

    def _source_rows(self) -> list[str]:
        # Comparison stays compact: only sources that can populate a visible
        # comparison column are shown. Audio analysis (BPM only) remains in the
        # per-field badge/legend instead of creating an all-dash table row.
        comparison_fields = ('title', 'artist', 'year', 'genre')
        available: set[str] = set()
        for field_name in comparison_fields:
            values = self._source_values.get(field_name, {})
            if isinstance(values, dict):
                available.update(source for source, value in values.items() if value not in (None, ''))
        available.discard('Przywrócone')
        preferred = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', 'Nazwa pliku', 'Ręcznie')
        sources = [source for source in preferred if source in available]
        sources.extend(source for source in sorted(available) if source not in sources)
        return sources

    def _refresh_source_comparison(self) -> None:
        if not hasattr(self, 'source_table'):
            return
        sources = self._source_rows()
        self.source_table.setRowCount(len(sources))
        colors = {
            'Tag': '#5ca3ff',
            'Discogs': '#43d17d',
            'MusicBrainz': '#b36cff',
            'Apple / iTunes': '#ff6670',
            'Analiza audio': '#ef5b64',
            'Nazwa pliku': '#9aa6b2',
            'Ręcznie': '#ffb84d',
        }
        display_names = {
            'Tag': 'TAG',
            'Discogs': 'Discogs',
            'MusicBrainz': 'MusicBrainz',
            'Apple / iTunes': 'Apple / iTunes',
            'Analiza audio': 'ANALIZA AUDIO',
            'Nazwa pliku': 'NAZWA',
            'Ręcznie': 'RĘCZNIE',
        }
        for row, source in enumerate(sources):
            source_color = colors.get(source, '#cbd6e2')
            source_item = QTableWidgetItem('')
            source_item.setData(Qt.ItemDataRole.UserRole, source)
            source_item.setForeground(QColor(source_color))
            font = source_item.font()
            font.setPointSizeF(max(7.2, font.pointSizeF() - 1.0))
            font.setBold(True)
            source_item.setFont(font)
            self.source_table.setItem(row, 0, source_item)
            source_cell = QWidget()
            source_cell.setObjectName('SourceNameCell')
            source_layout = QHBoxLayout(source_cell)
            source_layout.setContentsMargins(7, 0, 4, 0)
            source_layout.setSpacing(5)
            source_dot = QLabel()
            source_dot.setObjectName('SourceNameDot')
            source_dot.setProperty('sourceColor', source_color)
            source_dot.setPixmap(_color_dot_icon(source_color, 12).pixmap(12, 12))
            source_dot.setFixedSize(12, 12)
            source_name = QLabel(ui_text(self, display_names.get(source, source)))
            source_name.setObjectName('SourceNameText')
            source_name.setStyleSheet(f'background:transparent;color:{source_color};font-weight:700;')
            source_layout.addWidget(source_dot)
            source_layout.addWidget(source_name, 1)
            self.source_table.setCellWidget(row, 0, source_cell)
            for column, field_name in ((1, 'title'), (2, 'artist'), (3, 'year'), (4, 'genre')):
                value = self._source_values.get(field_name, {}).get(source)
                self.source_table.setItem(row, column, QTableWidgetItem(self._display_source_value(field_name, value) if value not in (None, '') else '—'))
            use_button = QPushButton(ui_text(self, 'Użyj danych'))
            use_button.setObjectName('UseSourceDataButton')
            use_button.setFixedSize(82, 18)
            use_button.setToolTip(ui_text(self, f'Zastosuj dostępne dane ze źródła: {display_names.get(source, source)}'))
            use_button.clicked.connect(lambda _checked=False, s=source: self._apply_source_bundle(s))
            cell = QWidget()
            cell.setObjectName('UseSourceDataCell')
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(7, 3, 7, 3)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(use_button)
            self.source_table.setCellWidget(row, 5, cell)
        visible_rows = min(max(len(sources), 4), 6)
        table_height = 27 + visible_rows * 31 + 6
        self.source_table.setFixedHeight(table_height)

    def _apply_source_bundle(self, source: str) -> None:
        fields = ('artist', 'title', 'album', 'year', 'genre', 'bpm', 'discogs_url', 'comment')
        available = [(field, self._source_values.get(field, {}).get(source)) for field in fields]
        available = [(field, value) for field, value in available if value not in (None, '') and field in self._field_widgets]
        if not available:
            return
        self._push_undo_state()
        self._suspend_tracking = True
        try:
            for field_name, value in available:
                self._set_widget_value(field_name, value)
                self._current_sources[field_name] = source
                self._refresh_source_badge(field_name)
        finally:
            self._suspend_tracking = False
        self._filename_manual = False
        self._refresh_all()
        self._observe_state()

    @staticmethod
    def _validated_web_url(text: str) -> QUrl | None:
        url = QUrl(text.strip())
        if url.isValid() and url.scheme() in {'http', 'https'} and bool(url.host()):
            return url
        return None

    def _refresh_url_action(self, *_):
        url = self._validated_web_url(self.discogs_url.text())
        self.open_url_button.setEnabled(url is not None)
        self.open_url_button.setToolTip(url.toString() if url is not None else 'Wpisz poprawny adres http:// lub https://')
        if url is not None and 'discogs.com' in url.host().casefold():
            self.open_url_button.setText(ui_text(self, 'Otwórz w Discogs'))
        else:
            self.open_url_button.setText(ui_text(self, 'Otwórz link'))

    def _open_metadata_url(self):
        url = self._validated_web_url(self.discogs_url.text())
        if url is not None:
            QDesktopServices.openUrl(url)

    def _refresh_change_highlights(self, *_):
        for name, widget in self._field_widgets.items():
            changed = self._widget_text(widget).strip() != str(self._initial_values.get(name, '')).strip()
            widget.setProperty('changed', changed)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _refresh_dirty_state(self) -> None:
        if not hasattr(self, '_saved_state'):
            return
        dirty = self._capture_editor_state() != self._saved_state
        self.dirty_notice.setVisible(dirty)

    def _preview_track(self) -> TrackRecord:
        preview = copy(self.track)
        artist = self.artist.text().strip() or None
        title = normalize_title_case(self.title.text().strip() or None)
        if self.normalize_names:
            artist = normalize_music_text(artist, self.name_rules)
            title = normalize_music_text(title, self.name_rules)
        preview.artist = artist
        preview.title = title
        preview.album = self.album.text().strip() or None
        preview.year = self.year.text().strip() or None
        preview.genre = self.genre.text().strip() or None
        bpm_text = self.bpm.text().strip().replace(',', '.')
        try:
            preview.bpm = float(bpm_text) if bpm_text else None
        except ValueError:
            preview.bpm = self.track.bpm
        preview.discogs_url = self.discogs_url.text().strip() or None
        preview.comment = self.comment.toPlainText().strip() or None
        preview.filename_override = None
        return preview

    def _auto_filename(self) -> str:
        return propose_filename(self._preview_track(), template=self.filename_template)

    def _update_filename_preview(self, *_):
        if not hasattr(self, 'filename_override'):
            return
        if not self._filename_manual:
            auto = self._auto_filename()
            if self.filename_override.text() != auto:
                self._suspend_tracking = True
                try:
                    self.filename_override.setText(auto)
                finally:
                    self._suspend_tracking = False

    def _restore_auto_filename(self):
        self._push_undo_state()
        self._filename_manual = False
        self._update_filename_preview()
        self._refresh_all()
        self._observe_state()

    def _validate_year(self) -> bool:
        text = self.year.text().strip()
        if is_valid_year_text(text):
            self.year.setProperty('invalidYear', False)
            self.year.style().unpolish(self.year); self.year.style().polish(self.year)
            return True
        self.year.setProperty('invalidYear', True)
        self.year.style().unpolish(self.year); self.year.style().polish(self.year)
        self.year.setFocus()
        QMessageBox.warning(self, ui_text(self, 'Nieprawidłowy rok'), ui_text(self, 'Rok musi składać się dokładnie z 4 cyfr, np. 2009.'))
        return False

    def _request_save(self):
        if not self._validate_year():
            return False
        self.save_requested.emit(self)
        self.has_saved_changes = True
        self._saved_state = deepcopy(self._capture_editor_state())
        self._last_observed_state = deepcopy(self._saved_state)
        self.dirty_notice.setVisible(False)
        self.saved_notice.setVisible(True)
        QTimer.singleShot(2200, lambda: self.saved_notice.setVisible(False))
        return True

    def values(self) -> dict[str, object]:
        bpm_text = self.bpm.text().strip().replace(',', '.')
        bpm = None
        if bpm_text:
            try:
                bpm = float(bpm_text)
            except ValueError:
                bpm = self.track.bpm
        auto_filename = self._auto_filename()
        result_name = self.filename_override.text().strip()
        filename_override = result_name if self._filename_manual and result_name and result_name != auto_filename else None
        artist = self.artist.text().strip() or None
        title = self.title.text().strip() or None
        if self.normalize_names:
            artist = normalize_music_text(artist, self.name_rules)
            title = normalize_music_text(normalize_title_case(title), self.name_rules)
        return {
            'artist': artist,
            'title': title,
            'album': self.album.text().strip() or None,
            'year': self.year.text().strip() or None,
            'genre': self.genre.text().strip() or None,
            'bpm': bpm,
            'discogs_url': self.discogs_url.text().strip() or None,
            'comment': self.comment.toPlainText().strip() or None,
            'filename_override': filename_override,
        }

    def online_locked(self) -> bool:
        return self.online_lock.isChecked()

    def source_selections(self) -> dict[str, str]:
        return dict(self._current_sources)

    def _cancel_unsaved_changes(self):
        self._apply_editor_state(deepcopy(self._saved_state))
        self.dirty_notice.setVisible(False)

    def _toggle_ready(self):
        desired = not self.mark_ready
        if desired:
            if not self._validate_year():
                return
            preview = self._preview_track()
            completeness = metadata_completeness(preview)
            missing = list(completeness['missing_core'])
            if missing:
                self._refresh_required_fields()
                first_widget = None
                for field_name in self.CORE_FIELDS:
                    widget = self._field_widgets.get(field_name)
                    if widget is not None and not self._widget_text(widget).strip():
                        first_widget = widget
                        break
                if first_widget is not None:
                    first_widget.setFocus()
                QMessageBox.warning(
                    self, ui_text(self, 'Brak wymaganych danych'),
                    ui_text(self, 'Nie można oznaczyć jako GOTOWE — uzupełnij wymagane pola: ') + ', '.join(missing),
                )
                return
        if self._capture_editor_state() != self._saved_state:
            self._request_save()
        self.ready_requested.emit(self, desired)
        self.mark_ready = effective_status(self.track) == 'ready'
        self._update_ready_button()
        self._saved_state = deepcopy(self._capture_editor_state())
        self._observe_state()

    def _update_ready_button(self):
        kind = effective_status(self.track)
        if kind == 'review' and review_severity(self.track) == 'critical':
            kind = 'reviewCritical'

        self.status_button.setText(ui_text(self, 'GOTOWE') if self.mark_ready else ui_text(self, 'DO SPRAWDZENIA'))
        _set_editor_button_icon(
            self.status_button,
            'check' if self.mark_ready else 'warning',
            '#70e6a0' if self.mark_ready else '#ffc14f',
            18,
        )
        self.status_button.setIconSize(QSize(18, 18))
        self.status_button.setProperty('currentStatusKind', 'ready' if self.mark_ready else 'review')
        self.status_button.setProperty('statusSeverity', kind)
        self.status_button.setToolTip(
            ui_text(self, 'Kliknij, aby zmienić na DO SPRAWDZENIA') if self.mark_ready
            else ui_text(self, 'Kliknij, aby oznaczyć jako GOTOWE')
        )
        self.status_button.style().unpolish(self.status_button)
        self.status_button.style().polish(self.status_button)

    def has_unsaved_changes(self) -> bool:
        return self._capture_editor_state() != self._saved_state

    def close_attention_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        if self.has_unsaved_changes():
            items.append(('amber', 'Niezapisane zmiany'))
        if not self.mark_ready:
            items.append(('amber', 'Status: DO SPRAWDZENIA'))

        missing = list(metadata_completeness(self._preview_track())['missing_core'])
        label_text = {
            'Wykonawca': 'wykonawca',
            'Tytuł / wersja': 'tytuł / wersja',
            'Rok': 'rok',
            'Gatunek': 'gatunek',
            'BPM': 'BPM',
        }
        critical = [label_text[label] for label in missing if label in {'Wykonawca', 'Tytuł / wersja'}]
        attention = [label_text[label] for label in missing if label in label_text and label not in {'Wykonawca', 'Tytuł / wersja'}]
        if critical:
            items.append(('critical', 'Brak ważnych danych: ' + ', '.join(critical)))
        if attention:
            items.append(('amber', 'Pola wymagające uwagi: ' + ', '.join(attention)))
        return items

    def create_close_guard_dialog(self) -> EditorCloseGuardDialog:
        return EditorCloseGuardDialog(
            self.close_attention_items(),
            has_unsaved_changes=self.has_unsaved_changes(),
            parent=self,
        )

    def _run_close_guard(self, *, attention_when_clean: bool) -> bool:
        if self._online_scan_busy:
            guard = EditorCloseGuardDialog(
                [('amber', 'Rozpoznawanie online nadal trwa. Poczekaj na zakończenie operacji.')],
                has_unsaved_changes=False,
                allow_close=False,
                parent=self,
            )
            guard.exec()
            return False
        dirty = self.has_unsaved_changes()
        if not dirty and (not attention_when_clean or not self.close_attention_items()):
            return True
        guard = self.create_close_guard_dialog()
        guard.exec()
        if guard.decision == 'save':
            return bool(self._request_save())
        return guard.decision in {'discard', 'close'}

    def _confirm_close(self) -> bool:
        return self._run_close_guard(attention_when_clean=True)

    def _request_navigation(self, delta: int) -> None:
        target = self.navigation_index + int(delta)
        if target < 0 or target >= self.navigation_total:
            return
        if not self._run_close_guard(attention_when_clean=False):
            return
        self.navigation_delta = int(delta)
        self.navigation_requested.emit(self.navigation_delta)
        self._force_closing = True
        self.accept()

    def _close_editor(self):
        if not self._confirm_close():
            return
        self._force_closing = True
        self.accept()

    def reject(self):
        self._close_editor()

    def closeEvent(self, event):
        if self._force_closing:
            event.accept()
            return
        if self._confirm_close():
            self._force_closing = True
            event.accept()
        else:
            event.ignore()

    @staticmethod
    def _external_cover_url(track: TrackRecord) -> str | None:
        if track.cover_art_url:
            return track.cover_art_url
        if track.musicbrainz_release_id:
            return f'https://coverartarchive.org/release/{track.musicbrainz_release_id}/front-500'
        return None

    def _clear_cover_proposals(self) -> None:
        while self.cover_proposals_grid.count():
            item = self.cover_proposals_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._cover_proposal_labels.clear()

    def _load_cover_gallery(self):
        self._cover_request_serial += 1
        serial = self._cover_request_serial
        self._cancel_pending_cover_requests()
        self._cover_candidate_pixmaps = {}
        self._cover_candidate_urls = {}
        self._cover_candidate_states = {}
        self._cover_proposals_expanded = False

        source_pix = QPixmap()
        embedded = extract_embedded_cover(self.track.path)
        if embedded:
            source_pix.loadFromData(embedded[0])
        self._cover_candidate_pixmaps['source'] = source_pix
        self._cover_candidate_states['source'] = 'ready' if not source_pix.isNull() else 'unavailable'
        self._cover_notes['source'] = 'Okładka osadzona w pliku źródłowym.'

        placeholder = QPixmap(str(asset_path(localized_no_cover_name(self))))
        self._cover_candidate_pixmaps['placeholder'] = placeholder
        self._cover_candidate_states['placeholder'] = 'ready'
        self._cover_notes['placeholder'] = 'Brak potwierdzonej okładki — grafika zastępcza ALO Music.'

        manual = QPixmap(self.manual_cover_path) if self.manual_cover_path and Path(self.manual_cover_path).is_file() else QPixmap()
        self._cover_candidate_pixmaps['manual'] = manual
        self._cover_candidate_states['manual'] = 'ready' if not manual.isNull() else 'unavailable'
        self._cover_notes['manual'] = 'Okładka wybrana ręcznie.'

        raw_covers = dict(self.track.field_source_values.get('__cover__', {}) or {})
        external_url = self._external_cover_url(self.track)
        if external_url and external_url not in raw_covers.values():
            raw_covers['Online'] = external_url
        if self.track.musicbrainz_release_id:
            mb_url = f'https://coverartarchive.org/release/{self.track.musicbrainz_release_id}/front-500'
            raw_covers.setdefault('MusicBrainz', mb_url)

        for source, url in raw_covers.items():
            if not url:
                continue
            key = f'external:{source}'
            self._cover_candidate_urls[key] = str(url)
            self._cover_candidate_pixmaps[key] = QPixmap()
            self._cover_candidate_states[key] = 'loading'
            self._cover_notes[key] = f'Okładka online — {source}.'

        self._rebuild_cover_proposals()

        for key, url in self._cover_candidate_urls.items():
            self._load_candidate_cover(key, url, serial)

        explicit = (self.cover_choice or 'auto').casefold()
        selected = 'placeholder'
        if explicit == 'manual' and not manual.isNull():
            selected = 'manual'
        elif explicit == 'source' and not source_pix.isNull():
            selected = 'source'
        elif explicit == 'external':
            if self._selected_external_url:
                selected = next((key for key, url in self._cover_candidate_urls.items() if url == self._selected_external_url), '')
            if not selected:
                selected = next(iter(self._cover_candidate_urls), '')
            if not selected:
                selected = 'source' if not source_pix.isNull() else 'placeholder'
        elif explicit == 'placeholder':
            selected = 'placeholder'
        else:
            if not manual.isNull():
                selected = 'manual'
            elif self._cover_candidate_urls:
                selected = next(iter(self._cover_candidate_urls))
            elif not source_pix.isNull():
                selected = 'source'
        self._select_cover_choice(selected, allow_unavailable=True, record_undo=False)

    def _rebuild_cover_proposals(self) -> None:
        self._clear_cover_proposals()
        entries: list[tuple[str, str]] = []
        if not self._cover_candidate_pixmaps.get('source', QPixmap()).isNull():
            entries.append(('source', 'OBECNA'))
        external_entries = [(key, key.split(':', 1)[1]) for key in self._cover_candidate_urls]
        visible_external = external_entries if self._cover_proposals_expanded else external_entries[:4]
        selected = getattr(self, '_selected_cover_key', '')
        if not self._cover_proposals_expanded and selected.startswith('external:'):
            selected_entry = next((entry for entry in external_entries if entry[0] == selected), None)
            if selected_entry and selected_entry not in visible_external:
                visible_external = [*visible_external[:3], selected_entry]
        entries.extend(visible_external)
        if not self._cover_candidate_pixmaps.get('manual', QPixmap()).isNull():
            entries.append(('manual', 'WŁASNA'))
        entries.append(('placeholder', 'BRAK OKŁADKI'))
        total_count = len(entries) + len(external_entries) - len(visible_external)
        self.cover_proposal_count.setText(ui_text(self, f'Propozycje ({total_count})'))
        self.show_more_covers_button.setVisible(len(external_entries) > len(visible_external))

        count = len(entries)
        preview_size = 84
        columns = 2

        for index, (key, title) in enumerate(entries):
            card = QFrame()
            card.setObjectName('CoverProposalCard')
            card.setProperty('selected', key == getattr(self, '_selected_cover_key', ''))
            card.setToolTip(ui_text(self, title))
            card.setMinimumSize(preview_size + 6, preview_size + 6)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(3, 3, 3, 3)
            lay.setSpacing(0)
            preview = ClickableCoverLabel('…')
            preview.setObjectName('CoverProposalPreview')
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setFixedSize(preview_size, preview_size)
            preview.setToolTip(ui_text(self, title))
            preview.clicked.connect(lambda k=key: self._select_cover_choice(k))
            lay.addWidget(preview, 0, Qt.AlignmentFlag.AlignCenter)
            selected_badge = QLabel('', card)
            selected_badge.setObjectName('CoverProposalSelectedBadge')
            selected_badge.setPixmap(editor_icon('status', '#f2fff8', 14).pixmap(14, 14))
            selected_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            selected_badge.setFixedSize(20, 20)
            selected_badge.move(64, 64)
            selected_badge.setVisible(key == getattr(self, '_selected_cover_key', ''))
            selected_badge.raise_()
            self._cover_proposal_labels[key] = preview
            row, col = divmod(index, columns)
            self.cover_proposals_grid.addWidget(card, row, col)
            self._refresh_cover_proposal_widget(key)

    def _show_all_cover_proposals(self) -> None:
        self._cover_proposals_expanded = True
        self._rebuild_cover_proposals()

    def _refresh_cover_proposal_widget(self, key: str) -> None:
        label = self._cover_proposal_labels.get(key)
        if label is None:
            return
        pix = self._cover_candidate_pixmaps.get(key, QPixmap())
        if pix.isNull():
            label.setPixmap(QPixmap())
            state = self._cover_candidate_states.get(key, 'unavailable')
            label.setText('…' if state == 'loading' else ui_text(self, 'Brak') if state == 'error' else '—')
        else:
            label.setText('')
            edge = max(24, min(label.width(), label.height()) - 2)
            label.setPixmap(pix.scaled(edge, edge, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        card = label.parentWidget()
        if card is not None:
            selected = key == getattr(self, '_selected_cover_key', '')
            card.setProperty('selected', selected)
            badge = card.findChild(QLabel, 'CoverProposalSelectedBadge')
            if badge is not None:
                badge.setVisible(selected)
                badge.raise_()
            card.style().unpolish(card)
            card.style().polish(card)

    def _load_candidate_cover(self, key: str, url: str, serial: int) -> None:
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f'ALO Music/{__version__}')
        reply = self._cover_network.get(request)
        self._cover_pending_replies.add(reply)
        timer = QTimer(reply)
        timer.setSingleShot(True)
        timer.setInterval(12_000)
        timer.timeout.connect(lambda r=reply, k=key, s=serial: self._cover_request_timed_out(r, k, s))
        self._cover_reply_timers[reply] = timer
        timer.start()
        reply.finished.connect(lambda r=reply, k=key, s=serial: self._candidate_cover_finished(r, k, s))

    def _cancel_pending_cover_requests(self) -> None:
        pending = tuple(self._cover_pending_replies)
        self._cover_pending_replies.clear()
        for reply in pending:
            timer = self._cover_reply_timers.pop(reply, None)
            if timer is not None:
                timer.stop()
            reply.abort()

    def _cover_request_timed_out(self, reply: QNetworkReply, key: str, serial: int) -> None:
        if serial != self._cover_request_serial or reply not in self._cover_pending_replies:
            return
        self._cover_candidate_states[key] = 'error'
        self._cover_candidate_pixmaps[key] = QPixmap()
        self._refresh_cover_proposal_widget(key)
        if key == getattr(self, '_selected_cover_key', ''):
            self._update_cover_main_preview()
        reply.abort()

    def _candidate_cover_finished(self, reply: QNetworkReply, key: str, serial: int) -> None:
        try:
            self._cover_pending_replies.discard(reply)
            timer = self._cover_reply_timers.pop(reply, None)
            if timer is not None:
                timer.stop()
            if serial != self._cover_request_serial:
                return
            pix = QPixmap()
            if reply.error() == QNetworkReply.NetworkError.NoError:
                pix.loadFromData(bytes(reply.readAll()))
            self._cover_candidate_pixmaps[key] = pix
            self._cover_candidate_states[key] = 'ready' if not pix.isNull() else 'error'
            self._refresh_cover_proposal_widget(key)
            if key == getattr(self, '_selected_cover_key', ''):
                self._update_cover_main_preview()
        finally:
            reply.deleteLater()

    def _update_cover_main_preview(self) -> None:
        key = getattr(self, '_selected_cover_key', 'placeholder')
        pix = self._cover_candidate_pixmaps.get(key, QPixmap())
        if pix.isNull():
            self.cover_main_preview.setPixmap(QPixmap())
            state = self._cover_candidate_states.get(key, 'unavailable')
            if state == 'loading':
                self.cover_main_preview.setText(ui_text(self, 'Ładowanie…'))
            elif state == 'error':
                self.cover_main_preview.setText(ui_text(self, 'Nie udało się pobrać okładki'))
            else:
                self.cover_main_preview.setText(ui_text(self, 'Brak okładki'))
        else:
            self.cover_main_preview.setText('')
            edge = max(40, min(self.cover_main_preview.width(), self.cover_main_preview.height()) - 8)
            self.cover_main_preview.setPixmap(pix.scaled(edge, edge, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        for proposal_key in list(self._cover_proposal_labels):
            self._refresh_cover_proposal_widget(proposal_key)
        self._refresh_status_summary()

    def _select_cover_choice(self, key: str, *, allow_unavailable: bool = True, record_undo: bool = True):
        if key == 'manual' and self._cover_candidate_pixmaps.get('manual', QPixmap()).isNull():
            self._choose_cover()
            return
        if key not in self._cover_candidate_pixmaps:
            key = 'placeholder'
        pix = self._cover_candidate_pixmaps.get(key, QPixmap())
        if pix.isNull() and not allow_unavailable and not key.startswith('external:'):
            return
        if record_undo and not self._suspend_tracking:
            self._push_undo_state()
        self._selected_cover_key = key
        if key.startswith('external:'):
            self.cover_choice = 'external'
            self._selected_external_url = self._cover_candidate_urls.get(key)
        elif key in {'source', 'manual', 'placeholder'}:
            self.cover_choice = key
        self._update_cover_main_preview()
        if not self._suspend_tracking:
            self._refresh_dirty_state()
            self._observe_state()

    def selected_cover_url(self) -> str | None:
        if not self.selected_cover_available():
            return None
        if self.cover_choice == 'external':
            return self._selected_external_url or self.track.cover_art_url
        return self.track.cover_art_url

    def selected_cover_available(self) -> bool:
        key = getattr(self, '_selected_cover_key', 'placeholder')
        if key == 'placeholder':
            return False
        state = self._cover_candidate_states.get(key, '')
        pix = self._cover_candidate_pixmaps.get(key, QPixmap())
        return state not in {'loading', 'error', 'unavailable'} and not pix.isNull()

    def cover_save_state(self) -> dict[str, object] | None:
        """Return a confirmed cover update, or None to preserve stored data."""
        if self.selected_cover_available():
            return {
                'manual_cover_path': self.manual_cover_path,
                'cover_choice': self.cover_choice,
                'cover_art_url': self.selected_cover_url(),
                'has_cover': True,
            }
        if self.cover_choice == 'placeholder':
            return {
                'manual_cover_path': self.manual_cover_path,
                'cover_choice': 'placeholder',
                'cover_art_url': None,
                'has_cover': False,
            }
        return None

    def _preview_selected_cover(self):
        key = getattr(self, '_selected_cover_key', 'placeholder')
        pix = self._cover_candidate_pixmaps.get(key, QPixmap())
        note = self._cover_notes.get(key, '')
        show_cover_preview(self, pix, title='Podgląd wybranej okładki', note=note)

    def _choose_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, ui_text(self, 'Wybierz okładkę'), '', ui_text(self, 'Obrazy (*.jpg *.jpeg *.png *.webp)'))
        if not path:
            return
        if not self._suspend_tracking:
            self._push_undo_state()
        self.manual_cover_path = path
        self._cover_candidate_pixmaps['manual'] = QPixmap(path)
        self._cover_candidate_states['manual'] = 'ready' if not self._cover_candidate_pixmaps['manual'].isNull() else 'error'
        self._cover_notes['manual'] = 'Okładka wybrana ręcznie.'
        self.cover_choice = 'manual'
        self._selected_cover_key = 'manual'
        self._rebuild_cover_proposals()
        self._update_cover_main_preview()
        self._refresh_dirty_state()
        self._observe_state()
