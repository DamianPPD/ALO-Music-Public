import os
from pathlib import Path
from xml.etree import ElementTree

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer import __version__
from audio_library_organizer.domain.preferences import AppPreferences
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui import main_window
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.dashboard_page import DashboardPage


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    host = main_window.MainWindow(AppSettings((), paths),
                                 QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    host.resize(1740, 1050)
    host.show()
    app.processEvents()
    yield host
    host.close()
    app.setStyleSheet(previous)


def _green_edge(button):
    image = button.grab().toImage()
    scale = image.devicePixelRatio()
    color = image.pixelColor(round(scale), round(button.height() / 2 * scale))
    return color.green() > color.red() + 40 and color.green() > color.blue()


def test_real_availability_refreshes_with_data_navigation_and_open_action(window, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toLocalFile()) or True)
    ready = window.dashboard.location_cards['ready']
    assert ready.open_button.isEnabled() and _green_edge(ready.open_button)
    moved = ready.path.with_name('GOTOWE-renamed')
    ready.path.rename(moved)
    window.refresh_data()
    assert not ready.open_button.isEnabled()
    assert ready.open_button.property('available') is False
    assert not _green_edge(ready.open_button)
    ready.open_button.click()
    assert not opened
    moved.rename(ready.path)
    window._navigate(1)
    window._navigate(0)
    QApplication.instance().processEvents()
    assert ready.open_button.isEnabled()
    assert ready.open_button.property('available') is True
    assert _green_edge(ready.open_button)
    ready.open_button.click()
    assert opened == [str(ready.path)]
    review = window.dashboard.location_cards['review']
    review.path.rmdir()
    review.open_button.click()
    assert not review.open_button.isEnabled()
    assert not _green_edge(review.open_button)
    assert opened == [str(ready.path)]


def test_status_cards_use_larger_type_icons_padding_and_progress_without_extra_data(window):
    page = window.dashboard
    page.set_summary({'total': 20, 'review': 3})
    page.set_health({'available': 20, 'missing_covers': 5, 'online_checked': 8,
                     'missing': 2, 'suspicious': 4, 'size_bytes': 2 * 1024**3})
    assert len(page.metric_cards) == 6 and set(page.stats_progress) == {'covers', 'online'}
    assert page.stats_values['covers'].text() == '15 / 20 (75%)'
    assert page.stats_values['online'].text() == '8 / 20 (40%)'
    assert page.stats_values['missing'].text() == '2'
    assert page.stats_values['suspicious'].text() == '4'
    for key, card in page.metric_cards.items():
        assert card.height() >= (80 if key in {'covers', 'online'} else 100)
        assert card.layout().contentsMargins().top() >= 12
        assert card.findChild(QLabel, 'StartMetricHeading').font().pointSizeF() >= 10
        assert page.stats_values[key].font().pointSizeF() >= 14
        assert card.findChild(QLabel, 'StartMetricIcon').pixmap().width() == 20
    assert all(bar.height() >= 9 for bar in page.stats_progress.values())
    assert page.attention_frame.minimumHeight() >= 80


def test_selected_track_folder_name_is_consistent_in_pl_en_and_runtime_version_is_dev(window):
    for language, name in (('pl', 'Foldery z zaznaczonych utworów'),
                           ('en', 'Folders from selected tracks')):
        window._apply_preferences(AppPreferences(language=language))
        QApplication.instance().processEvents()
        assert window.nav_buttons[3].text() == name
        assert window.dashboard.location_cards['custom_folders'].title_label.text() == name
        assert name in [label.text() for label in window.collections.findChildren(QLabel)]
        assert window.findChild(QLabel, 'BrandVersion').text() == 'v0.4.25-dev • 2026'
        assert window.dashboard.location_cards['custom_folders'].path.name == 'MOJE_FOLDERY_MP3'
        titles = [label.text() for label in window.dashboard.findChildren(QLabel)]
        assert 'Moje pliki MP3' not in titles and 'My MP3 files' not in titles
    assert __version__ == '0.4.25-dev'


def test_detailed_folder_artwork_and_steel_color_keep_other_semantics(window):
    page = window.dashboard
    navigation_folder = ElementTree.parse(asset_path('icons/start_c/folder.svg')).getroot()
    assert navigation_folder.attrib['stroke-width'] == '2.2'
    assert len(navigation_folder) == 1
    row = page.location_cards['custom_folders']
    assert row.property('accentColor') == '#8d9ba6'
    assert page.cards['duplicate']._accent == '#b987ff'
    assert page.location_cards['reports'].property('accentColor') == '#50c9da'
    assert '#8d9ba6' in row.path_label.text()
    document = QTextDocument()
    document.setHtml(row.path_label.text())
    assert document.toPlainText() == str(row.path)
    image = page.quick_access_host.grab().toImage()
    node = image.pixelColor(8, row.geometry().center().y())
    connector = image.pixelColor(18, row.geometry().center().y())
    assert abs(node.red() - node.blue()) < 40
    assert abs(connector.red() - connector.blue()) < 40
    for name in ('folder_root', 'folder_check', 'folder_warning', 'folder_x', 'folder_selected', 'folder_report'):
        svg = ElementTree.parse(asset_path('icons/start_c/' + name + '.svg')).getroot()
        assert svg.attrib['viewBox'] == '0 0 24 24'
        assert svg.attrib['fill'] == 'none'
        assert len(svg) >= 3
        assert 'filter' not in ElementTree.tostring(svg).decode()
