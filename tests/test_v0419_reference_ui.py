from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_top_toolbar_keeps_workflow_actions_with_single_start_accent(current_start_window):
    from PySide6.QtWidgets import QApplication, QFrame, QPushButton

    window = current_start_window
    group = window.action_frame.findChild(QFrame, 'WorkflowToolbarGroup')
    buttons = group.findChildren(QPushButton)
    assert buttons == [window.scan_btn, window.identify_btn, window.review_btn, window.export_btn]
    assert [button.text().split('.')[0] for button in buttons] == ['1', '2', '3', '4']
    images = [button.icon().pixmap(23, 23).toImage() for button in buttons]
    assert all(not image.isNull() for image in images)
    assert all(first != second for i, first in enumerate(images) for second in images[i + 1:])
    assert [button.isChecked() for button in window.nav_buttons] == [True, False, False, False, False, False]
    window.nav_buttons[1].click()
    QApplication.instance().processEvents()
    assert [button.isChecked() for button in window.nav_buttons] == [False, True, False, False, False, False]
    assert window.stack.currentIndex() == 1
    assert window.review_btn.property('operationActive') is True
    assert all(not button.property('operationActive') for button in buttons if button is not window.review_btn)
    window.nav_buttons[0].click()
    QApplication.instance().processEvents()
    assert window.stack.currentIndex() == 0 and window.nav_buttons[0].isChecked()
    assert all(not button.property('operationActive') for button in buttons)


def test_editor_section_headers_match_reference_wording_and_icons():
    for text in (
        "Metadane utworu",
        "Szczegóły rozpoznania",
        "Wybór okładki",
        "Porównanie źródeł",
    ):
        assert text in EDITOR
    assert "setObjectName('EditorSectionTitle')" in EDITOR
    assert "color:#e7eef3;" in THEME
    assert "mark.setObjectName('LibrarySectionMark')" in EDITOR


def test_editor_online_and_bottom_actions_use_real_icons():
    assert "QPushButton('Rozpoznaj online')" in EDITOR
    assert "_set_editor_button_icon(self.scan_online_button, 'editor_online_recognize', '#74e9fc'" in EDITOR
    assert "QPushButton('Przywróć dane sprzed online')" in EDITOR
    assert "_set_editor_button_icon(self.restore_pre_online_button, 'undo', '#dce8ef'" in EDITOR
    assert "QPushButton('Cofnij ostatnią zmianę')" in EDITOR
    assert "QPushButton('Anuluj zmiany')" not in EDITOR
    assert "_set_editor_button_icon(self.save_button, 'save', '#dce7ee'" in EDITOR
    assert "self.status_button = QPushButton('')" in EDITOR
    assert 'self.status_button.clicked.connect(self._toggle_ready)' in EDITOR
    assert "QPushButton('ZATWIERDŹ JAKO GOTOWE')" not in EDITOR


def test_cover_panel_is_compact_grid_like_reference():
    assert "self.cover_main_preview.setFixedSize(288, 288)" in EDITOR
    assert 'self.cover_selected_badge' not in EDITOR
    assert "selected_badge.setObjectName('CoverProposalSelectedMarker')" in EDITOR
    assert "self.choose_cover_button = QPushButton('Dodaj okładkę z pliku')" in EDITOR
    assert "self.search_cover_button = QPushButton('Szukaj okładki online')" in EDITOR
    assert "self.cover_browse_button = QPushButton('Wyszukaj')" not in EDITOR
    assert "self.show_more_covers_button = QPushButton('Pokaż więcej')" not in EDITOR
    assert 'Więcej okładek online…' not in EDITOR
    assert 'columns = 2' in EDITOR
    assert "entries.append(('placeholder', 'BRAK OKŁADKI'))" in EDITOR


def test_source_table_is_compact_and_source_marker_is_larger_than_text():
    assert 'header.setFixedHeight(27)' in EDITOR
    assert 'self.source_table.verticalHeader().setDefaultSectionSize(31)' in EDITOR
    assert "source_item.setIcon(editor_icon('audio_recognize'" in EDITOR
    assert "self.source_table.setItem(row, 0, source_item)" in EDITOR
    assert "font.setPointSizeF(max(7.2, font.pointSizeF() - 1.0))" in EDITOR
    # Live action caption sizing and the expanded 2×2 geometry are exercised
    # by test_metadata_editor_states_v0425 rather than source-text snapshots.
    assert "cell.setObjectName('UseSourceDataCell')" in EDITOR
