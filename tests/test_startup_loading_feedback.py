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


def test_availability_sync_only_updates_rows_when_state_changed():
    assert 'if exists != track.is_available:' in REPOSITORY
    assert "conn.executemany('UPDATE tracks SET is_available=? WHERE path=?'" in REPOSITORY
