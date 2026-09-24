from __future__ import annotations

import json
import sys
import types
from pathlib import Path


class FakeSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class FakeTimer:
    @staticmethod
    def singleShot(_delay, callback):
        callback()


def _install_fake_dashboard(monkeypatch):
    dashboard_page = types.ModuleType('audio_library_organizer.ui.dashboard_page')
    dashboard_page.DashboardPage = type('DashboardPage', (), {})
    monkeypatch.setitem(sys.modules, 'audio_library_organizer.ui.dashboard_page', dashboard_page)
    import audio_library_organizer.ui as ui_package
    monkeypatch.setattr(ui_package, 'dashboard_page', dashboard_page, raising=False)


def _install_fake_ui_module(monkeypatch, name: str, module: types.ModuleType):
    monkeypatch.setitem(sys.modules, f'audio_library_organizer.ui.{name}', module)
    import audio_library_organizer.ui as ui_package
    monkeypatch.setattr(ui_package, name, module, raising=False)


def test_smoke_test_flag_dispatches_without_normal_startup(monkeypatch):
    from audio_library_organizer import main as app_main

    seen = {'called': 0}

    def fake_smoke_test():
        seen['called'] += 1
        return 17

    monkeypatch.setattr(app_main, '_smoke_test', fake_smoke_test, raising=False)

    assert app_main.main(['--smoke-test']) == 17
    assert seen['called'] == 1


def test_smoke_test_uses_metadata_editor_dialog(monkeypatch, tmp_path: Path):
    from audio_library_organizer import main as app_main

    class FakeApplication:
        _instance = None

        def __init__(self, argv):
            self.argv = argv
            FakeApplication._instance = self

        @classmethod
        def instance(cls):
            return cls._instance

    qtwidgets = types.ModuleType('PySide6.QtWidgets')
    qtwidgets.QApplication = FakeApplication
    monkeypatch.setitem(sys.modules, 'PySide6', types.ModuleType('PySide6'))
    monkeypatch.setitem(sys.modules, 'PySide6.QtWidgets', qtwidgets)

    fingerprint = types.ModuleType('audio_library_organizer.audio.fingerprint')
    fingerprint.find_fpcalc = lambda: tmp_path / 'fpcalc.exe'
    monkeypatch.setitem(sys.modules, 'audio_library_organizer.audio.fingerprint', fingerprint)

    _install_fake_dashboard(monkeypatch)

    duplicates_page = types.ModuleType('audio_library_organizer.ui.duplicates_page')
    duplicates_page.DuplicatesPage = type('DuplicatesPage', (), {})
    monkeypatch.setitem(sys.modules, 'audio_library_organizer.ui.duplicates_page', duplicates_page)

    library_page = types.ModuleType('audio_library_organizer.ui.library_page')
    library_page.LibraryPage = type('LibraryPage', (), {})
    monkeypatch.setitem(sys.modules, 'audio_library_organizer.ui.library_page', library_page)

    main_window = types.ModuleType('audio_library_organizer.ui.main_window')
    main_window.MainWindow = type('MainWindow', (), {})
    _install_fake_ui_module(monkeypatch, 'main_window', main_window)

    metadata_editor = types.ModuleType('audio_library_organizer.ui.metadata_editor')
    metadata_editor.MetadataEditorDialog = type('MetadataEditorDialog', (), {})
    _install_fake_ui_module(monkeypatch, 'metadata_editor', metadata_editor)

    assert app_main._smoke_test() == 0


