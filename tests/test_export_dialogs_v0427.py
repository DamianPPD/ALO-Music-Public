from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs.exporter import ExportEvent, ExportPlan, execute_copy_plan


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def plan_for(tmp_path):
    library = LibraryPaths(tmp_path / 'library')
    library.ensure_created()
    tracks = []
    for index, status in enumerate(['ready', 'review', 'duplicate', 'not_selected'] * 2):
        path = tmp_path / f'{index}-synthetic.mp3'
        path.write_bytes(b'synthetic audio')
        tracks.append(TrackRecord(path=path, status=status, artist='Artist', title='Title',
                                  year='2000', genre='House', bpm=128))
    return ExportPlan.from_tracks(tracks, library), library


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_preview_uses_real_plan_and_cancels_without_copying(app, tmp_path, language):
    from audio_library_organizer.ui.export_dialogs import ExportPreviewDialog
    plan, library = plan_for(tmp_path)
    before = {i.track.path: i.track.path.read_bytes() for i in plan.items}
    dialog = ExportPreviewDialog(plan.preview_summary, plan=plan, folder_organization='artist', language=language)
    assert dialog.total_label.text() == '8'
    assert {k: v.text() for k, v in dialog.category_counts.items()} == {'ready': '2', 'review': '2', 'not_selected': '4'}
    assert len(dialog.example_labels) == 6
    assert str(plan.items[0].track.path) in dialog.example_labels[0].toolTip()
    assert str(plan.items[0].destination_dir) in dialog.example_labels[0].toolTip()
    assert len(dialog.footer.findChildren(QPushButton)) == 2
    dialog.show()
    app.processEvents()
    dialog.cancel_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not list(library.root.rglob('*.mp3'))
    assert all(path.read_bytes() == data for path, data in before.items())


def test_progress_counts_only_terminal_verified_outputs_and_stop_is_idempotent(app):
    from audio_library_organizer.ui.export_dialogs import ExportProgressDialog
    dialog = ExportProgressDialog(4)
    requests = []
    dialog.stop_requested.connect(lambda: requests.append(True))
    dialog.show()
    app.processEvents()
    assert dialog.progress.value() == 0
    dialog.update_event(ExportEvent('tags_written', 4, 0, 0, 0, Path('source.mp3'), Path('output.mp3')))
    assert dialog.count_labels['created'].text() == '0'
    dialog.update_event(ExportEvent('item_finished', 4, 1, 1, 0))
    assert dialog.count_labels['created'].text() == '1'
    assert dialog.count_labels['remaining'].text() == '3'
    assert dialog.progress.value() == 1
    dialog.stop_button.click()
    dialog.reject()  # Escape must request stop, never abandon a live worker.
    dialog.close()
    assert requests == [True]
    assert not dialog.stop_button.isEnabled()
    assert dialog.isVisible()
    dialog.finish()
    assert not dialog.isVisible()


@pytest.mark.parametrize('state', ['success', 'cancelled', 'problems'])
def test_summary_is_honest_and_has_two_middle_actions_one_footer(app, tmp_path, monkeypatch, state):
    from audio_library_organizer.ui.export_dialogs import ExportSummaryDialog
    from audio_library_organizer.jobs import exporter
    plan, library = plan_for(tmp_path)
    if state == 'problems':
        monkeypatch.setattr(exporter, 'verify_exact_copy', lambda *a, **k: False)
    result = execute_copy_plan(plan, cancelled=(lambda: True) if state == 'cancelled' else None)
    report = library.reports / 'audit.csv'
    report.write_text('actual audit', encoding='utf-8')
    opened = []
    monkeypatch.setattr('audio_library_organizer.ui.export_dialogs.QDesktopServices.openUrl',
                        lambda url: opened.append(url.toLocalFile()) or True)
    dialog = ExportSummaryDialog(result, plan, library.root, report)
    assert dialog.outcome == state
    assert len(dialog.actions.findChildren(QPushButton)) == 2
    assert [b.text() for b in dialog.footer.findChildren(QPushButton)] == ['Zamknij']
    assert dialog.created_label.text().startswith(str(result.created))
    assert {k: int(v.text()) for k, v in dialog.category_counts.items()} == result.category_counts
    dialog.folder_button.click()
    dialog.report_button.click()
    assert opened == [str(library.root), str(report)]
    report.unlink()
    dialog.report_button.click()
    assert len(opened) == 2 and dialog.notice.text()


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_dialogs_fit_small_window_and_long_names_have_tooltips(app, tmp_path, language):
    from audio_library_organizer.ui.export_dialogs import ExportPreviewDialog, ExportProgressDialog, ExportSummaryDialog
    plan, library = plan_for(tmp_path)
    long_name = 'Very long artist and title ' * 40
    result = execute_copy_plan(plan, cancelled=lambda: True)
    dialogs = [ExportPreviewDialog(plan.preview_summary, examples=[long_name], language=language),
               ExportProgressDialog(8, language=language),
               ExportSummaryDialog(result, plan, library.root, None, language=language)]
    for dialog in dialogs:
        dialog.resize(620, 470)
        dialog.show()
        app.processEvents()
        for button in dialog.footer.findChildren(QPushButton):
            assert button.isVisible()
            assert button.mapTo(dialog, button.rect().bottomRight()).y() < dialog.height()
        assert dialog.width() <= 640
    assert dialogs[0].example_labels[0].toolTip() == long_name
    assert len(dialogs[0].example_labels[0].text()) < len(long_name)
    dialogs[1].finish()


def test_preview_examples_use_the_dark_dialog_palette(app, tmp_path):
    from audio_library_organizer.ui.export_dialogs import ExportPreviewDialog
    from PySide6.QtGui import QPalette
    plan, library = plan_for(tmp_path)
    dialog = ExportPreviewDialog(plan.preview_summary, plan=plan)
    dialog.show()
    app.processEvents()
    content = dialog.example_labels[0].parentWidget()
    assert content.palette().color(QPalette.ColorRole.Window).name() == '#11171e'
