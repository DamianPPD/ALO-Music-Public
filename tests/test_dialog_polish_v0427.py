"""Approved dialog presentation and real operation boundaries; synthetic data only."""
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QSize
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from audio_library_organizer.jobs.exporter import ExportResult
from audio_library_organizer.ui import export_dialogs
from test_export_dialogs_v0427 import app, plan_for


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_warning_buttons_same_height_and_variant_d_accent(app, language):
    box = export_dialogs.ExportReviewWarning(22, language=language)
    box.show(); app.processEvents()
    buttons = [box.review_button, box.continue_button, box.cancel_button]
    assert [b.height() for b in buttons] == [40, 40, 40]
    assert len({b.mapTo(box, b.rect().center()).y() for b in buttons}) == 1
    button = box.continue_button
    assert not button.icon().isNull()
    assert button.iconSize() == QSize(16, 16)
    image = button.grab().toImage()
    ratio = image.devicePixelRatio()
    assert image.pixelColor(round(1 * ratio), round(button.height() / 2 * ratio)).name() == '#e9a83b'
    assert box.defaultButton() is box.review_button
    assert box.buttonRole(button) == QMessageBox.ButtonRole.DestructiveRole
    QTest.keyClick(box, Qt.Key.Key_Escape)
    assert box.clickedButton() is box.cancel_button


@pytest.mark.parametrize('mode,want', [('none', 'Bez podfolderów'), ('artist', 'Według wykonawcy'), ('genre', 'Według gatunku')])
def test_preview_organization_strip_tracks_real_mode_and_section_order(app, tmp_path, mode, want):
    plan, library = plan_for(tmp_path)
    dialog = export_dialogs.ExportPreviewDialog(plan.preview_summary, plan=plan, folder_organization=mode)
    dialog.show(); app.processEvents()
    assert hasattr(dialog, 'organization_bar'), 'Approved organization strip is missing'
    assert dialog.organization_value.text() == want
    bar = dialog.organization_bar
    assert bar.height() <= 50
    labels = dialog.body.findChildren(QLabel)
    risk = next(l for l in labels if l.text() == 'Konflikty i ryzyka')
    examples = next(l for l in labels if l.text().startswith('Przykładowe pliki'))
    assert risk.mapTo(dialog.body, risk.rect().bottomLeft()).y() < bar.y() < examples.y()
    assert len(dialog.example_labels) == 6
    assert not list(library.root.rglob('*.mp3'))
    dialog.reject()


def test_summary_action_icons_and_close_have_matching_geometry(app, tmp_path):
    plan, library = plan_for(tmp_path)
    dialog = export_dialogs.ExportSummaryDialog(ExportResult((), (), planned=8, cancelled=True), plan, library.root, None)
    dialog.show(); app.processEvents()
    assert dialog.report_button.iconSize() == dialog.folder_button.iconSize() == QSize(18, 18)
    assert dialog.close_button.height() == dialog.folder_button.height() == dialog.report_button.height() == 40
    assert dialog.close_button.width() >= 112
    assert dialog.close_button.mapTo(dialog.footer, dialog.close_button.rect().center()).x() > dialog.footer.width() / 2
    QTest.keyClick(dialog, Qt.Key.Key_Return)
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_warning_headline_is_not_clipped_after_button_resize(app):
    box = export_dialogs.ExportReviewWarning(2)
    box.show(); app.processEvents()
    label = box.findChild(QLabel, 'qt_msgbox_label')
    assert label.height() >= label.heightForWidth(label.width())
    box.cancel_button.click()
