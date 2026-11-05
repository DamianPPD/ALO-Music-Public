"""Explicit, initially unselected approval of an observed legacy proposal."""
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)


class LegacyAdoptionDialog(QDialog):
    approve_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, inventory, parent=None, *, language='pl', tracks=()):
        super().__init__(parent)
        self.inventory = inventory
        self.english = language == 'en'
        self._pending = False
        self._tracks = {track.track_id:track for track in tracks}
        self.setWindowTitle(self._text('Przypisz historyczny plik', 'Assign a historical output'))
        self.resize(800, 560)
        layout = QVBoxLayout(self)
        label = QLabel(self._text(
            'Wybierz i sprawdź jedną propozycję. Samo dopasowanie nie nadaje własności.',
            'Select and review one proposal. A match alone does not confer ownership.'))
        label.setWordWrap(True); layout.addWidget(label)
        filters=QHBoxLayout()
        self.status_filter=QComboBox(self)
        for pl,en,status in (
            ('Wszystkie','All',''),('Do przypisania','Candidates','CANDIDATE'),
            ('Konflikty','Conflicts','CONFLICT'),('Nierozstrzygnięte','Unresolved','UNRESOLVED'),
            ('Nieobsługiwane','Unsupported','UNSUPPORTED'),('Już przypisane','Already assigned','ALREADY_BOUND')):
            self.status_filter.addItem(self._text(pl,en),status)
        self.status_filter.setCurrentIndex(1)
        self.search=QLineEdit(self)
        self.search.setPlaceholderText(self._text('Szukaj wykonawcy, tytułu lub pliku…','Search artist, title or file…'))
        filters.addWidget(self.status_filter); filters.addWidget(self.search); layout.addLayout(filters)
        self.counts=QLabel(self); self.counts.setWordWrap(True); layout.addWidget(self.counts)
        self.table = QTableWidget(len(inventory.proposals), 3, self)
        self.table.setHorizontalHeaderLabels([self._text('Utwór', 'Track'),
                                              self._text('Plik wynikowy', 'Output file'), 'Status'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, proposal in enumerate(inventory.proposals):
            track=self._tracks.get(proposal.track_id)
            title=' — '.join(value for value in (track.artist,track.title) if value) if track else ''
            title=title or (proposal.locator.rsplit('/',1)[-1] if proposal.locator else self._text('Brak dopasowania','No match'))
            for j, value in enumerate((title, proposal.locator or '—', proposal.status)):
                item = QTableWidgetItem(value); item.setToolTip(value)
                self.table.setItem(i, j, item)
        self.table.setColumnWidth(0,260)
        self.table.setColumnWidth(1,360)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.details = QTextEdit(self); self.details.setReadOnly(True)
        layout.addWidget(self.details)
        self.confirm_check = QCheckBox(self._text(
            'Potwierdzam przypisanie tego pliku do wybranego rekordu.',
            'I confirm assigning this file to the selected record.'), self)
        self.confirm_check.setChecked(False); layout.addWidget(self.confirm_check)
        self.operation_label=QLabel(self); self.operation_label.setWordWrap(True)
        self.operation_progress=QProgressBar(self); self.operation_progress.hide()
        layout.addWidget(self.operation_label); layout.addWidget(self.operation_progress)
        buttons = QHBoxLayout()
        self.cancel_button=QPushButton(self._text('Anuluj przypisywanie','Cancel assignment'),self)
        self.cancel_button.setAutoDefault(False); self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        buttons.addWidget(self.cancel_button)
        self.approve_button = QPushButton(self._text('Zatwierdź przypisanie', 'Approve assignment'), self)
        self.approve_button.setEnabled(False); self.approve_button.setAutoDefault(False)
        close = QPushButton(self._text('Zamknij', 'Close'), self)
        close.setAutoDefault(False); close.clicked.connect(self.reject)
        buttons.addStretch(); buttons.addWidget(self.approve_button); buttons.addWidget(close); layout.addLayout(buttons)
        self.table.currentCellChanged.connect(self._selection_changed)
        self.confirm_check.toggled.connect(self._update_enabled)
        self.approve_button.clicked.connect(self._approve)
        self.status_filter.currentIndexChanged.connect(self._filter_rows)
        self.search.textChanged.connect(self._filter_rows)
        self._filter_rows()
        self.table.clearSelection(); self.table.setCurrentCell(-1, -1)

    def _text(self, polish, english):
        return english if self.english else polish

    def _filter_rows(self, *_):
        status=self.status_filter.currentData()
        query=self.search.text().casefold().strip()
        visible=0
        for row,p in enumerate(self.inventory.proposals):
            text=' '.join(self.table.item(row,col).text() for col in range(3)).casefold()
            show=(not status or p.status==status) and (not query or query in text)
            self.table.setRowHidden(row,not show)
            visible+=show
        self.table.clearSelection(); self.table.setCurrentCell(-1,-1)
        self.confirm_check.setChecked(False)
        values=self.inventory.statistics
        names=(('candidate','Kandydaci','Candidates'),('conflict','Konflikty','Conflicts'),
               ('unresolved','Nierozstrzygnięte','Unresolved'),('unsupported','Nieobsługiwane','Unsupported'),
               ('already_bound','Już przypisane','Already assigned'))
        self.counts.setText(' | '.join(f'{self._text(pl,en)}: {values[key]}' for key,pl,en in names)
                            +self._text(f' | Widoczne: {visible}',f' | Visible: {visible}'))
        self._update_enabled()

    def _cancel(self):
        if self._pending:
            self.cancel_button.setEnabled(False)
            self.operation_label.setText(self._text('Anulowanie — oczekiwanie na bezpieczne zakończenie…',
                                                     'Cancelling — waiting for safe completion…'))
            self.cancel_requested.emit()

    def closeEvent(self,event):
        if self._pending:
            self._cancel(); event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        if self._pending: self._cancel()
        else: super().reject()

    def operation_update(self,current,total,message):
        self.operation_label.setText(f'{message}: {current} / {total}')
        self.operation_progress.setRange(0,max(1,total)); self.operation_progress.setValue(current)
        self.operation_progress.show()

    def operation_succeeded(self):
        self._pending=False
        self.accept()

    def _selected(self):
        row = self.table.currentRow()
        return self.inventory.proposals[row] if 0 <= row < len(self.inventory.proposals) else None

    def _selection_changed(self, *_):
        self.confirm_check.setChecked(False)
        proposal = self._selected()
        if proposal is None:
            self.details.clear()
        else:
            observed = datetime.fromtimestamp(proposal.checked_at / 1e9, timezone.utc).isoformat()
            self.details.setPlainText('\n'.join((
                f'Library UUID: {proposal.library_id}', f'Track UUID: {proposal.track_id or "—"}',
                f'Source UUID: {proposal.source_id or "—"}', f'Output: {proposal.locator or "—"}',
                f'Root: {proposal.library_root}', f'Status: {proposal.status}',
                f'Evidence: {", ".join(proposal.evidence_sources) or "—"}',
                f'Audio validation: {proposal.audio_algorithm} / {proposal.audio_digest or "UNPROVEN"}',
                f'Full SHA-256: {proposal.full_sha256 or "UNPROVEN"}', f'Observed UTC: {observed}',
                f'Reasons: {", ".join(proposal.reason_codes)}',
                self._text('Dowody są obserwacją historyczną. Przed zapisem zostaną ponownie sprawdzone.',
                           'Evidence is a historical observation. It will be revalidated before saving.'),
                self._text('Operacja zapisze binding i odczytane tagi/okładkę jako snapshot w SQLite. Muzyka pozostanie nietknięta.',
                           'This operation saves ownership and observed tags/cover as a SQLite snapshot. Music stays unchanged.'),
                self._text('Tylko jednoznaczny MP3; konflikty, aliasy i niedostępne znane biblioteki blokują adopcję.',
                           'Only an unambiguous MP3; conflicts, aliases and unavailable known libraries block adoption.'),
            )))
        self._update_enabled()

    def _update_enabled(self, *_):
        proposal = self._selected()
        self.approve_button.setEnabled(not self._pending and proposal is not None
            and proposal.can_adopt and self.confirm_check.isChecked())

    def _approve(self):
        proposal = self._selected()
        if not self.approve_button.isEnabled() or proposal is None:
            return
        self._pending = True
        self.cancel_button.setEnabled(True)
        self.status_filter.setEnabled(False); self.search.setEnabled(False)
        self.operation_progress.setRange(0,1); self.operation_progress.setValue(0); self.operation_progress.show()
        self.table.setEnabled(False); self.confirm_check.setEnabled(False)
        self._update_enabled()
        self.approve_requested.emit(proposal.proposal_id)

    def operation_failed(self, message):
        self._pending = False
        self.cancel_button.setEnabled(False)
        self.status_filter.setEnabled(True); self.search.setEnabled(True)
        self.operation_label.setText(str(message))
        self.table.setEnabled(True); self.confirm_check.setEnabled(True)
        self.confirm_check.setChecked(False)
        self.details.append(str(message))
        self._update_enabled()
