from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
DUPLICATES = (ROOT / 'src/audio_library_organizer/ui/duplicates_page.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
LIBMAN = (ROOT / 'src/audio_library_organizer/ui/library_manager.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_metadata_editor_removes_before_after_compare_panel_and_status_hint():
    assert "QLabel('PRZED ZMIANĄ')" not in EDITOR
    assert "QLabel('PO ZMIANIE')" not in EDITOR
    assert "setObjectName('CompareBeforeCard')" not in EDITOR
    assert "setObjectName('CompareAfterCard')" not in EDITOR
    assert 'self.current_status_hint' not in EDITOR
    assert "'Wymaga sprawdzenia'" not in EDITOR


def test_pre_online_snapshot_is_visually_more_prominent():
    assert 'QLabel#PreOnlineSnapshotText' in THEME
    assert 'font-size:11' in THEME or 'font-size:12' in THEME
    assert "setMinimumHeight" in EDITOR and 'PreOnlineSnapshotCard' in EDITOR


def test_duplicates_are_a_data_table_without_program_recommendations_or_abc_play_buttons():
    assert 'QTableWidget' in DUPLICATES
    for header in ('Wariant', 'Nazwa pliku', 'Długość', 'BPM', 'Format', 'Bitrate', 'Hz', 'Rozmiar', 'Decyzja'):
        assert header in DUPLICATES
    assert 'recommend_duplicate' not in DUPLICATES
    assert 'REKOMENDOWANY DO ZACHOWANIA' not in DUPLICATES
    assert 'SUGESTIA PROGRAMU' not in DUPLICATES
    assert "QPushButton('▶ A')" not in DUPLICATES
    assert "QPushButton('▶ B')" not in DUPLICATES
    assert "QPushButton('▶ C')" not in DUPLICATES
    assert "QColor('#173c2d')" in DUPLICATES
    assert "QColor('#2a3038')" in DUPLICATES
    assert 'difference_columns' not in DUPLICATES
    assert "QColor('#302719')" not in DUPLICATES


def test_duplicate_nav_counter_uses_potential_duplicate_groups():
    assert 'duplicate_group_count' in MAIN
    assert "summary['duplicate']" not in MAIN[MAIN.find('def refresh_data'):MAIN.find('def _sync_availability')]


def test_library_manager_is_destination_focused_and_has_scrollable_scan_history():
    assert 'Folder biblioteki / zapisu' in LIBMAN
    assert 'Skanowane źródła' in LIBMAN
    assert "setObjectName('ScanHistoryList')" in LIBMAN
    assert 'Otwórz folder źródłowy' not in LIBMAN
    assert 'profile.library_root' in LIBMAN
    assert 'Otwórz w Eksploratorze' in LIBMAN
    assert 'registry.add_library(name, (), library_root=' in LIBMAN


def test_switching_library_does_not_automatically_scan_old_sources():
    activation = MAIN[MAIN.find('def _activate_library_profile'):MAIN.find('def _rebind_active_profile')]
    assert 'start_scan' not in activation


def test_library_details_surface_version_family_information():
    assert 'Rodzina wersji' in LIBRARY
    assert 'group_version_families' in LIBRARY


def test_main_player_transport_is_compact_and_visually_balanced():
    player = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
    assert 'self.play.setFixedSize(58, 58)' in player
    assert 'button.setFixedSize(44, 44)' in player
    assert "alo_icon('repeat'" in player
    assert 'QPushButton#PlayerIconButton' in THEME


def test_duplicate_recommendation_engine_is_not_part_of_user_workflow_anymore():
    health = (ROOT / 'src/audio_library_organizer/jobs/file_health.py').read_text(encoding='utf-8')
    assert 'def recommend_duplicate' not in health
    assert 'Rekomendowany do zachowania' not in health


def test_duplicate_refresh_preserves_the_users_selected_variant_when_group_stays_visible():
    assert 'selected_path' in DUPLICATES
    assert 'str(track.path).casefold() == selected_path' in DUPLICATES
