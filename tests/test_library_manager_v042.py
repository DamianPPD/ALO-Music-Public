from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/audio_library_organizer/ui/library_manager.py').read_text(encoding='utf-8')


def test_library_manager_has_explanatory_creation_dialog_before_folder_picker():
    assert 'class CreateLibraryDialog' in SOURCE
    assert 'Utwórz nową bibliotekę' in SOURCE
    assert 'Wybierz folder zapisu' in SOURCE
    assert 'Foldery źródłowe dodasz osobno podczas skanowania' in SOURCE
    assert 'Pliki muzyczne nie zostaną skopiowane ani usunięte' in SOURCE


def test_library_manager_has_no_temporary_sessions_and_click_only_selects_library():
    assert "QGroupBox('Sesje tymczasowe')" not in SOURCE
    assert 'open_temporary_session' not in SOURCE
    assert 'itemClicked.connect(self._activate_clicked_library)' not in SOURCE
    assert 'itemSelectionChanged.connect(self._selection_changed)' in SOURCE
    assert 'Kliknij, aby zaznaczyć' in SOURCE
    assert 'Ustaw jako aktywną' in SOURCE


def test_active_library_is_prominent_without_duplicate_active_card_and_remove_copy_is_safe():
    assert 'AKTYWNA BIBLIOTEKA' not in SOURCE
    assert 'AKTYWNA' in SOURCE
    assert 'ActiveLibraryRow' in SOURCE
    assert 'Pliki muzyczne pozostaną na dysku' in SOURCE


def test_main_library_card_selects_and_has_explicit_activation_button():
    assert 'MainLibraryCard' in SOURCE
    assert 'self.main_card.clicked.connect(self._select_main_library)' in SOURCE
    assert 'self.main_activate_button' in SOURCE
    assert 'def _activate_main_library' in SOURCE
    assert 'QSize(0, 66)' in SOURCE
    assert 'ActiveLibraryRow' in SOURCE
