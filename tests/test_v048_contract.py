from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRST_RUN = (ROOT / 'src/audio_library_organizer/ui/first_run.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
LIBMAN = (ROOT / 'src/audio_library_organizer/ui/library_manager.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
I18N = (ROOT / 'src/audio_library_organizer/ui/i18n.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_first_run_language_dialog_is_roomy_and_uses_real_flag_assets():
    assert 'setFixedSize(470, 250)' not in FIRST_RUN
    assert 'setMinimumSize(' in FIRST_RUN
    assert "asset_path('flag_pl.svg')" in FIRST_RUN
    assert "asset_path('flag_gb.svg')" in FIRST_RUN
    assert (ROOT / 'src/audio_library_organizer/assets/flag_pl.svg').is_file()
    assert (ROOT / 'src/audio_library_organizer/assets/flag_gb.svg').is_file()


def test_settings_language_description_is_natural_and_does_not_mention_theme():
    expected = 'Wybierz język interfejsu. Możesz go zmienić w dowolnym momencie.'
    assert expected in MAIN
    assert expected in I18N
    assert 'ALO pozostaje w dopracowanym ciemnym motywie.' not in MAIN


def test_online_lock_is_a_compact_recognition_action_not_a_checkbox_strip():
    assert "QCheckBox('🔒 Zablokuj dane przed ponownym rozpoznaniem online')" not in EDITOR
    assert "setObjectName('OnlineLockButton')" in EDITOR
    assert 'setCheckable(True)' in EDITOR
    assert 'pol.addWidget(self.online_lock)' in EDITOR
    assert 'root.addWidget(self.online_lock)' not in EDITOR
    assert "'lock' if locked else 'unlock'" in EDITOR
    assert 'QPushButton#OnlineLockButton' in THEME


def test_library_filter_row_is_compact_and_manual_filter_is_removed():
    assert "('Brak okładki', 'no_cover'), ('Brak roku', 'no_year'), ('Ręcznie edytowane', 'manual')" not in LIBRARY
    assert "('Brak okładki', 'no_cover'), ('Brak roku', 'no_year')" in LIBRARY
    assert 'self.search.setMaximumWidth(' in LIBRARY
    assert 'self.genre_filter.setMaximumWidth(' in LIBRARY
    assert 'self.status.setFixedWidth(' in LIBRARY or 'self.status.setMaximumWidth(' in LIBRARY


def test_library_switch_requires_explicit_button_and_rows_only_select():
    assert 'itemClicked.connect(self._activate_clicked_library)' not in LIBMAN
    assert "QPushButton('Ustaw jako aktywną')" in LIBMAN
    assert 'def _activate_selected_library' in LIBMAN
    assert "clicked.connect(lambda: self.activate_requested.emit('main'))" not in LIBMAN
    assert 'def _activate_main_library' in LIBMAN
    assert "Kliknij bibliotekę, aby ją zaznaczyć" in LIBMAN


def test_library_manager_has_selected_library_actions_menu():
    assert 'QToolButton' in LIBMAN
    assert "setText('⋯')" in LIBMAN
    for label in ('Zmień nazwę', 'Otwórz w Eksploratorze', 'Zacznij od nowa', 'Usuń bibliotekę'):
        assert label in LIBMAN
    assert 'def _rename_selected_library' in LIBMAN
    assert 'def _open_selected_library' in LIBMAN
    assert 'def _restart_selected_library' in LIBMAN


def test_library_selection_and_active_state_use_different_visual_languages():
    assert 'QListWidget#LibraryProfileList::item:selected' in THEME
    assert '#23456' in THEME or '#1d3f' in THEME or '#214a' in THEME
    assert "item.setBackground(QColor('#173126'))" in LIBMAN


def test_switch_guard_exists_for_unsaved_metadata_editor_state():
    assert 'has_unsaved_changes' in EDITOR
    assert '_active_metadata_editor' in MAIN
    assert 'Najpierw zapisz lub odrzuć zmiany w otwartym edytorze metadanych.' in MAIN
