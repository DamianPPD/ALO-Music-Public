from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONF = (ROOT / 'src/audio_library_organizer/ui/confidence.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_confidence_panel_has_percent_bar_description_but_no_level_badge():
    assert "self.percent = QLabel" in CONF
    assert 'self.bar = QProgressBar' in CONF
    assert 'self.description = QLabel' in CONF
    assert 'self.label = QLabel' not in CONF
    assert 'ConfidenceLevel' not in CONF


def test_missing_empty_state_uses_natural_complete_copy_and_graphic():
    assert 'MissingCompleteGraphic' in EDITOR
    assert 'Dane kompletne' in EDITOR
    assert 'Wszystkie wymagane pola są uzupełnione' in EDITOR
    assert 'Brak braków' not in EDITOR


def test_confidence_visual_has_polished_bar_spacing():
    assert 'QFrame#ConfidenceWidget' in THEME
    assert 'QProgressBar#ConfidenceBar' in THEME
