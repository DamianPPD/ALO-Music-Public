"""Approved Variant B geometry and decisions; no native mouse automation."""
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

from audio_library_organizer.jobs.exporter import ExportEvent, ExportResult
from audio_library_organizer.ui import export_dialogs
from test_export_dialogs_v0427 import app, plan_for
from test_export_window_v0427 import export_window, no_unhandled_qt_errors


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_variant_b_progress_has_one_main_counter_and_retains_complete_log(app, language):
    dialog = export_dialogs.ExportProgressDialog(733, language=language)
    dialog.resize(760, 620)
    dialog.show()
    dialog.update_event(ExportEvent('preflight_sources', 733, 0, 0, 0,
                                   Path('synthetic-source.mp3'), check_current=95, check_total=734))
    app.processEvents()
    assert not any(label.text() in ('plików do utworzenia', 'files to create')
                   for label in dialog.findChildren(QLabel))
    assert dialog.counter.text() == '0 / 733 — 0%'
    assert dialog.counter.font().pixelSize() >= 22
    assert '95 / 734' in dialog.check_progress.text()
    assert dialog.counter.geometry().intersects(dialog.check_progress.geometry()) is False
    assert abs(dialog.counter.mapTo(dialog.body, dialog.counter.rect().center()).y()
               - dialog.check_progress.mapTo(dialog.body, dialog.check_progress.rect().center()).y()) < 20
    assert dialog.progress.value() == 0
    assert {key: value.text() for key, value in dialog.count_labels.items()} == {
        'created': '0', 'remaining': '733', 'failed': '0'}
    assert dialog.scroll.verticalScrollBar().maximum() == 0
    assert sum(bool(label.pixmap() and not label.pixmap().isNull()) for label in dialog.findChildren(QLabel)) >= 4
    dialog.log.clear()
    for number in range(501):
        dialog.log.appendPlainText(f'real retained entry {number}')
    assert dialog.log.toPlainText().splitlines() == [f'real retained entry {i}' for i in range(501)]
    assert dialog.log.verticalScrollBar().maximum() > 0
    dialog.finish()


def test_variant_b_small_window_keeps_stop_accessible_and_long_path_available(app):
    dialog = export_dialogs.ExportProgressDialog(2)
    dialog.resize(520, 380)
    dialog.show()
    path = Path('synthetic') / (('Long artist and version ' * 15) + '.mp3')
    dialog.update_event(ExportEvent('preflight_sources', 2, 0, 0, 0, path, check_total=2))
    app.processEvents()
    assert dialog.height() <= 400
    assert dialog.stop_button.isVisible()
    assert dialog.stop_button.mapTo(dialog, dialog.stop_button.rect().bottomRight()).y() < dialog.height()
    assert dialog.current_file.toolTip() == str(path)
    assert len(dialog.current_file.text()) < len(path.name)
    requests = []
    dialog.stop_requested.connect(lambda: requests.append(True))
    dialog.stop_button.click()
    dialog.close()
    assert requests == [True] and dialog.isVisible()
    dialog.finish()


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_variant_b_summary_retains_selectable_full_diagnostics_and_category_icons(app, tmp_path, language):
    plan, library = plan_for(tmp_path)
    error = 'Private copy cleanup failed: synthetic\\.alo-copy-example: [WinError 5] access denied; ' * 15
    result = ExportResult((), (), planned=len(plan.items), cancelled=True, cleanup_warnings=(error,))
    dialog = export_dialogs.ExportSummaryDialog(result, plan, library.root, None, language=language)
    dialog.resize(760, 700)
    dialog.show()
    app.processEvents()
    assert error in dialog.notice.text()
    assert dialog.notice.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert sum(bool(label.pixmap() and not label.pixmap().isNull()) for label in dialog.findChildren(QLabel)) >= 5
    assert {key: int(value.text()) for key, value in dialog.category_counts.items()} == result.category_counts
    assert len(dialog.actions.findChildren(QPushButton)) == 2
    assert len(dialog.footer.findChildren(QPushButton)) == 1
    assert dialog.close_button.mapTo(dialog, dialog.close_button.rect().bottomRight()).y() < dialog.height()
    dialog.close()


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_variant_b_warning_uses_real_count_and_preserves_three_decision_roles(app, language):
    assert hasattr(export_dialogs, 'ExportReviewWarning'), 'Missing approved compact warning'
    box = export_dialogs.ExportReviewWarning(327, language=language)
    box.show()
    app.processEvents()
    assert '327' in box.text()
    assert box.informativeText()
    assert len(box.buttons()) == 3
    assert box.buttonRole(box.review_button) == QMessageBox.ButtonRole.AcceptRole
    assert box.buttonRole(box.continue_button) == QMessageBox.ButtonRole.DestructiveRole
    assert box.buttonRole(box.cancel_button) == QMessageBox.ButtonRole.RejectRole
    assert box.review_button.isDefault() and box.review_button.property('primary') is True
    assert box.continue_button.property('primary') is not True
    assert box.width() >= min(600, box.screen().availableGeometry().width() - 80)
    assert box.height() < 360
    box.cancel_button.click()


