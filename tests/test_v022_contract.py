from pathlib import Path

from audio_library_organizer.domain.candidates import MetadataCandidate
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.manual_edits import apply_manual_field
from audio_library_organizer.matching.resolver import apply_candidate

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
DUPLICATES = (ROOT / 'src/audio_library_organizer/ui/duplicates_page.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
PLAYER = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_title_normalization_uses_clear_title_case_and_preserves_common_acronyms(tmp_path: Path):
    from audio_library_organizer.metadata.naming import normalize_title_case

    assert normalize_title_case('TAKE ME AWAY (DAVE DARELL REMIX)') == 'Take Me Away (Dave Darell Remix)'
    assert normalize_title_case('HEAVEN (DJ SAMMY VIP MIX)') == 'Heaven (DJ Sammy VIP Mix)'
    assert normalize_title_case('LOVE II') == 'Love II'

    track = TrackRecord(path=tmp_path / 'x.mp3', title='old')
    apply_manual_field([track], 'title', 'ALL NIGHT LONG (VIP MIX)')
    assert track.title == 'All Night Long (VIP Mix)'


def test_artist_spelling_is_not_title_cased_by_manual_normalization(tmp_path: Path):
    track = TrackRecord(path=tmp_path / 'x.mp3', artist='old')
    apply_manual_field([track], 'artist', 'deadmau5')
    assert track.artist == 'deadmau5'


def test_pre_online_snapshot_can_restore_identity_and_main_metadata(tmp_path: Path):
    from audio_library_organizer.metadata.provenance import snapshot_pre_online, restore_pre_online

    track = TrackRecord(
        path=tmp_path / 'x.mp3', artist='Armani & Ghost', title='Airport (Original Mix)',
        album='Airport', year='2003', genre='Hard House / Jumpstyle', bpm=139,
    )
    snapshot_pre_online(track)
    assert track.pre_online_metadata['artist'] == 'Armani & Ghost'
    assert track.pre_online_metadata['bpm'] == 139

    track.artist = 'Wrong Artist'; track.title = 'Wrong Track'; track.year = '2020'; track.genre = 'Pop'; track.bpm = 120
    restore_pre_online(track)
    assert track.artist == 'Armani & Ghost'
    assert track.title == 'Airport (Original Mix)'
    assert track.year == '2003'
    assert track.genre == 'Hard House / Jumpstyle'
    assert track.bpm == 139


def test_suspicious_online_identity_change_is_flagged_for_review(tmp_path: Path):
    from audio_library_organizer.metadata.provenance import snapshot_pre_online

    track = TrackRecord(
        path=tmp_path / 'x.mp3', artist='Armani & Ghost', title='Airport (Original Mix)',
        year='2003', genre='Hard House', bpm=139, status='ready',
    )
    snapshot_pre_online(track)
    candidate = MetadataCandidate(
        source='discogs', artist='Completely Different Artist', title='Another Song',
        year='2020', genre='Pop', score=0.96, reasons=('test',),
    )
    apply_candidate(track, candidate)
    assert track.status == 'review'
    assert any('Duża różnica' in reason for reason in track.match_reasons)


def test_online_candidate_title_is_normalized_but_artist_is_preserved(tmp_path: Path):
    track = TrackRecord(path=tmp_path / 'x.mp3', artist='Old', title='Old', status='review')
    candidate = MetadataCandidate(
        source='discogs', artist='deadmau5', title='SOME CHORDS (VIP MIX)', score=0.9,
    )
    apply_candidate(track, candidate)
    assert track.artist == 'deadmau5'
    assert track.title == 'Some Chords (VIP Mix)'


def test_duplicate_page_has_only_keep_reject_and_edit_actions():
    assert "self.keep = QPushButton('ZACHOWAJ')" in DUPLICATES
    assert "self.reject = QPushButton('NIE WYBIERAM')" in DUPLICATES
    assert "self.edit_track = QPushButton('EDYTUJ')" in DUPLICATES
    assert "QPushButton('◈ DUPLIKAT')" not in DUPLICATES
    assert "QPushButton('☆ OSOBNA WERSJA')" not in DUPLICATES
    assert "self.files.setObjectName('DuplicateFiles')" in DUPLICATES
    assert 'QListWidget#DuplicateFiles::item:selected' in THEME


def test_duplicate_top_navigation_integrates_count_into_colored_button():
    assert 'duplicate_nav_badge' not in MAIN
    assert 'duplicate_group_count(tracks)' in MAIN
    assert 'setText(f"{duplicate_label} ({duplicate_groups})")' in MAIN
    assert "setProperty('hasItems'" in MAIN
    assert 'TopNavButton[hasItems="true"]' in THEME


def test_library_filter_starts_with_emphasized_all_tracks_then_statuses():
    all_pos = LIBRARY.index("'Wszystkie utwory', 'all'")
    ready_pos = LIBRARY.index("'Gotowe', 'ready'")
    assert all_pos < ready_pos
    assert "self.status.model().item(all_index).setData" in LIBRARY


def test_technical_data_heading_is_prominent():
    assert "self.technical_toggle = QPushButton('DANE TECHNICZNE')" in LIBRARY
    assert "self.technical_toggle.setIcon(alo_icon('settings'" in LIBRARY
    assert 'QPushButton#DisclosureButton' in THEME
    assert 'font-weight:800' in THEME[THEME.index('QPushButton#DisclosureButton'):]


def test_library_refresh_forces_details_to_update_after_reselect():
    refresh_start = LIBRARY.index('def refresh(')
    select_start = LIBRARY.index('def _track_is_playing', refresh_start)
    refresh_body = LIBRARY[refresh_start:select_start]
    assert 'self._show_detail()' in refresh_body


def test_settings_use_radio_choices_and_live_highlighted_folder_path():
    assert 'QRadioButton' in MAIN
    assert 'self.folder_org = QComboBox()' not in MAIN
    for key in ('none', 'artist', 'genre'):
        assert f"self.folder_org_buttons['{key}']" in MAIN
    assert "self.folder_preview.setTextFormat(Qt.TextFormat.RichText)" in MAIN
    assert '<b style=' in MAIN
    assert "Muzyka do skanowania" not in MAIN
    assert 'Wybierz główną lokalizację biblioteki ALO.' in MAIN
    assert 'Zmień lokalizację' in MAIN
    assert "Otwórz GOTOWE" not in MAIN


def test_settings_sections_have_stronger_visual_separation():
    for object_name in ('LocationCard', 'NamingCard', 'FolderOrganizationCard', 'IntegrationCard', 'ContactFooter'):
        assert f'QFrame#{object_name}' in THEME
    assert 'SettingsSectionDivider' in MAIN
    assert 'QFrame#SettingsSectionDivider' in THEME


def test_metadata_editor_shows_compact_pre_online_snapshot_and_restore_button():
    assert 'self.track_header_title = SelectableElidedLineEdit' in EDITOR
    assert 'self.pre_online_summary = self.track_header_title' in EDITOR
    assert "Przywróć dane sprzed online" in EDITOR
    assert 'PreOnlineSnapshotCard' in EDITOR
    assert 'SuspiciousOnlineWarning' in EDITOR


def test_metadata_editor_removes_before_after_compare_but_keeps_filename_snapshot_and_source_badges():
    assert 'CompareBeforeCard' not in EDITOR
    assert 'CompareAfterCard' not in EDITOR
    assert 'FilenamePreviewCard' in EDITOR
    assert 'MetadataSourceBadge' in EDITOR
    for object_name in ('FilenamePreviewCard', 'PreOnlineSnapshotCard'):
        assert f'QFrame#{object_name}' in THEME


def test_metadata_editor_marks_changed_fields_and_main_window_reselects_after_save():
    assert 'def _refresh_change_highlights' in EDITOR
    assert "setProperty('changed'" in EDITOR
    assert 'self.library.select_track_by_path(track.path)' in MAIN


def test_player_uses_compact_flat_footer_layout():
    assert "self.play.setFixedSize(58, 58)" in PLAYER
    assert "alo_icon('repeat'" in PLAYER
    assert "timeline = QHBoxLayout()" in PLAYER
    assert 'QFrame#PlayerCard' in THEME
    assert 'QPushButton#PlayerIconButton' in THEME


def test_manual_completion_immediately_promotes_review_track_to_ready(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path / 'x.mp3', artist='Armani & Ghost', title='Airport (Original Mix)',
        year=None, genre='Hard House', bpm=139, status='review',
    )
    apply_manual_field([track], 'year', '2003')
    assert track.status == 'ready'


def test_metadata_editor_has_local_undo_button_for_current_edit_session():
    assert "QPushButton('Cofnij ostatnią zmianę')" in EDITOR
    assert "_set_editor_button_icon(self.undo_button, 'undo'" in EDITOR
    assert 'def _undo_editor_change' in EDITOR
