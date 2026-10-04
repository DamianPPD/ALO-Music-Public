import os
import time
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint, QSettings, Qt, QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidgetAction
import requests
from shiboken6 import isValid

from audio_library_organizer.domain.candidates import AcoustIDHit
from audio_library_organizer.audio.fingerprint import FingerprintResult
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import SOURCE, approve_audio_source
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.domain.preferences import AppPreferences
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme
from audio_library_organizer.ui.main_window import MainWindow
from audio_library_organizer.ui.workers import AudioIdentificationWorker


def test_candidates_are_compact_columns_and_approval_collapses_to_summary(tmp_path):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'song.mp3'))
    hits = [AcoustIDHit('recording-1', 1.0, 'Stepping to the Beat (Remix)', 'DJ José', 'Single', '2006', 'ac-1'),
            AcoustIDHit('recording-2', .88, 'Stepping to the Beat', 'DJ José', 'Album', '2005', 'ac-2')]
    try:
        editor.show_audio_candidates(hits)
        editor.show()
        app.processEvents()
        table = editor.audio_candidates
        assert table.columnCount() == 5 and table.rowCount() == 2
        assert [table.horizontalHeaderItem(i).text() for i in range(5)] == [
            'Wybór', 'Tytuł / wersja', 'Wykonawca', 'Album / rok', 'Dopasowanie'
        ]
        assert table.item(0, 1).text() == hits[0].title
        assert table.item(0, 2).text() == hits[0].artist
        assert 'Single' in table.item(0, 3).text() and '2006' in table.item(0, 3).text()
        assert table.item(0, 4).text() == '100%'
        assert table.height() <= 130
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton,
                         pos=table.visualItemRect(table.item(0, 2)).center())
        assert table.currentRow() == 0 and editor.audio_confirm_button.isEnabled()
        assert 'recording-1' in editor.audio_detail.text()
        editor.audio_confirm_button.click()
        assert editor.audio_summary.isVisible()
        assert not editor.audio_candidate_content.isVisible()
        assert not editor.audio_confirm_button.isVisible()
        assert 'DJ José' in editor.audio_summary_result.text()
        assert editor.recognition_values['audio_status'].text() == 'Zatwierdzone'
        assert SOURCE in editor._source_rows()
        editor.audio_show_candidates_button.click()
        assert editor.audio_candidate_content.isVisible()
        assert not table.item(0, 0).icon().isNull()
        table.setCurrentCell(1, 2)
        editor.audio_confirm_button.click()
        assert editor.track.audio_recognition['recording_id'] == 'recording-2'
        assert editor._source_values['title'][SOURCE] == 'Stepping to the Beat'
    finally:
        editor._force_closing = True
        editor.close()


def test_approved_candidate_can_be_reconfirmed_and_selected_again_after_switching(tmp_path):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'song.mp3'))
    confirmed = []
    editor.audio_source_confirmed.connect(lambda _editor, previous: confirmed.append(previous))
    try:
        editor.show_audio_candidates([
            AcoustIDHit('first', .94, 'First mix', 'Artist', 'Single', '2006', 'ac-first'),
            AcoustIDHit('second', .88, 'Second mix', 'Artist', 'Album', '2007', 'ac-second'),
        ])
        editor.show()
        app.processEvents()
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        assert len(confirmed) == 1

        editor.audio_show_candidates_button.click()
        editor.audio_candidates.setCurrentCell(0, 2)
        assert not editor.audio_candidates.item(0, 0).icon().isNull()
        assert editor.audio_confirm_button.text() == 'Zatwierdź jako źródło audio'
        assert editor.audio_confirm_button.isEnabled()
        editor.audio_confirm_button.click()
        assert len(confirmed) == 2
        assert editor.track.audio_recognition['recording_id'] == 'first'

        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        editor.audio_show_candidates_button.click()
        assert editor.audio_confirm_button.text() == 'Confirm as audio source'
        assert editor.audio_confirm_button.isEnabled()
        editor.audio_candidates.setCurrentCell(1, 1)
        assert editor.audio_confirm_button.text() == 'Confirm as audio source'
        assert editor.audio_confirm_button.isEnabled()
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert editor.audio_confirm_button.text() == 'Zatwierdź jako źródło audio'
        editor.audio_confirm_button.click()
        assert len(confirmed) == 3
        assert editor.track.audio_recognition['recording_id'] == 'second'
        assert editor._source_values['title'][SOURCE] == 'Second mix'
        assert editor.recognition_values['audio_status'].text() == 'Zatwierdzone'
        assert editor.audio_summary.isVisible()
        editor.audio_show_candidates_button.click()
        assert editor.audio_candidates.item(0, 0).icon().isNull()
        assert not editor.audio_candidates.item(1, 0).icon().isNull()
        editor.audio_candidates.setCurrentCell(0, 1)
        assert editor.audio_confirm_button.text() == 'Zatwierdź jako źródło audio'
        assert editor.audio_confirm_button.isEnabled()
        editor.audio_confirm_button.click()
        assert len(confirmed) == 4
        assert editor.track.audio_recognition['recording_id'] == 'first'
        assert editor._source_values['title'][SOURCE] == 'First mix'
        assert editor._source_rows().count(SOURCE) == 1
        editor.audio_show_candidates_button.click()
        assert not editor.audio_candidates.item(0, 0).icon().isNull()
        assert editor.audio_candidates.item(1, 0).icon().isNull()
    finally:
        editor._force_closing = True
        editor.close()


