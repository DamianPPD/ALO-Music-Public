"""Explicit, initially unselected approval of an observed legacy proposal."""
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)


class LegacyAdoptionDialog(QDialog):
    approve_requested = Signal(str)

    def __init__(self, inventory, parent=None, *, language='pl'):
        super().__init__(parent)
        self.inventory = inventory
        self.english = language == 'en'
        self._pending = False
        self.setWindowTitle(self._text('Przypisz historyczny plik', 'Assign a historical output'))
        self.resize(800, 560)
        layout = QVBoxLayout(self)
        label = QLabel(self._text(
            'Wybierz i sprawdź jedną propozycję. Samo dopasowanie nie nadaje własności.',
            'Select and review one proposal. A match alone does not confer ownership.'))
        label.setWordWrap(True); layout.addWidget(label)
        self.table = QTableWidget(len(inventory.proposals), 3, self)
        self.table.setHorizontalHeaderLabels([self._text('UUID rekordu', 'Record UUID'),
                                              self._text('Plik wynikowy', 'Output file'), 'Status'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, proposal in enumerate(inventory.proposals):
            for j, value in enumerate((proposal.track_id or '—', proposal.locator or '—', proposal.status)):
                item = QTableWidgetItem(value); item.setToolTip(value)
                self.table.setItem(i, j, item)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.details = QTextEdit(self); self.details.setReadOnly(True)
        layout.addWidget(self.details)
        self.confirm_check = QCheckBox(self._text(
            'Potwierdzam przypisanie tego pliku do wybranego rekordu.',
            'I confirm assigning this file to the selected record.'), self)
        self.confirm_check.setChecked(False); layout.addWidget(self.confirm_check)
        buttons = QHBoxLayout()
        self.approve_button = QPushButton(self._text('Zatwierdź przypisanie', 'Approve assignment'), self)
        self.approve_button.setEnabled(False); self.approve_button.setAutoDefault(False)
        close = QPushButton(self._text('Zamknij', 'Close'), self)
        close.setAutoDefault(False); close.clicked.connect(self.reject)
        buttons.addStretch(); buttons.addWidget(self.approve_button); buttons.addWidget(close); layout.addLayout(buttons)
        self.table.currentCellChanged.connect(self._selection_changed)
        self.confirm_check.toggled.connect(self._update_enabled)
        self.approve_button.clicked.connect(self._approve)
        self.table.clearSelection(); self.table.setCurrentCell(-1, -1)

    def _text(self, polish, english):
        return english if self.english else polish

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
        self.table.setEnabled(False); self.confirm_check.setEnabled(False)
        self._update_enabled()
        self.approve_requested.emit(proposal.proposal_id)

    def operation_failed(self, message):
        self._pending = False
        self.table.setEnabled(True); self.confirm_check.setEnabled(True)
        self.confirm_check.setChecked(False)
        self.details.append(str(message))
        self._update_enabled()
