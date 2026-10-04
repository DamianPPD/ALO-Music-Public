import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QSettings, Qt, QEvent, QPoint
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QLabel, QFrame, QPushButton
from PySide6.QtTest import QTest
from shiboken6 import isValid

from audio_library_organizer.domain.preferences import AppPreferences
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.storage.library_profiles import LibraryRegistry
from audio_library_organizer.ui import main_window
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.icons import alo_icon


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    paths = LibraryPaths(tmp_path / 'library'); paths.ensure_created()
    host = main_window.MainWindow(AppSettings((), paths),
                                 QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    host.resize(1740, 1100); host.show(); app.processEvents()
    yield host
    host.close(); app.setStyleSheet(previous)


def test_scan_history_keeps_source_runs_and_latest_summary_in_existing_store(tmp_path):
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat)
    settings = AppSettings((), LibraryPaths(tmp_path / 'out'))
    registry = LibraryRegistry(settings)
    source = tmp_path / 'source'; source.mkdir()
    registry.record_scan('main', source, 12, scanned_at='2026-09-29T22:15:00')
    registry.record_scan('main', source, 17, scanned_at='2026-09-29T23:15:00')
    registry.save(store)
    restored = LibraryRegistry.from_store(store, settings)
    assert hasattr(restored, 'scan_history_for_source')
    assert [e.file_count for e in restored.scan_history_for_source(source)] == [17, 12]
    assert len(restored.scan_history()) == 1
    assert restored.scan_history()[0].file_count == 17


def test_remove_source_history_is_persistent_and_leaves_music_bindings_and_other_libraries(tmp_path):
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat)
    source = tmp_path / 'source'; source.mkdir()
    music = source / 'music.mp3'; music.write_bytes(b'unchanged music')
    settings = AppSettings((source,), LibraryPaths(tmp_path / 'out'))
    registry = LibraryRegistry(settings)
    registry.add_library('Other', (), tmp_path / 'other', profile_id='other')
    registry.record_scan('main', source, 1); registry.record_scan('main', source, 2)
    registry.record_scan('other', source, 3)
    assert hasattr(registry, 'remove_source_history')
    assert registry.remove_source_history(source) == 2
    registry.save(store)
    restored = LibraryRegistry.from_store(store, settings)
    assert restored.scan_history() == ()
    assert restored.scan_history('other')[0].file_count == 3
    assert restored.active.source_dirs == (source.resolve(),)
    assert music.read_bytes() == b'unchanged music'


def test_ready_organization_tracks_settings_in_pl_en_without_controls(window):
    ready = window.dashboard.location_cards['ready']
    assert hasattr(ready, 'detail_label')
    for lang, names in (('pl', ('Bez podfolderów', 'Według wykonawcy', 'Według gatunku')),
                        ('en', ('No subfolders', 'By artist', 'By genre'))):
        for mode, text in zip(('none', 'artist', 'genre'), names):
            window.qt_settings.setValue('ui/folder_organization', mode)
            window._apply_preferences(AppPreferences(language=lang))
            window.refresh_data()
            assert ready.detail_label.text() == '(' + text + ')'
            assert ready.detail_label.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction
            assert ready.detail_label.font().pointSizeF() < ready.title_label.font().pointSizeF()
            assert ready.findChildren(QPushButton) == [ready.open_button]


