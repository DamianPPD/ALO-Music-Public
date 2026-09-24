from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_top_toolbar_keeps_exact_reference_palette_and_custom_icons():
    assert "self.nav_icon_ids = ('home', 'library', 'duplicate', 'folder', 'help', 'settings')" in MAIN
    for pair in (
        "(self.scan_btn, 'scan')",
        "(self.identify_btn, 'search')",
        "(self.review_btn, 'review')",
        "(self.export_btn, 'export')",
        "(self.new_files_btn, 'plus')",
    ):
        assert pair in MAIN
    assert "self.scan_btn: '#43e59a'" in MAIN
    assert "self.export_btn: '#58cfff'" in MAIN
    assert "self.new_files_btn: '#9bd2ff'" in MAIN
    assert 'background:#116b45;' in THEME
    assert 'background:#0b2330;' in THEME
    assert 'background:#0a1e35;' in THEME


def test_editor_section_headers_match_reference_wording_and_icons():
    for text in (
        "Metadane utworu",
        "Status pliku",
        "Okładka (wybierana z listy)",
        "Porównanie źródeł  (pomocniczo)",
    ):
        assert text in EDITOR
    assert "setObjectName('EditorSectionTitle')" in EDITOR
    assert "color:#e7eef3;" in THEME
    assert "editor_icon(icon_name, '#5fd5f2'" in EDITOR


def test_editor_online_and_bottom_actions_use_real_icons():
    assert "QPushButton('Rozpoznaj online')" in EDITOR
    assert "_set_editor_button_icon(self.scan_online_button, 'search', '#e9fdff'" in EDITOR
    assert "QPushButton('Przywróć dane sprzed online')" in EDITOR
    assert "_set_editor_button_icon(self.restore_pre_online_button, 'undo', '#dce8ef'" in EDITOR
    assert "QPushButton('Cofnij ostatnią zmianę')" in EDITOR
    assert "QPushButton('Anuluj zmiany')" not in EDITOR
    assert "_set_editor_button_icon(self.save_button, 'save', '#dce7ee'" in EDITOR
    assert "self.status_button = QPushButton('')" in EDITOR
    assert 'self.status_button.clicked.connect(self._toggle_ready)' in EDITOR
    assert "QPushButton('ZATWIERDŹ JAKO GOTOWE')" not in EDITOR


def test_cover_panel_is_compact_grid_like_reference():
    assert "self.cover_main_preview.setFixedSize(248, 248)" in EDITOR
    assert "self.cover_selected_badge = QLabel(''," in EDITOR
    assert "self.cover_selected_badge.setPixmap(editor_icon('status'" in EDITOR
    assert "self.choose_cover_button = QPushButton('Dodaj')" in EDITOR
    assert "self.search_cover_button = QPushButton('Szukaj okładki online')" in EDITOR
    assert "self.cover_browse_button = QPushButton('Wyszukaj')" not in EDITOR
    assert "self.show_more_covers_button = QPushButton('Pokaż więcej')" in EDITOR
    assert 'Więcej okładek online…' not in EDITOR
    assert 'preview_size = 84' in EDITOR
    assert 'columns = 2' in EDITOR
    assert "entries.append(('placeholder', 'BRAK OKŁADKI'))" in EDITOR


def test_source_table_is_compact_and_source_marker_is_larger_than_text():
    assert 'header.setFixedHeight(27)' in EDITOR
    assert 'self.source_table.verticalHeader().setDefaultSectionSize(31)' in EDITOR
    assert "source_dot.setPixmap(_color_dot_icon" in EDITOR
    assert "self.source_table.setCellWidget(row, 0, source_cell)" in EDITOR
    assert "font.setPointSizeF(max(7.2, font.pointSizeF() - 1.0))" in EDITOR
    assert 'header.resizeSection(5, 126)' in EDITOR
    assert 'use_button.setFixedSize(82, 18)' in EDITOR
    assert "cell.setObjectName('UseSourceDataCell')" in EDITOR
