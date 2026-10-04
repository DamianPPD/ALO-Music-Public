from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.icons import alo_icon
from audio_library_organizer.ui.theme import style_for_theme


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
    assert "__version__ = '0.4.25-dev'" in (ROOT / 'src/audio_library_organizer/__init__.py').read_text(encoding='utf-8')
    assert 'version = "0.4.24"' in (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'v0.4.24' in (ROOT / 'START_HERE.txt').read_text(encoding='utf-8')


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
        # Only these approved replacements/controls use the new outline weight.
        approved_outline = {'export', 'recognize', 'control_more', 'control_close'}
        stroke = ('1.7' if path.stem in approved_outline else
                  '1.8' if path.stem.startswith('nav_') or path.stem == 'start_source_add' else '1.15')
        assert f'stroke-width="{stroke}"' in svg, path.name


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
        source = path.read_text(encoding='utf-8')
        if path.name == 'metadata_editor.py':
            # Explicitly approved status text, not a replacement for an icon.
            source = source.replace("'✓ Aktualnie wybrane'", "''")
        found = sorted(forbidden.intersection(source))
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
        assert not hasattr(card, 'copy_button')
        assert card.path_label.toolTip() == str(card.path)


def test_start_path_remains_selectable_without_copy_action(tmp_path):
    _app()
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    card = page.location_cards['reports']
    assert not hasattr(card, 'copy_button')
    assert card.path_label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse


def test_start_open_folder_uses_the_real_configured_location(tmp_path, monkeypatch):
    _app()
    paths = LibraryPaths(tmp_path / 'library'); paths.ensure_created()
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url) or True)
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    page.location_cards['review'].open_button.click()
    assert len(opened) == 1
    assert Path(opened[0].toLocalFile()) == paths.review


def test_start_marks_nonexistent_location_neutral_and_disables_open(tmp_path, monkeypatch):
    app = _app()
    paths = LibraryPaths(tmp_path / 'not-created')
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    page.setStyleSheet(style_for_theme('dark'))
    page.resize(1280, 1000)
    page.show()
    app.processEvents()
    card = page.location_cards['reports']
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toLocalFile()) or True)
    try:
        button = card.open_button
        assert not button.isEnabled()
        assert button.property('available') is False
        assert button.toolTip() == 'Niedostępna'
        assert button.accessibleDescription() == 'Niedostępna'
        edge = button.grab().toImage().pixelColor(1, button.height() // 2)
        assert edge.green() <= edge.red() + 40
        button.click()
        assert opened == []

        paths.reports.mkdir(parents=True)
        page.refresh_locations()
        app.processEvents()
        assert button.isEnabled() and button.property('available') is True
        assert button.accessibleDescription() == 'Dostępna'
        edge = button.grab().toImage().pixelColor(1, button.height() // 2)
        assert edge.green() > edge.red() + 40 and edge.green() > edge.blue()
        button.click()
        assert opened == [str(paths.reports)]
    finally:
        page.close()


def test_start_reflows_quick_access_for_wide_and_narrow_windows(tmp_path):
    app = _app()
    paths = LibraryPaths(tmp_path / 'library'); paths.ensure_created()
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    page.setStyleSheet(style_for_theme('dark'))
    page.show()
    try:
        for width in (1740, 950):
            page.resize(width, 1400)
            app.processEvents()
            structure, right = page.structure_panel, page.right_column
            if width == 1740:
                assert structure.geometry().right() < right.geometry().left()
            else:
                assert page.width() < 1050
                assert structure.geometry().bottom() < right.geometry().top()
            assert not structure.geometry().intersects(right.geometry())
            assert page.library_panels_host.contentsRect().contains(structure.geometry())
            assert page.library_panels_host.contentsRect().contains(right.geometry())
            assert page.sources_panel.geometry().bottom() < page.status_panel.geometry().top()
            assert page.scroll.horizontalScrollBar().maximum() == 0
            rows = list(page.location_cards.values())
            assert all(first.geometry().bottom() < second.geometry().top()
                       for first, second in zip(rows, rows[1:]))
    finally:
        page.close()


def test_add_tracks_copy_and_cancel_hierarchy_are_explicit(current_start_window):
    window = current_start_window
    add = window.dashboard.sources.add_button
    assert add.text() == 'Dodaj źródło' and not add.icon().isNull()
    assert window.dashboard.sources_panel.isAncestorOf(add)
    assert not window.action_frame.isAncestorOf(add)
    for kind, button, caption in (
        ('scan', window.scan_btn, 'Anuluj skanowanie'),
        ('online', window.identify_btn, 'Anuluj rozpoznawanie'),
    ):
        idle_icon = button.icon().pixmap(23, 23).toImage()
        window._set_busy(True, kind=kind)
        assert button.isEnabled() and button.text() == caption
        assert not add.isEnabled()
        assert '#e45f68' in button.styleSheet()
        assert button.icon().pixmap(23, 23).toImage() != idle_icon
        window._set_busy(False, kind=kind)
        assert add.isEnabled()
        assert button.text().startswith('1. ' if kind == 'scan' else '2. ')
        assert button.icon().pixmap(23, 23).toImage() == idle_icon


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
