"""Release Qt windows between tests while retaining the shared QApplication."""

import gc
import sys

import pytest


@pytest.fixture
def current_start_window(tmp_path, monkeypatch):
    """Real current Start UI with isolated preferences and library storage."""
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.domain.preferences import AppPreferences
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage

    app = QApplication.instance() or QApplication([])
    previous_style = app.styleSheet()
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    store = QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat)
    AppPreferences(language='pl', theme='dark').save(store)
    # main.py binds the current dashboard before constructing MainWindow.
    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    window = main_window.MainWindow(AppSettings((), paths), store)
    window.resize(1740, 1100)
    window.show()
    app.processEvents()
    try:
        yield window
    finally:
        window.close()
        app.setStyleSheet(previous_style)


@pytest.fixture(autouse=True)
def release_test_windows():
    yield
    widgets = sys.modules.get('PySide6.QtWidgets')
    if widgets is None or widgets.QApplication.instance() is None:
        return
    from PySide6.QtCore import QCoreApplication, QEvent

    # close() only hides Qt windows. Their Python signal cycles keep them alive,
    # so later application stylesheet changes revisit every previous editor.
    # Delete roots directly: teardown must never open an unsaved-changes dialog.
    deleted = False
    for window in widgets.QApplication.topLevelWidgets():
        if window.parentWidget() is None:
            window.hide()
            window.deleteLater()
            deleted = True
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    if deleted:
        gc.collect()