@pytest.mark.parametrize('outcome', ('success', 'no_results', 'error'))
def test_audio_thread_completion_releases_retry_only_after_idle(tmp_path, monkeypatch, outcome):
    from audio_library_organizer.ui import main_window as main_window_module

    app = QApplication.instance() or QApplication([])
    previous_style = app.styleSheet()
    threads = []

    class HeldThread(QThread):
        stop_requested = False

        def __init__(self, parent=None):
            super().__init__(parent)
            threads.append(self)

        def quit(self):
            self.stop_requested = True

        def release(self):
            super().quit()

    class LookupJob:
        calls = 0

        def lookup(self, _track, *, progress):
            self.calls += 1
            progress('lookup')
            if self.calls == 1 and outcome == 'error':
                raise requests.Timeout('timed out')
            if self.calls == 1 and outcome == 'no_results':
                return []
            return [AcoustIDHit('new-recording', .93, 'New mix', 'Artist', acoustid_id='ac-new')]

    def until(predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        assert predicate()

    job = LookupJob()
    monkeypatch.setattr(main_window_module, 'QThread', HeldThread)
    monkeypatch.setattr(main_window_module, 'AudioIdentification', lambda *_args, **_kwargs: job)
    window = MainWindow(AppSettings((), LibraryPaths(tmp_path / 'library')),
                        QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    track = TrackRecord(path=tmp_path / 'song.mp3')
    approve_audio_source(track, AcoustIDHit('old-recording', .9, 'Old mix', 'Artist', acoustid_id='ac-old'))
    editor = MetadataEditorDialog(track, window)
    editor.audio_scan_requested.connect(lambda e: window._start_audio_identification(track, e))
    try:
        editor.show()
        editor.audio_scan_button.click()
        first = window._thread
        until(lambda: first.stop_requested)
        assert window._thread is first
        assert editor._audio_scan_busy
        assert not editor.audio_scan_button.isEnabled()
        assert not editor.audio_retry_button.isEnabled()
        assert editor.track.audio_recognition['recording_id'] == 'old-recording'
        assert 'Najpierw zakończ bieżącą operację.' not in editor.audio_detail.text()

        first.release()
        until(lambda: window._thread is None)
        assert not editor._audio_scan_busy
        assert editor.audio_scan_button.isEnabled()
        if outcome == 'success':
            editor.audio_candidates.setCurrentCell(0, 1)
            editor.audio_confirm_button.click()
            assert editor.track.audio_recognition['recording_id'] == 'new-recording'
            retry = editor.audio_retry_button
        elif outcome == 'error':
            assert editor.audio_phase.text() == 'Błąd rozpoznawania audio'
            assert editor.audio_empty_status.isVisible()
            assert not editor.audio_candidate_content.isVisible()
            retry = editor.audio_empty_retry
        else:
            assert editor.audio_phase.text() == 'Brak wyników'
            assert editor.audio_empty_status.isVisible()
            assert not editor.audio_candidate_content.isVisible()
            retry = editor.audio_empty_retry
        assert retry.isEnabled()
        retry.click()
        assert window._thread is not None
        second = window._thread
        until(lambda: second.stop_requested)
        second.release()
        until(lambda: window._thread is None)
        assert job.calls == 2
        assert 'Najpierw zakończ bieżącą operację.' not in editor.audio_detail.text()
    finally:
        for thread in threads:
            if isValid(thread) and thread.isRunning():
                thread.release()
                thread.wait(2000)
        app.processEvents()
        editor._force_closing = True
        editor.close()
        window.close()
        app.setStyleSheet(previous_style)


def test_candidate_hover_and_selection_keep_whole_row_without_focus_frame(tmp_path):
    app = QApplication.instance() or QApplication([])
    old_style = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'song.mp3'))
    try:
        editor.show_audio_candidates([
            AcoustIDHit('r1', .9, 'Song', 'Artist'),
            AcoustIDHit('r2', .8, 'Other', 'Artist'),
        ])
        editor.resize(1180, 900)
        editor.show()
        app.processEvents()
        table = editor.audio_candidates
        assert table.selectionBehavior() == table.SelectionBehavior.SelectRows
        assert table.selectionMode() == table.SelectionMode.SingleSelection
        before = table.viewport().grab().toImage()
        QTest.mouseMove(table.viewport(), table.visualItemRect(table.item(0, 1)).center())
        app.processEvents()
        hover = table.viewport().grab().toImage()
        for column in (0, 1, 2, 3, 4):
            rect = table.visualItemRect(table.item(0, column))
            x, y = rect.right() - 5, rect.center().y()
            assert hover.pixelColor(x, y) != before.pixelColor(x, y)
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton,
                         pos=table.visualItemRect(table.item(0, 1)).center())
        app.processEvents()
        assert table.currentRow() == 0
        assert {item.row() for item in table.selectedIndexes()} == {0}
        assert len(table.selectedIndexes()) == table.columnCount()
        assert editor.audio_confirm_button.isEnabled()
        assert not table.hasFocus() and not table.viewport().hasFocus()
        selected = table.viewport().grab().toImage()
        for column in range(table.columnCount()):
            rect = table.visualItemRect(table.item(0, column))
            point = QPoint(rect.right() - 5, rect.center().y())
            selected_color, hover_color = selected.pixelColor(point), hover.pixelColor(point)
            assert 225 <= selected_color.hue() <= 285, selected_color.name()
            assert selected_color.blue() > selected_color.green()
            assert selected_color.value() < 100
            assert selected_color != hover_color
            assert selected_color.value() > hover_color.value() + 15
            assert hover_color.blue() >= hover_color.green()
    finally:
        editor._force_closing = True
        editor.close()
        app.setStyleSheet(old_style)


