from audio_library_organizer import __version__
from audio_library_organizer.help_content import HELP_TOPICS
from pathlib import Path


def test_new_polish_ui_release_has_incremented_version():
    assert __version__ == '0.4.24'


def test_user_facing_version_markers_match_v0424():
    root = Path(__file__).resolve().parents[1]
    assert 'Wersja wyświetlana: 0.4.24' in (root / 'README.md').read_text(encoding='utf-8')
    assert 'GPL-3.0-or-later' in (root / 'README.md').read_text(encoding='utf-8')
    assert 'ALO Music v0.4.24' in (root / 'START_ALO.bat').read_text(encoding='utf-8')
    assert 'Wersja <b>0.4.24</b>' in HELP_TOPICS['O programie']
