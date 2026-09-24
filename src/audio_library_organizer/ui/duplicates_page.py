from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem, QStyle,
)

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.duplicates.grouper import group_potential_duplicates
from audio_library_organizer.ui.state import display_bpm
from audio_library_organizer.ui.i18n import ui_text
from audio_library_organizer.ui.icons import alo_icon


class DuplicateRowDelegate(QStyledItemDelegate):
    """Keep the row decision color visible and draw only a blue selection outline."""

    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        clean = QStyleOptionViewItem(option)
        clean.state &= ~QStyle.StateFlag.State_HasFocus
        if selected:
            clean.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, clean, index)
        if not selected:
            return

        painter.save()
        painter.setPen(QPen(QColor('#5ca3ff'), 1))
        rect = option.rect.adjusted(0, 0, -1, -1)
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if index.column() == 0:
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
        if index.column() == index.model().columnCount() - 1:
            painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.restore()


class DuplicatesPage(QWidget):
    """Data-first comparison surface for potential duplicates and alternate versions.

    ALO deliberately does not recommend a winner here.  It only exposes technical
    differences and persists the user's explicit ZACHOWAJ / NIE WYBIERAM decision.
    """

    decision_requested = Signal(object, str)
    edit_track_requested = Signal(object)

    COLUMNS = ('Wariant', 'Nazwa pliku', 'Długość', 'BPM', 'Format', 'Bitrate', 'Hz', 'Rozmiar', 'Decyzja')

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player_bar = player
        self.groups: list[list[TrackRecord]] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(12)

        left = QVBoxLayout()
        self.count_label = QLabel('0 plików • 0 grup')
        self.count_label.setObjectName('DuplicateCount')
        left.addWidget(self.count_label)
        self.group_list = QListWidget(); self.group_list.setObjectName('DuplicateGroups')
        self.group_list.setMinimumWidth(320)
        left.addWidget(self.group_list, 1)
        root.addLayout(left, 1)

        right = QVBoxLayout(); right.setSpacing(10)
        self.title = QLabel('Wybierz grupę potencjalnych duplikatów')
        self.title.setStyleSheet('font-size:16pt;font-weight:750;')
        self.title.setWordWrap(True)
        right.addWidget(self.title)

        info = QFrame(); info.setObjectName('InfoBanner')
        il = QVBoxLayout(info); il.setContentsMargins(10, 8, 10, 8)
        text = QLabel(
            'Porównaj dane techniczne i sam wybierz plik, który chcesz zachować. '
            'Różna długość może oznaczać Radio Edit, Extended Mix albo inną wersję — '
            'ALO niczego nie wybiera i niczego nie usuwa automatycznie.'
        )
        text.setWordWrap(True); il.addWidget(text); right.addWidget(info)

        self.files = QTableWidget(0, len(self.COLUMNS))
        self.files.setObjectName('DuplicateFiles')
        self.files.setHorizontalHeaderLabels(self.COLUMNS)
        self.files.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.files.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.files.setAlternatingRowColors(False)
        self.files.setItemDelegate(DuplicateRowDelegate(self.files))
        self.files.verticalHeader().setVisible(False)
        self.files.verticalHeader().setDefaultSectionSize(38)
        header = self.files.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in range(2, len(self.COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        right.addWidget(self.files, 1)

        decisions = QHBoxLayout(); decisions.setSpacing(7)
        self.keep = QPushButton('ZACHOWAJ'); self.keep.setObjectName('DuplicateKeep'); self.keep.setIcon(alo_icon('status', '#8fe9ad', 17))
        self.reject = QPushButton('NIE WYBIERAM'); self.reject.setObjectName('DuplicateReject'); self.reject.setIcon(alo_icon('cancel', '#b8c2c9', 17))
        self.edit_track = QPushButton('EDYTUJ'); self.edit_track.setObjectName('ToolbarAction'); self.edit_track.setIcon(alo_icon('edit', '#73d8ef', 17))
        for button in (self.keep, self.reject, self.edit_track):
            decisions.addWidget(button)
        decisions.addStretch(1)
        right.addLayout(decisions)

        note = QLabel(
            'Dwuklik w wiersz uruchamia odsłuch. Przy przełączaniu wariantów A/B odsłuch zachowuje ten sam moment utworu. '
            'ZACHOWAJ = zielona komórka decyzji, NIE WYBIERAM = szara. Brak decyzji pozostawia zwykłe ciemne tło.'
        )
        note.setWordWrap(True); note.setObjectName('MutedText'); right.addWidget(note)
        root.addLayout(right, 3)

        self.group_list.currentRowChanged.connect(self._show_group)
        self.files.cellDoubleClicked.connect(lambda row, _column: self._play_index(row))
        self.keep.clicked.connect(lambda: self._emit_decision('keep'))
        self.reject.clicked.connect(lambda: self._emit_decision('not_selected'))
        self.edit_track.clicked.connect(self._edit_track)

    def group_count(self) -> int:
        return len(self.groups)

    def set_tracks(self, tracks: list[TrackRecord]):
        current_group = self.group_list.currentRow()
        group_scroll = self.group_list.verticalScrollBar().value()
        file_scroll = self.files.verticalScrollBar().value()
        previously_selected, _previous_group = self._selected()
        selected_path = str(previously_selected.path).casefold() if previously_selected is not None else None

        self.groups = group_potential_duplicates(tracks, include_resolved=True)
        self.group_list.clear()
        total_files = sum(len(group) for group in self.groups)
        self.count_label.setText(f'{total_files} plików • {len(self.groups)} grup')
        for i, group in enumerate(self.groups, 1):
            label = group[0].proposed_filename or group[0].filename
            decided = sum(1 for t in group if '__status__' in t.locked_fields)
            suffix = f' • decyzje {decided}/{len(group)}'
            self.group_list.addItem(f'{i:03d} · {label} · {len(group)} pliki{suffix}')
        if self.groups:
            group_index = min(max(current_group, 0), len(self.groups) - 1)
            if selected_path is not None:
                for index, group in enumerate(self.groups):
                    if any(str(track.path).casefold() == selected_path for track in group):
                        group_index = index
                        break
            self.group_list.setCurrentRow(group_index)
            if selected_path is not None:
                for row, track in enumerate(self.groups[group_index]):
                    if str(track.path).casefold() == selected_path:
                        self.files.selectRow(row)
                        break
            self.group_list.verticalScrollBar().setValue(group_scroll)
            self.files.verticalScrollBar().setValue(file_scroll)
        else:
            self.files.setRowCount(0); self.title.setText('Brak potencjalnych duplikatów')

    @staticmethod
    def _decision_text(track: TrackRecord) -> str:
        if '__status__' in track.locked_fields:
            if track.status == 'not_selected':
                return 'NIE WYBIERAM'
            if track.status in {'ready', 'review'}:
                return 'ZACHOWAJ'
        return '—'

    @staticmethod
    def _decision_color(track: TrackRecord) -> QColor | None:
        if '__status__' in track.locked_fields and track.status in {'ready', 'review'}:
            return QColor('#173c2d')
        if track.status == 'not_selected':
            return QColor('#2a3038')
        return None

    @staticmethod
    def _duration(track: TrackRecord) -> str:
        if track.duration_seconds is None:
            return '—'
        total = max(0, int(round(track.duration_seconds)))
        return f'{total // 60}:{total % 60:02d}'

    def _show_group(self, row: int):
        self.files.setRowCount(0)
        if row < 0 or row >= len(self.groups):
            return
        group = self.groups[row]
        self.title.setText(group[0].proposed_filename or group[0].filename)
        self.files.setRowCount(len(group))
        rows: list[tuple[TrackRecord, tuple[str, ...]]] = []
        for idx, track in enumerate(group):
            size_mb = track.size_bytes / (1024 * 1024) if track.size_bytes else 0
            values = (
                chr(65 + idx),
                track.filename,
                self._duration(track),
                display_bpm(track.bpm) or '—',
                (track.codec or '—').upper(),
                f'{track.bitrate_kbps} kb/s' if track.bitrate_kbps else '—',
                str(track.sample_rate_hz or '—'),
                f'{size_mb:.1f} MB',
                ui_text(self, self._decision_text(track)),
            )
            rows.append((track, tuple(str(value) for value in values)))

        for idx, (track, values) in enumerate(rows):
            decision_background = self._decision_color(track)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, track)
                if col == len(self.COLUMNS) - 1 and decision_background is not None:
                    item.setBackground(QBrush(decision_background))
                    item.setForeground(QBrush(QColor('#8fe9ad' if track.status in {'ready', 'review'} else '#c6ced8')))
                if col in {0, 2, 3, 4, 5, 6, 7, 8}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.files.setItem(idx, col, item)
        if self.files.rowCount():
            self.files.selectRow(0)

    def _play_index(self, index: int):
        row = self.group_list.currentRow()
        if row < 0 or row >= len(self.groups):
            return
        group = self.groups[row]
        if index < 0 or index >= len(group):
            return
        position = self.player_bar.player.position()
        duration_ms = int((group[index].duration_seconds or 0) * 1000)
        if duration_ms:
            position = min(position, max(0, duration_ms - 500))
        self.player_bar.load_track(group[index], position_ms=position, autoplay=True, source_label='Duplikaty')

    def _selected(self):
        row = self.group_list.currentRow(); index = self.files.currentRow()
        if row < 0 or row >= len(self.groups) or index < 0:
            return None, None
        group = self.groups[row]
        if index >= len(group):
            return None, None
        return group[index], group

    def current_group_tracks(self) -> list[TrackRecord]:
        """Return the current duplicate group in its displayed row order."""
        row = self.group_list.currentRow()
        if row < 0 or row >= len(self.groups):
            return []
        return list(self.groups[row])

    def _emit_decision(self, decision: str):
        selected, _group = self._selected()
        if selected is not None:
            self.decision_requested.emit(selected, decision)

    def _edit_track(self):
        selected, _group = self._selected()
        if selected is not None:
            self.edit_track_requested.emit(selected)
