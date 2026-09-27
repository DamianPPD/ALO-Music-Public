import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidgetAction
import requests

from audio_library_organizer.domain.candidates import AcoustIDHit
from audio_library_organizer.audio.fingerprint import FingerprintResult
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import SOURCE
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.domain.preferences import AppPreferences
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
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
        editor.show_audio_candidates([AcoustIDHit('mb1', .94, 'Song', 'Artist', 'Album', '2012', 'ac1')])
        editor.audio_candidates.setCurrentCell(0, 1)
        editor.audio_confirm_button.click()
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
