from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')


def test_normalization_rows_are_large_and_have_explicit_edit_action():
    assert 'setDefaultSectionSize(40)' in MAIN or 'setDefaultSectionSize(42)' in MAIN
    assert 'Edytuj zaznaczoną' in MAIN
    assert 'def _edit_normalization_rule' in MAIN


def test_normalization_edit_uses_readable_dialog_fields_instead_of_tiny_cell_editor():
    assert "setWindowTitle('Edytuj regułę normalizacji')" in MAIN
    assert "QFormLayout" in MAIN
    assert "QDialogButtonBox" in MAIN
