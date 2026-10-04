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
from audio_library_organizer.ui.icons import start_icon
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
    assert .63 <= page.structure_panel.width() / page.library_panels_host.width() <= .69
    assert page.structure_panel.geometry().right() < page.status_panel.geometry().left()
    assert page.structure_panel.y() == page.status_panel.y()
    assert page.attention_frame.parentWidget() is page.status_panel
    rows = list(page.location_cards.values())
    assert len({row.x() for row in rows}) == 1
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
        assert row.availability.text() == 'Dostępna'
        assert row.availability.property('available') is True
        assert row.availability_dot.property('available') is True
        row.open_button.click()
    assert visited == [str(row.path) for row in page.location_cards.values()]
    ready = page.location_cards['ready']
    ready.path.rmdir()
    ready.set_path(ready.path)
    assert ready.availability.text() == 'Niedostępna'
    assert ready.availability_dot.property('available') is False
    assert not ready.open_button.isEnabled()
    ready.open_button.click()
    assert len(visited) == 6
    changed = LibraryPaths(tmp_path / 'Druga biblioteka')
    changed.ensure_created()
    page.set_library(AppSettings((), changed))
    assert page.location_cards['root'].path == changed.root
    assert ready.path == changed.ready and ready.open_button.isEnabled()


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


def test_small_icons_share_one_color_and_location_accents_stay_distinct(page):
    assert len({row.property('accentColor') for row in page.location_cards.values()}) == 6
    for key, title, path, icon_name, accent in page._location_specs(AppSettings((), LibraryPaths(page._library_root))):
        row = page.location_cards[key]
        assert row.title_icon.pixmap().toImage() == start_icon(icon_name, '#628fb0', 20).pixmap(20, 20).toImage()
        assert row.title_icon.width() == 24
        assert row.open_button.icon().pixmap(15, 15).toImage() == start_icon('folder_open', '#628fb0', 15).pixmap(15, 15).toImage()
    for box in page.metric_cards.values():
        icon = box.findChild(QLabel, 'StartMetricIcon')
        assert icon.pixmap().width() == 18 and icon.width() == 22
    QApplication.instance().processEvents()
    image = page.quick_access_host.grab().toImage()
    first = next(iter(page.location_cards.values()))
    assert image.pixelColor(8, first.geometry().center().y()).blue() > 80


@pytest.mark.parametrize('scale', ['1', '1.25'])
def test_start_panels_fit_window_and_remain_above_player_at_basic_dpi(tmp_path, scale):
    code = '''
import sys
from pathlib import Path
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtWidgets import QApplication
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui import main_window
from audio_library_organizer.ui.dashboard_page import DashboardPage
app = QApplication([])
main_window.DashboardPage = DashboardPage
paths = LibraryPaths(Path(sys.argv[1]) / 'library')
paths.ensure_created()
window = main_window.MainWindow(AppSettings((), paths), QSettings(str(Path(sys.argv[1]) / 'prefs.ini'), QSettings.Format.IniFormat))
try:
    window.dashboard.set_summary({'total': 419, 'review': 201})
    window.dashboard.set_health({'available': 419, 'missing_covers': 314, 'online_checked': 80})
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
        for row in page.location_cards.values():
            assert row.contentsRect().contains(row.open_button.geometry())
            assert row.open_button.width() >= row.open_button.fontMetrics().horizontalAdvance(row.open_button.text()) + 25
finally:
    window.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                            env=dict(os.environ, QT_SCALE_FACTOR=scale), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
