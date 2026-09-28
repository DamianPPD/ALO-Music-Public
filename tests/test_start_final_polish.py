import hashlib
import os
import tomllib
from xml.etree import ElementTree

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui import icons, main_window
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.dashboard_page import DashboardPage


START_C_NAMES = {
    'nav_start', 'nav_library', 'nav_duplicates', 'nav_folders', 'nav_help', 'nav_settings',
    'scan', 'recognize', 'review', 'export', 'plus', 'cancel',
    'status_ring', 'check_circle', 'spinner', 'warning',
    'music_note', 'duplicates', 'cover', 'folder', 'folder_check', 'folder_x',
    'report', 'cloud', 'document_warning', 'database', 'document_x', 'disk',
}


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def restore_app_style():
    app = _app()
    original_style = app.styleSheet()
    yield
    app.setStyleSheet(original_style)


def _window(tmp_path, monkeypatch):
    _app()
    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    return main_window.MainWindow(AppSettings((), paths), store)


def _pixels(pixmap):
    assert pixmap is not None and not pixmap.isNull()
    image = pixmap.toImage()
    # Transparent RGB storage may be uninitialised by Qt; compare visible pixels.
    return tuple(
        (color.red(), color.green(), color.blue(), color.alpha()) if color.alpha() else (0, 0, 0, 0)
        for y in range(image.height()) for x in range(image.width())
        for color in (image.pixelColor(x, y),)
    )


def test_hero_uses_the_exact_approved_panorama_without_changing_height(tmp_path):
    _app()
    image = asset_path('start_studio.png')
    assert hashlib.sha256(image.read_bytes()).hexdigest() == '9d29b815ce91a984bd6db4f8f3e4cb9a7b357fe5ef9138ddf3454df9f5453a92'
    page = DashboardPage(AppSettings((), LibraryPaths(tmp_path / 'library')))
    try:
        page.resize(1500, 900)
        page.show()
        _app().processEvents()
        assert page.hero.artwork_path == image
        assert page.hero.height() == 232
        assert page.hero_title.text() == 'Twoja muzyka.\nW Twoim stylu.'
        rendered = page.hero.grab().toImage()
        left = rendered.pixelColor(8, rendered.height() // 2)
        right = rendered.pixelColor(rendered.width() * 3 // 4, rendered.height() // 2)
        assert left.red() < 35 and left.green() < 35
        assert right.red() > left.red() + 30
    finally:
        page.close()


def test_c_icon_assets_are_real_consistent_svg_and_render_at_dpi_sizes():
    _app()
    with (asset_path('start_studio.png').parents[3] / 'pyproject.toml').open('rb') as stream:
        package_data = tomllib.load(stream)['tool']['setuptools']['package-data']['audio_library_organizer']
    assert 'assets/icons/start_c/*.svg' in package_data
    for name in START_C_NAMES:
        path = asset_path(f'icons/start_c/{name}.svg')
        assert path.is_file(), name
        root = ElementTree.parse(path).getroot()
        assert root.attrib['viewBox'] == '0 0 24 24'
        assert root.attrib['stroke-width'] == '2.2'
        assert root.attrib['stroke'] == 'currentColor'
        assert 'filter' not in path.read_text(encoding='utf-8')
        for size in (18, 23, 32):
            pixmap = icons.start_icon(name, '#51e49e', size).pixmap(size, size)
            assert not pixmap.isNull(), (name, size)
            assert any(pixmap.toImage().pixelColor(x, y).alpha() for x in range(0, size, 2) for y in range(0, size, 2))


def test_start_sections_use_c_icons_without_changing_actions(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.show()
        _app().processEvents()
        assert len(window.action_buttons) == 5
        for button, name in zip(window.nav_buttons, window.nav_icon_ids):
            assert _pixels(button.icon().pixmap(20, 20)) == _pixels(icons.start_icon(name, button._icon_color.name(), 20).pixmap(20, 20))
        for button, name in window.action_icon_ids:
            color = window.action_icon_colors[button]
            assert _pixels(button.icon().pixmap(23, 23)) == _pixels(icons.start_icon(name, color, 23).pixmap(23, 23))
        stat_icons = {'total': 'music_note', 'review': 'warning', 'duplicate': 'duplicates', 'missing_covers': 'cover'}
        for key, name in stat_icons.items():
            card = window.dashboard.cards[key]
            assert _pixels(card.stat_icon.pixmap()) == _pixels(icons.start_icon(name, card._accent, 32).pixmap(32, 32))
        locations = {'root': 'folder', 'ready': 'folder_check', 'review': 'warning',
                     'not_selected': 'folder_x', 'custom_folders': 'music_note', 'reports': 'report'}
        for key, name in locations.items():
            card = window.dashboard.location_cards[key]
            assert _pixels(card.title_icon.pixmap()) == _pixels(icons.start_icon(name, card.property('accentColor'), 29).pixmap(29, 29))
        metrics = {'covers': 'cover', 'online': 'cloud', 'suspicious': 'document_warning',
                   'size': 'database', 'missing': 'document_x', 'free_space': 'disk'}
        for key, name in metrics.items():
            box = window.dashboard.stats_values[key].parentWidget()
            icon = next(label for label in box.findChildren(QLabel) if label.pixmap() is not None)
            assert _pixels(icon.pixmap()) == _pixels(icons.start_icon(name, '#79dcb0', 15).pixmap(15, 15))
        assert len(window.dashboard.location_cards) == 6
    finally:
        window.close()


def test_operation_c_status_and_width_stay_right_of_workflow(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.show()
        _app().processEvents()
        assert window.operation_frame.parentWidget() is window.action_frame
        assert window.operation_frame.width() >= 350
        gap = window.operation_frame.geometry().left() - window.new_files_btn.geometry().right()
        assert 16 <= gap <= 40
        assert _pixels(window.operation_icon.pixmap()) == _pixels(icons.start_icon('status_ring', '#8fa1b3', 17).pixmap(17, 17))
        assert _pixels(window.operation_state_icon.pixmap()) == _pixels(icons.start_icon('check_circle', '#67e495', 17).pixmap(17, 17))
        window._set_operation_state('scan', 'SKANOWANIE', '127 / 419 · 30%')
        assert _pixels(window.operation_state_icon.pixmap()) == _pixels(icons.start_icon('spinner', '#55dca0', 17).pixmap(17, 17))
        window._set_operation_state('error', 'BŁĄD', 'Przerwano')
        assert _pixels(window.operation_state_icon.pixmap()) == _pixels(icons.start_icon('warning', '#ff6b6b', 17).pixmap(17, 17))
    finally:
        window.close()
