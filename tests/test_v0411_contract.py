from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUPLICATES = (ROOT / 'src/audio_library_organizer/ui/duplicates_page.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
LEGEND = (ROOT / 'src/audio_library_organizer/ui/library_status_legend.py').read_text(encoding='utf-8')
BASE_THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/v0411_theme.py').read_text(encoding='utf-8')
HELP = (ROOT / 'src/audio_library_organizer/help_content.py').read_text(encoding='utf-8')


def test_duplicate_decision_color_is_limited_to_decision_cell():
    assert 'if col == len(self.COLUMNS) - 1 and decision_background is not None:' in DUPLICATES
    assert "QColor('#173c2d')" in DUPLICATES
    assert "QColor('#2a3038')" in DUPLICATES
    assert 'ZACHOWAJ = zielona komórka decyzji' in DUPLICATES
    assert 'NIE WYBIERAM = szara' in DUPLICATES


def test_editor_footer_uses_one_two_state_status_toggle():
    assert "kind = effective_status(self.track)" in EDITOR
    assert "self.status_button.setProperty('currentStatusKind', 'ready' if self.mark_ready else 'review')" in EDITOR
    from audio_library_organizer.ui import theme as base_theme
    from audio_library_organizer.ui.v0411_theme import install_v0411_base_overrides
    original = base_theme.DARK_STYLE
    try:
        base_theme.DARK_STYLE = original.replace('QPushButton#CurrentStatusButton[currentStatusKind="not_selected"] { background:#30363f; border-color:#68727e; color:#d4d9df; }', '')
        install_v0411_base_overrides()
        assert 'QPushButton#CurrentStatusButton[currentStatusKind="not_selected"]' in base_theme.DARK_STYLE
    finally:
        base_theme.DARK_STYLE = original
    assert 'QFrame#CurrentStatusBanner[statusKind="not_selected"]' in BASE_THEME


def test_library_legend_is_dropdown_in_existing_view_controls():
    assert 'view_controls.addWidget(button)' in LEGEND
    assert "setObjectName('LibraryStatusLegendButton')" in LEGEND
    assert 'QMenu' in LEGEND
    assert 'DO SPRAWDZENIA — ważne' in LEGEND


def test_operation_panel_has_clear_bottom_separator():
    assert 'border-bottom:3px solid #2f7f8d' in THEME


def test_help_describes_decision_cell_not_entire_row():
    assert 'kolumnie <b>Decyzja</b>' in HELP
    assert 'koloruje cały wiersz' not in HELP


def test_duplicate_delegate_removes_single_cell_focus_frame():
    assert 'State_HasFocus' in DUPLICATES
    assert 'clean.state &= ~QStyle.StateFlag.State_HasFocus' in DUPLICATES
