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


def test_full_sync_path_requests_missing_record_purge():
    assert 'sync_availability(purge_missing=True)' in WINDOW
