import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.icons import alo_icon, start_icon
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.theme import style_for_theme


@pytest.fixture
def page(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    paths = LibraryPaths(tmp_path / 'ALO Music - Biblioteka')
    paths.ensure_created()
    dashboard = DashboardPage(AppSettings((), paths))
    dashboard.resize(1800, 1050)
    dashboard.show()
    app.processEvents()
    yield dashboard
    dashboard.close()
    app.setStyleSheet(previous)


def test_two_panels_replace_old_sections_and_show_six_real_full_paths(page):
    texts = [label.text() for label in page.findChildren(QLabel)]
    assert texts.count('Struktura biblioteki') == texts.count('Stan biblioteki') == 1
    assert texts.count('Wymaga uwagi') == 1
    assert 'Szybki dostęp' not in texts and 'Statystyki biblioteki' not in texts
    assert not any('Wariant 3' in text for text in texts)
    assert len(page.location_cards) == 6 and len(page.metric_cards) == 6
    assert .61 <= page.structure_panel.width() / page.library_panels_host.width() <= .65
    assert .35 <= page.status_panel.width() / page.library_panels_host.width() <= .39
    assert page.structure_panel.geometry().right() < page.status_panel.geometry().left()
    assert page.structure_panel.y() == page.status_panel.y()
    assert page.attention_frame.parentWidget() is page.status_panel
    rows = list(page.location_cards.values())
    assert texts.count('Biblioteka główna') == 1
    assert not hasattr(page, 'library_label') and not hasattr(page, 'open_folder_button')
    assert rows[0].x() < rows[1].x()
    assert rows[0].height() > rows[1].height()
    assert len({row.x() for row in rows[1:]}) == 1
    assert all(first.geometry().bottom() < second.y() for first, second in zip(rows, rows[1:]))
    for key, title, path, icon, accent in page._location_specs(AppSettings((), LibraryPaths(page._library_root))):
        row = page.location_cards[key]
        document = QTextDocument()
        document.setHtml(row.path_label.text())
        assert document.toPlainText() == str(path)
        assert row.path == path and row.path_label.toolTip() == str(path)
        assert row.property('accentColor') == accent


def test_location_actions_availability_and_library_switch_use_real_paths(page, tmp_path, monkeypatch):
    visited = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: visited.append(url.toLocalFile()) or True)
    for row in page.location_cards.values():
        assert row.open_button.property('available') is True
        edge = row.open_button.grab().toImage().pixelColor(1, row.open_button.height() // 2)
        assert edge.green() > edge.red() + 40 and edge.green() > edge.blue()
        assert not row.findChildren(QLabel, 'QuickAccessAvailability')
        assert not row.findChildren(QLabel, 'LibraryLocationStatusDot')
        assert row.open_button.text() == 'Otwórz folder'
        assert row.open_button.icon().isNull()
        assert row.open_button.findChild(QLabel, 'StartFolderChevron') is not None
        row.open_button.click()
    assert visited == [str(row.path) for row in page.location_cards.values()]
    ready = page.location_cards['ready']
    ready.path.rmdir()
    ready.set_path(ready.path)
    assert ready.open_button.property('available') is False
    assert not ready.open_button.isEnabled()
    edge = ready.open_button.grab().toImage().pixelColor(1, ready.open_button.height() // 2)
    assert edge.green() <= edge.red() + 40
    ready.open_button.click()
    assert len(visited) == 6
    changed = LibraryPaths(tmp_path / 'Druga biblioteka')
    changed.ensure_created()
    page.set_library(AppSettings((), changed))
    assert page.location_cards['root'].path == changed.root
    assert ready.path == changed.ready and ready.open_button.isEnabled()
    assert ready.open_button.property('available') is True
    page.set_library_name('Druga biblioteka')
    assert page.location_cards['root'].title_label.text() == 'Biblioteka główna'


def test_status_values_progress_and_attention_remain_dynamic(page, monkeypatch):
    monkeypatch.setattr('audio_library_organizer.ui.dashboard_page.shutil.disk_usage',
                        lambda path: SimpleNamespace(free=35 * 1024**3))
    page.set_summary({'total': 20, 'review': 3, 'duplicate': 2})
    page.set_health({'available': 20, 'missing_covers': 5, 'online_checked': 8,
                     'missing': 2, 'suspicious': 4, 'size_bytes': 2 * 1024**3})
    assert page.stats_values['covers'].text() == '15 / 20 (75%)'
    assert page.stats_values['online'].text() == '8 / 20 (40%)'
    assert page.stats_progress['covers'].value() == 75
    assert page.stats_progress['online'].value() == 40
    assert page.stats_values['size'].text() == '2.00 GB'
    assert page.stats_values['missing'].text() == '2'
    assert page.stats_values['suspicious'].text() == '4'
    assert page.stats_values['free_space'].text() == '35.0 GB'
    assert '3 do sprawdzenia' in page.attention_text.text()
    assert '5 bez okładki' in page.attention_text.text()
    assert page.attention_frame.isVisible()
    page.set_summary({'total': 2})
    page.set_health({'available': 2, 'online_checked': 1})
    assert page.stats_values['covers'].text() == '2 / 2 (100%)'
    assert page.stats_values['online'].text() == '1 / 2 (50%)'
    assert not page.attention_frame.isVisible()
    pl = ('Utwory z okładką', 'Utwory rozpoznane online', 'Rozmiar biblioteki',
          'Brakujące pliki', 'Metadane do sprawdzenia', 'Wolne miejsce na dysku')
    en = ('Tracks with cover art', 'Tracks identified online', 'Library size',
          'Missing files', 'Metadata to review', 'Free disk space')
    assert [page.metric_cards[key].findChild(QLabel, 'StartMetricHeading').text()
            for key in page.metric_cards] == list(pl)
    apply_static_language(page, 'en')
    page.refresh_language()
    assert [page.metric_cards[key].findChild(QLabel, 'StartMetricHeading').text()
            for key in page.metric_cards] == list(en)
    apply_static_language(page, 'pl')
    page.refresh_language()
    assert [page.metric_cards[key].findChild(QLabel, 'StartMetricHeading').text()
            for key in page.metric_cards] == list(pl)


def test_folder_icons_follow_accents_headers_reuse_two_lines_and_tree_starts_under_root(page):
    assert len({row.property('accentColor') for row in page.location_cards.values()}) == 6
    for key, title, path, icon_name, accent in page._location_specs(AppSettings((), LibraryPaths(page._library_root))):
        row = page.location_cards[key]
        assert row.title_icon.pixmap().toImage() == start_icon(icon_name, accent, 20).pixmap(20, 20).toImage()
        assert row.title_icon.width() == 24
        assert row.open_button.findChild(QLabel, 'StartFolderChevron').pixmap().toImage() == alo_icon('chevron-right', '#628fb0', 12).pixmap(12, 12).toImage()
    assert [spec[3] for spec in page._location_specs(AppSettings((), LibraryPaths(page._library_root)))] == [
        'folder_root', 'folder_check', 'folder_warning', 'folder_x', 'folder_selected', 'folder_report']
    for panel in (page.structure_panel, page.status_panel):
        mark = panel.findChild(QLabel, 'LibrarySectionMark')
        assert mark is not None and mark.size().width() == 20 and mark.height() == 7
        assert mark.pixmap().isNull()
        image = mark.grab().toImage()
        assert image.pixelColor(10, 0).blue() > image.pixelColor(10, 3).blue()
        assert image.pixelColor(10, 6).blue() > image.pixelColor(10, 3).blue()
    for box in page.metric_cards.values():
        icon = box.findChild(QLabel, 'StartMetricIcon')
        assert icon.pixmap().width() == 20 and icon.width() == 26
    QApplication.instance().processEvents()
    image = page.quick_access_host.grab().toImage()
    rows = list(page.location_cards.values())
    root = rows[0]
    assert root.grab().toImage().pixelColor(3, root.height() // 2).blue() > 210
    assert rows[1].grab().toImage().pixelColor(3, rows[1].height() // 2).blue() < 80
    assert image.pixelColor(8, root.geometry().center().y()).blue() < 80
    assert image.pixelColor(8, root.geometry().bottom() + 2).blue() > 60
    for row in rows[1:]:
        assert image.pixelColor(8, row.geometry().center().y()).blue() > 80


@pytest.mark.parametrize('scale', ['1', '1.25'])
def test_start_panels_fit_window_and_remain_above_player_at_basic_dpi(tmp_path, scale):
    code = '''
import sys
from pathlib import Path
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtWidgets import QApplication, QLabel
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui import main_window
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.i18n import apply_static_language
app = QApplication([])
main_window.DashboardPage = DashboardPage
paths = LibraryPaths(Path(sys.argv[1]) / 'library')
paths.ensure_created()
window = main_window.MainWindow(AppSettings((), paths), QSettings(str(Path(sys.argv[1]) / 'prefs.ini'), QSettings.Format.IniFormat))
try:
    window.dashboard.set_summary({'total': 419, 'review': 201})
    window.dashboard.set_health({'available': 419, 'missing_covers': 314, 'online_checked': 80})
    for language in ('pl', 'en'):
        apply_static_language(window.dashboard, language)
        window.dashboard.refresh_language()
        for width in (1740, 1500):
            window.resize(width, 1000)
            window.show()
            app.processEvents()
            page = window.dashboard
            assert page.scroll.horizontalScrollBar().maximum() == 0
            assert page.library_panels_host.geometry().right() < page.scroll.widget().width()
            scroll_bottom = page.scroll.mapTo(window, page.scroll.rect().bottomLeft()).y()
            player_top = window.player.mapTo(window, QPoint()).y()
            assert scroll_bottom < player_top
            assert page.hero.height() == 200
            assert all(card.height() == 92 for card in page.cards.values())
            selected = page.location_cards['custom_folders'].title_label
            assert selected.fontMetrics().horizontalAdvance(selected.text()) <= selected.width()
            for row in page.location_cards.values():
                button = row.open_button
                assert row.contentsRect().contains(button.geometry())
                assert button.width() >= button.fontMetrics().horizontalAdvance(button.text()) + 25
                assert button.rect().contains(button.findChild(QLabel, 'StartFolderChevron').geometry())
            for card in page.metric_cards.values():
                heading = card.findChild(QLabel, 'StartMetricHeading')
                assert card.contentsRect().contains(heading.geometry())
                assert heading.height() >= heading.heightForWidth(heading.width())
finally:
    window.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                            env=dict(os.environ, QT_SCALE_FACTOR=scale), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
