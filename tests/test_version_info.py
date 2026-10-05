from audio_library_organizer import __version__
from audio_library_organizer.help_content import HELP_TOPICS
from pathlib import Path


def test_runtime_version_marks_the_development_build():
    assert __version__ == '0.4.26-dev'


def test_dev_help_uses_runtime_version_and_public_release_documents_are_unchanged():
    root = Path(__file__).resolve().parents[1]
    assert 'Wersja wyświetlana: 0.4.26-dev' in (root / 'README.md').read_text(encoding='utf-8')
    assert 'GPL-3.0-or-later' in (root / 'README.md').read_text(encoding='utf-8')
    assert 'ALO Music v0.4.26-dev' in (root / 'START_ALO.bat').read_text(encoding='utf-8')
    assert f'Wersja <b>{__version__}</b>' in HELP_TOPICS['O programie']
