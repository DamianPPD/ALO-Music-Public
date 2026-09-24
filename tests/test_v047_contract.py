from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
I18N = (ROOT / 'src/audio_library_organizer/ui/i18n.py').read_text(encoding='utf-8')


def test_metadata_editor_exposes_one_whole_track_online_lock_control():
    assert 'Rozpoznawanie online odblokowane' in EDITOR
    assert 'Dane chronione przed ponownym rozpoznaniem online' in EDITOR
    assert 'online_locked' in EDITOR
    assert "setObjectName('OnlineLockButton')" in EDITOR


def test_library_shows_lock_marker_for_online_locked_tracks():
    assert 'is_online_locked' in LIBRARY
    assert "alo_icon('lock' if locked_online" in LIBRARY
    assert 'Zablokowany przed ponownym rozpoznaniem online' in LIBRARY


def test_main_window_persists_editor_lock_and_reports_skipped_tracks():
    assert 'set_online_locked(track, dialog.online_locked())' in MAIN
    assert 'skipped_locked' in MAIN


def test_lock_copy_is_translated_to_english():
    assert 'Zablokuj dane przed ponownym rozpoznaniem online' in I18N
    assert 'Lock data against online re-identification' in I18N
