import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.preferences import AppPreferences
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def _window(tmp_path, monkeypatch):
    _app()
    from audio_library_organizer.ui import main_window
    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    AppPreferences(language='pl').save(store)
    return MainWindow(AppSettings((), paths), store)


def test_studio_hero_uses_bundled_reference_and_refreshes_pl_en(tmp_path):
    _app()
    page = DashboardPage(AppSettings((), LibraryPaths(tmp_path / 'library')))
    try:
        assert asset_path('start_studio.png').is_file()
        assert page.hero.artwork_path == asset_path('start_studio.png')
        assert page.hero.minimumHeight() == 200
        assert page.hero_title.text() == 'Twoja kolekcja. Pełna kontrola.'
        apply_static_language(page, 'en')
        page.refresh_language()
        assert page.hero_title.text() == 'Your collection. Full control.'
        assert page.hero_description.text() == 'Organize • complete • analyze'
        apply_static_language(page, 'pl')
        page.refresh_language()
        assert page.hero_title.text() == 'Twoja kolekcja. Pełna kontrola.'
    finally:
        page.close()


def test_studio_sections_use_dashboard_proportions_without_empty_spacer(tmp_path):
    _app()
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    page = DashboardPage(AppSettings((), paths))
    try:
        page.resize(1500, 900)
        page.show()
        _app().processEvents()
        assert page.hero.height() == 200
        assert all(card.height() >= 90 for card in page.cards.values())
        assert all(card.height() >= 82 for card in page.location_cards.values())
        metric = page.stats_values['covers'].parentWidget()
        assert metric.height() >= 58
        assert page.location_cards['root'].geometry().top() < page.location_cards['not_selected'].geometry().top()
        assert page.stats_values['covers'].parentWidget().geometry().top() == page.stats_values['size'].parentWidget().geometry().top()
        page.set_summary({'total': 10, 'review': 2})
        page.set_health({'available': 10, 'missing_covers': 3})
        _app().processEvents()
        assert page.attention_frame.isVisible()
        # The page may scroll, but the final section follows its content
        # without an empty stretch above the player.
        assert page.scroll.widget().layout().itemAt(page.scroll.widget().layout().count() - 1).spacerItem() is None
        assert page.scroll.widget().height() - page.attention_frame.geometry().bottom() < 25
    finally:
        page.close()


def test_start_has_all_locations_and_six_graphical_statistics_without_copy(tmp_path):
    _app()
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    page = DashboardPage(AppSettings((), paths))
    try:
        assert set(page.cards) == {'total', 'review', 'duplicate', 'missing_covers'}
        assert set(page.location_cards) == {'root', 'ready', 'review', 'not_selected', 'custom_folders', 'reports'}
        assert all(card.open_button.text() == 'Otwórz folder' for card in page.location_cards.values())
        assert not any(hasattr(card, 'copy_button') for card in page.location_cards.values())
        assert set(page.stats_values) == {'covers', 'online', 'suspicious', 'size', 'missing', 'free_space'}
        page.set_summary({'total': 10, 'review': 2, 'duplicate': 1})
        page.set_health({'available': 10, 'missing_covers': 3, 'online_checked': 4})
        assert page.stats_values['covers'].text() == '7 / 10 (70%)'
        assert page.attention_frame.isVisibleTo(page) is False or '2 do sprawdzenia' in page.attention_text.text()
    finally:
        page.close()


def test_operation_is_inside_workflow_and_updates_idle_active_progress(tmp_path, monkeypatch):
    original_style = _app().styleSheet()
    window = _window(tmp_path, monkeypatch)
    try:
        window.show()
        _app().processEvents()
        assert window.operation_frame.parentWidget() is window.action_frame
        assert window.operation_frame.layout().count() > 0
        assert window.operation_frame.geometry().right() > window.new_files_btn.geometry().right()
        assert window.operation_title.text() == 'GOTOWY'
        assert window.operation_status.text() == 'Wybierz etap pracy'
        window._set_operation_state('online', 'ROZPOZNAWANIE ONLINE', '127 / 419 · 30%')
        window.progress.setRange(0, 419)
        window.progress.setValue(127)
        window.progress.show()
        assert window.operation_frame.property('operationKind') == 'online'
        assert window.progress.value() == 127
        assert window.operation_status.text() == '127 / 419 · 30%'
    finally:
        window.close()
        _app().setStyleSheet(original_style)


def test_navigation_retains_six_actions_and_single_green_checked_state(tmp_path, monkeypatch):
    original_style = _app().styleSheet()
    window = _window(tmp_path, monkeypatch)
    try:
        assert len(window.nav_buttons) == 6
        assert all(button.iconSize().width() >= 19 for button in window.nav_buttons)
        assert [button.isChecked() for button in window.nav_buttons] == [True, False, False, False, False, False]
        assert window.nav_buttons[0]._icon_color.name() == '#4cde96'
        window._navigate(2)
        assert [button.isChecked() for button in window.nav_buttons] == [False, False, True, False, False, False]
        assert window.nav_buttons[2]._icon_color.name() == '#4cde96'
        window._apply_preferences(AppPreferences(language='en'))
        assert window.nav_buttons[2].text().startswith('Duplicates')
        window._navigate(0)
        assert window.stack.currentWidget() is window.dashboard
        assert window.dashboard.hero in window.dashboard.findChildren(type(window.dashboard.hero))
    finally:
        window.close()
        _app().setStyleSheet(original_style)