def test_audio_phase_and_approval_share_a1_module_icon(tmp_path):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'song.mp3'))
    try:
        editor.show_audio_candidates([AcoustIDHit('r1', .9, 'Song', 'Artist')])
        editor.show()
        app.processEvents()
        assert editor.audio_phase.text() == 'Znaleziono kandydatów'
        assert editor.audio_phase_icon.isVisible()
        assert not editor.audio_phase_icon.pixmap().isNull()
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        assert editor.audio_summary.isVisible()
        assert not editor.audio_summary_icon.pixmap().isNull()
        assert editor.audio_phase_icon.pixmap().toImage() == editor.audio_summary_icon.pixmap().toImage()
    finally:
        editor._force_closing = True
        editor.close()


def test_rescan_preserves_approved_source_and_language_switches(tmp_path):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'song.mp3'))
    signals = []
    editor.audio_scan_requested.connect(signals.append)
    try:
        editor.show_audio_candidates([AcoustIDHit('old', .9, 'Old song', 'Artist', 'Album', '2001', 'ac-old')])
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        assert editor.audio_retry_button.height() == editor.audio_show_candidates_button.height()
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert editor.audio_summary_heading.text() == 'Audio source confirmed'
        assert editor.audio_show_candidates_button.text() == 'Show candidates'
        assert editor.audio_retry_button.text() == 'Recognize again'
        assert editor.audio_candidates.horizontalHeaderItem(3).text() == 'Album / year'
        assert editor.audio_candidates.horizontalHeaderItem(0).text() == 'Select'
        assert editor.audio_candidates.horizontalHeaderItem(4).text() == 'Match'
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert editor.audio_summary_heading.text() == 'Źródło audio zatwierdzone'
        assert editor.audio_candidates.horizontalHeaderItem(0).text() == 'Wybór'
        assert editor.audio_show_candidates_button.text() == 'Pokaż kandydatów'
        editor.audio_retry_button.click()
        assert signals == [editor]
        editor.start_audio_lookup()
        assert editor.track.audio_recognition['recording_id'] == 'old'
        assert editor.audio_summary.isHidden() is False
        editor.show_audio_candidates([AcoustIDHit('new', .8, 'New song', 'Artist', 'Album', '2002', 'ac-new')])
        assert editor.track.audio_recognition['recording_id'] == 'old'
        assert editor.recognition_values['audio_status'].text() == 'Zatwierdzone'
    finally:
        editor._force_closing = True
        editor.close()


