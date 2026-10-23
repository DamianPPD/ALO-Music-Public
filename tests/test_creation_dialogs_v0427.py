"""Creation dialog contracts on isolated data and actual MainWindow operations."""
import importlib
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QMessageBox

from test_export_dialogs_v0427 import app
from test_export_window_v0427 import export_window, until, no_unhandled_qt_errors


def dialogs():
    name = 'audio_library_organizer.ui.creation_dialogs'
    assert importlib.util.find_spec(name), 'Approved creation dialogs are missing'
    return importlib.import_module(name)


@pytest.mark.parametrize('kind', ['folder', 'playlist'])
@pytest.mark.parametrize('count,want', [(1, '1 utwór'), (2, '2 utwory'), (5, '5 utworów'),
                                      (21, '21 utworów'), (22, '22 utwory'), (25, '25 utworów')])
def test_creation_counts_and_plural_forms_are_real(app, tmp_path, kind, count, want):
    ui = dialogs()
    dialog = ui.CreationNameDialog(kind, count, initial_target=tmp_path / 'playlista.m3u8', language='pl')
    assert str(count) in dialog.description.text()
    result = ui.CreationResultDialog(kind, 'Synthetic <name>', count, tmp_path, language='pl')
    assert result.count_label.text() == want
    assert 'Synthetic <name>' in result.message.text()
    assert result.message.textFormat() == Qt.TextFormat.PlainText
    assert str(tmp_path) in result.location_label.text()
    assert result.location_label.isReadOnly()
    result.location_label.selectAll()
    assert result.location_label.selectedText() == str(tmp_path)


@pytest.mark.parametrize('kind', ['folder', 'playlist'])
@pytest.mark.parametrize('key', ['cancel', 'escape', 'close', 'enter'])
def test_creation_buttons_keyboard_and_cancel_never_write_files(app, tmp_path, kind, key):
    dialog = dialogs().CreationNameDialog(kind, 2, initial_target=tmp_path / 'test.m3u8')
    dialog.show(); app.processEvents()
    dialog.name_edit.clear()
    assert not dialog.create_button.isEnabled()
    dialog.name_edit.setText('Synthetic')
    assert dialog.create_button.isEnabled()
    assert dialog.create_button.height() == dialog.cancel_button.height() == 40
    assert dialog.width() <= 470
    assert dialog.name_edit.hasFocus()
    if key == 'cancel': dialog.cancel_button.click()
    elif key == 'escape': QTest.keyClick(dialog, Qt.Key.Key_Escape)
    elif key == 'close': dialog.close()
    else: QTest.keyClick(dialog.name_edit, Qt.Key.Key_Return)
    assert dialog.result() == (QDialog.DialogCode.Accepted if key == 'enter' else QDialog.DialogCode.Rejected)
    assert not list(tmp_path.iterdir())


def test_playlist_destination_choice_preserves_overwrite_confirmation(app, tmp_path, monkeypatch):
    ui = dialogs(); target = tmp_path / 'existing.m3u8'; target.write_bytes(b'protected playlist')
    dialog = ui.CreationNameDialog('playlist', 2, initial_target=tmp_path / 'default.m3u8')
    monkeypatch.setattr(ui.QFileDialog, 'getSaveFileName', lambda *a, **k: (str(target), ''))
    dialog.choose_target()
    assert dialog.target_path() == target
    monkeypatch.setattr(ui.QMessageBox, 'exec', lambda self: QMessageBox.StandardButton.No)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Rejected
    monkeypatch.setattr(ui.QMessageBox, 'exec', lambda self: QMessageBox.StandardButton.Yes)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert target.read_bytes() == b'protected playlist'  # Presentation never writes a playlist.


def observe_results(monkeypatch, ui):
    seen = []
    def show(dialog):
        seen.append((dialog.windowTitle(), dialog.message.text(), dialog.count_label.text(),
                     dialog.location_label.text(), dialog.details.toPlainText()))
        return 0
    monkeypatch.setattr(ui.CreationResultDialog, 'exec', show)
    return seen


