from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'src/audio_library_organizer/main.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_settings_exposes_language_normalization_library_management_and_backup():
    assert 'preferences_saved = Signal(object)' in MAIN_WINDOW
    assert 'manage_libraries_requested = Signal()' in MAIN_WINDOW
    assert 'backup_requested = Signal()' in MAIN_WINDOW
    assert 'restore_backup_requested = Signal()' in MAIN_WINDOW
    assert "QLabel('Język interfejsu')" in MAIN_WINDOW
    assert 'self.save_language_button' in MAIN_WINDOW
    assert 'self.save_api_button' in MAIN_WINDOW
    assert "QLabel('Normalizacja nazw')" in MAIN_WINDOW
    assert "QLabel('Kopia bezpieczeństwa ALO')" in MAIN_WINDOW
    assert 'self.normalization_table = QTableWidget' in MAIN_WINDOW


def test_required_filename_fields_use_green_tick_asset_not_green_square():
    assert "check_green.svg" in MAIN_WINDOW
    assert 'setEnabled(not required)' not in MAIN_WINDOW
    assert 'requiredLocked' in MAIN_WINDOW


def test_main_window_uses_library_registry_and_exposes_prominent_active_library_without_theme_toggle():
    assert 'LibraryRegistry.from_store' in MAIN_WINDOW
    assert 'self.manage_libraries_nav' in MAIN_WINDOW
    assert 'self.active_library_badge' not in MAIN_WINDOW
    assert 'self.theme_toggle' not in MAIN_WINDOW
    assert 'LibraryManagerDialog' in MAIN_WINDOW
    assert 'self.library.playlist_requested.connect' in MAIN_WINDOW
    assert 'self.collections.play_requested.connect' in MAIN_WINDOW


def test_toolbar_actions_are_visually_distinct_and_online_label_is_explicit(current_start_window):
    from PySide6.QtWidgets import QPushButton
    from audio_library_organizer.ui.icons import alo_icon

    window = current_start_window
    add = window.dashboard.sources.add_button
    online = window.identify_btn
    assert add.text() == 'Dodaj źródło'
    assert add.toolTip() == 'Wybierz folder z nowymi plikami'
    assert online.text() == '2. Rozpoznaj utwory online'
    assert online.objectName() == 'IdentifyOnlineAction'
    assert window.dashboard.sources_panel.isAncestorOf(add)
    assert not window.action_frame.isAncestorOf(add)
    assert window.findChildren(QPushButton, 'StartAddSource') == [add]
    assert add.icon().pixmap(18, 18).toImage() == alo_icon('start_source_add', '#a5cbde', 18).pixmap(18, 18).toImage()
    window.dashboard.scroll.ensureWidgetVisible(add)
    assert add.grab().toImage().pixelColor(6, 6) != online.grab().toImage().pixelColor(6, 6)


def test_startup_loads_preferences_and_uses_dark_theme_before_showing_window():
    assert 'AppPreferences.from_store(store)' in MAIN
    assert "style_for_theme('dark')" in MAIN or "style_for_theme(prefs.theme)" in MAIN

LIBRARY_MANAGER = (ROOT / 'src/audio_library_organizer/ui/library_manager.py').read_text(encoding='utf-8')

def test_removing_active_extra_library_rebinds_ui_to_main_profile():
    assert 'was_active = self.registry.active.profile_id == profile.profile_id' in LIBRARY_MANAGER
    assert "self.activate_requested.emit('main')" in LIBRARY_MANAGER

def test_library_manager_explains_new_library_and_handles_invalid_library_creation():
    assert "except ValueError as exc:" in LIBRARY_MANAGER
    assert "Nie można dodać biblioteki" in LIBRARY_MANAGER
    assert "Pliki muzyczne nie zostaną skopiowane ani usunięte." in LIBRARY_MANAGER
