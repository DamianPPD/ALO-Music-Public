"""Runtime and packaging resource contracts survive asset cleanup."""

from pathlib import Path
import shutil
import sys
import tomllib

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from audio_library_organizer.ui import icons
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.first_run import FirstRunDialog, LanguageSelectionDialog
from audio_library_organizer.ui.i18n import apply_static_language, localized_no_cover_name


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'src/audio_library_organizer'
ASSETS = PACKAGE / 'assets'


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_declared_a1_aliases_resolve_their_own_artwork_without_info_fallback():
    for alias, target in icons._A1_ALIASES.items():
        path = ASSETS / 'icons/a1' / (target + '.svg')
        assert path.is_file(), (alias, target)
        expected = path.read_text().replace('currentColor', '#8fb9c8').encode()
        assert icons._svg_source(alias, '#8fb9c8') == expected


def test_unknown_a1_name_keeps_the_real_bundled_info_fallback(app):
    expected = (ASSETS / 'icons/a1/info.svg').read_text().replace('currentColor', '#8fb9c8').encode()
    assert icons._svg_source('unknown-ui-icon', '#8fb9c8') == expected
    assert not icons.alo_icon('unknown-ui-icon', '#8fb9c8', 16).pixmap(16, 16).isNull()


def test_live_navigation_uses_existing_start_c_artwork(current_start_window):
    for button, name in zip(current_start_window.nav_buttons, current_start_window.nav_icon_ids):
        assert (ASSETS / 'icons/start_c' / (name + '.svg')).is_file()
        expected = icons.start_icon(name, button._icon_color.name(), 20).pixmap(20, 20).toImage()
        assert button.icon().pixmap(20, 20).toImage() == expected


def test_package_data_includes_every_surviving_runtime_resource():
    with (ROOT / 'pyproject.toml').open('rb') as stream:
        patterns = tomllib.load(stream)['tool']['setuptools']['package-data']['audio_library_organizer']
    packaged = {path for pattern in patterns for path in PACKAGE.glob(pattern) if path.is_file()}
    resources = {path for path in ASSETS.rglob('*') if path.is_file()}
    assert resources <= packaged
    assert ASSETS / 'alo.ico' in packaged
    assert ASSETS / 'icons/a1/info.svg' in packaged


@pytest.mark.parametrize('language,cover', [('pl', 'no_cover.png'), ('en', 'no_cover_en.png')])
def test_frozen_first_run_and_localized_no_cover_use_packaged_resources(app, tmp_path, monkeypatch, language, cover):
    bundle = tmp_path / 'bundle'
    shutil.copytree(ASSETS, bundle / 'assets')
    monkeypatch.setattr(sys, '_MEIPASS', str(bundle), raising=False)
    for name in ('alo.ico', 'alo_icon.png', 'flag_pl.svg', 'flag_gb.svg', cover):
        assert asset_path(name) == bundle / 'assets' / name
        assert asset_path(name).is_file()
    gate = LanguageSelectionDialog(initial_language=language)
    setup = FirstRunDialog()
    try:
        apply_static_language(setup, language)
        assert localized_no_cover_name(setup) == cover
        assert not QPixmap(str(asset_path(localized_no_cover_name(setup)))).isNull()
        flag_buttons = gate.findChildren(QPushButton)
        assert len(flag_buttons) == 2
        assert all(not button.icon().pixmap(36, 22).isNull() for button in flag_buttons)
        assert any(label.pixmap() is not None and not label.pixmap().isNull()
                   for label in setup.findChildren(QLabel))
    finally:
        gate.close()
        setup.close()