def test_editor_candidate_approval_is_explicit_and_shows_full_source(tmp_path):
    app = QApplication.instance() or QApplication([])
    track = TrackRecord(path=tmp_path / 'track.mp3', artist='Original', title='Untouched')
    candidates = [AcoustIDHit('mb1', .94, 'Song (Remix)', 'Artist', 'Album', '2012', 'ac1'),
                  AcoustIDHit('mb2', .67, 'Other', 'Other artist')]
    editor = MetadataEditorDialog(track)
    try:
        assert editor.audio_scan_button.height() == editor.scan_online_button.height()
        editor.show_audio_candidates(candidates)
        assert editor.artist.text() == 'Original'
        assert SOURCE not in editor._source_values.get('artist', {})
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        assert editor.artist.text() == 'Original' and track.artist == 'Original'
        assert editor._source_values['artist'][SOURCE] == 'Artist'
        assert any(editor.source_table.item(row, 0).data(256) == SOURCE for row in range(editor.source_table.rowCount()))
        assert editor._source_buttons['artist'].menu().actions()
        assert SOURCE in editor._source_rows()
        assert editor.recognition_values['audio_status'].text() == 'Zatwierdzone'
        assert 'Artist' in editor.recognition_values['audio_result'].text()
        assert editor.SOURCE_COLORS[SOURCE] != editor.SOURCE_COLORS['Analiza audio']
        assert any(SOURCE.upper() in option.defaultWidget().findChild(QLabel, 'SourceMenuProvider').text()
                   for option in editor.source_legend_button.menu().actions()
                   if isinstance(option, QWidgetAction) and option.defaultWidget())
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert editor.audio_scan_button.text() == 'Identify by audio'
        assert editor.audio_confirm_button.text() == 'Confirm as audio source'
        assert editor.audio_confirm_button.isEnabled()
        assert editor.audio_summary_heading.text() == 'Audio source confirmed'
        assert editor.recognition_values['audio_status'].text() == 'Approved'
        assert 'AUDIO RECOGNITION' in [editor.source_table.item(row, 0).text() for row in range(editor.source_table.rowCount())]
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert editor.audio_scan_button.text() == 'Rozpoznaj po audio'
        assert editor.audio_summary_heading.text() == 'Źródło audio zatwierdzone'
        assert editor.recognition_values['audio_status'].text() == 'Zatwierdzone'
    finally:
        editor._force_closing = True
        editor.close()


def test_editor_does_not_offer_an_unidentified_recording_for_approval(tmp_path):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'song.mp3'))
    try:
        editor.show_audio_candidates([AcoustIDHit('mb-empty', .88, acoustid_id='ac-empty'),
                                      AcoustIDHit('mb-good', .86, 'Known song', 'Artist', acoustid_id='ac-good')])
        assert editor.audio_candidates.rowCount() == 1
        assert 'Known song' in editor.audio_candidates.item(0, 1).text()
        assert '— – —' not in editor.audio_candidates.item(0, 1).text()
        editor.audio_candidates.setCurrentCell(0, 1)
        assert editor.audio_confirm_button.isEnabled()
        editor.show_audio_candidates([AcoustIDHit('mb-empty', .88, acoustid_id='ac-empty')])
        assert editor.audio_candidates.rowCount() == 0
        assert not editor.audio_confirm_button.isEnabled()
        assert editor.audio_detail.text() == 'Brak kandydatów z wykonawcą i tytułem.'
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert editor.audio_detail.text() == 'No candidates with an artist and title.'
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert editor.audio_detail.text() == 'Brak kandydatów z wykonawcą i tytułem.'
    finally:
        editor._force_closing = True
        editor.close()