def test_variant_b_nominal_summary_has_no_empty_diagnostics_gap(app, tmp_path):
    plan, library = plan_for(tmp_path)
    result = ExportResult((), (), planned=len(plan.items), cancelled=True)
    dialog = export_dialogs.ExportSummaryDialog(result, plan, library.root, None)
    dialog.resize(760, 740)
    dialog.show()
    app.processEvents()
    assert dialog.notice.isHidden()
    assert dialog.scroll.verticalScrollBar().maximum() == 0
    assert dialog.folder_button.isVisible() and dialog.report_button.isVisible()
    dialog.report_button.click()  # An unavailable report must expose a visible notice.
    app.processEvents()
    assert dialog.notice.isVisible() and dialog.notice.text()
    dialog.close()


@pytest.mark.parametrize('count, expected', [(1, '1 plik oznaczony'), (2, '2 pliki oznaczone'), (12, '12 plików oznaczonych')])
def test_variant_b_warning_polish_count_is_readable(app, count, expected):
    box = export_dialogs.ExportReviewWarning(count, language='pl')
    assert expected in box.text()


@pytest.mark.parametrize('action', ['report', 'folder'])
def test_summary_action_error_keeps_original_full_export_diagnostics(app, tmp_path, monkeypatch, action):
    plan, library = plan_for(tmp_path)
    original = 'Private copy cleanup failed: synthetic staging; controlled original cause'
    result = ExportResult((), (), planned=len(plan.items), fatal_error='controlled original fatal', cleanup_warnings=(original,))
    dialog = export_dialogs.ExportSummaryDialog(result, plan, library.root, None,
                                               report_errors=('controlled original report error',))
    before = dialog.notice.text()
    monkeypatch.setattr(export_dialogs.QDesktopServices, 'openUrl', lambda url: False)
    getattr(dialog, action + '_button').click()
    assert all(message in dialog.notice.text() for message in (original, 'controlled original fatal', 'controlled original report error'))
    assert len(dialog.notice.text()) > len(before)
    assert dialog.notice.toolTip() == dialog.notice.text()
    assert dialog.notice.isHidden() is False
    dialog.close()


@pytest.mark.parametrize('choice', ['review', 'continue', 'cancel'])
def test_variant_b_warning_decisions_do_not_bypass_preview_or_start_worker(export_window, monkeypatch, choice):
    from audio_library_organizer.ui import main_window
    window, tracks, summaries = export_window
    track = window.repository.get_track(tracks[0].track_id)
    track.status = 'review'
    window.repository.upsert_track(track)
    seen, previews, reviews = [], [], []

    def choose(box):
        assert box.property('variantB') is True
        assert '1' in box.text()
        seen.append(box)
        role = {'review': QMessageBox.ButtonRole.AcceptRole,
                'continue': QMessageBox.ButtonRole.DestructiveRole,
                'cancel': QMessageBox.ButtonRole.RejectRole}[choice]
        next(button for button in box.buttons() if box.buttonRole(button) == role).click()
        return 0

    monkeypatch.setattr(QMessageBox, 'exec', choose)
    monkeypatch.setattr(window, '_open_review', lambda: reviews.append(True))
    monkeypatch.setattr(main_window, 'confirm_bulk_copy', lambda *a, **k: previews.append(True) or False)
    window.export_library()
    assert len(seen) == 1
    assert reviews == ([True] if choice == 'review' else [])
    assert previews == ([True] if choice == 'continue' else [])
    assert window._thread is None and not summaries
