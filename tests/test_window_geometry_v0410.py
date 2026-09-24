from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/main.py').read_text(encoding='utf-8')


def test_main_window_restores_and_saves_user_geometry():
    assert "store.value('main_window/geometry')" in MAIN
    assert 'window.restoreGeometry(saved_geometry)' in MAIN
    assert "store.setValue('main_window/geometry', window.saveGeometry())" in MAIN
    assert 'app.aboutToQuit.connect(save_window_geometry)' in MAIN


def test_main_window_has_safe_minimum_size():
    assert 'window.setMinimumSize(1180, 720)' in MAIN