def test_real_playlist_write_uses_available_count_selected_count_and_original_m3u8(export_window, tmp_path, monkeypatch):
    ui = dialogs(); window, tracks, _ = export_window
    target = tmp_path / 'chosen' / 'Synthetic playlist.m3u8'
    monkeypatch.setattr(ui.QFileDialog, 'getSaveFileName', lambda *a, **k: (str(target), ''))
    choices = []
    def choose(dialog):
        choices.append((dialog.description.text(), dialog.availability_label.text()))
        dialog.choose_target(); dialog.accept(); return dialog.result()
    monkeypatch.setattr(ui.CreationNameDialog, 'exec', choose)
    seen = observe_results(monkeypatch, ui)
    before = {t.path: t.path.read_bytes() for t in tracks}
    window._export_playlist([*(t.path for t in tracks), tmp_path / 'missing.mp3'])
    assert '3' in choices[0][0] and '2' in choices[0][1]
    payload = target.read_text(encoding='utf-8-sig').splitlines()
    assert payload[0] == '#EXTM3U' and len(payload) == 3
    assert target.read_bytes().startswith(b'\xef\xbb\xbf')
    assert all((target.parent / line).resolve() == t.path.resolve() for line, t in zip(payload[1:], tracks))
    assert len(seen) == 1 and seen[0][0] == 'Playlista utworzona'
    assert seen[0][2] == '2 utwory' and str(target) in seen[0][3]
    assert all(p.read_bytes() == b for p, b in before.items())


@pytest.mark.parametrize('failure', ['cancel', 'write_error'])
def test_playlist_cancel_or_write_error_has_no_success(export_window, tmp_path, monkeypatch, failure):
    ui = dialogs(); window, tracks, _ = export_window
    from audio_library_organizer.ui import main_window
    target = tmp_path / 'failed.m3u8'
    monkeypatch.setattr(ui.CreationNameDialog, 'exec', lambda self: QDialog.DialogCode.Rejected if failure == 'cancel' else QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ui.CreationNameDialog, 'target_path', lambda self: target)
    if failure == 'write_error':
        def deny(*a, **k): raise OSError('controlled write denial')
        monkeypatch.setattr(main_window, 'write_m3u8', deny)
    seen = observe_results(monkeypatch, ui)
    window._export_playlist([t.path for t in tracks])
    assert not seen and not target.exists()


def test_real_folder_filtered_count_actual_location_and_success(export_window, monkeypatch):
    ui = dialogs(); window, tracks, _ = export_window
    tracks[1].is_available = False
    descriptions = []
    def choose(dialog):
        descriptions.append((dialog.description.text(), dialog.availability_label.text()))
        dialog.name_edit.setText('Synthetic folder'); dialog.accept(); return dialog.result()
    monkeypatch.setattr(ui.CreationNameDialog, 'exec', choose)
    seen = observe_results(monkeypatch, ui)
    before = {t.path: t.path.read_bytes() for t in tracks}
    window._create_collection_from_tracks(tracks)
    until(lambda: window._thread is None)
    target = window.app_settings.library.custom_folders / 'Synthetic folder'
    assert len(list(target.glob('*.mp3'))) == 1
    assert '2' in descriptions[0][0] and '1' in descriptions[0][1]
    assert len(seen) == 1 and seen[0][0] == 'Folder utworzony'
    assert seen[0][2] == '1 utwór' and str(target) in seen[0][3]
    assert all(p.read_bytes() == b for p, b in before.items())


def test_real_partial_folder_keeps_error_and_does_not_claim_full_success(export_window, monkeypatch):
    ui = dialogs(); window, tracks, _ = export_window
    from audio_library_organizer.jobs.collections import build_collection_plan
    from audio_library_organizer.jobs import exporter
    real_write = exporter.write_resolved_tags; calls = []
    def second_fails(*a, **k):
        calls.append(True)
        if len(calls) == 2: raise OSError('controlled second file tag error')
        return real_write(*a, **k)
    monkeypatch.setattr(exporter, 'write_resolved_tags', second_fails)
    seen = observe_results(monkeypatch, ui)
    plan = build_collection_plan(window.app_settings.library, 'Partial synthetic', tracks)
    window._start_collection_plan(plan); until(lambda: window._thread is None)
    assert len(seen) == 1 and seen[0][0] != 'Folder utworzony'
    assert seen[0][2] == '1 utwór'
    assert 'controlled second file tag error' in seen[0][4]
    assert len(list(plan.items[0].destination_dir.glob('*.mp3'))) == 1


@pytest.mark.parametrize('kind', ['folder', 'playlist'])
def test_creation_english_ui(app, tmp_path, kind):
    ui = dialogs()
    d = ui.CreationNameDialog(kind, 2, initial_target=tmp_path / 'Demo.m3u8', language='en')
    assert d.windowTitle() == ('New folder' if kind == 'folder' else 'New playlist')
    assert '2 selected tracks' in d.description.text()
    assert d.cancel_button.text() == 'Cancel'
    result = ui.CreationResultDialog(kind, 'Demo', 1, tmp_path, language='en')
    assert result.count_label.text() == '1 track' and result.close_button.text() == 'Close'