def test_retry_does_not_replace_approved_source_until_second_approval(tmp_path):
    app = QApplication.instance() or QApplication([])
    track = TrackRecord(path=tmp_path / 'track.mp3')
    editor = MetadataEditorDialog(track)
    try:
        editor.show_audio_candidates([AcoustIDHit('old', .9, 'Old', 'Old artist')])
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        editor.start_audio_lookup()
        editor.show_audio_candidates([AcoustIDHit('new', .8, 'New', 'New artist')])
        assert editor._source_values['title'][SOURCE] == 'Old'
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        assert editor._source_values['title'][SOURCE] == 'New'
        assert editor.title.text() == ''
    finally:
        editor._force_closing = True
        editor.close()


def test_source_dropdown_changes_only_the_field_chosen_by_user(tmp_path):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'song.mp3', artist='Original', title='Original title'))
    try:
        editor.show_audio_candidates([AcoustIDHit('mb1', .9, 'Found title', 'Found artist')])
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        assert editor.artist.text() == 'Original'
        assert editor.title.text() == 'Original title'
        editor._select_source_value('artist', SOURCE)
        assert editor.artist.text() == 'Found artist'
        assert editor.title.text() == 'Original title'
        assert editor.source_selections()['artist'] == SOURCE
    finally:
        editor._force_closing = True
        editor.close()


def test_confirm_in_real_editor_workflow_persists_without_test_upsert(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    original_style = app.styleSheet()
    settings = AppSettings((), LibraryPaths(tmp_path / 'library'))
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat)
    window = MainWindow(settings, store)
    track = TrackRecord(path=tmp_path / 'song.mp3', artist='Original', title='Untouched')
    track.path.write_bytes(b'placeholder')

    def use_editor(editor):
        editor.show_audio_candidates([
            AcoustIDHit('mb1', .94, 'Song', 'Artist', 'Album', '2012', 'ac1'),
            AcoustIDHit('mb2', .89, 'Other song', 'Other artist', 'Other album', '2015', 'ac2'),
        ])
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        editor.audio_show_candidates_button.click()
        assert editor.audio_confirm_button.isEnabled()
        editor.audio_confirm_button.click()  # Repeat A without creating another source.
        editor.audio_show_candidates_button.click()
        editor.audio_candidates.setCurrentCell(1, 1)
        editor.audio_confirm_button.click()  # A -> B.
        assert window.repository.list_tracks()[0].audio_recognition['recording_id'] == 'mb2'
        editor.audio_show_candidates_button.click()
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()  # B -> A.
        assert len(window.repository.list_tracks()) == 1
        assert editor._source_rows().count(SOURCE) == 1
        editor._force_closing = True
        return 0

    monkeypatch.setattr(MetadataEditorDialog, 'exec', use_editor)
    try:
        window._open_metadata_editor(track)
        persisted = window.repository.list_tracks()[0]
        assert persisted.artist == 'Original' and persisted.title == 'Untouched'
        assert persisted.audio_recognition['recording_id'] == 'mb1'
        reopened = MetadataEditorDialog(persisted)
        try:
            assert SOURCE in reopened._source_rows()
            assert reopened._source_values['artist'][SOURCE] == 'Artist'
            assert reopened.recognition_values['audio_status'].text() == 'Zatwierdzone'
            reopened.show()
            app.processEvents()
            assert reopened.audio_summary.isVisible()
            assert not reopened.audio_candidate_content.isVisible()
            reopened.audio_show_candidates_button.click()
            assert reopened.audio_candidates.rowCount() == 1
            assert not reopened.audio_candidates.item(0, 0).icon().isNull()
        finally:
            reopened._force_closing = True
            reopened.close()
    finally:
        window.close()
        app.processEvents()
        app.setStyleSheet(original_style)


