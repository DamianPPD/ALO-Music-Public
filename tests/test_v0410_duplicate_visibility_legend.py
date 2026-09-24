from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.duplicates.grouper import apply_duplicate_decision, group_potential_duplicates, duplicate_group_count
from audio_library_organizer.ui.state import library_status_presentation, status_presentation

ROOT = Path(__file__).resolve().parents[1]
DUPLICATES = (ROOT / 'src/audio_library_organizer/ui/duplicates_page.py').read_text(encoding='utf-8')
LEGEND_PATH = ROOT / 'src/audio_library_organizer/ui/library_status_legend.py'
MAIN = (ROOT / 'src/audio_library_organizer/main.py').read_text(encoding='utf-8')


def test_resolved_duplicate_group_can_remain_visible_for_decision_review(tmp_path: Path):
    a = TrackRecord(path=tmp_path / 'a.mp3', artist='A', title='Track', duration_seconds=300, status='duplicate')
    b = TrackRecord(path=tmp_path / 'b.mp3', artist='A', title='Track', duration_seconds=301, status='duplicate')
    apply_duplicate_decision(a, 'keep')
    apply_duplicate_decision(b, 'not_selected')

    groups = group_potential_duplicates([a, b], include_resolved=True)

    assert groups == [[a, b]]



def test_resolved_duplicate_group_is_not_counted_as_pending_work(tmp_path: Path):
    a = TrackRecord(path=tmp_path / 'a.mp3', artist='A', title='Track', duration_seconds=300, status='duplicate')
    b = TrackRecord(path=tmp_path / 'b.mp3', artist='A', title='Track', duration_seconds=301, status='duplicate')
    apply_duplicate_decision(a, 'keep')
    apply_duplicate_decision(b, 'not_selected')

    assert duplicate_group_count([a, b]) == 0

def test_duplicates_page_keeps_resolved_groups_visible_and_has_only_three_actions():
    assert 'group_potential_duplicates(tracks, include_resolved=True)' in DUPLICATES
    assert "QPushButton('Następna nierozstrzygnięta')" not in DUPLICATES
    assert 'next_unresolved' not in DUPLICATES
    assert '_select_next_unresolved_group' not in DUPLICATES


def test_library_has_compact_dropdown_status_legend():
    assert LEGEND_PATH.exists()
    legend = LEGEND_PATH.read_text(encoding='utf-8')
    assert 'QToolButton' in legend
    assert 'QMenu' in legend
    assert "setObjectName('LibraryStatusLegendButton')" in legend
    assert "setText('Legenda statusów')" in legend
    assert "setIcon(alo_icon('info'" in legend
    for label in ('GOTOWE', 'DUPLIKAT', 'DO SPRAWDZENIA', 'DO SPRAWDZENIA — ważne', 'NIE WYBIERAM'):
        assert label in legend
    assert 'view_controls.addWidget(button)' in legend
    assert "setObjectName('LibraryStatusLegend')" not in legend
    assert 'install_library_status_legend(window.library)' in MAIN


def test_duplicate_primary_ready_uses_same_green_as_every_other_ready_track(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path / 'selected.mp3',
        artist='A', title='Track', year='2000', genre='House', bpm=128,
        status='ready', locked_fields={'duplicate_primary', '__status__'},
    )

    assert library_status_presentation(track) == status_presentation('ready')
