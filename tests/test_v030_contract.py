from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
PLAYER = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')
SETTINGS = (ROOT / 'src/audio_library_organizer/domain/settings.py').read_text(encoding='utf-8')


def test_library_has_multi_genre_bpm_filters_and_collection_actions():
    assert 'self.genre_filter' in LIBRARY
    assert 'self.bpm_min' in LIBRARY and 'self.bpm_max' in LIBRARY
    assert 'track_matches_library_filters' in LIBRARY
    assert 'Zaznacz wszystko' in LIBRARY
    assert 'Utwórz folder z zaznaczonych' in LIBRARY
    assert 'create_collection_requested' in LIBRARY
    assert 'Key_Left' in LIBRARY and 'Key_Right' in LIBRARY


def test_custom_mp3_folders_have_path_page_and_navigation():
    assert 'MOJE_FOLDERY_MP3' in SETTINGS
    assert 'CollectionsPage' in MAIN
    assert 'Moje foldery MP3' in MAIN


def test_dashboard_has_library_health_and_ministats():
    assert 'Stan biblioteki' in MAIN
    for text in ('Brak okładki', 'Utwory sprawdzone online', 'Rozmiar biblioteki', 'Wolne miejsce na dysku'):
        assert text in MAIN
    for removed_text in ('Najczęstszy gatunek', 'Rozpoznane online', 'Średnie BPM'):
        assert removed_text not in MAIN
    assert 'build_library_health' in MAIN


def test_confidence_is_graphical_in_editor_and_library_details():
    assert 'ConfidenceWidget' in EDITOR
    assert 'ConfidenceWidget' in LIBRARY
    assert 'MetadataStatusCompact' in EDITOR
    assert 'RecognitionInfoCompact' in EDITOR
    assert 'QProgressBar#ConfidenceBar' in THEME


def test_metadata_source_menu_has_no_manual_choice_and_uses_colored_icons():
    menu_section = EDITOR[EDITOR.index('def _rebuild_source_menu'):EDITOR.index('def _display_source_value')]
    assert "QAction('RĘCZNIE" not in menu_section
    assert 'SOURCE_COLORS' in EDITOR
    assert 'SourceMenuOption' in menu_section
    assert 'QWidgetAction' in menu_section
    assert "self._current_sources[field_name] = 'Ręcznie'" in EDITOR


def test_ready_validation_explains_missing_fields_and_focuses_first():
    assert 'Nie można oznaczyć jako GOTOWE' in EDITOR
    assert 'setFocus()' in EDITOR
    assert 'missingRequired' in EDITOR


def test_editor_has_compact_shared_player_without_skip_buttons():
    assert 'CompactPlayerBar' in PLAYER
    assert 'compact_player' in EDITOR
    compact = PLAYER[PLAYER.index('class CompactPlayerBar'):]
    assert 'SeekSlider' in compact
    assert "'−10 s'" not in compact and "'+10 s'" not in compact
    assert 'self.player_bar.player' in compact


def test_duplicates_count_is_integrated_into_button_not_separate_badge():
    assert 'duplicate_nav_badge' not in MAIN
    assert 'duplicate_group_count(tracks)' in MAIN
    assert 'setText(f"{duplicate_label} ({duplicate_groups})")' in MAIN
    assert "setProperty('hasItems'" in MAIN
    assert 'TopNavButton[hasItems="true"]' in THEME


def test_required_filename_checkboxes_are_green_locked_and_genre_rule_is_explained():
    assert "setProperty('requiredLocked', required)" in MAIN
    assert 'Element wymagany — nie można wyłączyć' in MAIN
    assert 'QCheckBox[requiredLocked="true"]' in THEME
    assert 'pierwszy gatunek' in MAIN.casefold()


def test_online_button_can_cancel_and_resume_without_extra_button():
    assert 'cancel_current_identification' in MAIN
    assert 'action.cancel_online' in MAIN
    assert 'action.resume_online' in MAIN
    assert 'CancelOnlineAction' in THEME


def test_startup_and_main_use_persistent_library_database():
    assert "self.app_settings.library.database" in MAIN
    assert 'SessionStorage.create()' not in MAIN
