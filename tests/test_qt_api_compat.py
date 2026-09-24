from pathlib import Path


UNSCOPED_ENUM_ALIASES = {
    'Qt.Horizontal': 'Qt.Orientation.Horizontal',
    'Qt.AlignCenter': 'Qt.AlignmentFlag.AlignCenter',
    'Qt.TextSelectableByMouse': 'Qt.TextInteractionFlag.TextSelectableByMouse',
    'Qt.LinksAccessibleByMouse': 'Qt.TextInteractionFlag.LinksAccessibleByMouse',
    'Qt.UserRole': 'Qt.ItemDataRole.UserRole',
    'Qt.KeepAspectRatio': 'Qt.AspectRatioMode.KeepAspectRatio',
    'Qt.SmoothTransformation': 'Qt.TransformationMode.SmoothTransformation',
    'Qt.MatchExactly': 'Qt.MatchFlag.MatchExactly',
    'QTableView.SelectRows': 'QAbstractItemView.SelectionBehavior.SelectRows',
    'QAbstractItemView.ExtendedSelection': 'QAbstractItemView.SelectionMode.ExtendedSelection',
    'QMediaPlayer.PlayingState': 'QMediaPlayer.PlaybackState.PlayingState',
    'QMessageBox.Yes': 'QMessageBox.StandardButton.Yes',
    'QMessageBox.No': 'QMessageBox.StandardButton.No',
}


def test_gui_uses_scoped_qt6_enums_for_current_pyside6_compatibility():
    ui_root = Path('src/audio_library_organizer/ui')
    offenders = []
    for path in ui_root.glob('*.py'):
        text = path.read_text(encoding='utf-8')
        for old, new in UNSCOPED_ENUM_ALIASES.items():
            if old in text:
                offenders.append(f'{path}: {old} -> {new}')
    assert offenders == [], '\n'.join(offenders)


def test_settings_ui_marks_folder_selection_as_persistent_and_scan_can_be_cancelled():
    main_window = Path('src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
    assert 'Biblioteka docelowa jest zapamiętywana między uruchomieniami' in main_window
    assert 'Anuluj skanowanie' in main_window


def test_dashboard_does_not_duplicate_main_toolbar_action_buttons_and_player_is_prominent():
    main_window = Path('src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
    player = Path('src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
    theme = Path('src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')

    # The dashboard stays compact; the top toolbar owns the workflow actions.
    dashboard_section = main_window.split('class DashboardPage', 1)[1].split('class SettingsPage', 1)[0]
    assert "QPushButton('1. Skanuj" not in dashboard_section
    assert "QPushButton('2. Rozpoznaj" not in dashboard_section
    assert "QPushButton('3. Skopiuj" not in dashboard_section
    assert 'Etapy pracy' not in dashboard_section

    assert "setObjectName('PlayButton')" in player
    assert 'setFixedSize(58, 58)' in player
    assert 'QPushButton#PlayButton' in theme


def test_v017_layout_uses_top_navigation_collapsible_details_and_single_click_player_source():
    main_window = Path('src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
    library = Path('src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
    player = Path('src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')

    assert "setObjectName('TopNav')" in main_window
    assert "setObjectName('Sidebar')" not in main_window
    assert 'track_selected' in library
    assert 'self.library.track_selected.connect' not in main_window
    assert 'self.table.doubleClicked.connect(self._play_selected)' in library
    assert 'Szczegóły' in library
    assert 'ZATWIERDŹ JAKO GOTOWE' in library
    assert 'Edytuj metadane' in library
    assert 'setFixedSize(58, 58)' in player


def test_settings_and_locations_use_colored_cards_and_saved_confirmation():
    main_window = Path('src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
    assert "setObjectName('LocationCard')" in main_window
    assert "setObjectName('IntegrationCard')" in main_window
    assert 'Ustawienia zapisane' in main_window


def test_v017_library_and_editor_can_preview_external_cover_before_export():
    library = Path('src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
    editor = Path('src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')

    assert 'QNetworkAccessManager' in library
    assert '_load_remote_cover' in library
    assert 'cover_art_url' in library
    assert 'QNetworkAccessManager' in editor
    assert '_load_candidate_cover' in editor


def test_v017_library_selection_is_neutral_and_player_sets_local_file_source():
    theme = Path('src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')
    player = Path('src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')

    assert 'QTableView::item:selected { background:#304052;' in theme
    assert 'QTableView::item:focus { border:0;' in theme
    assert 'QTableView::item:selected { background:#244d39;' not in theme
    assert 'source_url = QUrl.fromLocalFile(str(self.current_path.resolve()))' in player
    assert 'self.player.setSource(source_url)' in player


def test_library_removes_native_cell_focus_outline_with_delegate():
    library = Path('src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')

    assert 'class LibraryRowDelegate(QStyledItemDelegate)' in library
    assert 'clean.state &= ~QStyle.StateFlag.State_HasFocus' in library
    assert 'self.table.setItemDelegate(LibraryRowDelegate(self.table))' in library


def test_library_playlist_button_shows_m3u8_extension():
    library = Path('src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')

    assert "QPushButton('Utwórz playlistę (.m3u8)')" in library


def test_playing_track_marker_does_not_change_status_text_used_for_sorting():
    library = Path('src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')

    assert "f'▶ {status_text}'" not in library
    assert 'status_text, track.artist or' in library


def test_playing_track_is_highlighted_across_the_entire_library_row():
    library = Path('src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')

    assert 'playing_background = QBrush(PLAYING_BACKGROUND)' in library
    assert 'for item in items:\n                    item.setBackground(playing_background)' in library


def test_playing_row_highlight_remains_visible_even_when_row_is_selected():
    library = Path('src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
    delegate = library.split('class LibraryRowDelegate(QStyledItemDelegate)', 1)[1].split('class LibraryPage', 1)[0]

    assert 'PLAYING_ROLE = int(Qt.ItemDataRole.UserRole) + 1' in library
    assert 'index.data(PLAYING_ROLE)' in delegate
    assert 'clean.state &= ~QStyle.StateFlag.State_Selected' in delegate
    assert 'item.setData(is_playing, PLAYING_ROLE)' in library
