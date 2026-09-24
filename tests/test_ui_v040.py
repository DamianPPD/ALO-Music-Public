from pathlib import Path

from audio_library_organizer.ui.genre_input import build_genre_suggestions
from audio_library_organizer.ui.confidence import confidence_color

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = (ROOT / 'src/audio_library_organizer/ui/collections_page.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
PLAYER = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_genre_suggestions_merge_defaults_library_values_and_filter_prefix():
    values = ['Trance / Vocal', 'House / Funky', 'Progressive Trance']
    all_items = build_genre_suggestions(values)
    assert 'Trance' in all_items
    assert 'Vocal' in all_items
    assert 'House' in all_items
    filtered = build_genre_suggestions(values, query='tra')
    assert 'Trance' in filtered and 'Progressive Trance' in filtered
    assert 'House' not in filtered


def test_confidence_uses_real_spectrum_colors():
    assert confidence_color(0) != confidence_color(50) != confidence_color(100)
    assert confidence_color(20).startswith('#')


def test_collections_files_can_play_with_shared_player_and_have_playlist_action():
    assert 'play_requested = Signal(object)' in COLLECTIONS
    assert 'playlist_requested = Signal(object)' in COLLECTIONS
    assert 'self.files.doubleClicked.connect(self._play_selected_file)' in COLLECTIONS


def test_editor_has_graphical_empty_state_only_for_missing_panel_and_visible_player_frame():
    assert 'MissingEmptyState' in EDITOR
    assert 'Dane kompletne' in EDITOR
    assert 'Wszystkie wymagane pola są uzupełnione' in EDITOR
    assert 'QFrame#CompactPlayerBar' in THEME and 'border:2px' in THEME


def test_required_filename_checkbox_uses_green_tick_without_solid_green_square():
    main_window = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
    assert 'check_green.svg' in main_window
    assert 'QCheckBox[requiredLocked="true"]::indicator:checked' in THEME
    required_rule = THEME.split('QCheckBox[requiredLocked="true"]::indicator:checked', 1)[1].split('}', 1)[0]
    assert 'background:#43d17d' not in required_rule.replace(' ', '')


def test_dynamic_dialogs_receive_selected_language_before_exec():
    main_window = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
    manager_block = main_window.split('def _open_library_manager(self):', 1)[1].split('def _activate_library_profile', 1)[0]
    editor_block = main_window.split('def _open_metadata_editor(self, track, *, duplicate_context: bool = False):', 1)[1].split('def _save_metadata_from_editor', 1)[0]
    assert 'apply_static_language(dialog, self.preferences.language)' in manager_block
    assert 'apply_static_language(dialog, self.preferences.language)' in editor_block


# Mini-player identity and shared controls are covered at runtime by
# test_player_reference_followup, replacing the obsolete ODSŁUCH-label contract.