def test_first_run_acceptance_uses_qdialog_dialog_code(monkeypatch, tmp_path: Path):
    from audio_library_organizer import main as app_main

    class FakeApplication:
        def __init__(self, argv):
            self.argv = argv
            self.aboutToQuit = FakeSignal()

        def setApplicationName(self, name):
            pass

        def setOrganizationName(self, name):
            pass

        def setStyleSheet(self, style):
            pass

        def exec(self):
            return 0

    class FakeSettingsStore:
        def __init__(self):
            self.data = {}

        def value(self, key, default=''):
            return self.data.get(key, default)

        def setValue(self, key, value):
            self.data[key] = value

        def remove(self, key):
            self.data.pop(key, None)

        def sync(self):
            pass

    class FakeQDialog:
        class DialogCode:
            Accepted = 1

    qtcore = types.ModuleType('PySide6.QtCore')
    qtcore.QSettings = FakeSettingsStore
    qtcore.QTimer = FakeTimer
    qtwidgets = types.ModuleType('PySide6.QtWidgets')
    qtwidgets.QApplication = FakeApplication
    qtwidgets.QDialog = FakeQDialog
    pyside = types.ModuleType('PySide6')
    monkeypatch.setitem(sys.modules, 'PySide6', pyside)
    monkeypatch.setitem(sys.modules, 'PySide6.QtCore', qtcore)
    monkeypatch.setitem(sys.modules, 'PySide6.QtWidgets', qtwidgets)

    settings_result = types.SimpleNamespace(
        source_dirs=(tmp_path / 'source',),
        library=types.SimpleNamespace(root=tmp_path / 'library'),
    )

    first_run = types.ModuleType('audio_library_organizer.ui.first_run')

    class FakeFirstRunDialog:
        def __init__(self):
            self.settings_result = settings_result

        def exec(self):
            return FakeQDialog.DialogCode.Accepted

    first_run.FirstRunDialog = FakeFirstRunDialog
    _install_fake_ui_module(monkeypatch, 'first_run', first_run)

    _install_fake_dashboard(monkeypatch)

    main_window = types.ModuleType('audio_library_organizer.ui.main_window')

    class FakeMainWindow:
        def __init__(self, settings, store):
            assert settings is settings_result

        def setMinimumSize(self, width, height):
            pass

        def restoreGeometry(self, geometry):
            pass

        def saveGeometry(self):
            return b'geometry'

        def show(self):
            pass

    main_window.MainWindow = FakeMainWindow
    _install_fake_ui_module(monkeypatch, 'main_window', main_window)

    theme = types.ModuleType('audio_library_organizer.ui.theme')
    theme.APP_STYLE = ''
    theme.DARK_STYLE = theme.APP_STYLE
    _install_fake_ui_module(monkeypatch, 'theme', theme)

    assert app_main.main() == 0


def test_startup_reuses_saved_library_paths_without_opening_wizard(monkeypatch, tmp_path: Path):
    from audio_library_organizer import main as app_main

    source = tmp_path / 'SOURCE'; source.mkdir()
    library = tmp_path / 'LIBRARY'; library.mkdir()

    class FakeApplication:
        def __init__(self, argv): self.argv = argv; self.aboutToQuit = FakeSignal()
        def setApplicationName(self, name): pass
        def setOrganizationName(self, name): pass
        def setStyleSheet(self, style): pass
        def exec(self): return 0

    class FakeSettingsStore:
        last = None
        def __init__(self):
            self.data = {
                'sources': json.dumps([str(source)]),
                'library_root': str(library),
                'discogs_token': 'keep-me',
            }
            FakeSettingsStore.last = self
        def value(self, key, default=''): return self.data.get(key, default)
        def setValue(self, key, value): self.data[key] = value
        def remove(self, key): self.data.pop(key, None)
        def sync(self): pass

    class FakeQDialog:
        class DialogCode:
            Accepted = 1

    qtcore = types.ModuleType('PySide6.QtCore'); qtcore.QSettings = FakeSettingsStore; qtcore.QTimer = FakeTimer
    qtwidgets = types.ModuleType('PySide6.QtWidgets'); qtwidgets.QApplication = FakeApplication; qtwidgets.QDialog = FakeQDialog
    monkeypatch.setitem(sys.modules, 'PySide6', types.ModuleType('PySide6'))
    monkeypatch.setitem(sys.modules, 'PySide6.QtCore', qtcore)
    monkeypatch.setitem(sys.modules, 'PySide6.QtWidgets', qtwidgets)

    first_run = types.ModuleType('audio_library_organizer.ui.first_run')
    class FakeFirstRunDialog:
        def __init__(self, *args, **kwargs):
            raise AssertionError('wizard should not open for saved library')
    first_run.FirstRunDialog = FakeFirstRunDialog
    _install_fake_ui_module(monkeypatch, 'first_run', first_run)

    _install_fake_dashboard(monkeypatch)

    main_window = types.ModuleType('audio_library_organizer.ui.main_window')
    seen = {}
    class FakeMainWindow:
        def __init__(self, settings, store):
            seen['settings'] = settings
        def setMinimumSize(self, width, height): pass
        def restoreGeometry(self, geometry): pass
        def saveGeometry(self): return b'geometry'
        def show(self): pass
    main_window.MainWindow = FakeMainWindow
    _install_fake_ui_module(monkeypatch, 'main_window', main_window)

    theme = types.ModuleType('audio_library_organizer.ui.theme')
    theme.APP_STYLE = ''
    theme.DARK_STYLE = theme.APP_STYLE
    _install_fake_ui_module(monkeypatch, 'theme', theme)

    assert app_main.main() == 0
    assert seen['settings'].source_dirs == (source.resolve(),)
    assert seen['settings'].library.root == library.resolve()
    assert FakeSettingsStore.last.data['discogs_token'] == 'keep-me'