@pytest.mark.parametrize('operation', ['folder', 'playlist'])
@pytest.mark.parametrize('stale', [False, True])
def test_context_creation_keeps_real_worker_context_guard(export_window, tmp_path, monkeypatch, operation, stale):
    ui = dialogs(); window, tracks, _ = export_window
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: 0)
    from test_library_file_ui_v0427 import menu_for
    target = tmp_path / 'context.m3u8'
    monkeypatch.setattr(ui.QFileDialog, 'getSaveFileName', lambda *a, **k: (str(target), ''))
    def choose(dialog):
        if operation == 'playlist': dialog.choose_target()
        else: dialog.name_edit.setText('Context folder')
        if stale:
            track = window.repository.get_track(tracks[0].track_id)
            track.title = 'Changed while modal is open'
            window.repository.upsert_track(track)
        dialog.accept(); return dialog.result()
    monkeypatch.setattr(ui.CreationNameDialog, 'exec', choose)
    seen = observe_results(monkeypatch, ui)
    menu = menu_for(window.library, tracks[0])
    token = window.library._context_menu_state['token']
    assert window.library._context_tracks(token) is not None
    if operation == 'playlist': window._export_context_playlist((token, (tracks[0].path,)))
    else: window._create_context_collection((token, (tracks[0],)))
    until(lambda: window.library._menu_tasks.queue.active is None and window._thread is None)
    if stale:
        assert not seen and not target.exists()
        assert not (window.app_settings.library.custom_folders / 'Context folder').exists()
    else:
        assert len(seen) == 1 and seen[0][2] == '1 utwór'
        assert target.exists() if operation == 'playlist' else (window.app_settings.library.custom_folders / 'Context folder').exists()
    menu.close()


def test_folder_cancel_starts_no_worker(export_window, monkeypatch):
    ui = dialogs(); window, tracks, _ = export_window
    monkeypatch.setattr(ui.CreationNameDialog, 'exec', lambda self: QDialog.DialogCode.Rejected)
    seen = observe_results(monkeypatch, ui)
    window._create_collection_from_tracks(tracks)
    assert window._thread is None and not seen
    assert not list(window.app_settings.library.custom_folders.glob('*/*.mp3'))


def test_many_failure_messages_keep_close_on_screen_and_full_diagnostics(app, tmp_path):
    errors = [f'/synthetic/track_{i:03}.mp3: controlled write denial' for i in range(50)]
    d = dialogs().CreationResultDialog('folder', 'Many failures', 0, tmp_path, outcome='problems', expected_count=50, errors=errors)
    d.show(); app.processEvents()
    assert d.height() <= d.screen().availableGeometry().height() - 40
    assert d.close_button.mapTo(d, d.close_button.rect().bottomRight()).y() < d.height()
    text = d.details.toPlainText() if hasattr(d.details, 'toPlainText') else d.details.text()
    assert text.splitlines() == errors


@pytest.mark.parametrize('invalid', ['/', '.', '..', 'bad\0name'])
def test_invalid_playlist_target_remains_in_form_without_writing(app, tmp_path, invalid):
    d = dialogs().CreationNameDialog('playlist', 1, initial_target=tmp_path / 'valid.m3u8')
    d.name_edit.setText(invalid)
    d.accept()
    assert d.result() == QDialog.DialogCode.Rejected
    assert d.validation_notice.text()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('language,yes,no', [('pl', 'Tak', 'Nie'), ('en', 'Yes', 'No')])
def test_overwrite_question_is_localized_and_defaults_to_no(app, tmp_path, monkeypatch, language, yes, no):
    ui = dialogs(); target = tmp_path / 'protected.m3u8'; target.write_bytes(b'protected')
    d = ui.CreationNameDialog('playlist', 2, initial_target=target, language=language)
    def inspect(question):
        assert question.button(QMessageBox.StandardButton.Yes).text() == yes
        assert question.button(QMessageBox.StandardButton.No).text() == no
        assert question.defaultButton() is question.button(QMessageBox.StandardButton.No)
        assert question.textFormat() == Qt.TextFormat.PlainText
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(ui.QMessageBox, 'exec', inspect)
    d.accept()
    assert d.result() == QDialog.DialogCode.Rejected and target.read_bytes() == b'protected'


def test_normal_result_is_compact_without_outer_scrolling(app, tmp_path):
    d = dialogs().CreationResultDialog('playlist', 'Demo', 2, tmp_path / 'Demo.m3u8')
    d.show(); app.processEvents()
    assert d.height() <= 400
