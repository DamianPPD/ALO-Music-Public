from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.reporting import build_library_health


ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
WORKERS = (ROOT / 'src/audio_library_organizer/ui/workers.py').read_text(encoding='utf-8')


def test_library_health_exposes_practical_cover_and_online_counts(tmp_path: Path):
    tracks = [
        TrackRecord(path=tmp_path/'a.mp3', has_cover=True, size_bytes=100),
        TrackRecord(path=tmp_path/'b.mp3', musicbrainz_recording_id='mb1', size_bytes=200),
        TrackRecord(path=tmp_path/'c.mp3', size_bytes=300),
    ]

    health = build_library_health(tracks)

    assert health['missing_covers'] == 2
    assert health['online_checked'] == 1


def test_dashboard_uses_only_agreed_practical_health_stats():
    for label in (
        'Dostępne pliki',
        'Brakujące pliki',
        'Brak okładki',
        'Utwory sprawdzone online',
        'Rozmiar biblioteki',
        'Wolne miejsce na dysku',
        'Podejrzane dane',
    ):
        assert label in MAIN_WINDOW

    assert 'Liczba gatunków' not in MAIN_WINDOW
    assert 'Najczęstszy gatunek' not in MAIN_WINDOW
    assert 'shutil.disk_usage' in MAIN_WINDOW


def test_metadata_editor_offers_online_scan_for_only_current_track():
    assert 'online_scan_requested = Signal(object)' in EDITOR
    assert 'Rozpoznaj online' in EDITOR
    assert 'SingleTrackOnlineButton' in EDITOR
    assert 'online_scan_requested.emit(self)' in EDITOR


def test_main_window_wires_single_track_scan_to_forced_identification():
    assert 'online_scan_requested.connect' in MAIN_WINDOW
    assert 'force=True' in MAIN_WINDOW
    assert 'tracks=[track]' in MAIN_WINDOW


def test_identification_worker_relays_completion_onto_gui_thread():
    # The relay is created before the worker is moved to its QThread, so it
    # keeps GUI-thread affinity. Raw worker results cross to it explicitly with
    # QueuedConnection before public finished/failed callbacks are invoked.
    assert 'class _GuiThreadRelay(QObject)' in WORKERS
    assert '_raw_finished = Signal(object)' in WORKERS
    assert '_raw_failed = Signal(str)' in WORKERS
    assert 'Qt.ConnectionType.QueuedConnection' in WORKERS
    assert 'self._raw_finished.connect(' in WORKERS
    assert 'self._gui_relay.forward_finished' in WORKERS
    assert 'self._raw_failed.connect(' in WORKERS
    assert 'self._gui_relay.forward_failed' in WORKERS
    assert 'return self._gui_relay.finished' in WORKERS
    assert 'return self._gui_relay.failed' in WORKERS
