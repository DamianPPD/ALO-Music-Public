from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.state import effective_status, library_status_presentation, review_reasons, review_severity

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
PLAYER = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
REPORTING = (ROOT / 'src/audio_library_organizer/jobs/reporting.py').read_text(encoding='utf-8')
HELP = (ROOT / 'src/audio_library_organizer/help_content.py').read_text(encoding='utf-8')


def _track(name='x.mp3', **changes):
    base = dict(
        path=Path(name), size_bytes=1000, mtime_ns=1,
        artist='Artist', title='Title', year='2001', genre='House', bpm=128,
        status='ready', confidence=0.9,
    )
    base.update(changes)
    return TrackRecord(**base)


def test_manual_complete_ready_stays_ready_even_with_old_warning_and_low_confidence():
    track = _track(confidence=0.20, match_reasons=['Duża różnica względem danych sprzed online'])
    track.locked_fields.add('__status__')
    assert effective_status(track) == 'ready'
    assert review_reasons(track) == []


def test_unlocked_low_confidence_ready_becomes_review():
    track = _track(confidence=0.50)
    assert effective_status(track) == 'review'
    assert 'Niska pewność rozpoznania' in review_reasons(track)


def test_review_has_amber_and_critical_red_variants_but_same_label():
    normal = _track(status='review', confidence=0.60)
    critical = _track(status='review', artist=None, confidence=0.20)
    assert review_severity(normal) == 'normal'
    assert review_severity(critical) == 'critical'
    assert library_status_presentation(normal).label == 'DO SPRAWDZENIA'
    assert library_status_presentation(critical).label == 'DO SPRAWDZENIA'
    assert library_status_presentation(normal).accent != library_status_presentation(critical).accent


def test_library_has_no_decision_filter_or_previous_next_review_navigation():
    assert "('Do decyzji', 'decision')" not in LIBRARY
    assert "QPushButton('← Poprzedni')" not in LIBRARY
    assert "QPushButton('Następny →')" not in LIBRARY
    assert 'decision_queue(self._tracks)' not in LIBRARY


def test_user_facing_report_and_help_no_longer_call_review_do_decyzji():
    assert '>Do decyzji<' not in REPORTING
    assert '<h2>Do decyzji</h2>' not in REPORTING
    assert "'Do decyzji i cofanie zmian'" not in HELP


def test_metadata_editor_keeps_status_only_on_bottom_action_and_active_url_action():
    assert 'AKTUALNY STATUS:' not in EDITOR
    assert "self.status_button.setText(ui_text(self, 'GOTOWE')" in EDITOR
    assert "self.status_button.setProperty('currentStatusKind', 'ready' if self.mark_ready else 'review')" in EDITOR
    assert "status_card.setObjectName('MetadataStatusCompact')" in EDITOR
    assert 'Otwórz link' in EDITOR
    assert 'QDesktopServices.openUrl' in EDITOR
    assert "scheme() in {'http', 'https'}" in EDITOR


def test_library_single_selection_does_not_replace_current_media_and_double_click_plays():
    assert 'self.library.track_selected.connect(lambda track: self.player.load_track(track, autoplay=False))' not in MAIN
    assert 'self.table.doubleClicked.connect(self._play_selected)' in LIBRARY
    assert 'set_playing_track' in LIBRARY
    assert 'TERAZ GRA' in LIBRARY


def test_player_supports_source_label_and_queue_next():
    assert 'track_changed = Signal(object)' in PLAYER
    assert 'queue_next' in PLAYER
    assert 'Źródło:' in PLAYER
    assert 'Następny:' in PLAYER
    assert 'Odtwórz jako następny' in LIBRARY


def test_player_runtime_source_and_queue_labels_use_ui_translation():
    assert 'from audio_library_organizer.ui.i18n import ui_text' in PLAYER
    assert "ui_text(self, 'Źródło:')" in PLAYER
    assert "ui_text(self, 'Następny:')" in PLAYER
