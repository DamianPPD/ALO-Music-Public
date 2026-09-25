import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSettings

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.preferences import AppPreferences
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.jobs.reporting import export_session_html
from audio_library_organizer.ui.i18n import apply_static_language, translate_static_text
from audio_library_organizer.ui.i18n import localized_no_cover_name
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.help_center import HelpCenter


def _app():
    return QApplication.instance() or QApplication([])


def test_english_status_names_and_runtime_counts():
    assert translate_static_text('DO SPRAWDZENIA', 'en') == 'NEEDS REVIEW'
    assert translate_static_text('NIE WYBIERAM', 'en') == 'NOT SELECTED'
    assert translate_static_text('3 plików • 2 grup', 'en') == '3 files • 2 groups'
    assert translate_static_text('Sortowanie: Status ↑   •   Filtry: brak', 'en') == 'Sort: Status ↑   •   Filters: none'


def test_library_status_rows_update_when_language_changes(tmp_path):
    _app()
    page = LibraryPage()
    ready = TrackRecord(path=tmp_path / 'ready.mp3', artist='Artist', title='Title', year='2008', genre='House', bpm=128, status='ready')
    review = TrackRecord(path=tmp_path / 'review.mp3', artist='Artist', title='Title', status='review')
    omitted = TrackRecord(path=tmp_path / 'omitted.mp3', status='not_selected')
    page.set_tracks([ready, review, omitted])
    try:
        apply_static_language(page, 'en')
        page.refresh(preserve_order=True)
        labels = [page.model.item(i, 0).text() for i in range(page.model.rowCount())]
        assert set(labels) == {'READY', 'NEEDS REVIEW', 'NOT SELECTED'}
        assert page.model.headerData(1, Qt.Orientation.Horizontal).lower() == 'artist'
        apply_static_language(page, 'pl')
        page.refresh(preserve_order=True)
        assert {page.model.item(i, 0).text() for i in range(page.model.rowCount())} == {'GOTOWE', 'DO SPRAWDZENIA', 'NIE WYBIERAM'}
    finally:
        page.close()


def test_help_contents_follow_language_without_losing_topic():
    _app()
    help_page = HelpCenter()
    try:
        help_page.show_topic('Statusy i zatwierdzanie')
        help_page.set_language('en')
        assert help_page.topics.currentItem().text() == 'Statuses and approval'
        assert 'NEEDS REVIEW' in help_page.browser.toPlainText()
        assert 'DO SPRAWDZENIA' not in help_page.browser.toPlainText()
        help_page.set_language('pl')
        assert help_page.topics.currentItem().text() == 'Statusy i zatwierdzanie'
    finally:
        help_page.close()


def test_live_window_switch_rebuilds_loaded_library_and_operation_text(tmp_path, monkeypatch):
    app = _app()
    original_stylesheet = app.styleSheet()
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage

    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    settings = AppSettings((), LibraryPaths(tmp_path / 'library'))
    settings.library.ensure_created()
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat)
    AppPreferences(language='pl').save(store)
    window = main_window.MainWindow(settings, store)
    (tmp_path / 'review.mp3').write_bytes(b'mock audio')
    track = TrackRecord(path=tmp_path / 'review.mp3', artist='Artist', title='Track', status='review')
    try:
        window.repository.upsert_track(track)
        window.refresh_data()
        window.player.current_track = track
        window.player._load_cover(track)
        original_cover = window.player._cover_pixmap.toImage()
        window._show_operation('Ręcznie zatwierdzono jako GOTOWE: sample.mp3')
        window._apply_preferences(AppPreferences(language='en'))
        assert window.library.model.item(0, 0).text() == 'NEEDS REVIEW'
        assert window.operation_status.text() == 'Manually marked as READY: sample.mp3'
        assert '1 needs review' in window.dashboard.attention_text.text()
        assert localized_no_cover_name(window.player) == 'no_cover_en.png'
        assert window.player._cover_pixmap.toImage() != original_cover
        window._apply_preferences(AppPreferences(language='pl'))
        assert window.library.model.item(0, 0).text() == 'DO SPRAWDZENIA'
        assert window.operation_status.text() == 'Ręcznie zatwierdzono jako GOTOWE: sample.mp3'
        assert window.player._cover_pixmap.toImage() == original_cover
    finally:
        window.close()
        app.setStyleSheet(original_stylesheet)


def test_english_session_report_translates_review_and_keeps_metadata(tmp_path):
    review = TrackRecord(path=tmp_path / 'sample.mp3', artist='Artist', title='Track', status='review')
    html = export_session_html([review], tmp_path / 'session.html', language='en').read_text(encoding='utf-8')
    assert '<html lang="en">' in html
    assert 'NEEDS REVIEW — reasons' in html
    assert '<td>NEEDS REVIEW</td>' in html
    assert 'Missing: Year' in html
    assert 'DO SPRAWDZENIA' not in html
