from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUPLICATES = (ROOT / 'src/audio_library_organizer/ui/duplicates_page.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
PLAYER = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
HELP = (ROOT / 'src/audio_library_organizer/help_content.py').read_text(encoding='utf-8')
INIT = (ROOT / 'src/audio_library_organizer/__init__.py').read_text(encoding='utf-8')
PYPROJECT = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
START = (ROOT / 'START_HERE.txt').read_text(encoding='utf-8')


def test_duplicates_have_only_decision_column_no_separate_status_column():
    assert "'Status', 'Decyzja'" not in DUPLICATES
    assert "COLUMNS = ('Wariant', 'Nazwa pliku', 'Długość', 'BPM', 'Format', 'Bitrate', 'Hz', 'Rozmiar', 'Decyzja')" in DUPLICATES
    assert 'DuplicateStatusBadge' not in DUPLICATES
    assert 'def _technical_status_text' not in DUPLICATES


def test_duplicate_rows_use_only_decision_colors_without_orange_difference_highlight():
    assert "QColor('#173c2d')" in DUPLICATES
    assert "QColor('#2a3038')" in DUPLICATES
    assert 'if col == len(self.COLUMNS) - 1 and decision_background is not None:' in DUPLICATES
    assert 'item.setBackground(QBrush(decision_background))' in DUPLICATES
    assert "difference_background = QColor('#302719')" not in DUPLICATES
    assert "difference_foreground = QColor('#ffd27a')" not in DUPLICATES
    assert 'difference_columns' not in DUPLICATES


def test_duplicates_show_progress_without_extra_next_unresolved_button():
    assert 'ui_text(self, "decyzje")' in DUPLICATES
    assert ' {decided}/{len(group)}' in DUPLICATES
    assert "QPushButton('Następna nierozstrzygnięta')" not in DUPLICATES
    assert 'def _select_next_unresolved_group' not in DUPLICATES


def test_library_refresh_preserves_user_view_state_instead_of_resetting_sorting():
    for needle in (
        'def _capture_view_state',
        'def _restore_view_state',
        'sortIndicatorSection()',
        'sortIndicatorOrder()',
        'self.table.sortByColumn(',
        'verticalScrollBar().value()',
        'verticalScrollBar().setValue(',
        'self.table.columnWidth(',
        'self.table.setColumnWidth(',
    ):
        assert needle in LIBRARY


def test_library_has_visible_sort_filter_summary_and_explicit_reset_only():
    assert "setObjectName('LibraryViewState')" in LIBRARY
    assert "QPushButton('Resetuj widok')" in LIBRARY
    assert 'def _update_view_state_label' in LIBRARY
    assert 'def _reset_view' in LIBRARY
    assert 'sortIndicatorChanged.connect(self._update_view_state_label)' in LIBRARY


def test_player_transport_is_flat_compact_and_seek_focused():
    assert "self.back.setObjectName('PlayerIconButton')" in PLAYER
    assert "self.repeat.setObjectName('PlayerIconButton')" in PLAYER


def test_help_describes_decision_colors_without_separate_duplicate_status_column():
    assert 'Status DUPLIKAT jest osobnym oznaczeniem technicznym' not in HELP
    assert 'kolumnie <b>Decyzja</b>' in HELP
    assert 'NIE WYBIERAM' in HELP and 'szaro' in HELP


def test_version_is_0415_in_runtime_and_package_metadata():
    assert "__version__ = '0.4.24'" in INIT
    assert 'version = "0.4.24"' in PYPROJECT
    assert 'v0.4.24' in START
