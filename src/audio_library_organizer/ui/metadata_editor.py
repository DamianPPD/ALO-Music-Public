from __future__ import annotations

from copy import copy, deepcopy
from html import escape
from pathlib import Path
import sys

from PySide6.QtCore import Property, Qt, QTimer, QUrl, Signal, Slot, QRegularExpression, QSize, QRectF, QPoint, QPointF, QBuffer, QByteArray, QIODevice, QObject, QEvent
from PySide6.QtGui import QAction, QPixmap, QIcon, QColor, QPalette, QPainter, QPen, QPolygonF, QRegularExpressionValidator, QDesktopServices, QImageReader
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLayout,
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
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from audio_library_organizer import __version__, crash_debug
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.candidates import AcoustIDHit
from audio_library_organizer.jobs.audio_identification import SOURCE as AUDIO_SOURCE, approve_audio_source
from audio_library_organizer.metadata.artwork import extract_embedded_cover
from audio_library_organizer.metadata.naming import DEFAULT_FILENAME_TEMPLATE, normalize_title_case, propose_filename
from audio_library_organizer.metadata.normalization import normalize_music_text, is_valid_year_text
from audio_library_organizer.domain.preferences import default_name_rules
from audio_library_organizer.metadata.online_lock import is_online_locked
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.icons import editor_icon, library_icon
from audio_library_organizer.ui.state import display_bpm, metadata_completeness, effective_status, library_status_presentation, review_severity
from audio_library_organizer.ui.confidence import ConfidenceWidget
from audio_library_organizer.ui.player import CompactPlayerBar
from audio_library_organizer.ui.widgets import ClickableCoverLabel, SelectableElidedLineEdit, show_cover_preview
from audio_library_organizer.ui.genre_input import GenreChipInput
from audio_library_organizer.ui.theme import AUDIO_ID_ACCENT, APPLE_SOURCE_ACCENT
from audio_library_organizer.ui.i18n import ui_text, language_for, apply_static_language, localized_no_cover_name


def _editor_surface_palette(widget: QWidget) -> None:
    # QSS unpolish restores the palette saved before the first polish. Give
    # the editor's large backing surfaces a dark fallback before that snapshot.
    palette = widget.palette()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base):
        palette.setColor(role, QColor('#10141a'))
    widget.setPalette(palette)


def _fill_editor_native_background(event_type, message) -> bool:
    """Initialize Windows' native client before Qt's first backingstore paint."""
    if sys.platform != 'win32' or event_type != b'windows_generic_MSG' or not message:
        return False
    import ctypes
    from ctypes import wintypes

    native = wintypes.MSG.from_address(int(message))
    if native.message != 0x0014 or not native.wParam:  # WM_ERASEBKGND supplies the HDC
        return False
    try:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
        user32.FillRect.restype = ctypes.c_int
        gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
        gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi32.DeleteObject.restype = wintypes.BOOL
        rectangle = wintypes.RECT()
        if not user32.GetClientRect(native.hWnd, ctypes.byref(rectangle)):
            return False
        brush = gdi32.CreateSolidBrush(0x1a1410)  # COLORREF for #10141a (BGR)
        if not brush:
            return False
        try:
            painted = bool(user32.FillRect(native.wParam, ctypes.byref(rectangle), brush))
        finally:
            gdi32.DeleteObject(brush)
        crash_debug.record('editor.native_background', hwnd=int(native.hWnd),
                           message='WM_ERASEBKGND', painted=painted, color='#10141a')
        return painted
    except (OSError, AttributeError, TypeError, ValueError):
        return False


class RecognitionDetailsButton(QToolButton):
    """Keep the detail icon and trailing state chevron visible together."""

    def __init__(self, parent=None, *, icon_name='details', icon_size=14,
                 color='#bdcfd8', chevron_name='RecognitionDetailsChevron'):
        super().__init__(parent)
        self._chevron_color = color
        if icon_name is not None:
            self.setIcon(library_icon(icon_name, color, icon_size))
        self.setIconSize(QSize(icon_size, icon_size))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chevron = QLabel(self)
        self._chevron.setObjectName(chevron_name)
        self._chevron.setFixedSize(14, 14)
        self._chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.toggled.connect(self._refresh_chevron)
        self._refresh_chevron(False)

    def _refresh_chevron(self, expanded: bool) -> None:
        self._chevron.setPixmap(library_icon('collapse' if expanded else 'expand', self._chevron_color, 14).pixmap(14, 14))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        x = ((self.width() - self._chevron.width()) // 2 if self.icon().isNull()
             else self.width() - self._chevron.width() - 7)
        self._chevron.move(x,
                           (self.height() - self._chevron.height()) // 2)


class CoverProposalsHost(QFrame):
    """Center two rows of fixed square thumbnails in the available height."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(260, 260)
        self.setMaximumWidth(288)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor('#293944'), 1))
        x, y = self.width() // 2, self.height() // 2
        painter.drawLine(x, 12, x, self.height() - 13)
        painter.drawLine(12, y, self.width() - 13, y)
        painter.end()


class RecognitionDetailsPopup(QFrame):
    closed = Signal()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)


class _EditorSurfaceTrace(QObject):
    """Observe surface transitions without changing painting or event delivery."""

    def __init__(self, editor, surfaces):
        super().__init__(editor)
        self.editor_id = id(editor)
        self.pending_paint = {name for _widget, name in surfaces}
        for widget, name in surfaces:
            widget.setProperty('_alo_editor_surface', name)
            widget.installEventFilter(self)
            self._record(widget, 'constructed')

    def _record(self, widget, stage):
        color = widget.palette().color(widget.backgroundRole())
        crash_debug.record('editor.surface', editor_id=self.editor_id,
                           surface=widget.property('_alo_editor_surface'), stage=stage,
                           object_name=widget.objectName(), widget_class=widget.metaObject().className(),
                           background=color.name(), background_alpha=color.alpha(),
                           background_role=widget.backgroundRole().name,
                           visible=widget.isVisible(), size=[widget.width(), widget.height()],
                           auto_fill=widget.autoFillBackground(),
                           styled_background=widget.testAttribute(Qt.WidgetAttribute.WA_StyledBackground),
                           opaque_paint=widget.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent),
                           native_window=bool(widget.internalWinId()))

    def eventFilter(self, widget, event):
        kind = event.type()
        surface = widget.property('_alo_editor_surface')
        if kind in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.PaletteChange,
                    QEvent.Type.StyleChange, QEvent.Type.WinIdChange, QEvent.Type.Resize):
            self.pending_paint.add(surface)
            self._record(widget, kind.name)
        elif kind == QEvent.Type.Paint and surface in self.pending_paint:
            self.pending_paint.discard(surface)
            self._record(widget, 'Paint')
        return False


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


def _source_bundle_option(option, index, table):
    styled = QStyleOptionViewItem(option)
    styled.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus)
    if index.row() == table.hovered_row:
        styled.state |= QStyle.StateFlag.State_MouseOver
    else:
        styled.state &= ~QStyle.StateFlag.State_MouseOver
    return styled


class SourceBundleDelegate(QStyledItemDelegate):
    """Keep comparison rows neutral; the action caption marks the applied bundle."""

    def paint(self, painter, option, index):
        super().paint(painter, _source_bundle_option(option, index, self.parent()), index)


class SourceNameDelegate(QStyledItemDelegate):
    """Paint the source name in its provider color even under Qt's item stylesheet."""

    def paint(self, painter, option, index):
        styled = _source_bundle_option(option, index, self.parent())
        self.initStyleOption(styled, index)
        label = styled.text
        icon = QIcon(styled.icon)
        styled.text = ''
        styled.icon = QIcon()
        widget = styled.widget or self.parent()
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, widget)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        painter.save()
        icon_size = widget.iconSize()
        icon_left = styled.rect.left() + 6
        if not icon.isNull():
            painter.drawPixmap(icon_left, styled.rect.center().y() - icon_size.height() // 2,
                               icon.pixmap(icon_size))
        painter.setFont(styled.font)
        painter.setPen(foreground.color() if foreground is not None else QColor('#cbd6e2'))
        text_rect = styled.rect.adjusted(icon_left - styled.rect.left() + icon_size.width() + 8, 0, -3, 0)
        painter.setClipRect(text_rect)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        painter.restore()