def test_sources_table_uses_saved_data_compact_rows_real_dots_and_internal_scroll(window, tmp_path):
    page = window.dashboard
    assert hasattr(page, 'sources')
    for index in range(16):
        path = tmp_path / f'source-{index}'
        if index != 0: path.mkdir()
        window.library_registry.record_scan('main', path, 100 + index,
                                            scanned_at=f'2026-09-29T23:{index:02}:00')
    window.refresh_data(); QApplication.instance().processEvents()
    table = page.sources.table
    assert [table.horizontalHeaderItem(i).text() for i in range(5)] == [
        'Folder źródłowy', 'Ostatni skan', 'Pliki', 'Status', 'Akcja']
    assert table.columnCount() == 5 and table.rowCount() == 16
    assert table.item(0, 0).text() == str((tmp_path / 'source-15').resolve())
    assert table.item(0, 1).text() == '29.09.2026 23:15'
    assert table.item(0, 2).text() == '115'
    assert table.cellWidget(0, 3).findChild(QLabel, 'ScanSourceStatusDot').property('available') is True
    assert table.cellWidget(15, 3).findChild(QLabel, 'ScanSourceStatusDot').property('available') is False
    assert all(table.rowHeight(i) <= 28 for i in range(16))
    assert table.verticalScrollBar().maximum() > 0
    assert page.sources_panel.height() > page.status_panel.height()
    assert page.sources_panel.y() < page.status_panel.y()
    before = page.library_panels_host.height()
    previous_status = table.cellWidget(15, 3)
    window.library_registry.record_scan('main', tmp_path / 'source-17', 2)
    window.refresh_data(); QApplication.instance().processEvents()
    assert not isValid(previous_status) or not previous_status.isVisible()
    assert page.library_panels_host.height() == before
    moved = tmp_path / 'renamed'; (tmp_path / 'source-15').rename(moved)
    window._navigate(1); window._navigate(0); QApplication.instance().processEvents()
    dot = table.cellWidget(1, 3).findChild(QLabel, 'ScanSourceStatusDot')
    assert dot.text() == '' and dot.property('available') is False


def test_source_menu_opens_copies_shows_scoped_history_and_only_removes_records(window, tmp_path, monkeypatch):
    assert hasattr(window.dashboard, 'sources')
    path = tmp_path / 'source'; path.mkdir()
    music = path / 'music.mp3'; music.write_bytes(b'music')
    registry = window.library_registry
    registry.record_scan('main', path, 1, scanned_at='2026-09-29T22:15:00')
    registry.record_scan('main', path, 2, scanned_at='2026-09-29T23:15:00')
    window.refresh_data()
    sources = window.dashboard.sources
    control = sources.table.cellWidget(0, 4)
    assert control.text() == '' and not control.icon().isNull()
    assert control.accessibleName() == 'Akcja'
    assert control.icon().pixmap(14, 14).toImage() == alo_icon('control_more', '#91a7b4', 14).pixmap(14, 14).toImage()
    assert sources.table.cellWidget(0, 4).menu().isWindow()
    menu = sources.menu_for_source(path)
    actions = menu.actions()
    assert [a.text() for a in actions] == ['Otwórz folder', 'Kopiuj ścieżkę', 'Pokaż historię skanów', 'Usuń z historii']
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toLocalFile()) or True)
    actions[0].trigger(); assert opened == [str(path)]
    actions[1].trigger(); assert QApplication.clipboard().text() == str(path)
    actions[2].trigger()
    history = sources.history_dialog.findChild(type(sources.table))
    assert history.rowCount() == 2
    assert [history.item(i, 1).text() for i in range(2)] == ['2', '1']
    sources.history_dialog.close()
    path.rename(tmp_path / 'renamed')
    unavailable = sources.menu_for_source(path)
    assert not unavailable.actions()[0].isEnabled()
    unavailable.actions()[3].trigger()
    assert registry.scan_history() == () and sources.table.rowCount() == 0
    assert (tmp_path / 'renamed' / 'music.mp3').read_bytes() == b'music'
    assert LibraryRegistry.from_store(window.qt_settings, window.main_settings).scan_history() == ()


def test_add_source_reuses_existing_folder_workflow_and_busy_state(window, tmp_path, monkeypatch):
    assert hasattr(window.dashboard, 'sources')
    button = window.new_files_btn
    assert window.dashboard.sources.add_button is button
    assert not window.action_frame.isAncestorOf(button)
    assert button.text() == 'Dodaj źródło'
    calls = []
    path = tmp_path / 'incoming'; path.mkdir()
    dialogs = []
    def choose_folder(*args, **kwargs):
        dialogs.append((args, kwargs))
        return str(path)
    monkeypatch.setattr(main_window.QFileDialog, 'getExistingDirectory', choose_folder)
    monkeypatch.setattr(window, 'start_scan', lambda **kwargs: calls.append(kwargs))
    button.click()
    assert len(dialogs) == 1
    assert dialogs[0][0][0] is window
    assert dialogs[0][1]['options'] & main_window.QFileDialog.Option.DontUseNativeDialog
    assert calls == [{'source_dirs': (path.resolve(),), 'new_files': True}]
    assert window.app_settings.source_dirs == (path.resolve(),)
    window._set_busy(True, kind='online'); assert not button.isEnabled()
    window._set_busy(False); assert button.isEnabled() and button.text() == 'Dodaj źródło'


