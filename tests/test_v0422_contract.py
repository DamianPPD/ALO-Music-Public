from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.icons import alo_icon


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'src/audio_library_organizer/assets/icons/a1'
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')
I18N = (ROOT / 'src/audio_library_organizer/ui/i18n.py').read_text(encoding='utf-8')


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication(['alo-v0422-tests'])
    return _APP


def test_version_is_0422_everywhere():
    assert "__version__ = '0.4.23'" in (ROOT / 'src/audio_library_organizer/__init__.py').read_text(encoding='utf-8')
    assert 'version = "0.4.23"' in (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'v0.4.23' in (ROOT / 'START_HERE.txt').read_text(encoding='utf-8')


def test_a1_asset_pack_has_required_ultra_thin_icons():
    required = {
        'add_tracks', 'cancel', 'check_library', 'copy', 'cover', 'duplicates',
        'edit', 'export', 'folder', 'folder_open', 'help', 'info', 'integration',
        'library', 'lock', 'metadata', 'pause', 'play', 'recognize', 'report',
        'restore', 'save', 'scan', 'settings', 'start', 'status', 'undo',
        'unlock', 'volume', 'warning',
    }
    assert required <= {path.stem for path in ASSETS.glob('*.svg')}
    for path in ASSETS.glob('*.svg'):
        svg = path.read_text(encoding='utf-8')
        assert 'viewBox="0 0 24 24"' in svg
        assert 'stroke="currentColor"' in svg
        assert 'stroke-width="1.15"' in svg


def test_a1_loader_renders_icons_at_common_windows_scale_sizes():
    _app()
    for logical_size in (16, 20, 24, 30, 36):
        icon = alo_icon('folder', '#63d6ff', logical_size)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()
        pixmap = icon.pixmap(logical_size, logical_size)
        assert not pixmap.isNull()
        image = pixmap.toImage()
        assert any(
            image.pixelColor(x, y).alpha() > 0
            for y in range(image.height())
            for x in range(image.width())
        )


def test_ui_controls_do_not_use_font_glyphs_as_icons():
    forbidden = set('📁⏳🔒🔓⚙▶♫✎✓⚠ⓘ◎⌕⇩↗↶★●◈▣＋')
    ui_root = ROOT / 'src/audio_library_organizer/ui'
    offenders = {}
    for path in ui_root.glob('*.py'):
        if path.name == 'i18n.py':
            continue  # legacy translation aliases are not rendered controls
        found = sorted(forbidden.intersection(path.read_text(encoding='utf-8')))
        if found:
            offenders[path.name] = found
    assert offenders == {}


def test_start_has_real_quick_access_locations_and_actions(tmp_path):
    _app()
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    assert set(page.location_cards) == {
        'root', 'ready', 'review', 'not_selected', 'custom_folders', 'reports'
    }
    expected = {
        'root': paths.root,
        'ready': paths.ready,
        'review': paths.review,
        'not_selected': paths.not_selected,
        'custom_folders': paths.custom_folders,
        'reports': paths.reports,
    }
    assert {key: card.path for key, card in page.location_cards.items()} == expected
    for card in page.location_cards.values():
        assert card.open_button.toolTip() == 'Otwórz folder w Eksploratorze'
        assert card.copy_button.toolTip() == 'Kopiuj ścieżkę'
        assert card.path_label.toolTip() == str(card.path)


def test_start_copy_path_uses_clipboard(tmp_path):
    app = _app()
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    page.location_cards['reports'].copy_button.click()
    assert app.clipboard().text() == str(paths.reports)


def test_start_open_folder_uses_the_real_configured_location(tmp_path, monkeypatch):
    _app()
    paths = LibraryPaths(tmp_path / 'library'); paths.ensure_created()
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url) or True)
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    page.location_cards['review'].open_button.click()
    assert len(opened) == 1
    assert Path(opened[0].toLocalFile()) == paths.review


def test_start_marks_nonexistent_location_neutral_and_disables_open(tmp_path):
    _app()
    paths = LibraryPaths(tmp_path / 'not-created')
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    card = page.location_cards['reports']
    assert card.availability.text() == 'Niedostępna'
    assert card.open_button.isEnabled() is False
    assert card.copy_button.isEnabled() is True


def test_start_reflows_quick_access_for_wide_and_narrow_windows(tmp_path):
    app = _app()
    paths = LibraryPaths(tmp_path / 'library'); paths.ensure_created()
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    page.resize(1280, 900); page.show(); app.processEvents()
    assert page.quick_access_layout.indexOf(page.location_cards['review']) >= 0
    wide_position = page.quick_access_layout.getItemPosition(page.quick_access_layout.indexOf(page.location_cards['review']))
    page.resize(950, 900); app.processEvents(); page._reflow_locations()
    narrow_position = page.quick_access_layout.getItemPosition(page.quick_access_layout.indexOf(page.location_cards['review']))
    assert wide_position[:2] == (0, 2)
    assert page.width() < 1100
    assert narrow_position[:2] == (1, 0)
    page.close()


def test_add_tracks_copy_and_cancel_hierarchy_are_explicit():
    assert "QPushButton('Dodaj utwory do biblioteki')" in MAIN
    assert "Dodaj pliki audio do biblioteki ALO Music" in MAIN
    assert "'action.add_files': {'pl': 'Dodaj utwory do biblioteki', 'en': 'Add tracks to library'}" in I18N
    assert 'QPushButton#CancelScanAction:hover' in THEME
    assert 'QPushButton#CancelOnlineAction:hover' in THEME
    assert 'border:1px solid #e45f68' in THEME
    assert "self.scan_btn.setIcon(alo_icon('cancel'" in MAIN
    assert "self.identify_btn.setIcon(alo_icon('cancel'" in MAIN
    assert '⏳ Anulowanie' not in MAIN


def test_integrations_are_separate_cards_with_configuration_statuses():
    for provider in ('acoustid', 'discogs', 'musicbrainz', 'apple'):
        assert f"setProperty('providerKind', '{provider}')" in MAIN
    assert MAIN.count("setObjectName('ProviderStatusBadge')") >= 4
    assert 'Skonfigurowano' in MAIN
    assert 'Brak klucza' in MAIN
    assert 'Nie wymaga klucza API' in MAIN
    assert "setEchoMode(QLineEdit.EchoMode.Password)" in MAIN


def test_render_script_exports_start_and_integrations_views():
    render = (ROOT / 'scripts/render_ui_reference.py').read_text(encoding='utf-8')
    assert "save(str(out / 'start.png'))" in render
    assert "save(str(out / 'integrations.png'))" in render
