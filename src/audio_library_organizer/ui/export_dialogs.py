"""The three export views; file work stays in the existing export worker."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices, QCloseEvent
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QSizePolicy, QProgressBar, QPlainTextEdit,
)

from audio_library_organizer.ui.i18n import language_for
from audio_library_organizer.ui.icons import alo_icon

GREEN, AMBER, VIOLET, BLUE, RED = '#35d893', '#d8a23a', '#db8fd4', '#66aaf0', '#f34d64'


class _ElidedLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self.fontMetrics().height() + 8)
        self.set_full_text(text)

    def set_full_text(self, text, tooltip=None):
        self.full_text = str(text)
        self.setToolTip(str(tooltip) if tooltip is not None else self.full_text)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, max(20, self.width() - 6)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class _ExportDialog(QDialog):
    def __init__(self, parent=None, *, language=None):
        super().__init__(parent)
        self.language = language or language_for(parent)
        self.setProperty('_alo_language', self.language)
        self.setObjectName('ExportDialog')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(420)
        self.setStyleSheet('''
            QDialog#ExportDialog, QWidget#ExportBody, QWidget#ExportExamples { background:#11171e; color:#dbe8ee; }
            QLabel { color:#dbe8ee; background:transparent; border:0; }
            QLabel[muted="true"] { color:#91a3b0; }
            QFrame#ExportCard { background:#17212a; border:1px solid #2b3b47; border-radius:10px; }
            QFrame#ExportRisk { background:#211f1a; border:1px solid #d8a23a; border-radius:10px; }
            QScrollArea { border:0; background:transparent; }
            QScrollBar:vertical { background:#11171e; width:10px; margin:0; }
            QScrollBar::handle:vertical { background:#344955; min-height:24px; border-radius:4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
            QPushButton { padding:10px 16px; border:1px solid #344955; border-radius:7px;
                          background:#202e38; color:#e0eaf0; min-height:20px; }
            QPushButton:hover { border-color:#83a5b7; }
            QPushButton:focus { border:2px solid #9bc6dc; }
            QPushButton:disabled { color:#82929c; background:#263039; }
            QPushButton[primary="true"] { background:#247d59; border-color:#35d893; }
            QPushButton[danger="true"] { background:#6e2a36; border-color:#f34d64; }
            QProgressBar { border:1px solid #2b3b47; border-radius:5px; background:#17212a; min-height:12px; }
            QProgressBar::chunk { background:#35d893; border-radius:4px; }
            QPlainTextEdit { background:#0e151c; color:#b8c9d3; border:1px solid #2b3b47; border-radius:6px; padding:8px; }
        ''')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(16)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName('ExportBody')
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 10, 0)
        self.body_layout.setSpacing(16)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)
        self.footer = QWidget()
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(0, 0, 0, 0)
        self.footer_layout.addStretch()
        outer.addWidget(self.footer)
        screen = self.screen().availableGeometry()
        self.resize(min(790, screen.width() - 40), min(820, screen.height() - 60))

    def tr(self, pl, en):
        return en if self.language == 'en' else pl

    def label(self, text, *, size=None, color=None, bold=False, muted=False):
        label = QLabel(str(text))
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setProperty('muted', muted)
        styles = []
        if size:
            styles.append(f'font-size:{size}px')
        if color:
            styles.append(f'color:{color}')
        if bold:
            styles.append('font-weight:600')
        if styles:
            label.setStyleSheet(';'.join(styles))
        return label

    def panel(self, *, risk=False):
        frame = QFrame()
        frame.setObjectName('ExportRisk' if risk else 'ExportCard')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        return frame, layout

    def heading(self, title, icon='copy', color=GREEN):
        self.setWindowTitle(title)
        row = QHBoxLayout()
        glyph = QLabel()
        glyph.setPixmap(alo_icon(icon, color, 28).pixmap(28, 28))
        row.addWidget(glyph)
        row.addWidget(self.label(title, size=22, bold=True), 1)
        self.body_layout.addLayout(row)

    def hero(self, value, caption):
        frame, layout = self.panel()
        number = self.label(str(value), size=42, bold=True)
        layout.addWidget(number)
        layout.addWidget(self.label(caption, muted=True))
        self.body_layout.addWidget(frame)
        return number

    def tiles(self, values, captions=None):
        row = QHBoxLayout()
        labels = {}
        for key, title, color, count in values:
            frame, layout = self.panel()
            layout.addWidget(self.label(title, size=12, color=color, bold=True))
            labels[key] = self.label(str(count), size=29, color=color, bold=True)
            layout.addWidget(labels[key])
            if captions:
                layout.addWidget(self.label(captions[key], muted=True))
            row.addWidget(frame, 1)
        self.body_layout.addLayout(row)
        return labels

    def categories(self, counts, *, completed=False):
        prefix = self.tr('Utworzone w folderze', 'Created in') if completed else self.tr('Do folderu', 'Target folder')
        return self.tiles([
            ('ready', self.tr('GOTOWE', 'READY'), GREEN, counts.get('ready', 0)),
            ('review', self.tr('DO SPRAWDZENIA', 'NEEDS REVIEW'), AMBER, counts.get('review', 0)),
            ('not_selected', self.tr('NIE WYBRANE', 'NOT SELECTED'), VIOLET, counts.get('not_selected', 0)),
        ], {key: f'{prefix} {folder}' for key, folder in (
            ('ready', 'GOTOWE'), ('review', 'DO_SPRAWDZENIA'), ('not_selected', 'NIE_WYBRANE'))})

    def metric_row(self, layout, name, count, color=AMBER):
        row = QHBoxLayout()
        row.addWidget(self.label(name), 1)
        value = self.label(str(count), color=color if count else GREEN, bold=True)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value)
        layout.addLayout(row)
        return value

    def risks(self, metrics, *, completed=False):
        frame, layout = self.panel(risk=True)
        title = QHBoxLayout()
        glyph = QLabel()
        glyph.setPixmap(alo_icon('warning', AMBER, 22).pixmap(22, 22))
        title.addWidget(glyph)
        title.addWidget(self.label(self.tr('Konflikty i ryzyka', 'Conflicts and risks'), color=AMBER, bold=True), 1)
        layout.addLayout(title)
        self.metric_row(layout, self.tr('Konflikty nazw', 'Name conflicts'), metrics.get('name_conflicts', 0))
        self.metric_row(layout, self.tr('Istniejące nazwy w folderze docelowym', 'Existing target names'), metrics.get('existing_targets', 0))
        self.metric_row(layout, self.tr('Nadpisane pliki' if completed else 'Pliki do nadpisania',
                                   'Overwritten files' if completed else 'Files to overwrite'), 0, RED)
        layout.addWidget(self.label(self.tr('Przy kolizji powstaje nowa, unikalna nazwa. Istniejące pliki pozostają bez zmian.',
                                           'A collision gets a new, unique name. Existing files remain unchanged.'), muted=True))
        self.body_layout.addWidget(frame)
        return layout


class ExportPreviewDialog(_ExportDialog):
    def __init__(self, summary, parent=None, *, examples=None, folder_organization='none', plan=None, language=None):
        super().__init__(parent, language=language)
        self.heading(self.tr('Podgląd przed utworzeniem plików', 'Preview before creating files'))
        total = summary['total']
        self.total_label = self.hero(total, self.tr('plików wynikowych do utworzenia', 'output files to create'))
        self.body_layout.addWidget(self.label(self.tr('Oryginalne pliki nie zostaną zmienione ani usunięte.',
                                                     'Original files will not be changed or deleted.'), color=GREEN))
        self.category_counts = self.categories({**summary, 'not_selected': summary.get('duplicate', 0) + summary.get('not_selected', 0)})
        self.risks(summary)
        organization = {
            'none': self.tr('Bez podfolderów', 'No subfolders'),
            'artist': self.tr('Według wykonawcy', 'By artist'),
            'genre': self.tr('Według gatunku', 'By genre'),
        }.get(folder_organization, self.tr('Bez podfolderów', 'No subfolders'))
        self.body_layout.addWidget(self.label(self.tr('Organizacja GOTOWE: ', 'READY organization: ') + organization))
        rows = []
        if plan is not None:
            for item in plan.items[:6]:
                target = item.destination_dir / item.filename
                rows.append((f'{item.track.filename}  →  {target.name}', f'{item.track.path}\n→ {target}'))
        else:
            rows = [(line, line) for line in (examples or [])[:6]]
        self.body_layout.addWidget(self.label(self.tr(f'Przykładowe pliki ({len(rows)} z {total})',
                                                     f'Example files ({len(rows)} of {total})'), bold=True))
        samples = QScrollArea()
        samples.setWidgetResizable(True)
        samples.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        samples.setMinimumHeight(70)
        samples.setMaximumHeight(165)
        content = QWidget()
        content.setObjectName('ExportExamples')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 0, 6, 0)
        self.example_labels = []
        for text, tooltip in rows:
            label = _ElidedLabel(text)
            label.setToolTip(tooltip)
            layout.addWidget(label)
            self.example_labels.append(label)
        samples.setWidget(content)
        self.body_layout.addWidget(samples)
        self.cancel_button = QPushButton(self.tr('Anuluj', 'Cancel'))
        self.create_button = QPushButton(self.tr('Utwórz pliki', 'Create files'))
        self.create_button.setProperty('primary', True)
        self.create_button.setIcon(alo_icon('copy', '#e2f8ed'))
        self.create_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.create_button.clicked.connect(self.accept)
        self.footer_layout.addWidget(self.cancel_button)
        self.footer_layout.addWidget(self.create_button)


class ExportProgressDialog(_ExportDialog):
    stop_requested = Signal()

    def __init__(self, total, parent=None, *, language=None):
        super().__init__(parent, language=language)
        self.running, self.stopping = True, False
        self._current_phase = 'operation_started'
        self.heading(self.tr('Tworzenie plików wynikowych', 'Creating output files'))
        self.total_label = self.hero(total, self.tr('plików do utworzenia', 'files to create'))
        self.counter = self.label(f'0 / {total} — 0%', bold=True)
        self.body_layout.addWidget(self.counter)
        self.check_progress = self.label('', muted=True)
        self.check_progress.hide()
        self.body_layout.addWidget(self.check_progress)
        self.progress = QProgressBar()
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.body_layout.addWidget(self.progress)
        self.count_labels = self.tiles([
            ('created', self.tr('Utworzone', 'Created'), GREEN, 0),
            ('remaining', self.tr('Pozostało', 'Remaining'), BLUE, total),
            ('failed', self.tr('Błędy', 'Errors'), RED, 0),
        ])
        frame, layout = self.panel()
        layout.addWidget(self.label(self.tr('Aktualnie przetwarzany plik:', 'Current file:'), bold=True))
        self.current_file = _ElidedLabel('—')
        self.current_target = _ElidedLabel('')
        self.stage = self.label(self.tr('Oczekiwanie na rozpoczęcie…', 'Waiting to start…'), color=BLUE)
        for widget in (self.current_file, self.current_target, self.stage):
            layout.addWidget(widget)
        self.body_layout.addWidget(frame)
        self.body_layout.addWidget(self.label(self.tr('Dziennik operacji', 'Operation log'), bold=True))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        self.log.setMinimumHeight(100)
        self.log.setMaximumHeight(190)
        self.body_layout.addWidget(self.log)
        self.notice = self.label('', color=AMBER)
        self.body_layout.addWidget(self.notice)
        self.stop_button = QPushButton(self.tr('Zatrzymaj tworzenie', 'Stop creating'))
        self.stop_button.setProperty('danger', True)
        self.stop_button.setIcon(alo_icon('cancel', '#ffe2e6'))
        self.stop_button.clicked.connect(self.request_stop)
        self.footer_layout.addWidget(self.stop_button)

    @Slot(object)
    def update_event(self, event):
        self._current_phase = event.phase
        self.progress.setValue(event.processed)
        percent = round(100 * event.processed / event.total) if event.total else 0
        self.counter.setText(f'{event.processed} / {event.total} — {percent}%')
        checking = event.phase.startswith('preflight_')
        self.check_progress.setVisible(checking)
        if checking:
            text = self.tr('Kontrola plików', 'File checks')
            self.check_progress.setText(f'{text}: {event.check_current} / {event.check_total}' if event.check_total else
                                       self.tr('Ustalanie zakresu kontroli…', 'Determining check scope…'))
            if event.source is None:
                self.current_file.set_full_text('—')
            self.current_target.set_full_text('')
        for key, value in (('created', event.created), ('remaining', event.remaining), ('failed', event.failed)):
            self.count_labels[key].setText(str(value))
        if event.source is not None:
            self.current_file.set_full_text(event.source.name, str(event.source))
        if event.phase == 'item_started':
            self.current_target.set_full_text('')
        if event.destination is not None:
            self.current_target.set_full_text(f'→ {event.destination}', str(event.destination))
        stages = {
            'preflight_context': ('FAZA 1 — Sprawdzanie bezpieczeństwa: biblioteki i SQLite', 'PHASE 1 — Library safety checks: libraries and SQLite'),
            'preflight_sources': ('FAZA 1 — Sprawdzanie bezpieczeństwa: analiza źródeł i audio', 'PHASE 1 — Library safety checks: sources and audio'),
            'preflight_inventory': ('FAZA 1 — Sprawdzanie bezpieczeństwa: wyszukiwanie istniejących wyników', 'PHASE 1 — Library safety checks: finding existing outputs'),
            'preflight_reports': ('FAZA 1 — Sprawdzanie bezpieczeństwa: odczyt wcześniejszych raportów', 'PHASE 1 — Library safety checks: reading previous reports'),
            'preflight_outputs': ('FAZA 1 — Sprawdzanie bezpieczeństwa: weryfikacja istniejących wyników', 'PHASE 1 — Library safety checks: verifying existing outputs'),
            'preflight_saving': ('FAZA 1 — Sprawdzanie bezpieczeństwa: kończenie transakcji SQLite', 'PHASE 1 — Library safety checks: completing the SQLite transaction'),
            'operation_started': ('FAZA 2 — Tworzenie plików', 'PHASE 2 — Creating files'),
            'item_started': ('Kopiowanie', 'Copying'),
            'copied': ('Skopiowano plik — kontrola SHA-256', 'File copied — checking SHA-256'),
            'raw_verified': ('Zweryfikowano kopię', 'Raw copy verified'),
            'tagging': ('Zapisywanie metadanych', 'Writing metadata'),
            'tags_written': ('Zapisano metadane', 'Metadata written'),
            'final_verifying': ('Końcowa kontrola pliku', 'Final file verification'),
            'final_verified': ('Plik końcowy zweryfikowany', 'Final file verified'),
            'item_finished': ('Zakończono przetwarzanie pliku', 'File completed'),
            'item_failed': ('Błąd przetwarzania pliku', 'File failed'),
            'operation_finished': ('Oczekiwanie na zakończenie workera…', 'Waiting for worker shutdown…'),
            'operation_finishing': ('FAZA 3 — Kończenie zadania i przygotowanie raportu…', 'PHASE 3 — Finishing the task and preparing the report…'),
        }
        text = self.tr(*stages.get(event.phase, (event.phase, event.phase)))
        self.stage.setText(text)
        detail = event.message or (event.source.name if event.source else '')
        self.log.appendPlainText(text + (f': {detail}' if detail else ''))
        if self.stopping:
            self._stop_notice()

    def _stop_notice(self):
        if self._current_phase.startswith('preflight_'):
            text = self.tr('Kończenie kontroli w najbliższym bezpiecznym punkcie. Kopiowanie nie zostało rozpoczęte. Bieżąca operacja dyskowa lub SQLite musi wrócić.',
                           'Finishing the safety check at the next safe point. Copying has not started. A current disk or SQLite operation must return.')
        elif self._current_phase == 'operation_finishing':
            text = self.tr('Kończenie zadania i przygotowanie raportu. Oczekiwanie na bezpieczny koniec wątku.',
                           'Finishing the task and preparing the report. Waiting for safe thread shutdown.')
        else:
            text = self.tr('Bieżący plik zostanie bezpiecznie dokończony. Następny nie zostanie rozpoczęty.',
                           'The current file will finish safely. The next file will not start.')
        self.notice.setText(text)

    @Slot()
    def request_stop(self):
        if not self.running or self.stopping:
            return
        self.stopping = True
        self.stop_button.setText(self.tr('Zatrzymywanie…', 'Stopping…'))
        self.stop_button.setEnabled(False)
        self._stop_notice()
        self.log.appendPlainText(self.tr('Odebrano żądanie zatrzymania.', 'Stop request received.'))
        self.stop_requested.emit()

    def reject(self):
        if self.running:
            self.request_stop()
        else:
            super().reject()

    def closeEvent(self, event: QCloseEvent):
        if self.running:
            self.request_stop()
            event.ignore()
        else:
            super().closeEvent(event)

    def finish(self):
        self.running = False
        self.accept()


class ExportSummaryDialog(_ExportDialog):
    def __init__(self, result, plan, library_root, report, parent=None, *, metrics=None, report_errors=(), language=None):
        super().__init__(parent, language=language)
        self.heading(self.tr('Tworzenie zakończone', 'Creation completed'),
                     'check' if result.status == 'success' and not report_errors else 'warning',
                     GREEN if result.status == 'success' and not report_errors else AMBER)
        self.outcome = 'problems' if report_errors and result.status == 'success' else result.status
        title = {
            'success': ('Operacja zakończona pomyślnie.', 'Operation completed successfully.'),
            'problems': ('Zakończono z problemami.', 'Completed with problems.'),
            'cancelled': ('Tworzenie zostało zatrzymane przez użytkownika.', 'Creation was stopped by the user.'),
        }[self.outcome]
        self.body_layout.addWidget(self.label(self.tr(*title), size=21, bold=True,
                                             color=GREEN if self.outcome == 'success' else AMBER))
        self.created_label = self.hero(result.created, self.tr('utworzone i zweryfikowane pliki', 'created and verified files'))
        self.body_layout.addWidget(self.label(self.tr(
            f'Zaplanowano: {len(plan.items)} · Przetworzono: {result.processed} · Pozostało: {result.remaining} · Błędy: {result.failed} · Pominięto: {result.skipped}',
            f'Planned: {len(plan.items)} · Processed: {result.processed} · Remaining: {result.remaining} · Errors: {result.failed} · Skipped: {result.skipped}')))
        self.category_counts = self.categories(result.category_counts, completed=True)
        risk_layout = self.risks(metrics or {}, completed=True)
        counts = {status: sum(o.status == status for o in result.outcomes)
                  for status in ('copy_error', 'tag_error', 'verification_error')}
        self.metric_row(risk_layout, self.tr('Błędy kopiowania', 'Copy errors'), counts['copy_error'], RED)
        self.metric_row(risk_layout, self.tr('Błędy zapisu metadanych', 'Metadata errors'), counts['tag_error'], RED)
        self.metric_row(risk_layout, self.tr('Błędy weryfikacji', 'Verification errors'), counts['verification_error'], RED)
        seconds = int(result.elapsed_seconds)
        duration = f'{seconds // 60} min {seconds % 60} s' if seconds >= 60 else f'{seconds} s'
        self.body_layout.addWidget(self.label(self.tr('Czas operacji: ', 'Operation time: ') + duration, muted=True))
        if result.cancelled:
            self.body_layout.addWidget(self.label(self.tr(
                'Poprawne kopie pozostały w bibliotece. Ponowne uruchomienie może utworzyć kolejne kopie z unikalnymi nazwami.',
                'Completed copies remain in the library. Running again may create additional copies with unique names.'), color=AMBER))
        self.notice = self.label('\n'.join(filter(None, [result.fatal_error, *result.cleanup_warnings, *report_errors])), color=AMBER)
        if result.cancelled and result.stop_phase == 'preflight' and not result.fatal_error:
            prefix = self.tr('Zatrzymano przed rozpoczęciem kopiowania. Wszystkie pozycje pozostały nieprzetworzone.',
                             'Stopped before copying began. All items remain unprocessed.')
            self.notice.setText(prefix + ('\n' + self.notice.text() if self.notice.text() else ''))
        self.body_layout.addWidget(self.notice)
        self.body_layout.addWidget(self.label(self.tr('Co dalej?', 'What next?'), size=18, bold=True))
        self.actions = QWidget()
        actions_layout = QHBoxLayout(self.actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        self.folder_button = QPushButton(self.tr('Otwórz folder wynikowy', 'Open output folder'))
        self.folder_button.setIcon(alo_icon('folder_open', BLUE))
        self.report_button = QPushButton(self.tr('Przejrzyj raport', 'View report'))
        self.report_button.setIcon(alo_icon('report', BLUE))
        self.root, self.report = Path(library_root), Path(report) if report else None
        self.folder_button.clicked.connect(self.open_folder)
        self.report_button.clicked.connect(self.open_report)
        actions_layout.addWidget(self.folder_button, 1)
        actions_layout.addWidget(self.report_button, 1)
        self.body_layout.addWidget(self.actions)
        self.close_button = QPushButton(self.tr('Zamknij', 'Close'))
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        self.footer_layout.addWidget(self.close_button)

    def _open(self, path, *, directory=False):
        try:
            if path is None or not (path.is_dir() if directory else path.is_file()):
                raise OSError(self.tr('Folder lub raport nie jest dostępny.', 'The folder or report is unavailable.'))
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise OSError(self.tr('Nie udało się otworzyć folderu lub raportu.', 'Could not open the folder or report.'))
        except OSError as exc:
            self.notice.setText(str(exc))

    @Slot()
    def open_folder(self):
        self._open(self.root, directory=True)

    @Slot()
    def open_report(self):
        self._open(self.report)