def test_audio_button_runs_local_fingerprint_and_shows_acoustid_candidates(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    original_style = app.styleSheet()
    settings = AppSettings((), LibraryPaths(tmp_path / 'library'))
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat)
    store.setValue('providers/acoustid_key', 'key')
    window = MainWindow(settings, store)
    track = TrackRecord(path=tmp_path / 'song.mp3', artist='Original')
    track.path.write_bytes(b'placeholder')
    from audio_library_organizer.jobs import audio_identification
    from audio_library_organizer.providers import acoustid
    monkeypatch.setattr(audio_identification, 'fingerprint_audio', lambda path: FingerprintResult('FP', 230))
    def lookup(_client, fingerprint, duration):
        assert (fingerprint, duration) == ('FP', 230)
        return [AcoustIDHit('mb1', .94, 'Song', 'Artist', 'Album', '2012')]
    monkeypatch.setattr(acoustid.AcoustIDClient, 'lookup', lookup)

    def use_editor(editor):
        editor.audio_scan_button.click()
        deadline = time.monotonic() + 2
        while window._thread is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        app.processEvents()
        try:
            assert editor.audio_candidates.rowCount() == 1
            assert 'Song' in editor.audio_candidates.item(0, 1).text()
            assert track.artist == 'Original'
        finally:
            editor._force_closing = True
        return 0

    monkeypatch.setattr(MetadataEditorDialog, 'exec', use_editor)
    try:
        window._open_metadata_editor(track)
    finally:
        window.close()
        app.processEvents()
        app.setStyleSheet(original_style)


def test_audio_network_timeout_is_reported_in_both_languages(tmp_path):
    app = QApplication.instance() or QApplication([])
    class TimeoutJob:
        def lookup(self, track, *, progress):
            raise requests.Timeout('private remote error')
    worker = AudioIdentificationWorker(TimeoutJob(), TrackRecord(path=tmp_path / 'song.mp3'))
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'song.mp3'))
    worker.failed.connect(editor.show_audio_error)
    try:
        worker.run()
        app.processEvents()
        assert editor.audio_detail.text() == 'Przekroczono czas oczekiwania na AcoustID.'
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert editor.audio_detail.text() == 'AcoustID request timed out.'
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert editor.audio_detail.text() == 'Przekroczono czas oczekiwania na AcoustID.'
    finally:
        editor._force_closing = True
        editor.close()


def test_main_window_language_switch_refreshes_open_audio_editor(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    original_style = app.styleSheet()
    settings = AppSettings((), LibraryPaths(tmp_path / 'library'))
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat)
    window = MainWindow(settings, store)
    track = TrackRecord(path=tmp_path / 'song.mp3', title='Original')

    def use_editor(editor):
        editor.show_audio_candidates([AcoustIDHit('mb1', .9, 'Found title', 'Found artist')])
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
        window._apply_preferences(AppPreferences(language='en'))
        try:
            assert editor.audio_scan_button.text() == 'Identify by audio'
            assert editor.audio_summary_heading.text() == 'Audio source confirmed'
            assert editor.recognition_values['audio_status'].text() == 'Approved'
            window._apply_preferences(AppPreferences(language='pl'))
            assert editor.audio_summary_heading.text() == 'Źródło audio zatwierdzone'
        finally:
            editor._force_closing = True
        return 0

    monkeypatch.setattr(MetadataEditorDialog, 'exec', use_editor)
    try:
        window._open_metadata_editor(track)
    finally:
        window.close()
        app.setStyleSheet(original_style)


def test_audio_button_reports_missing_api_key_in_editor(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    original_style = app.styleSheet()
    settings = AppSettings((), LibraryPaths(tmp_path / 'library'))
    window = MainWindow(settings, QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    track = TrackRecord(path=tmp_path / 'song.mp3')

    def use_editor(editor):
        editor.audio_scan_button.click()
        deadline = time.monotonic() + 2
        while window._thread is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        try:
            assert 'Brak klucza AcoustID' in editor.audio_detail.text()
            assert editor.audio_scan_button.isEnabled()
        finally:
            editor._force_closing = True
        return 0

    monkeypatch.setattr(MetadataEditorDialog, 'exec', use_editor)
    try:
        window._open_metadata_editor(track)
    finally:
        window.close()
        app.setStyleSheet(original_style)
