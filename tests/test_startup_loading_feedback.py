from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/main.py').read_text(encoding='utf-8')
REPOSITORY = (ROOT / 'src/audio_library_organizer/storage/repository.py').read_text(encoding='utf-8')


def test_startup_displays_busy_loader_before_main_window_is_built():
    assert 'def _show_startup_loader' in MAIN
    assert "QProgressBar" in MAIN
    assert "setRange(0, 0)" in MAIN
    assert 'Ładowanie biblioteki' in MAIN
    assert 'app.processEvents()' in MAIN
    assert MAIN.index('_show_startup_loader') < MAIN.index('window = MainWindow')


def test_startup_loader_uses_existing_alo_branding_assets():
    assert "asset_path('alo.ico')" in MAIN
    assert "asset_path('alo_icon.png')" in MAIN
    assert 'setWindowIcon' in MAIN
    assert 'QPixmap' in MAIN


def test_availability_sync_only_updates_rows_when_state_changed(tmp_path, monkeypatch):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.storage import repository

    repo = repository.LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    path = tmp_path / 'missing.mp3'
    track = TrackRecord(path=path)
    repo.upsert_track(track)
    statements = []
    real_connect = repository.connect

    def traced_connect(database_path):
        conn = real_connect(database_path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(repository, 'connect', traced_connect)
    assert repo.sync_availability().missing == 1
    updates = [sql for sql in statements if sql.startswith('UPDATE tracks')]
    assert len(updates) == 1
    assert f"WHERE track_id='{track.track_id}'" in updates[0]
    assert repo.get_track(track.track_id).is_available is False
    statements.clear()
    repo.sync_availability()
    assert not any(sql.startswith('UPDATE tracks') for sql in statements)
