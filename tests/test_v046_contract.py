from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
LIBMAN = (ROOT / 'src/audio_library_organizer/ui/library_manager.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def _slice(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def test_start_uses_active_library_name_and_removes_workflow_and_average_bpm():
    dashboard = _slice(MAIN, 'class DashboardPage', 'class SettingsPage')
    assert 'self.dashboard_title' in dashboard
    assert 'set_library_name' in dashboard
    assert "QLabel('Start — biblioteka ALO Music')" not in dashboard
    assert "'avg_bpm'" not in dashboard
    assert 'Średnie BPM' not in dashboard
    assert 'Etapy pracy' not in dashboard


def test_top_nav_uses_libraries_action_without_duplicate_badges():
    main_init = _slice(MAIN, 'class MainWindow', 'def _t(')
    assert "self.manage_libraries_nav" in main_init
    assert "setObjectName('ManageLibrariesNavAction')" in main_init
    assert 'self.active_library_badge' not in MAIN
    assert 'self.session_summary' not in MAIN


def test_add_new_files_is_visually_separate_from_workflow():
    main_init = _slice(MAIN, 'class MainWindow', 'def _t(')
    assert 'WorkflowToolbarSeparator' in main_init
    assert 'action.addSpacing(' in main_init
    assert 'QPushButton#ManageLibrariesNavAction' in THEME
    assert 'QPushButton#AddFilesAction' in THEME


def test_settings_locations_do_not_render_growing_scan_source_rows():
    rebuild = _slice(MAIN, 'def _rebuild_location_rows', 'def refresh_main_settings')
    assert 'settings.source_dirs' not in rebuild
    assert 'Muzyka do skanowania' not in rebuild
    assert 'LibraryAvailabilityStatus' in rebuild
    assert 'Zmień lokalizację' in rebuild
    assert '_path_row(' not in rebuild


def test_library_manager_has_no_duplicate_active_card_and_can_clear_history():
    assert "setObjectName('ActiveLibraryCard')" not in LIBMAN
    assert 'AKTYWNA BIBLIOTEKA' not in LIBMAN
    assert 'Wyczyść historię skanów' in LIBMAN
    assert 'clear_scan_history' in LIBMAN
    assert 'Otwórz w Eksploratorze' in LIBMAN
