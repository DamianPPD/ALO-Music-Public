from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / 'src/audio_library_organizer/ui/dashboard_page.py'
MAIN = (ROOT / 'src/audio_library_organizer/main.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/v0411_theme.py').read_text(encoding='utf-8')


def _dashboard_source() -> str:
    return DASHBOARD.read_text(encoding='utf-8')


def test_start_dashboard_uses_compact_path_bar_without_redundant_subtitle():
    source = _dashboard_source()
    assert "QLabel('Biblioteka ALO Music')" not in source
    assert "self.library_label = QLabel" in source
    assert "self.open_folder_button = QPushButton('Otwórz folder')" in source
    assert "self.dashboard_title = QLabel('Biblioteka główna')" in source


def test_start_dashboard_has_four_clickable_quick_counters():
    source = _dashboard_source()
    for key, label in (
        ('total', 'Utwory'),
        ('review', 'Do sprawdzenia'),
        ('duplicate', 'Duplikaty'),
        ('missing_covers', 'Brak okładki'),
    ):
        assert f"'{key}': DashboardStatCard('{label}'" in source
    assert 'quick_view_requested = Signal(str)' in source
    assert "self.cards['total'].clicked.connect(lambda: self.quick_view_requested.emit('all'))" in source
    assert "self.cards['review'].clicked.connect(lambda: self.quick_view_requested.emit('review'))" in source
    assert "self.cards['duplicate'].clicked.connect(lambda: self.quick_view_requested.emit('duplicate'))" in source
    assert "self.cards['missing_covers'].clicked.connect(lambda: self.quick_view_requested.emit('no_cover'))" in source


def test_start_dashboard_does_not_duplicate_global_workflow_buttons():
    source = _dashboard_source()
    for marker in (
        "self.scan_button = QPushButton('▣ Skanuj bibliotekę')",
        "self.identify_button = QPushButton('◎ Rozpoznaj online')",
        "self.duplicates_button = QPushButton('◈ Duplikaty')",
        'identify_requested = Signal()',
        'duplicates_requested = Signal()',
    ):
        assert marker not in source


def test_start_dashboard_has_compact_library_statistics_without_unwanted_metrics():
    source = _dashboard_source()
    assert "QLabel('Statystyki biblioteki')" in source
    for key, label in (
        ('covers', 'OKŁADKI'),
        ('online', 'ROZPOZNANE ONLINE'),
        ('missing', 'BRAKUJĄCE PLIKI'),
        ('suspicious', 'PODEJRZANE DANE'),
        ('size', 'ROZMIAR BIBLIOTEKI'),
        ('free_space', 'WOLNE MIEJSCE'),
    ):
        assert f"('{key}', '{label}')" in source
    assert 'LICZBA GATUNKÓW' not in source
    assert 'ŚREDNIE BPM' not in source
    assert "('ready', 'GOTOWE')" not in source
    assert "self.stats_values['covers'].setText" in source
    assert "self.stats_values['online'].setText" in source


def test_start_dashboard_shows_attention_only_when_there_is_something_to_fix():
    source = _dashboard_source()
    assert 'self.attention_frame.setVisible(bool(parts))' in source
    for phrase in ('{review} do sprawdzenia', '{duplicate} grup duplikatów',
                   '{missing_covers} bez okładki', '{missing} brakujących plików'):
        assert f"parts.append(ui_text(self, f'{phrase}'))" in source


def test_last_scan_is_compact_and_persisted_per_library():
    source = _dashboard_source()
    assert 'dashboard/last_scan/' in source
    assert 'Ostatnie skanowanie:' in source
    assert 'self._save_last_scan(now)' in source
    assert 'self._load_last_scan()' in source


def test_start_dashboard_does_not_repeat_version_in_bottom_right_corner():
    source = _dashboard_source()
    assert "QLabel(f'ALO Music v{__version__}')" not in source
    assert 'from audio_library_organizer import __version__' not in source


def test_main_installs_dashboard_and_wires_quick_views_only():
    assert 'main_window_ui.DashboardPage = DashboardPage' in MAIN
    assert 'def _wire_dashboard_actions(window):' in MAIN
    assert "dashboard.quick_view_requested.connect(lambda key: _open_dashboard_quick_view(window, key))" in MAIN
    assert 'dashboard.identify_requested.connect' not in MAIN
    assert 'dashboard.duplicates_requested.connect' not in MAIN
    assert "if key == 'duplicate':" in MAIN
    assert "index = window.library.status.findData(key)" in MAIN


def test_startup_loader_shows_version_and_ready_track_count():
    assert 'from audio_library_organizer import __version__' in MAIN
    assert "version = QLabel(f'ALO Music v{__version__}')" in MAIN
    assert "status = QLabel(translate_static_text('Ładowanie biblioteki…', language))" in MAIN
    assert 'loader.status_label = status' in MAIN
    assert "setText(f'Gotowe: {total} utworów')" in MAIN
    assert 'QTimer.singleShot(450, startup_loader.close)' in MAIN


def test_player_seek_slider_is_visibly_thicker_than_volume_slider():
    assert 'QSlider#SeekSlider::groove:horizontal { height:12px;' in THEME
    assert 'QSlider#SeekSlider::handle:horizontal { width:24px;' in THEME
    assert 'QSlider#VolumeSlider::groove:horizontal { height:6px;' in THEME