class SourceComparisonTable(QTableWidget):
    """Keep source, title and action readable as the editor width changes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hovered_row = -1
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def mouseMoveEvent(self, event):
        row = self.indexAt(event.position().toPoint()).row()
        if row != self.hovered_row:
            self.hovered_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_row = -1
        self.viewport().update()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_columns()
        self.resize_to_rows()

    def resize_columns(self):
        header = self.horizontalHeader()
        action_width = 126
        for row in range(self.rowCount()):
            cell = self.cellWidget(row, 6)
            button = cell.findChild(QPushButton, 'UseSourceDataButton') if cell else None
            if button is not None:
                # Include both layout margins and the styled item's padding/border.
                action_width = max(action_width, button.width() + 32)
        fixed = {0: 208, 4: 58, 5: 95, 6: action_width}
        for column, width in fixed.items():
            header.resizeSection(column, width)
        available = self.viewport().width() - sum(fixed.values())
        artist = max(200, round(available * 29 / 71))
        title = max(280, round(available * 23 / 71))
        album = max(155, available - artist - title)
        if artist + title + album > available:
            artist = max(200, available - title - album)
            album = max(155, available - artist - title)
        for column, width in ((1, artist), (2, title), (3, album)):
            header.resizeSection(column, width)

    def resize_to_rows(self):
        overflow = sum(self.columnWidth(column) for column in range(self.columnCount())) > self.viewport().width()
        height = self.horizontalHeader().height() + max(1, self.rowCount()) * 31 + 6
        if overflow:
            height += self.horizontalScrollBar().sizeHint().height()
        if self.height() != height:
            self.setFixedHeight(height)


class AudioCandidateRowDelegate(QStyledItemDelegate):
    """Paint row hover and a centered radio selector for the pending choice."""

    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option)
        styled.state &= ~QStyle.StateFlag.State_HasFocus
        if index.row() == self.parent().hovered_row and not styled.state & QStyle.StateFlag.State_Selected:
            styled.state |= QStyle.StateFlag.State_MouseOver
        else:
            styled.state &= ~QStyle.StateFlag.State_MouseOver
        if index.column() != 0:
            super().paint(painter, styled, index)
            return
        self.initStyleOption(styled, index)
        styled.text = ''
        styled.icon = QIcon()
        table = self.parent()
        table.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, table)
        selected = bool(styled.state & QStyle.StateFlag.State_Selected)
        center = QPointF(styled.rect.center()) + QPointF(.5, .5)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(AUDIO_ID_ACCENT if selected else '#77809b'), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(center.x() - 7, center.y() - 7, 14, 14))
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(AUDIO_ID_ACCENT))
            painter.drawEllipse(QRectF(center.x() - 2.5, center.y() - 2.5, 5, 5))
        painter.restore()


class AudioCandidatesTable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hovered_row = -1
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setItemDelegate(AudioCandidateRowDelegate(self))

    def mouseMoveEvent(self, event):
        row = self.indexAt(event.position().toPoint()).row()
        if row != self.hovered_row:
            self.hovered_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_row = -1
        self.viewport().update()
        super().leaveEvent(event)


class MissingEmptyState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        box = QVBoxLayout(self); box.setContentsMargins(0, 2, 0, 2); box.setSpacing(1)
        graphic = MissingCompleteGraphic(self); box.addWidget(graphic, 0, Qt.AlignmentFlag.AlignHCenter)
        title = QLabel('Dane kompletne'); title.setObjectName('MissingEmptyTitle'); title.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(title)
        subtitle = QLabel('Wszystkie wymagane pola są uzupełnione'); subtitle.setObjectName('MissingEmptySubtitle'); subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(subtitle)


def _section_mark() -> QLabel:
    # The Library's technical header uses two QSS borders, not an SVG asset.
    mark = QLabel()
    mark.setObjectName('LibrarySectionMark')
    mark.setFixedSize(20, 7)
    return mark


def _section_header(text: str, *, icon_widget=None) -> QWidget:
    host = QWidget()
    host.setObjectName('EditorSectionHeader')
    host.setStyleSheet('background:transparent;')
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 5)
    row.setSpacing(8)
    label = QLabel(text)
    label.setObjectName('EditorSectionTitle')
    row.addWidget(icon_widget if icon_widget is not None else _section_mark())
    row.addWidget(label)
    row.addStretch(1)
    return host


def _cover_selection_marker_pixmap() -> QPixmap:
    size = 18
    pixmap = QPixmap(size * 3, size * 3)
    pixmap.setDevicePixelRatio(3.0)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#101c23'))
    painter.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(size, 0), QPointF(size, size)]))
    painter.setPen(QPen(QColor('#45616c'), .6, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawLine(QPointF(1, 1), QPointF(size - 1, size - 1))
    painter.setPen(QPen(QColor('#8fb9c8'), 1.25, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawPolyline(QPolygonF([QPointF(8.5, 5.2), QPointF(11, 7.5), QPointF(15, 3.8)]))
    painter.end()
    return pixmap


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

    def __init__(self, provider: str, value: str, color: str, parent=None, *, audio_icon: bool = False):
        super().__init__(parent)
        self.setObjectName('SourceMenuOption')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 10, 5)
        row.setSpacing(6)
        dot = QLabel()
        dot.setObjectName('SourceMenuDot')
        dot.setPixmap((editor_icon('audio_recognize', color, 15) if audio_icon else _color_dot_icon(color, 10)).pixmap(15 if audio_icon else 10, 15 if audio_icon else 10))
        dot.setFixedSize(15 if audio_icon else 10, 15 if audio_icon else 10)
        if audio_icon:
            dot.setProperty('sourceKind', 'audio_recognition')
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
    audio_scan_requested = Signal(object)
    audio_source_confirmed = Signal(object, object)
    navigation_requested = Signal(int)

    CORE_FIELDS = ('artist', 'title', 'year', 'genre', 'bpm')
    SOURCE_LABELS = {
        'Tag': 'TAG',
        'Discogs': 'DISCOGS',
        'MusicBrainz': 'MUSICBRAINZ',
        'Apple / iTunes': 'APPLE',
        'Ręcznie': 'RĘCZNIE',
        'Analiza audio': '≋ ANALIZA',
        AUDIO_SOURCE: 'ROZPOZNANIE AUDIO',
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
        AUDIO_SOURCE: 'audio_recognition',
        'Nazwa pliku': 'filename',
    }
    SOURCE_ORDER = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', AUDIO_SOURCE, 'Analiza audio', 'Nazwa pliku')
    SOURCE_COLORS = {
        'Tag': '#5ca3ff',
        'Discogs': '#43d17d',
        'MusicBrainz': '#b36cff',
        'Apple / iTunes': APPLE_SOURCE_ACCENT,
        'Analiza audio': '#ef5b64',
        AUDIO_SOURCE: AUDIO_ID_ACCENT,
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
        self.setObjectName('MetadataEditorDialog')
        self._native_first_paint_pending = True
        _editor_surface_palette(self)
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
        self._audio_scan_busy = False
        self._audio_scan_waits_for_thread = False
        self._audio_hits: list[AcoustIDHit] = []
        self._undo_stack: list[dict[str, object]] = []
        self._field_widgets: dict[str, QLineEdit | QTextEdit] = {}
        self._source_buttons: dict[str, QToolButton] = {}
        self._field_status_icons: dict[str, QLabel] = {}
        self._field_value_shells: dict[str, QFrame] = {}
        self._current_sources = dict(track.field_sources or {})
        self._source_values = deepcopy(track.field_source_values or {})
        self._last_applied_source: str | None = None
        self._cover_network = QNetworkAccessManager(self)
        self._cover_request_serial = 0
        self._cover_candidate_states: dict[str, str] = {}
        self._cover_pending_replies: set[QNetworkReply] = set()
        self._cover_reply_timers: dict[QNetworkReply, QTimer] = {}
        self._cover_live_ready = False
        self._cover_preview_active = False
        self._committed_player_cover = None
        self._cover_labels: dict[str, ClickableCoverLabel] = {}
        self._cover_buttons: dict[str, QPushButton] = {}
        self._cover_pixmaps: dict[str, QPixmap] = {}
        self._cover_notes: dict[str, str] = {}
        self._initial_values = self._track_value_map(track)
        self._ensure_current_source_values()
        self.finished.connect(lambda _result: self._cancel_pending_cover_requests())

        self.setWindowTitle('Edytuj metadane')
        available = self.screen().availableGeometry()
        target_width = min(1600, max(1, available.width() - 32))
        target_height = min(1060, max(1, available.height() - 64))
        self.resize(target_width, target_height)
        self.move(available.x() + (available.width() - target_width) // 2,
                  available.y() + (available.height() - target_height) // 2)
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
        _editor_surface_palette(self.content_scroll)
        _editor_surface_palette(self.content_scroll.viewport())
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
        content_host.setObjectName('MetadataEditorContent')
        _editor_surface_palette(content_host)
        content = QVBoxLayout(content_host)
        content.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
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
        _set_editor_button_icon(self.scan_online_button, 'editor_online_recognize', '#74e9fc', 20)
        self.scan_online_button.setToolTip('Uruchom rozpoznawanie online tylko dla tego utworu.')
        self.scan_online_button.clicked.connect(lambda: self.online_scan_requested.emit(self))
        pol.addWidget(self.scan_online_button)
        pol.addSpacing(4)
        self.audio_scan_button = QPushButton('Rozpoznaj po audio')
        self.audio_scan_button.setObjectName('SingleTrackAudioButton')
        self.audio_scan_button.setProperty('actionRole', 'primary')
        _set_editor_button_icon(self.audio_scan_button, 'audio_recognize', '#c1c7ff', 20)
        self.audio_scan_button.setToolTip('Rozpoznaj ten utwór po lokalnie wygenerowanym fingerprintcie audio.')
        self.audio_scan_button.clicked.connect(lambda: self.audio_scan_requested.emit(self))
        pol.addWidget(self.audio_scan_button)
        self.restore_pre_online_button = QPushButton('Przywróć dane sprzed online')
        self.restore_pre_online_button.setObjectName('RestoreOnlineButton')
        self.restore_pre_online_button.setProperty('actionRole', 'secondary')
        _set_editor_button_icon(self.restore_pre_online_button, 'undo', '#dce8ef', 18)
        self.restore_pre_online_button.setEnabled(bool(track.pre_online_metadata))
        self.restore_pre_online_button.clicked.connect(self._restore_pre_online_fields)
        pol.addWidget(self.restore_pre_online_button)
        self.online_lock.setProperty('actionRole', 'tool')
        pol.addWidget(self.online_lock)
        for online_action in (self.scan_online_button, self.audio_scan_button, self.restore_pre_online_button, self.online_lock):
            online_action.setFixedHeight(36)
        self._update_online_lock_button()
        content.addWidget(pre_online)
        self.set_online_scan_busy(False)

        recognition_result = QWidget()
        recognition_result.setObjectName('RecognitionResultRow')
        result_row = QHBoxLayout(recognition_result)
        result_row.setContentsMargins(2, 0, 0, 0)
        result_row.setSpacing(8)
        self.recognition_result_status = QLabel()
        self.recognition_result_status.setObjectName('RecognitionResultStatus')
        self.recognition_result_status.setTextFormat(Qt.TextFormat.RichText)
        result_row.addWidget(self.recognition_result_status)
        self.recognition_details_button = self.recognition_toggle = RecognitionDetailsButton()
        self.recognition_details_button.setObjectName('EditorRecognitionDetailsButton')
        self.recognition_details_button.setText('Szczegóły')
        self.recognition_details_button.setToolTip('Szczegóły rozpoznania')
        self.recognition_details_button.setAccessibleName('Szczegóły rozpoznania')
        self.recognition_details_button.setCheckable(True)
        self.recognition_details_button.setFixedHeight(24)
        self.recognition_details_button.clicked.connect(self._toggle_recognition_details)
        result_row.addWidget(self.recognition_details_button)
        result_row.addStretch(1)
        content.addWidget(recognition_result)

        audio_panel = self.audio_panel = QFrame()
        audio_panel.setObjectName('AudioRecognitionPanel')
        ap = QVBoxLayout(audio_panel)
        ap.setContentsMargins(10, 7, 10, 7)
        ap.setSpacing(4)
        self.audio_phase = QLabel('Oczekiwanie na rozpoznanie audio')
        self.audio_phase.setObjectName('AudioRecognitionPhase')
        self.audio_phase_header = QWidget()
        phase_header = QHBoxLayout(self.audio_phase_header)
        phase_header.setContentsMargins(0, 0, 0, 0)
        phase_header.setSpacing(6)
        self.audio_phase_icon = QLabel()
        self.audio_phase_icon.setPixmap(editor_icon('audio_recognize', AUDIO_ID_ACCENT, 17).pixmap(17, 17))
        self.audio_phase_icon.setFixedSize(17, 17)
        phase_header.addWidget(self.audio_phase_icon)
        phase_header.addWidget(self.audio_phase, 1)
        ap.addWidget(self.audio_phase_header)
        self.audio_candidates = AudioCandidatesTable(0, 5)
        self.audio_candidates.setObjectName('AudioRecognitionCandidates')
        self.audio_candidates.setHorizontalHeaderLabels(('Wybór', 'Tytuł / wersja', 'Wykonawca', 'Album / rok', 'Dopasowanie'))
        self.audio_candidates.verticalHeader().hide()
        self.audio_candidates.verticalHeader().setDefaultSectionSize(27)
        self.audio_candidates.horizontalHeader().setFixedHeight(26)
        self.audio_candidates.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.audio_candidates.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.audio_candidates.horizontalHeader().resizeSection(0, 56)
        self.audio_candidates.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.audio_candidates.horizontalHeader().resizeSection(4, 105)
        self.audio_candidates.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.audio_candidates.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.audio_candidates.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.audio_candidates.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audio_candidates.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.audio_candidates.currentCellChanged.connect(lambda row, _column, _old_row, _old_column: self._show_audio_candidate_detail(row))
        self.audio_candidate_content = QWidget()
        candidate_layout = QVBoxLayout(self.audio_candidate_content)
        candidate_layout.setContentsMargins(0, 0, 0, 0)
        candidate_layout.setSpacing(4)
        candidate_layout.addWidget(self.audio_candidates)
        self.audio_detail = QLabel('')
        self.audio_detail.setObjectName('AudioRecognitionDetail')
        self.audio_detail.setWordWrap(True)
        candidate_layout.addWidget(self.audio_detail)
        self.audio_confirm_button = QPushButton('Zatwierdź jako źródło audio')
        self.audio_confirm_button.setObjectName('AudioRecognitionConfirmButton')
        self.audio_confirm_button.setEnabled(False)
        self.audio_confirm_button.clicked.connect(self._approve_audio_candidate)
        self.audio_confirm_button.setFixedHeight(30)
        candidate_layout.addWidget(self.audio_confirm_button, 0, Qt.AlignmentFlag.AlignRight)
        ap.addWidget(self.audio_candidate_content)

        self.audio_summary = QFrame()
        self.audio_summary.setObjectName('AudioRecognitionSummary')
        summary = QHBoxLayout(self.audio_summary)
        summary.setContentsMargins(8, 5, 8, 5)
        summary.setSpacing(8)
        self.audio_summary_icon = QLabel()
        self.audio_summary_icon.setObjectName('AudioRecognitionSummaryIcon')
        self.audio_summary_icon.setPixmap(editor_icon('audio_recognize', AUDIO_ID_ACCENT, 17).pixmap(17, 17))
        self.audio_summary_icon.setFixedSize(23, 23)
        summary.addWidget(self.audio_summary_icon)
        summary_text = QVBoxLayout()
        summary_text.setSpacing(1)
        heading_row = QHBoxLayout()
        heading_row.setSpacing(4)
        summary_check = QLabel()
        summary_check.setPixmap(editor_icon('check', AUDIO_ID_ACCENT, 13).pixmap(13, 13))
        summary_check.setFixedSize(13, 13)
        heading_row.addWidget(summary_check)
        self.audio_summary_heading = QLabel('Źródło audio zatwierdzone')
        self.audio_summary_heading.setObjectName('AudioRecognitionSummaryHeading')
        heading_row.addWidget(self.audio_summary_heading, 1)
        summary_text.addLayout(heading_row)
        self.audio_summary_result = QLabel()
        self.audio_summary_result.setObjectName('AudioRecognitionSummaryResult')
        self.audio_summary_meta = QLabel()
        self.audio_summary_meta.setObjectName('AudioRecognitionSummaryMeta')
        for label in (self.audio_summary_result, self.audio_summary_meta):
            summary_text.addWidget(label)
        summary.addLayout(summary_text, 1)
        self.audio_show_candidates_button = QPushButton('Pokaż kandydatów')
        self.audio_show_candidates_button.setObjectName('AudioRecognitionShowCandidates')
        self.audio_show_candidates_button.setFixedHeight(30)
        self.audio_show_candidates_button.clicked.connect(self._open_audio_candidates)
        summary.addWidget(self.audio_show_candidates_button)
        self.audio_retry_button = QPushButton('Rozpoznaj ponownie')
        self.audio_retry_button.setObjectName('AudioRecognitionRetry')
        self.audio_retry_button.setFixedHeight(30)
        _set_editor_button_icon(self.audio_retry_button, 'audio_recognize', AUDIO_ID_ACCENT, 15)
        self.audio_retry_button.clicked.connect(lambda: self.audio_scan_requested.emit(self))
        summary.addWidget(self.audio_retry_button)
        ap.addWidget(self.audio_summary)
        self.audio_empty_status = QFrame()
        self.audio_empty_status.setObjectName('AudioRecognitionSummary')
        self.audio_empty_status.setProperty('emptyResult', True)
        empty_row = QHBoxLayout(self.audio_empty_status)
        empty_row.setContentsMargins(8, 5, 8, 5)
        empty_row.setSpacing(8)
        empty_icon = QLabel()
        empty_icon.setObjectName('AudioRecognitionEmptyIcon')
        empty_icon.setPixmap(library_icon('status_problem', '#f34d64', 20).pixmap(20, 20))
        empty_icon.setFixedSize(24, 24)
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_row.addWidget(empty_icon)
        empty_text = QVBoxLayout()
        empty_text.setSpacing(1)
        self.audio_empty_heading = QLabel('Brak wyników rozpoznawania audio')
        self.audio_empty_heading.setObjectName('AudioRecognitionSummaryHeading')
        self.audio_empty_message = QLabel('Nie znaleziono kandydatów.')
        self.audio_empty_message.setObjectName('AudioRecognitionSummaryResult')
        empty_text.addWidget(self.audio_empty_heading)
        empty_text.addWidget(self.audio_empty_message)
        empty_row.addLayout(empty_text, 1)
        self.audio_empty_retry = QPushButton('Rozpoznaj ponownie')
        self.audio_empty_retry.setObjectName('AudioRecognitionRetry')
        self.audio_empty_retry.setFixedHeight(30)
        _set_editor_button_icon(self.audio_empty_retry, 'audio_recognize', '#f34d64', 15)
        self.audio_empty_retry.clicked.connect(lambda: self.audio_scan_requested.emit(self))
        empty_row.addWidget(self.audio_empty_retry)
        ap.addWidget(self.audio_empty_status)
        self.audio_empty_status.hide()
        self._audio_empty_heading_key = 'Brak wyników rozpoznawania audio'
        self._audio_empty_message_key = 'Nie znaleziono kandydatów.'
        if track.audio_recognition:
            self._refresh_audio_summary()
            self.audio_summary.show()
            self.audio_candidate_content.hide()
            self.audio_phase_header.hide()
        else:
            self.audio_summary.hide()
            audio_panel.hide()
        content.addWidget(audio_panel)

        self.suspicious_warning = QLabel('Duża różnica względem danych sprzed online — sprawdź wykonawcę i tytuł przed zatwierdzeniem.')
        self.suspicious_warning.setObjectName('SuspiciousOnlineWarning')
        self.suspicious_warning.setWordWrap(True)
        self.suspicious_warning.setVisible(any('Duża różnica' in reason for reason in track.match_reasons))
        content.addWidget(self.suspicious_warning)

        # Metadata on the left; covers on the right. Recognition lives in a popup.
        workspace = QHBoxLayout()
        workspace.setSpacing(10)
        self.metadata_column = QWidget()
        self.metadata_column.setObjectName('MetadataEditorColumn')
        self.metadata_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        metadata_column_layout = QVBoxLayout(self.metadata_column)
        metadata_column_layout.setContentsMargins(0, 0, 0, 0)
        metadata_column_layout.setSpacing(8)
        self.cover_recognition_column = QWidget()
        self.cover_recognition_column.setObjectName('EditorCoverRecognitionColumn')
        self.cover_recognition_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cover_recognition_layout = QVBoxLayout(self.cover_recognition_column)
        cover_recognition_layout.setContentsMargins(0, 0, 0, 0)
        cover_recognition_layout.setSpacing(8)

        metadata = self.metadata_card = QFrame()
        metadata.setObjectName('PrimaryMetadataCard')
        metadata.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        form = QFormLayout(metadata)
        form.setContentsMargins(10, 8, 10, 8)
        form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        metadata_head = _section_header('Metadane utworu')
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
        self.comment.setFixedHeight(66)
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
        metadata_column_layout.addWidget(metadata)

        recognition = self.recognition_card = self.recognition_details_popup = RecognitionDetailsPopup(
            self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        _editor_surface_palette(recognition)
        recognition.setObjectName('RecognitionDetailsPopup')
        recognition.setFixedWidth(min(540, max(1, available.width() - 32)))
        recognition.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        ril = QVBoxLayout(recognition)
        ril.setContentsMargins(10, 8, 10, 8)
        ril.setSpacing(5)
        ri_title = _section_header('Szczegóły rozpoznania')
        ril.addWidget(ri_title)
        self.recognition_details_body = QWidget()
        self.recognition_details_body.setObjectName('EditorRecognitionDetails')
        recognition_body_layout = QVBoxLayout(self.recognition_details_body)
        recognition_body_layout.setContentsMargins(0, 0, 0, 0)
        recognition_body_layout.setSpacing(5)
        recognition_details = QGridLayout()
        self._recognition_details_grid = recognition_details
        self._recognition_detail_lines = []
        recognition_details.setHorizontalSpacing(20)
        recognition_details.setVerticalSpacing(5)
        recognition_details.setColumnStretch(0, 1)
        recognition_details.setColumnStretch(1, 1)
        recognition_body_layout.addLayout(recognition_details)
        self.recognition_values = {}
        for row, (key, label) in enumerate((
            ('source', 'Główne źródło'),
            ('fields', 'Rozpoznane pola'),
            ('duration', 'Długość'),
            ('bitrate', 'Bitrate'),
        )):
            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            name = QLabel(label)
            name.setObjectName('RecognitionFieldName')
            value = QLabel('—')
            value.setObjectName('RecognitionFieldValue')
            value.setWordWrap(key == 'source')
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            line.addWidget(name)
            line.addStretch(1)
            line.addWidget(value)
            recognition_details.addLayout(line, row, 0)
            self._recognition_detail_lines.append(line)
            self.recognition_values[key] = value

        for row, (key, label) in enumerate((('audio_status', 'Rozpoznanie audio'), ('audio_score', 'Dopasowanie'), ('audio_result', 'Wynik audio'))):
            line = QHBoxLayout()
            line.setSpacing(8)
            name = QLabel(label)
            name.setObjectName('RecognitionFieldName')
            value = QLabel('—')
            value.setObjectName('AudioRecognitionValue')
            value.setStyleSheet(f'color:{self.SOURCE_COLORS[AUDIO_SOURCE]};font-weight:700;')
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setWordWrap(True)
            line.addWidget(name)
            line.addStretch(1)
            line.addWidget(value)
            recognition_details.addLayout(line, row, 1)
            self._recognition_detail_lines.append(line)
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
        recognition_details.addLayout(confidence_row, 3, 1)
        self._recognition_detail_lines.append(confidence_row)
        self.recognition_bar = QProgressBar()
        self.recognition_bar.setObjectName('RecognitionConfidenceBar')
        self.recognition_bar.setRange(0, 100)
        self.recognition_bar.setTextVisible(False)
        self.recognition_bar.setFixedHeight(6)
        recognition_body_layout.addWidget(self.recognition_bar)
        self.recognition_details_scroll = QScrollArea()
        self.recognition_details_scroll.setObjectName('RecognitionDetailsScroll')
        self.recognition_details_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.recognition_details_scroll.setWidgetResizable(True)
        self.recognition_details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recognition_details_scroll.setWidget(self.recognition_details_body)
        for surface in (self.recognition_details_scroll, self.recognition_details_scroll.viewport(), self.recognition_details_body):
            _editor_surface_palette(surface)
        ril.addWidget(self.recognition_details_scroll)
        recognition.closed.connect(lambda: self.recognition_details_button.setChecked(False))
        self.finished.connect(lambda _result: recognition.hide())
        workspace.addWidget(self.metadata_column, 3)

        gallery = self.cover_gallery = QFrame()
        gallery.setObjectName('CoverGallery')
        gallery.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        gl = QVBoxLayout(gallery)
        gl.setContentsMargins(10, 8, 10, 8)
        gl.setSpacing(6)
        gh = _section_header('Wybór okładki')
        gl.addWidget(gh)

        cover_top = QHBoxLayout()
        cover_top.setSpacing(10)

        cover_main_col = QVBoxLayout()
        cover_main_col.setSpacing(4)
        self.cover_main_preview = ClickableCoverLabel('Brak okładki')
        self.cover_main_preview.setObjectName('CoverMainPreview')
        self.cover_main_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_main_preview.setFixedSize(288, 288)
        self.cover_main_preview.clicked.connect(self._preview_selected_cover)
        cover_main_col.addWidget(self.cover_main_preview, 0, Qt.AlignmentFlag.AlignLeft)

        self.cover_info = QFrame()
        self.cover_info.setObjectName('CoverInformationPanel')
        self.cover_info.setFixedWidth(288)
        self.cover_info.setFixedHeight(96)
        self.cover_info.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        info_layout = QVBoxLayout(self.cover_info)
        info_layout.setContentsMargins(6, 3, 6, 3)
        info_layout.setSpacing(2)
        self.cover_info_heading = QLabel('Informacje o okładce')
        self.cover_info_heading.setObjectName('CoverInformationHeading')
        info_layout.addWidget(self.cover_info_heading)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName('CoverInformationSeparator')
        info_layout.addWidget(separator)
        info_grid = QGridLayout()
        info_grid.setContentsMargins(0, 0, 0, 0)
        info_grid.setHorizontalSpacing(6)
        info_grid.setVerticalSpacing(1)
        self.cover_info_labels = {}
        self.cover_info_values = {}
        for key, title, row, column in (('source', 'Źródło', 0, 0),
                                      ('format', 'Format', 0, 2),
                                      ('type', 'Typ', 1, 0),
                                      ('resolution', 'Rozdzielczość', 2, 0),
                                      ('size', 'Rozmiar pliku', 2, 2)):
            label = QLabel(title)
            label.setObjectName('CoverInformationLabel')
            value = QLabel('—')
            value.setObjectName('CoverInformationValue')
            value.setWordWrap(key in {'source', 'type', 'resolution'})
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.cover_info_labels[key] = label
            self.cover_info_values[key] = value
            info_grid.addWidget(label, row, column)
            info_grid.addWidget(value, row, column + 1, 1, 3 if key == 'type' else 1)
        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(3, 1)
        info_layout.addLayout(info_grid)
        cover_main_col.addWidget(self.cover_info, 0, Qt.AlignmentFlag.AlignLeft)
        cover_main_col.addStretch(1)

        self.choose_cover_button = QPushButton('Dodaj okładkę z pliku')
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
        cover_side.addLayout(proposals_head)

        self.cover_proposals_host = CoverProposalsHost()
        self.cover_proposals_host.setObjectName('CoverProposalsHost')
        self.cover_proposals_grid = QGridLayout(self.cover_proposals_host)
        self.cover_proposals_grid.setContentsMargins(7, 7, 7, 7)
        self.cover_proposals_grid.setHorizontalSpacing(6)
        self.cover_proposals_grid.setVerticalSpacing(6)
        self.cover_proposals_grid.setColumnMinimumWidth(0, 120)
        self.cover_proposals_grid.setColumnMinimumWidth(1, 120)
        for index in range(2):
            self.cover_proposals_grid.setRowStretch(index, 1)
            self.cover_proposals_grid.setColumnStretch(index, 1)
        cover_side.addWidget(self.cover_proposals_host, 1)
        cover_top.addLayout(cover_side, 1)
        gl.addLayout(cover_top, 1)

        cover_actions = QWidget()
        cover_actions.setObjectName('CoverActions')
        cover_actions.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        cover_actions_layout = QHBoxLayout(cover_actions)
        cover_actions_layout.setContentsMargins(0, 2, 0, 0)
        cover_actions_layout.setSpacing(7)
        cover_actions_layout.addWidget(self.choose_cover_button, 1)
        cover_actions_layout.addWidget(self.search_cover_button, 1)
        gl.addWidget(cover_actions)

        self._cover_candidate_urls: dict[str, str] = {}
        self._cover_candidate_pixmaps: dict[str, QPixmap] = {}
        self._manual_cover_paths: dict[str, str] = {}
        self._cover_details: dict[str, dict[str, object]] = {}
        self._cover_proposal_labels: dict[str, ClickableCoverLabel] = {}
        self._selected_cover_key = 'placeholder'
        self._selected_external_url = track.cover_art_url
        cover_recognition_layout.addWidget(gallery)
        workspace.addWidget(self.cover_recognition_column, 2)
        content.addLayout(workspace)

        naming = QFrame()
        naming.setObjectName('FilenamePreviewCard')
        nl = QVBoxLayout(naming)
        nl.setContentsMargins(10, 6, 10, 6)
        nl.setSpacing(3)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        filename_icon = QLabel()
        filename_icon.setObjectName('OutputFilenameIcon')
        filename_icon.setFixedSize(20, 20)
        filename_icon.setPixmap(library_icon('metadata_edit', '#91adbe', 20).pixmap(20, 20))
        name_row.addWidget(filename_icon)
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
        self.source_legend_button = RecognitionDetailsButton(
            icon_name='legend', icon_size=18, color='#bdcbd3', chevron_name='SourceLegendChevron')
        self.source_legend_button.setObjectName('SourceLegendInfoButton')
        self.source_legend_button.setText('')
        self.source_legend_button.setIcon(library_icon('legend', '#bdcbd3', 18))
        self.source_legend_button.setIconSize(QSize(18, 18))
        self.source_legend_button.setFixedSize(42, 20)
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
            (AUDIO_SOURCE, 'ROZPOZNANIE AUDIO', 'identyfikacja przez fingerprint i AcoustID'),
            ('Nazwa pliku', 'NAZWA', 'wartość odczytana z nazwy pliku'),
        )
        legend_colors = dict(self.SOURCE_COLORS)
        legend_colors.setdefault('Ręcznie', '#ffb84d')
        for source_key, source, description in legend_rows:
            action = QWidgetAction(legend_menu)
            option = SourceMenuOption(
                ui_text(self, source),
                ui_text(self, description),
                legend_colors.get(source_key, '#8a96a8'),
                legend_menu,
                audio_icon=source_key == AUDIO_SOURCE,
            )
            action.setDefaultWidget(option)
            legend_menu.addAction(action)
        self.source_legend_button.setMenu(legend_menu)
        self.source_legend_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        legend_menu.aboutToShow.connect(lambda: self.source_legend_button._refresh_chevron(True))
        legend_menu.aboutToHide.connect(lambda: self.source_legend_button._refresh_chevron(False))
        compare_title = _section_header('Porównanie źródeł')
        compare_title.layout().insertWidget(2, self.source_legend_button)
        compare_head.addWidget(compare_title, 1)
        self.source_comparison_toggle = RecognitionDetailsButton(
            icon_name=None, color='#a8bdca', chevron_name='SourceComparisonChevron')
        self.source_comparison_toggle.setObjectName('SourceComparisonToggle')
        self.source_comparison_toggle.setCheckable(True)
        self.source_comparison_toggle.setChecked(True)
        self.source_comparison_toggle.setFixedSize(24, 22)
        self.source_comparison_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.source_comparison_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.source_comparison_toggle.toggled.connect(self._toggle_source_comparison)
        compare_head.addWidget(self.source_comparison_toggle, 0, Qt.AlignmentFlag.AlignRight)
        comparison_layout.addLayout(compare_head)

        self.source_table = SourceComparisonTable(0, 7)
        self.source_table.setObjectName('SourceComparisonTable')
        self.source_table.setHorizontalHeaderLabels(('Źródło', 'Wykonawca', 'Tytuł / wersja', 'Album / Release', 'Rok', 'Gatunek', 'Akcja'))
        self.source_table.verticalHeader().setVisible(False)
        self.source_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.source_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.source_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.source_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_table.setAlternatingRowColors(True)
        self.source_table.setIconSize(QSize(12, 12))
        self.source_table.setItemDelegate(SourceBundleDelegate(self.source_table))
        self.source_table.setItemDelegateForColumn(0, SourceNameDelegate(self.source_table))
        self.source_table.setWordWrap(False)
        self.source_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.source_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.source_table.verticalHeader().setDefaultSectionSize(31)
        self.source_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header = self.source_table.horizontalHeader()
        header.setFixedHeight(27)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.source_table.resize_columns()
        comparison_layout.addWidget(self.source_table)
        self._toggle_source_comparison(True)
        comparison.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        content.addWidget(comparison)
        content.addStretch(1)

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
        if self.compact_player is not None:
            self.compact_player.player_bar.cover_ready.connect(self._playing_cover_ready)
        self._refresh_source_comparison()
        self._connect_edit_tracking()
        self.discogs_url.textChanged.connect(self._refresh_url_action)
        self._suspend_tracking = False
        self._refresh_all()
        self._saved_state = self._capture_editor_state()
        self._last_observed_state = deepcopy(self._saved_state)
        self._cover_live_ready = True
        self.finished.connect(lambda _result: self._restore_live_cover_preview())
        self._update_ready_button()
        self._refresh_url_action()
        self._background_trace = _EditorSurfaceTrace(self, (
            (self, 'dialog'), (self.content_scroll, 'scroll'),
            (self.content_scroll.viewport(), 'viewport'),
            (self.content_scroll.widget(), 'content'),
            (self.recognition_details_popup, 'recognition-popup'),
        ))
        # show()/exec() creates the native window before its usual polish pass.
        # Resolve the theme palette first so navigation never exposes Qt's light default.
        self.ensurePolished()

    def _toggle_recognition_details(self, expanded: bool) -> None:
        popup = self.recognition_details_popup
        if not expanded:
            popup.hide()
            return
        popup.ensurePolished()
        self._resize_recognition_details()
        popup.show()
        popup.setFocus()

    def _resize_recognition_details(self) -> None:
        popup = self.recognition_details_popup
        scroll = self.recognition_details_scroll
        body = self.recognition_details_body
        available = self.recognition_details_button.screen().availableGeometry()
        popup.setFixedWidth(min(540, max(1, available.width() - 32)))
        # Use one column on narrow screens; hiding a horizontal scrollbar would
        # otherwise make the right-hand values inaccessible.
        grid = self._recognition_details_grid
        narrow = popup.width() < 480
        for index, line in enumerate(self._recognition_detail_lines):
            grid.removeItem(line)
            line.invalidate()
            grid.addLayout(line, index if narrow else index % 4, 0 if narrow else index // 4)
        grid.setColumnStretch(1, 0 if narrow else 1)
        grid.invalidate()
        margins = popup.layout().contentsMargins()
        body_width = popup.contentsRect().width() - margins.left() - margins.right()
        header_height = popup.layout().itemAt(0).sizeHint().height()
        overhead = (margins.top() + margins.bottom() + 2 * popup.frameWidth()
                    + header_height + popup.layout().spacing())
        max_body_height = max(1, min(360, available.height() - 32) - overhead)
        body.layout().invalidate()
        body_height = body.layout().totalHeightForWidth(body_width)
        if body_height > max_body_height:
            body_width -= scroll.verticalScrollBar().sizeHint().width()
            body_height = body.layout().totalHeightForWidth(max(1, body_width))
        body.setMinimumHeight(body_height)
        scroll.setFixedHeight(min(body_height, max_body_height))
        popup.adjustSize()
        popup.layout().activate()
        anchor = self.recognition_details_button.mapToGlobal(QPoint(0, self.recognition_details_button.height() + 4))
        x = min(max(anchor.x(), available.left()), max(available.left(), available.right() - popup.width() + 1))
        y = min(max(anchor.y(), available.top()), max(available.top(), available.bottom() - popup.height() + 1))
        popup.move(x, y)

    def _toggle_source_comparison(self, expanded: bool) -> None:
        self.source_table.setVisible(expanded)
        caption = 'Zwiń porównanie źródeł' if expanded else 'Rozwiń porównanie źródeł'
        self.source_comparison_toggle.setProperty('_alo_pl_tooltip', caption)
        self.source_comparison_toggle.setToolTip(ui_text(self, caption))
        self.source_comparison_toggle.setAccessibleName(ui_text(self, caption))

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
        host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
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
        indicator.setFixedSize(24, 24)
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
                option = SourceMenuOption(ui_text(self, self.SOURCE_LABELS.get(source, source.upper())), text, color, menu,
                                          audio_icon=source == AUDIO_SOURCE)
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
        if hasattr(self, 'audio_scan_button'):
            self.audio_scan_button.setEnabled(not locked and not self._audio_scan_busy)
        if hasattr(self, 'audio_retry_button'):
            self.audio_retry_button.setEnabled(not locked and not self._audio_scan_busy)
            self.audio_empty_retry.setEnabled(not locked and not self._audio_scan_busy)

    def set_online_scan_busy(self, busy: bool) -> None:
        self._online_scan_busy = bool(busy)
        if not hasattr(self, 'scan_online_button'):
            return
        self.scan_online_button.setText(ui_text(self, 'Rozpoznawanie…' if busy else 'Rozpoznaj online'))
        _set_editor_button_icon(self.scan_online_button, 'editor_online_recognize', '#91a4b0' if busy else '#74e9fc', 20)
        self.scan_online_button.setEnabled(not busy and not self.online_lock.isChecked())
        self.previous_file_button.setEnabled(not busy and self.navigation_index > 0)
        self.next_file_button.setEnabled(not busy and self.navigation_index + 1 < self.navigation_total)

    def start_audio_lookup(self, *, wait_for_thread: bool = False) -> None:
        self._audio_scan_waits_for_thread = wait_for_thread
        self.audio_panel.show()
        self.audio_empty_status.hide()
        self._audio_hits.clear()
        self.audio_candidates.setRowCount(0)
        self.audio_detail.clear()
        self._update_audio_confirm_button(-1)
        self.audio_phase_header.show()
        if self.track.audio_recognition:
            self.audio_candidate_content.hide()
            self.audio_summary.show()
        else:
            self.audio_candidate_content.show()
        self._refresh_audio_summary()
        self.audio_phase.setText(ui_text(self, 'Oczekiwanie na rozpoznanie audio'))
        self.set_audio_scan_busy(True)

    def set_audio_scan_busy(self, busy: bool) -> None:
        self._audio_scan_busy = bool(busy)
        self.audio_scan_button.setEnabled(not busy and not self.online_lock.isChecked())
        self.audio_retry_button.setEnabled(not busy and not self.online_lock.isChecked())
        self.audio_empty_retry.setEnabled(not busy and not self.online_lock.isChecked())
        self.audio_scan_button.setText(ui_text(self, 'Rozpoznawanie…' if busy else 'Rozpoznaj po audio'))
        self._update_audio_confirm_button(self.audio_candidates.currentRow())
        self.previous_file_button.setEnabled(not busy and self.navigation_index > 0)
        self.next_file_button.setEnabled(not busy and self.navigation_index + 1 < self.navigation_total)

    @Slot()
    def finish_audio_lookup(self) -> None:
        self._audio_scan_waits_for_thread = False
        self.set_audio_scan_busy(False)

    def set_audio_phase(self, phase: str) -> None:
        messages = {'fingerprint': 'Generowanie fingerprintu…', 'lookup': 'Wyszukiwanie w AcoustID…'}
        self.audio_phase.setText(ui_text(self, messages.get(phase, phase)))

    def show_audio_error(self, message: str) -> None:
        self.audio_panel.show()
        self.audio_phase_header.hide()
        self.audio_candidate_content.hide()
        self.audio_summary.hide()
        self._show_audio_empty('Błąd rozpoznawania audio', message)
        self.audio_phase.setText(ui_text(self, 'Błąd rozpoznawania audio'))
        self.audio_detail.setText(ui_text(self, message))
        if not self._audio_scan_waits_for_thread:
            self.set_audio_scan_busy(False)

    def _show_audio_empty(self, heading: str, message: str) -> None:
        self._audio_empty_heading_key = heading
        self._audio_empty_message_key = message
        self.audio_empty_heading.setText(ui_text(self, heading))
        self.audio_empty_message.setText(ui_text(self, message))
        self.audio_empty_status.show()

    def show_audio_candidates(self, hits: list[AcoustIDHit]) -> None:
        self.audio_panel.show()
        self.audio_summary.hide()
        self.audio_empty_status.hide()
        self._audio_hits = [hit for hit in hits if (hit.artist or '').strip() and (hit.title or '').strip()][:5]
        self.audio_candidate_content.setVisible(bool(self._audio_hits))
        self.audio_phase_header.setVisible(bool(self._audio_hits))
        if not self._audio_hits:
            self._show_audio_empty('Brak wyników rozpoznawania audio', 'Nie znaleziono kandydatów.')
        self.audio_candidates.clearContents()
        self.audio_candidates.setRowCount(len(self._audio_hits))
        for row, hit in enumerate(self._audio_hits):
            values = ('', hit.title, hit.artist, ' · '.join(filter(None, (hit.album, hit.year))), f'{round(hit.score * 100)}%')
            for column, value in enumerate(values):
                item = QTableWidgetItem(value or ('—' if column == 3 else ''))
                if column in (0, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(value or '')
                self.audio_candidates.setItem(row, column, item)
        self._refresh_audio_candidate_markers()
        self.audio_candidates.setFixedHeight(26 + max(1, len(self._audio_hits)) * 27 + 6)
        self.audio_phase.setText(ui_text(self, 'Znaleziono kandydatów' if self._audio_hits else 'Brak wyników'))
        self.audio_detail.setText('' if self._audio_hits else ui_text(self, 'Brak kandydatów z wykonawcą i tytułem.'))
        self._update_audio_confirm_button(-1)
        if not self._audio_scan_waits_for_thread:
            self.set_audio_scan_busy(False)

    def _approved_audio_hit(self) -> AcoustIDHit | None:
        approved = self.track.audio_recognition or {}
        if not approved.get('recording_id') or not approved.get('title') or not approved.get('artist'):
            return None
        return AcoustIDHit(approved['recording_id'], float(approved.get('score') or 0), approved['title'],
                           approved['artist'], approved.get('album'), approved.get('year'), approved.get('acoustid_id'))

    def _refresh_audio_candidate_markers(self) -> None:
        for row, hit in enumerate(self._audio_hits):
            item = self.audio_candidates.item(row, 0)
            if item:
                is_approved = self._audio_hit_is_approved(hit)
                # Approval stays in the tooltip; the delegate paints only the current row's selector.
                item.setText('')
                item.setIcon(QIcon())
                item.setToolTip(ui_text(self, 'Źródło audio zatwierdzone') if is_approved else '')
                item.setForeground(QColor(AUDIO_ID_ACCENT))

    def _audio_hit_is_approved(self, hit: AcoustIDHit) -> bool:
        approved = self.track.audio_recognition or {}
        return bool(approved.get('recording_id')) and approved['recording_id'] == hit.recording_id

    def _update_audio_confirm_button(self, index: int) -> None:
        valid = 0 <= index < len(self._audio_hits)
        self.audio_confirm_button.setText(ui_text(self, 'Zatwierdź jako źródło audio'))
        self.audio_confirm_button.setEnabled(valid and not self._audio_scan_busy)

    def _refresh_audio_summary(self) -> None:
        approved = self.track.audio_recognition or {}
        if not approved:
            self.audio_summary.hide()
            return
        self.audio_summary_heading.setText(ui_text(self, 'Źródło audio zatwierdzone'))
        self.audio_summary_result.setText(f'{approved.get("artist") or "—"} – {approved.get("title") or "—"}')
        details = [f'{round(float(approved["score"]) * 100)}%' if approved.get('score') is not None else None,
                   approved.get('year'), 'MusicBrainz / AcoustID']
        self.audio_summary_meta.setText(' · '.join(str(value) for value in details if value))
        self._refresh_audio_candidate_markers()

    def _open_audio_candidates(self) -> None:
        if not self._audio_hits:
            approved = self._approved_audio_hit()
            if approved:
                self.show_audio_candidates([approved])
                return
        self.audio_summary.hide()
        self.audio_phase_header.show()
        self.audio_candidate_content.show()
        self._refresh_audio_candidate_markers()
        self._update_audio_confirm_button(self.audio_candidates.currentRow())

    def _show_audio_candidate_detail(self, index: int) -> None:
        self._update_audio_confirm_button(index)
        if 0 <= index < len(self._audio_hits):
            hit = self._audio_hits[index]
            details = [f'{ui_text(self, "Album")}: {hit.album or "—"}',
                       f'{ui_text(self, "Rok")}: {hit.year or "—"}',
                       f'MusicBrainz: {hit.recording_id}',
                       f'AcoustID: {hit.acoustid_id or "—"}',
                       ui_text(self, 'Wynik jest propozycją, nie gwarancją poprawności.')]
            self.audio_detail.setText('  ·  '.join(details))

    def _approve_audio_candidate(self) -> None:
        index = self.audio_candidates.currentRow()
        if not 0 <= index < len(self._audio_hits):
            return
        previous = deepcopy(self.track)
        approve_audio_source(self.track, self._audio_hits[index])
        self._source_values = deepcopy(self.track.field_source_values)
        for field_name in self._field_widgets:
            self._rebuild_source_menu(field_name)
        self._refresh_source_comparison()
        self._refresh_recognition_info()
        self.audio_phase.setText(ui_text(self, 'Źródło audio zatwierdzone'))
        self._refresh_audio_summary()
        self.audio_summary.show()
        self.audio_candidate_content.hide()
        self.audio_phase_header.hide()
        self.audio_source_confirmed.emit(self, previous)

    def refresh_audio_language(self) -> None:
        for field_name in self._field_widgets:
            self._rebuild_source_menu(field_name)
            self._refresh_source_badge(field_name)
        self._refresh_source_comparison()
        self._refresh_recognition_info()
        self._refresh_audio_summary()
        if not self.audio_empty_status.isHidden():
            self._show_audio_empty(self._audio_empty_heading_key, self._audio_empty_message_key)
        self._refresh_cover_information()
        self._show_audio_candidate_detail(self.audio_candidates.currentRow())
        if self.compact_player is not None:
            self.compact_player.surface.set_muted(self.compact_player.player_bar.audio.isMuted())

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
            problem = self._field_status_kind(field_name) == 'critical'
            if field_name == 'year':
                widget.setProperty('invalidYear', not is_valid_year_text(self.year.text().strip()))
            widget.setProperty('missingRequired', missing)
            widget.setProperty('fieldProblem', problem)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            inner_edit = getattr(widget, 'edit', None)
            if inner_edit is not None:
                inner_edit.setProperty('missingRequired', missing)
                inner_edit.setProperty('fieldProblem', problem)
                inner_edit.style().unpolish(inner_edit)
                inner_edit.style().polish(inner_edit)
            shell = self._field_value_shells.get(field_name)
            if shell is not None:
                shell.setProperty('missingRequired', missing)
                shell.setProperty('fieldProblem', problem)
                shell.style().unpolish(shell)
                shell.style().polish(shell)

    def _field_status_kind(self, field_name: str) -> str:
        text = self._widget_text(self._field_widgets[field_name]).strip()
        if field_name in self.CORE_FIELDS and not text:
            return 'critical'
        if field_name == 'year' and not is_valid_year_text(text):
            return 'critical'
        if field_name == 'bpm' and text:
            try:
                float(text.replace(',', '.'))
            except ValueError:
                return 'critical'
        return 'ok'

    def _refresh_status_summary(self) -> None:
        # Field presentation is independent of the removed file-status panel.
        icons = {'warning': ('status_review', '#d8a23a'),
                 'critical': ('status_problem', '#f34d64')}
        for field_name, indicator in self._field_status_icons.items():
            field_kind = self._field_status_kind(field_name)
            problematic = field_kind in icons
            text = self._widget_text(self._field_widgets[field_name]).strip()
            indicator.setText('')
            if problematic:
                icon_name, color = icons[field_kind]
                indicator.setPixmap(library_icon(icon_name, color, 20).pixmap(20, 20))
            else:
                indicator.setPixmap(QPixmap())
            indicator.setProperty('statusKind', field_kind)
            indicator.setVisible(problematic)
            indicator.style().unpolish(indicator)
            indicator.style().polish(indicator)
            tooltip = '' if not problematic else 'Brak danych' if not text else 'PROBLEM'
            indicator.setToolTip(ui_text(self, tooltip))

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
        self.recognition_result_status.setProperty('sourceColor', source_color)
        self.recognition_result_status.setText(
            escape(ui_text(self, 'Główne źródło')) + ': '
            f'<span style="color:{source_color};font-weight:700;">{escape(ui_text(self, source_display))}</span>'
        )
        self.recognition_values['source'].setProperty('sourceColor', source_color)
        self.recognition_values['source'].setStyleSheet(
            f'color:{source_color}; background:transparent; font-weight:700;'
        )
        self.recognition_values['fields'].setText(f'{present}/5')
        self.recognition_values['duration'].setText(duration)
        self.recognition_values['bitrate'].setText(bitrate)
        approved = self.track.audio_recognition
        self.recognition_values['audio_status'].setText(ui_text(self, 'Zatwierdzone') if approved else '—')
        score = approved.get('score') if approved else None
        self.recognition_values['audio_score'].setText(f'{round(float(score) * 100)}%' if score is not None else '—')
        self.recognition_values['audio_result'].setText(
            f'{approved.get("artist") or "—"} – {approved.get("title") or "—"}' if approved else '—'
        )
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
        if self.recognition_details_popup.isVisible():
            self._resize_recognition_details()

    def _refresh_current_status_banner(self) -> None:
        # Status jest celowo prezentowany tylko na dolnym przycisku edytora.
        return

    def _source_rows(self) -> list[str]:
        # Comparison stays compact: only sources that can populate a visible
        # comparison column are shown. Audio analysis (BPM only) remains in the
        # per-field badge/legend instead of creating an all-dash table row.
        comparison_fields = ('title', 'artist', 'album', 'year', 'genre')
        available: set[str] = set()
        for field_name in comparison_fields:
            values = self._source_values.get(field_name, {})
            if isinstance(values, dict):
                available.update(source for source, value in values.items() if value not in (None, ''))
        available.discard('Przywrócone')
        preferred = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', AUDIO_SOURCE, 'Nazwa pliku', 'Ręcznie')
        sources = [source for source in preferred if source in available]
        sources.extend(source for source in sorted(available) if source not in sources)
        return sources

    def _refresh_source_comparison(self) -> None:
        if not hasattr(self, 'source_table'):
            return
        sources = self._source_rows()
        self.source_table.clearContents()  # Drop any old cell widgets before inserting source labels and actions.
        self.source_table.setRowCount(len(sources))
        colors = self.SOURCE_COLORS
        display_names = {
            'Tag': 'TAG',
            'Discogs': 'Discogs',
            'MusicBrainz': 'MusicBrainz',
            'Apple / iTunes': 'Apple / iTunes',
            'Analiza audio': 'ANALIZA AUDIO',
            AUDIO_SOURCE: 'ROZPOZNANIE AUDIO',
            'Nazwa pliku': 'NAZWA',
            'Ręcznie': 'RĘCZNIE',
        }
        for row, source in enumerate(sources):
            source_color = colors.get(source, '#cbd6e2')
            source_item = QTableWidgetItem(ui_text(self, display_names.get(source, source)))
            source_item.setData(Qt.ItemDataRole.UserRole, source)
            source_item.setForeground(QColor(source_color))
            font = source_item.font()
            font.setPointSizeF(max(7.2, font.pointSizeF() - 1.0))
            font.setBold(True)
            source_item.setFont(font)
            source_item.setIcon(editor_icon('audio_recognize', source_color, 15) if source == AUDIO_SOURCE
                                else _color_dot_icon(source_color, 12))
            self.source_table.setItem(row, 0, source_item)
            for column, field_name in ((1, 'artist'), (2, 'title'), (3, 'album'), (4, 'year'), (5, 'genre')):
                value = self._source_values.get(field_name, {}).get(source)
                shown = self._display_source_value(field_name, value) if value not in (None, '') else '—'
                self.source_table.setItem(row, column, QTableWidgetItem(shown))
            selected = source == self._last_applied_source
            caption = '✓ Aktualnie wybrane' if selected else 'Użyj danych'
            use_button = QPushButton(ui_text(self, caption))
            use_button.setObjectName('UseSourceDataButton')
            use_button.setProperty('selected', selected)
            use_button.setProperty('_alo_pl_text', caption)
            use_button.setToolTip(ui_text(self, f'Zastosuj dostępne dane ze źródła: {display_names.get(source, source)}'))
            use_button.clicked.connect(lambda _checked=False, s=source: self._apply_source_bundle(s))
            cell = QWidget()
            cell.setObjectName('UseSourceDataCell')
            cell.setProperty('selected', selected)
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(7, 3, 7, 3)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(use_button)
            self.source_table.setCellWidget(row, 6, cell)
            # Measure after parenting, when the editor's font/style is resolved.
            use_button.ensurePolished()
            use_button.setFixedSize(max(82, use_button.fontMetrics().horizontalAdvance(use_button.text()) + 18), 18)
            for column in range(6):
                self.source_table.item(row, column).setData(Qt.ItemDataRole.UserRole + 1, selected)
        self.source_table.resize_columns()
        self.source_table.resize_to_rows()

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
        self._last_applied_source = source
        self._refresh_all()
        self._refresh_source_comparison()
        self.source_table.clearSelection()
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
        self._commit_live_cover_preview()
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
        self._restore_live_cover_preview()
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
        if self._online_scan_busy or self._audio_scan_busy:
            message = (
                'Rozpoznawanie online nadal trwa. Poczekaj na zakończenie operacji.'
                if self._online_scan_busy else
                'Rozpoznawanie po audio nadal trwa. Poczekaj na zakończenie operacji.'
            )
            guard = EditorCloseGuardDialog(
                [('amber', message)],
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
        crash_debug.record('editor.navigation.request', editor_id=id(self), delta=int(delta),
                           index=self.navigation_index, total=self.navigation_total)
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
            self._restore_live_cover_preview()
            event.accept()
            return
        if self._confirm_close():
            self._restore_live_cover_preview()
            self._force_closing = True
            event.accept()
        else:
            event.ignore()

    def nativeEvent(self, event_type, message):
        # Qt acknowledges native erases without filling them. The new HWND can
        # be exposed before the first backingstore flush; QPalette/QSS do not
        # paint that interval. Leave every subsequent erase to Qt so established
        # child content is never cleared outside the backingstore's dirty region.
        if self._native_first_paint_pending and _fill_editor_native_background(event_type, message):
            return True, 1
        return False, 0

    def paintEvent(self, event):
        super().paintEvent(event)
        handle = self.windowHandle()
        if handle is not None and handle.isExposed():
            self._native_first_paint_pending = False

    def hideEvent(self, event):
        self.recognition_details_popup.hide()
        super().hideEvent(event)

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
        self._manual_cover_paths = {}
        self._cover_candidate_states = {}
        self._cover_details = {}

        source_pix = QPixmap()
        embedded = extract_embedded_cover(self.track.path)
        if embedded:
            source_pix.loadFromData(embedded[0])
            self._cover_details['source'] = {
                'bytes': len(embedded[0]), 'format': self._cover_image_format(embedded[0]),
                'type': 'Okładka główna (Front)',
            }
        self._cover_candidate_pixmaps['source'] = source_pix
        self._cover_candidate_states['source'] = 'ready' if not source_pix.isNull() else 'unavailable'
        self._cover_notes['source'] = 'Okładka osadzona w pliku źródłowym.'

        placeholder = QPixmap(str(asset_path(localized_no_cover_name(self))))
        self._cover_candidate_pixmaps['placeholder'] = placeholder
        self._cover_candidate_states['placeholder'] = 'ready'
        self._cover_notes['placeholder'] = 'Brak potwierdzonej okładki — grafika zastępcza ALO Music.'

        manual = QPixmap(self.manual_cover_path) if self.manual_cover_path and Path(self.manual_cover_path).is_file() else QPixmap()
        if not manual.isNull():
            path = Path(self.manual_cover_path)
            self._manual_cover_paths['manual'] = str(path)
            self._cover_details['manual'] = {'bytes': path.stat().st_size,
                                             'format': path.suffix.lstrip('.').upper().replace('JPEG', 'JPG')}
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

        playing_cover_url = None
        playing_cover_pixmap = QPixmap()
        if self.compact_player is not None:
            bar = self.compact_player.player_bar
            if (bar.current_track is not None
                    and Path(bar.current_track.path).resolve() == Path(self.track.path).resolve()):
                playing_cover_url = bar._cover_loaded_url
                playing_cover_pixmap = bar._cover_pixmap

        online_slots = 5 - int(not source_pix.isNull()) - int(not manual.isNull())
        online_covers = [(source, url) for source, url in raw_covers.items() if url]
        if self.cover_choice == 'external' and self._selected_external_url:
            selected_cover = next((item for item in online_covers if item[1] == self._selected_external_url), None)
            if selected_cover and selected_cover not in online_covers[:online_slots]:
                online_covers = [*online_covers[:online_slots - 1], selected_cover]
        for source, url in online_covers[:online_slots]:
            key = f'external:{source}'
            self._cover_candidate_urls[key] = str(url)
            cached = playing_cover_pixmap if playing_cover_url == str(url) else QPixmap()
            self._cover_candidate_pixmaps[key] = cached
            self._cover_candidate_states[key] = 'ready' if not cached.isNull() else 'loading'
            self._cover_notes[key] = f'Okładka online — {source}.'

        self._rebuild_cover_proposals()

        for key, url in self._cover_candidate_urls.items():
            if self._cover_candidate_states[key] == 'loading':
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

    def _playing_cover_ready(self, path: Path, url: str, pix: QPixmap) -> None:
        if Path(path).resolve() != Path(self.track.path).resolve() or pix.isNull():
            return
        key = getattr(self, '_selected_cover_key', '')
        if not key.startswith('external:') or self._cover_candidate_urls.get(key) != url:
            return
        self._cover_candidate_pixmaps[key] = pix
        self._cover_candidate_states[key] = 'ready'
        self._refresh_cover_proposal_widget(key)
        self._update_cover_main_preview()

    def _current_cover_player(self):
        if self.compact_player is None:
            return None
        bar = self.compact_player.player_bar
        if bar.current_track is None:
            return None
        return bar if Path(bar.current_track.path).resolve() == Path(self.track.path).resolve() else None

    def _sync_live_cover_preview(self, pix: QPixmap) -> None:
        if not self._cover_live_ready or (self._suspend_tracking and not self._cover_preview_active):
            return
        bar = self._current_cover_player()
        if bar is None or bar._cover_pixmap.cacheKey() == pix.cacheKey():
            return
        if not self._cover_preview_active:
            self._committed_player_cover = (bar._cover_pixmap, bar._cover_loaded_url,
                                            bar._cover_note, bar._cover_reply is not None)
        # Any older online reply belongs to the committed cover, not to this preview.
        bar._cancel_cover_request()
        bar._cover_loaded_url = None
        bar._set_cover_image(pix)
        saved = getattr(self, '_saved_state', None)
        same_saved_choice = saved is not None and all(
            saved.get(field) == self._capture_editor_state().get(field)
            for field in ('selected_cover_key', 'cover_choice', 'manual_cover_path', 'selected_external_url')
        )
        if same_saved_choice and not self._cover_preview_active:
            bar._cover_loaded_url = self._selected_external_url if self.cover_choice == 'external' else None
            self._committed_player_cover = (bar._cover_pixmap, bar._cover_loaded_url, bar._cover_note, False)
        else:
            self._cover_preview_active = True

    def _commit_live_cover_preview(self) -> None:
        bar = self._current_cover_player()
        if bar is not None and self._cover_preview_active:
            bar._cover_loaded_url = self._selected_external_url if self.cover_choice == 'external' else None
            self._committed_player_cover = (bar._cover_pixmap, bar._cover_loaded_url, bar._cover_note, False)
        self._cover_preview_active = False

    def _restore_live_cover_preview(self) -> None:
        if not self._cover_preview_active:
            return
        bar = self._current_cover_player()
        if bar is not None and self._committed_player_cover is not None:
            pix, url, note, was_loading = self._committed_player_cover
            bar._cancel_cover_request()
            bar._cover_loaded_url = url
            bar._set_cover_image(pix, note)
            if was_loading:
                bar._load_cover(self.track)
        self._cover_preview_active = False

    def _rebuild_cover_proposals(self) -> None:
        self._clear_cover_proposals()
        entries: list[tuple[str, str]] = []
        if not self._cover_candidate_pixmaps.get('source', QPixmap()).isNull():
            entries.append(('source', 'OBECNA'))
        external_entries = [(key, key.split(':', 1)[1]) for key in self._cover_candidate_urls]
        entries.extend(external_entries)
        entries.extend((key, 'WŁASNA') for key in self._manual_cover_paths)
        entries.append(('placeholder', 'BRAK OKŁADKI'))
        # Limit only the visible grid. Keep the active cover and "no cover"
        # reachable without discarding loaded candidates or changing acquisition.
        visible_entries = entries[:-1][:3]
        selected_key = getattr(self, '_selected_cover_key', '')
        selected_entry = next((entry for entry in entries[:-1] if entry[0] == selected_key), None)
        if selected_entry is not None and selected_entry not in visible_entries:
            visible_entries[-1:] = [selected_entry]
        visible_entries.append(entries[-1])
        self.cover_proposal_count.setText(ui_text(self, f'Propozycje ({len(visible_entries)})'))
        full = len(entries) >= 6
        self.choose_cover_button.setEnabled(not full)
        tooltip = 'Osiągnięto limit 6 okładek' if full else 'Wybierz własny plik okładki'
        self.choose_cover_button.setProperty('_alo_pl_tooltip', tooltip)
        self.choose_cover_button.setToolTip(ui_text(self, tooltip))

        preview_size = 114
        columns = 2

        for index, (key, title) in enumerate(visible_entries):
            card = QFrame()
            card.setObjectName('CoverProposalCard')
            card.setProperty('selected', key == getattr(self, '_selected_cover_key', ''))
            card.setToolTip(ui_text(self, title))
            card.setFixedSize(preview_size + 6, preview_size + 6)
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
            selected_badge = QLabel('', preview)
            selected_badge.setObjectName('CoverProposalSelectedMarker')
            selected_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            selected_badge.setPixmap(_cover_selection_marker_pixmap())
            selected_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            selected_badge.setFixedSize(selected_badge.pixmap().deviceIndependentSize().toSize())
            selected_badge.move(preview_size - selected_badge.width(), 0)
            selected_badge.setVisible(key == getattr(self, '_selected_cover_key', ''))
            selected_badge.raise_()
            self._cover_proposal_labels[key] = preview
            row, col = divmod(index, columns)
            self.cover_proposals_grid.addWidget(card, row, col, Qt.AlignmentFlag.AlignCenter)
            self._refresh_cover_proposal_widget(key)

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
            badge = card.findChild(QLabel, 'CoverProposalSelectedMarker')
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
        if self._cover_candidate_states.get(key) == 'ready' and not self._cover_candidate_pixmaps.get(key, QPixmap()).isNull():
            reply.abort()
            return
        self._cover_candidate_states[key] = 'error'
        self._cover_candidate_pixmaps[key] = QPixmap()
        self._cover_details.pop(key, None)
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
                data = bytes(reply.readAll())
                pix.loadFromData(data)
                if not pix.isNull():
                    self._cover_details[key] = {'bytes': len(data), 'format': self._cover_image_format(data),
                                                'type': 'Okładka główna (Front)'}
            if pix.isNull() and self._cover_candidate_states.get(key) == 'ready' and not self._cover_candidate_pixmaps.get(key, QPixmap()).isNull():
                return
            self._cover_candidate_pixmaps[key] = pix
            self._cover_candidate_states[key] = 'ready' if not pix.isNull() else 'error'
            if pix.isNull():
                self._cover_details.pop(key, None)
            self._refresh_cover_proposal_widget(key)
            if key == getattr(self, '_selected_cover_key', ''):
                self._update_cover_main_preview()
        finally:
            reply.deleteLater()

    def _update_cover_main_preview(self) -> None:
        key = getattr(self, '_selected_cover_key', 'placeholder')
        pix = self._cover_candidate_pixmaps.get(key, QPixmap())
        if self.compact_player is not None:
            self.compact_player.surface.set_cover_pixmap(pix)
        self._sync_live_cover_preview(pix)
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
        self._refresh_cover_information()
        self._refresh_status_summary()

    @staticmethod
    def _cover_image_format(data: bytes) -> str:
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        image_format = bytes(QImageReader(buffer).format()).decode('ascii', 'ignore').upper()
        buffer.close()
        return 'JPG' if image_format == 'JPEG' else image_format

    def _refresh_cover_information(self) -> None:
        key = self._selected_cover_key
        pix = self._cover_candidate_pixmaps.get(key, QPixmap())
        details = self._cover_details.get(key, {})
        if key == 'placeholder':
            source = '—'
            source_key = None
        elif key in self._manual_cover_paths:
            source = ui_text(self, 'Ręcznie')
            source_key = 'Ręcznie'
        elif key == 'source':
            source = 'TAG' if not pix.isNull() else '—'
            source_key = 'Tag' if not pix.isNull() else None
        else:
            source_key = key.split(':', 1)[1] if key.startswith('external:') else None
            source = source_key or '—'
        color = self.SOURCE_COLORS.get(source_key)
        self.cover_info_values['source'].setStyleSheet(f'color:{color};' if color else '')
        size = details.get('bytes')
        values = {
            'source': source,
            'resolution': f'{pix.width()} × {pix.height()} px' if not pix.isNull() and key != 'placeholder' else '—',
            'type': ui_text(self, str(details['type'])) if details.get('type') else '—',
            'format': str(details.get('format') or '—'),
            'size': f'{round(int(size) / 1024)} KB' if size is not None else '—',
        }
        for name, value in values.items():
            self.cover_info_values[name].setText(value)

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
        elif key in self._manual_cover_paths:
            self.cover_choice = 'manual'
            self.manual_cover_path = self._manual_cover_paths[key]
        elif key in {'source', 'placeholder'}:
            self.cover_choice = key
        if key not in self._cover_proposal_labels:
            self._rebuild_cover_proposals()
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
        real_covers = (len(self._cover_candidate_urls) + len(self._manual_cover_paths)
                       + int(not self._cover_candidate_pixmaps.get('source', QPixmap()).isNull()))
        if real_covers >= 5:
            return
        path, _ = QFileDialog.getOpenFileName(self, ui_text(self, 'Wybierz okładkę'), '', ui_text(self, 'Obrazy (*.jpg *.jpeg *.png *.webp)'))
        if not path:
            return
        existing = next((key for key, existing_path in self._manual_cover_paths.items() if existing_path == path), None)
        if existing:
            self._select_cover_choice(existing)
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        if not self._suspend_tracking:
            self._push_undo_state()
        key = 'manual' if 'manual' not in self._manual_cover_paths else f'manual:{len(self._manual_cover_paths)}'
        self._manual_cover_paths[key] = path
        self.manual_cover_path = path
        self._cover_candidate_pixmaps[key] = pixmap
        self._cover_details[key] = {'bytes': Path(path).stat().st_size,
                                    'format': Path(path).suffix.lstrip('.').upper().replace('JPEG', 'JPG')}
        self._cover_candidate_states[key] = 'ready'
        self._cover_notes[key] = 'Okładka wybrana ręcznie.'
        self.cover_choice = 'manual'
        self._selected_cover_key = key
        self._rebuild_cover_proposals()
        self._update_cover_main_preview()
        self._refresh_dirty_state()
        self._observe_state()
