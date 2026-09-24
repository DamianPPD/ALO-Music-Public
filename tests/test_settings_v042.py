from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
PREFS = (ROOT / 'src/audio_library_organizer/domain/preferences.py').read_text(encoding='utf-8')


def test_settings_keep_language_but_remove_theme_choice_and_quick_toggle():
    assert 'self.language_combo' in MAIN
    assert 'self.theme_combo' not in MAIN
    assert 'self.theme_toggle' not in MAIN
    assert "theme = 'dark'" in PREFS or "object.__setattr__(self, 'theme', 'dark')" in PREFS


def test_language_and_api_sections_have_local_save_actions():
    assert 'self.save_language_button' in MAIN
    assert "Zapisz język" in MAIN
    assert 'self.save_api_button' in MAIN
    assert 'Zapisz klucze' in MAIN


def test_settings_locations_are_rebuilt_from_current_main_settings():
    assert 'def refresh_main_settings(self, settings: AppSettings)' in MAIN
    assert 'self._rebuild_location_rows()' in MAIN