def test_attention_is_one_red_noninteractive_line_and_status_keeps_six_metrics(window):
    page = window.dashboard
    assert not hasattr(page, 'last_scan_label')
    assert hasattr(page, 'attention_line')
    page.set_summary({'total': 419, 'review': 201})
    page.set_health({'available': 419, 'missing_covers': 313, 'online_checked': 80})
    assert page.attention_text.text() == 'Wymaga uwagi: 201 utworów wymaga sprawdzenia metadanych • 313 utworów nie ma okładki'
    assert not isinstance(page.attention_line, QFrame)
    assert not page.status_panel.isAncestorOf(page.attention_text)
    assert page.attention_line.y() < page.library_panels_host.y()
    assert not page.attention_text.wordWrap()
    assert page.attention_text.palette().windowText().color().red() > 200
    assert not page.attention_line.findChildren(QPushButton)
    assert len(page.metric_cards) == 6 and len(page.stats_progress) == 2
    assert all(card.height() <= 44 for card in page.metric_cards.values())
    assert all(bar.height() <= 5 for bar in page.stats_progress.values())
    window._last_ui_summary = dict(page._summary)
    window._last_ui_health = dict(page._health)
    window._apply_preferences(AppPreferences(language='en'))
    assert page.attention_text.text() == 'Needs attention: 201 tracks require metadata review • 313 tracks have no cover art'
    assert [page.sources.table.horizontalHeaderItem(i).text() for i in range(5)] == [
        'Source folder', 'Last scan', 'Files', 'Status', 'Action']
    assert page.sources.add_button.text() == 'Add source'
    page.set_summary({}); page.set_health({})
    assert not page.attention_line.isVisible()


def test_status_dot_inherits_row_background_without_a_rectangle(window, tmp_path):
    path = tmp_path / 'source'; path.mkdir()
    window.library_registry.record_scan('main', path, 1)
    window.refresh_data(); QApplication.instance().processEvents()
    table = window.dashboard.sources.table
    cell = table.cellWidget(0, 3)
    picture = table.viewport().grab().toImage()
    corner = cell.pos()
    background = picture.pixelColor(corner.x() + 2, corner.y() + 2)
    row_background = picture.pixelColor(corner.x() - 3, corner.y() + 2)
    assert background == row_background
    dot = cell.findChild(QLabel, 'ScanSourceStatusDot')
    green = dot.grab().toImage().pixelColor(3, 3)
    assert green.green() > green.red() + 50
    path.rmdir(); window.refresh_data(); QApplication.instance().processEvents()
    cell = table.cellWidget(0, 3)
    dot = cell.findChild(QLabel, 'ScanSourceStatusDot')
    red = dot.grab().toImage().pixelColor(3, 3)
    assert red.red() > red.green() + 50
    assert not table.cellWidget(0, 4).menu().actions()[0].isEnabled()


def test_source_columns_fill_viewport_and_keep_full_scan_date(window, tmp_path):
    path = tmp_path / 'source'; path.mkdir()
    window.library_registry.record_scan('main', path, 100, scanned_at='2026-10-04T07:03:00')
    window.refresh_data(); QApplication.instance().processEvents()
    table = window.dashboard.sources.table
    for width in (1740, 1500):
        window.resize(width, 1100); QApplication.instance().processEvents()
        sizes = [table.columnWidth(i) for i in range(5)]
        assert abs(sum(sizes) - table.viewport().width()) <= 2
        assert sizes[0] == max(sizes)
        assert table.fontMetrics().horizontalAdvance(table.item(0, 1).text()) + 12 <= sizes[1]
        assert table.fontMetrics().horizontalAdvance(table.item(0, 2).text()) + 18 <= sizes[2]
        assert max(sizes[2:]) <= 60
        assert table.horizontalScrollBar().maximum() == 0


def test_source_clicks_leave_no_selection_or_focus_outline(window, tmp_path):
    path = tmp_path / 'source'; path.mkdir()
    window.library_registry.record_scan('main', path, 1)
    window.refresh_data(); app = QApplication.instance(); app.processEvents()
    table = window.dashboard.sources.table
    window.dashboard.scroll.ensureWidgetVisible(table); app.processEvents()
    point = table.visualItemRect(table.item(0, 0)).center()
    before = table.viewport().grab().toImage()
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert table.selectedIndexes() == []
    assert not table.hasFocus()
    app.sendEvent(table.viewport(), QEvent(QEvent.Type.Leave)); app.processEvents()
    after = table.viewport().grab().toImage()
    rect = table.visualItemRect(table.item(0, 0))
    assert before.copy(rect) == after.copy(rect)


