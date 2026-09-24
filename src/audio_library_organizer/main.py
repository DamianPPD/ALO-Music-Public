from __future__ import annotations

import sys


def _smoke_test() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from audio_library_organizer.audio.fingerprint import find_fpcalc
        from audio_library_organizer.ui.dashboard_page import DashboardPage
        from audio_library_organizer.ui.duplicates_page import DuplicatesPage
        from audio_library_organizer.ui.library_page import LibraryPage
        from audio_library_organizer.ui.main_window import MainWindow
        from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
    except Exception:
        return 3

    _ = (DashboardPage, DuplicatesPage, LibraryPage, MainWindow, MetadataEditorDialog)
    app = QApplication.instance() or QApplication(['ALO-Music-smoke-test'])
    if app is None:
        return 3
    if find_fpcalc() is None:
        return 4
    return 0


def _show_startup_loader(app):
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon, QPixmap
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
        from audio_library_organizer import __version__
        from audio_library_organizer.ui.assets import asset_path
    except (ImportError, AttributeError):
        return None

    loader = QWidget()
    loader.setObjectName('StartupLoader')
    loader.setWindowTitle('ALO Music')
    loader.setWindowIcon(QIcon(str(asset_path('alo.ico'))))
    loader.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
    loader.setFixedSize(500, 172)

    layout = QVBoxLayout(loader)
    layout.setContentsMargins(24, 18, 24, 18)
    layout.setSpacing(10)

    brand_row = QHBoxLayout()
    brand_row.setSpacing(12)
    logo = QLabel()
    logo.setFixedSize(58, 58)
    logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pix = QPixmap(str(asset_path('alo_icon.png')))
    if not pix.isNull():
        logo.setPixmap(
            pix.scaled(
                56, 56,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    brand_row.addWidget(logo)

    text_box = QVBoxLayout()
    text_box.setSpacing(2)
    title = QLabel('ALO Music')
    title.setStyleSheet('font-size:18pt;font-weight:800;')
    text_box.addWidget(title)
    version = QLabel(f'ALO Music v{__version__}')
    version.setObjectName('MutedText')
    version.setStyleSheet('font-size:9pt;font-weight:600;')
    text_box.addWidget(version)
    status = QLabel('Ładowanie biblioteki…')
    status.setObjectName('MutedText')
    text_box.addWidget(status)
    text_box.addStretch(1)
    brand_row.addLayout(text_box, 1)
    layout.addLayout(brand_row)

    progress = QProgressBar()
    progress.setTextVisible(False)
    progress.setRange(0, 0)
    progress.setMinimumHeight(8)
    layout.addWidget(progress)

    loader.status_label = status
    loader.show()
    if hasattr(app, 'processEvents'):
        app.processEvents()
    return loader


def _open_dashboard_quick_view(window, key: str) -> None:
    if key == 'duplicate':
        window._navigate(2)
        return
    index = window.library.status.findData(key)
    if index >= 0:
        window.library.status.setCurrentIndex(index)
    window._navigate(1)


def _wire_dashboard_actions(window):
    dashboard = getattr(window, 'dashboard', None)
    if dashboard is None:
        return
    if hasattr(dashboard, 'quick_view_requested'):
        dashboard.quick_view_requested.connect(lambda key: _open_dashboard_quick_view(window, key))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if '--smoke-test' in args:
        return _smoke_test()

    try:
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtWidgets import QApplication, QDialog
    except ImportError:
        print('Brakuje PySide6. Uruchom run_audio_library_organizer.bat albo zainstaluj: pip install -e ".[gui,analysis]"')
        return 2

    from audio_library_organizer.ui import first_run as first_run_ui
    LanguageSelectionDialog = getattr(first_run_ui, 'LanguageSelectionDialog', None)
    FirstRunDialog = first_run_ui.FirstRunDialog
    from audio_library_organizer.ui import main_window as main_window_ui
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    main_window_ui.DashboardPage = DashboardPage
    MainWindow = main_window_ui.MainWindow
    try:
        from audio_library_organizer.ui.theme import style_for_theme
    except ImportError:
        from audio_library_organizer.ui.theme import APP_STYLE
        style_for_theme = lambda _theme: APP_STYLE
    from audio_library_organizer.ui.v0411_theme import style_for_v0411
    from audio_library_organizer.domain.preferences import AppPreferences, language_selection_done, save_language_selection
    from audio_library_organizer.ui.i18n import apply_static_language
    from audio_library_organizer.ui.state import load_app_settings, save_app_settings

    app = QApplication(sys.argv)
    app.setApplicationName('Audio Library Organizer')
    app.setOrganizationName('ALO')
    store = QSettings()
    prefs = AppPreferences.from_store(store)
    app.setStyleSheet(style_for_theme(prefs.theme) + style_for_v0411(prefs.theme))

    if not language_selection_done(store) and LanguageSelectionDialog is not None:
        language_dialog = LanguageSelectionDialog(initial_language=prefs.language)
        if language_dialog.exec() != QDialog.DialogCode.Accepted or not language_dialog.selected_language:
            return 0
        save_language_selection(store, language_dialog.selected_language)
        prefs = AppPreferences.from_store(store)

    settings = load_app_settings(store)
    if settings is None:
        dialog = FirstRunDialog()
        apply_static_language(dialog, prefs.language)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.settings_result is None:
            return 0
        settings = dialog.settings_result
        save_app_settings(store, settings)

    startup_loader = _show_startup_loader(app)
    try:
        window = MainWindow(settings, store)
        _wire_dashboard_actions(window)
        if hasattr(window, 'library'):
            from audio_library_organizer.ui.library_status_legend import install_library_status_legend
            install_library_status_legend(window.library)
        window.setMinimumSize(1180, 720)
        saved_geometry = store.value('main_window/geometry')
        if saved_geometry:
            window.restoreGeometry(saved_geometry)

        def save_window_geometry():
            store.setValue('main_window/geometry', window.saveGeometry())
            store.sync()

        app.aboutToQuit.connect(save_window_geometry)
        window.show()
        if hasattr(app, 'processEvents'):
            app.processEvents()

        if startup_loader is not None:
            try:
                total = len(window.repository.list_tracks(available_only=True))
            except Exception:
                total = 0
            if hasattr(startup_loader, 'status_label'):
                if prefs.language == 'en':
                    startup_loader.status_label.setText(f'Ready: {total} tracks')
                else:
                    startup_loader.status_label.setText(f'Gotowe: {total} utworów')
            if hasattr(app, 'processEvents'):
                app.processEvents()
            QTimer.singleShot(450, startup_loader.close)
    except Exception:
        if startup_loader is not None:
            startup_loader.close()
        raise

    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
