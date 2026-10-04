from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_four_numbered_steps_are_grouped_before_auxiliary_add_files_action(current_start_window, tmp_path, monkeypatch):
    """Four workflow steps stay together; source addition lives in Start."""
    from PySide6.QtWidgets import QApplication, QFrame, QPushButton
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.storage.library_profiles import LibraryRegistry

    window = current_start_window
    group = window.action_frame.findChild(QFrame, 'WorkflowToolbarGroup')
    buttons = group.findChildren(QPushButton)
    assert buttons == [window.scan_btn, window.identify_btn, window.review_btn, window.export_btn]
    assert window.action_frame.findChildren(QPushButton) == buttons
    assert [button.text() for button in buttons] == [
        '1. Skanuj foldery', '2. Rozpoznaj utwory online',
        '3. Sprawdź w Bibliotece', '4. Utwórz pliki wynikowe',
    ]
    assert all(first.geometry().right() < second.geometry().left()
               for first, second in zip(buttons, buttons[1:]))
    separator = window.action_frame.findChild(QFrame, 'WorkflowToolbarSeparator')
    assert group.geometry().right() < separator.geometry().left()
    add = window.dashboard.sources.add_button
    assert window.dashboard.sources_panel.isAncestorOf(add)
    assert not window.action_frame.isAncestorOf(add)
    assert window.findChildren(QPushButton, 'StartAddSource') == [add]

    source = tmp_path / 'incoming'
    source.mkdir()
    dialogs, scans = [], []
    def choose_folder(*args, **kwargs):
        dialogs.append((args, kwargs))
        return str(source)
    def run_scan(**kwargs):
        scans.append(kwargs)
        window._scan_finished(window.service.scan(source_dirs=kwargs['source_dirs']))
    monkeypatch.setattr(main_window.QFileDialog, 'getExistingDirectory', choose_folder)
    monkeypatch.setattr(window, 'start_scan', run_scan)
    add.click()
    QApplication.instance().processEvents()
    assert len(dialogs) == 1 and dialogs[0][0][1] == 'Wybierz folder z nowymi plikami'
    assert scans == [{'source_dirs': (source.resolve(),), 'new_files': True}]
    assert window.app_settings.source_dirs == (source.resolve(),)
    restored = LibraryRegistry.from_store(window.qt_settings, window.main_settings)
    assert restored.active.source_dirs == (source.resolve(),)
    assert restored.scan_history()[0].source_dir == source.resolve()
    assert window.dashboard.sources.table.item(0, 0).text() == str(source.resolve())


def test_workflow_actions_have_distinct_icons_and_clear_export_name():
    assert "QPushButton('1. Skanuj foldery')" in MAIN
    assert "QPushButton('2. Rozpoznaj utwory online')" in MAIN
    assert "QPushButton('3. Sprawdź w Bibliotece')" in MAIN
    assert "QPushButton('4. Utwórz pliki wynikowe')" in MAIN
    assert "(self.scan_btn, 'scan')" in MAIN
    assert "(self.identify_btn, 'search')" in MAIN
    assert "(self.review_btn, 'review')" in MAIN
    assert "(self.export_btn, 'export')" in MAIN
    assert 'Utwórz pliki wynikowe' in MAIN
    assert 'QFrame#WorkflowToolbarSeparator' in THEME