def test_status_header_is_compact_and_ready_mode_is_cool_readable_text(window):
    page = window.dashboard
    assert page.status_panel.layout().contentsMargins().top() < page.sources_panel.layout().contentsMargins().top()
    status_text = page.status_panel.layout().itemAt(0).layout().itemAt(1).layout()
    assert status_text.spacing() < 3
    label = page.location_cards['ready'].detail_label
    color = label.palette().windowText().color()
    assert color.blue() > color.red() + 40
    assert color.green() > 165
    assert len(page.metric_cards) == 6 and len(page.stats_progress) == 2


def test_add_source_mouse_click_saves_source_scans_and_refreshes_table(window, tmp_path, monkeypatch):
    path = tmp_path / 'incoming'; path.mkdir()
    button = window.dashboard.sources.add_button
    app = QApplication.instance()
    window.dashboard.scroll.ensureWidgetVisible(button); app.processEvents()
    dialogs = []
    def choose_folder(*args, **kwargs):
        dialogs.append(args)
        return str(path)
    monkeypatch.setattr(main_window.QFileDialog, 'getExistingDirectory', choose_folder)
    def run_existing_scan(**kwargs):
        result = window.service.scan(source_dirs=kwargs['source_dirs'])
        window._scan_finished(result)
    monkeypatch.setattr(window, 'start_scan', run_existing_scan)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton); app.processEvents()
    assert len(dialogs) == 1
    assert window.library_registry.active.source_dirs == (path.resolve(),)
    restored = LibraryRegistry.from_store(window.qt_settings, window.main_settings)
    assert restored.scan_history()[0].source_dir == path.resolve()
    assert window.dashboard.sources.table.item(0, 0).text() == str(path.resolve())


def test_add_source_plus_and_hover_pressed_are_distinct(window):
    app = QApplication.instance(); button = window.dashboard.sources.add_button
    assert not button.icon().isNull() and button.iconSize().width() >= 16
    window.dashboard.scroll.ensureWidgetVisible(button); app.processEvents()
    QTest.mouseMove(window, QPoint(1, 1)); app.processEvents()
    normal = button.grab().toImage().pixelColor(6, 6)
    QTest.mouseMove(button, button.rect().center()); app.processEvents()
    hover = button.grab().toImage().pixelColor(6, 6)
    button.setDown(True)
    pressed = button.grab().toImage().pixelColor(6, 6)
    button.setDown(False)
    assert len({normal.name(), hover.name(), pressed.name()}) == 3


def test_scan_history_clicks_keep_data_visible_without_selection_or_focus(window, tmp_path):
    path = tmp_path / 'source'; path.mkdir()
    registry = window.library_registry
    registry.record_scan('main', path, 12, scanned_at='2026-10-04T07:03:00')
    registry.record_scan('main', path, 17, scanned_at='2026-10-04T07:13:00')
    window.refresh_data()
    sources = window.dashboard.sources
    sources.menu_for_source(path).actions()[2].trigger()
    app = QApplication.instance(); app.processEvents()
    dialog = sources.history_dialog
    assert dialog.isVisible()
    table = dialog.findChild(type(sources.table))
    assert table.columnCount() == 2 and table.rowCount() == 2
    assert [[table.item(row, column).text() for column in range(2)] for row in range(2)] == [
        ['04.10.2026 07:13', '17'], ['04.10.2026 07:03', '12']]
    QTest.mouseMove(dialog, QPoint(1, 1)); app.processEvents()
    rect = table.visualItemRect(table.item(0, 0))
    before = table.viewport().grab().toImage().copy(rect)
    for row, column in ((0, 0), (1, 1)):
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton,
                         pos=table.visualItemRect(table.item(row, column)).center())
        app.processEvents()
        assert table.selectedIndexes() == []
        assert not table.hasFocus()
    QTest.mouseMove(dialog, QPoint(1, 1)); app.processEvents()
    assert table.viewport().grab().toImage().copy(rect) == before
    assert dialog.isVisible()
    dialog.close(); app.processEvents()
