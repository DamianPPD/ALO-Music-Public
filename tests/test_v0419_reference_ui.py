from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_top_toolbar_keeps_workflow_actions_with_single_start_accent():
    assert "self.nav_icon_ids = ('nav_start', 'nav_library', 'nav_duplicates', 'nav_folders', 'nav_help', 'nav_settings')" in MAIN
    for pair in (
        "(self.scan_btn, 'scan')",
        "(self.identify_btn, 'search')",
        "(self.review_btn, 'review')",
        "(self.export_btn, 'export')",
        "(self.new_files_btn, 'plus')",
    ):
        assert pair in MAIN
    assert "self.scan_btn: '#dbe8e2'" in MAIN
    assert "self.export_btn: '#dbe8e2'" in MAIN
    assert "self.new_files_btn: '#dbe8e2'" in MAIN
    assert "bg = '#102b21' if active else '#0c1920'" in MAIN
    assert 'QPushButton#TopNavButton:checked' in THEME
    assert 'border-bottom:2px solid #4cde96' in THEME


def test_editor_section_headers_match_reference_wording_and_icons():
    for text in (
        "Metadane utworu",
        "Szczegóły rozpoznania",
        "Okładka (wybierana z listy)",
        "Porównanie źródeł  (pomocniczo)",
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
    assert "self.choose_cover_button = QPushButton('Dodaj')" in EDITOR
    assert "self.search_cover_button = QPushButton('Szukaj okładki online')" in EDITOR
    assert "self.cover_browse_button = QPushButton('Wyszukaj')" not in EDITOR
    assert "self.show_more_covers_button = QPushButton('Pokaż więcej')" not in EDITOR
    assert 'Więcej okładek online…' not in EDITOR
    assert 'preview_size = 90' in EDITOR
    assert 'columns = 2' in EDITOR
    assert "entries.append(('placeholder', 'BRAK OKŁADKI'))" in EDITOR


def test_source_table_is_compact_and_source_marker_is_larger_than_text():
    assert 'header.setFixedHeight(27)' in EDITOR
    assert 'self.source_table.verticalHeader().setDefaultSectionSize(31)' in EDITOR
    assert "source_item.setIcon(editor_icon('audio_recognize'" in EDITOR
    assert "self.source_table.setItem(row, 0, source_item)" in EDITOR
    assert "font.setPointSizeF(max(7.2, font.pointSizeF() - 1.0))" in EDITOR
    assert '6: 126' in EDITOR
    assert 'use_button.setFixedSize(82, 18)' in EDITOR
    assert "cell.setObjectName('UseSourceDataCell')" in EDITOR
