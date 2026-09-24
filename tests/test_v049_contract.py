from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUPLICATES = (ROOT / 'src/audio_library_organizer/ui/duplicates_page.py').read_text(encoding='utf-8')


def test_duplicate_decision_rows_keep_green_and_gray_backgrounds():
    color_body = DUPLICATES.split('def _decision_color', 1)[1].split('def _duration', 1)[0]
    assert "QColor('#173c2d')" in color_body
    assert "QColor('#2a3038')" in color_body
    assert 'decision_background = self._decision_color(track)' in DUPLICATES
    assert 'item.setBackground(QBrush(decision_background))' in DUPLICATES


def test_selected_duplicate_row_keeps_decision_color_and_gets_blue_outline():
    assert 'class DuplicateRowDelegate' in DUPLICATES
    assert 'State_Selected' in DUPLICATES
    assert "QColor('#5ca3ff')" in DUPLICATES
    assert 'setItemDelegate(DuplicateRowDelegate' in DUPLICATES
