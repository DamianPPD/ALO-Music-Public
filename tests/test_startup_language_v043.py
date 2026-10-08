from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/main.py').read_text(encoding='utf-8')
FIRST_RUN = (ROOT / 'src/audio_library_organizer/ui/first_run.py').read_text(encoding='utf-8')
MANAGER = (ROOT / 'src/audio_library_organizer/ui/library_manager.py').read_text(encoding='utf-8')
WINDOW = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')


def test_startup_has_language_picker_before_library_wizard():
    assert 'LanguageSelectionDialog' in FIRST_RUN
    assert 'Wybierz język' in FIRST_RUN
    assert 'Choose language' in FIRST_RUN
    assert 'language_selection_done' in MAIN
    assert 'save_language_selection' in MAIN
    assert MAIN.index('LanguageSelectionDialog') < MAIN.index('FirstRunDialog')


def test_advanced_settings_exposes_full_clean_reset_not_library_manager():
    assert 'Resetuj ALO do czystego stanu' not in MANAGER
    assert 'full_reset_requested = Signal()' in WINDOW
    assert 'full_reset_requested.connect(self._reset_alo_to_clean_state)' in WINDOW
    assert 'reset_alo_state' in WINDOW
    assert 'Resetuj ALO do czystego stanu' in WINDOW.split("class MainWindow", 1)[0]


def test_full_sync_path_retains_missing_work(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.storage.repository import LibraryRepository
    from audio_library_organizer.ui.main_window import MainWindow

    repo = LibraryRepository(tmp_path/'library.sqlite3'); repo.initialize()
    track = TrackRecord(tmp_path/'unavailable.mp3', title='Saved work', status='not_selected')
    repo.upsert_track(track)
    class Window:
        repository = repo
    window = Window()
    assert MainWindow._sync_availability(window) == []
    saved = repo.get_track(track.track_id)
    assert saved.title == 'Saved work' and saved.status == 'not_selected'
    assert saved.is_available is False
    assert window.availability.purged == 0
