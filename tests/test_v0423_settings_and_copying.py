from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMessageBox, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.preferences import default_name_rules
from audio_library_organizer.domain.provider_settings import ProviderSettings
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.metadata.naming import DEFAULT_FILENAME_TEMPLATE
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.main_window import SettingsPage
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication(['alo-v0423-tests'])
    return _APP


def _settings(tmp_path: Path, *, create: bool = True) -> AppSettings:
    paths = LibraryPaths(tmp_path / 'library')
    if create:
        paths.ensure_created()
    return AppSettings(source_dirs=(), library=paths)


def _track(tmp_path: Path, filename: str) -> TrackRecord:
    return TrackRecord(
        path=tmp_path / filename,
        artist='Artist',
        title='Title',
        status='review',
    )


def _close_editor(dialog: MetadataEditorDialog) -> None:
    dialog._force_closing = True
    dialog.close()


def test_track_header_keeps_selection_when_context_menu_takes_focus_and_allows_repeated_copy(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path, 'Artist A - First Track.mp3'))
    try:
        title = dialog.track_header_title
        dialog.show()
        title.setFocus()
        app.processEvents()

        title.setSelection(0, 8)
        title.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.PopupFocusReason))
        assert title.selectedText() == 'Artist A'
        title.copy()
        assert app.clipboard().text() == 'Artist A'

        title.setFocus()
        title.setSelection(11, 5)
        title.copy()
        assert app.clipboard().text() == 'First'
    finally:
        _close_editor(dialog)


def test_track_header_copy_remains_available_across_real_a_b_a_editor_navigation_loop(tmp_path: Path, monkeypatch):
    from audio_library_organizer.ui.main_window import MainWindow

    app = _app()
    tracks = [
        _track(tmp_path, 'Artist A - First Track.mp3'),
        _track(tmp_path, 'Artist B - Second Track.mp3'),
    ]
    store = QSettings(str(tmp_path / 'navigation.ini'), QSettings.Format.IniFormat)
    window = MainWindow(_settings(tmp_path), store)
    monkeypatch.setattr(window.library, 'visible_tracks', lambda: tracks)
    visits: list[tuple[str, str]] = []
    steps = iter((('Artist A', 1), ('Second', -1), ('First', 0)))

    def exercise_editor(dialog):
        fragment, delta = next(steps)
        title = dialog.track_header_title
        title.setFocus(); app.processEvents()
        start = title.text().index(fragment)
        title.setSelection(start, len(fragment)); title.copy()
        visits.append((dialog.track.path.name, app.clipboard().text()))
        dialog.navigation_delta = delta
        return 0

    monkeypatch.setattr(MetadataEditorDialog, 'exec', exercise_editor)
    try:
        window._open_metadata_editor(tracks[0])
        assert visits == [
            ('Artist A - First Track.mp3', 'Artist A'),
            ('Artist B - Second Track.mp3', 'Second'),
            ('Artist A - First Track.mp3', 'First'),
        ]
    finally:
        window.close()


def test_settings_render_six_ordered_configuration_sections_without_quick_access_duplicate(tmp_path: Path):
    app = _app()
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    page = SettingsPage(_settings(tmp_path), store)
    page.show()
    app.processEvents()
    try:
        sections = [
            frame
            for frame in page.findChildren(QFrame)
            if frame.objectName() == 'SettingsSection'
        ]
        section_names = [frame.property('sectionName') for frame in sections]
        assert section_names == [
            'library',
            'naming',
            'online',
            'integrations',
            'interface',
            'advanced',
        ]

        library = next(frame for frame in sections if frame.property('sectionName') == 'library')
        assert library.findChildren(QFrame, 'PathRow') == []
        assert page.library_path_label.text() == str(page.app_settings.library.root)
        assert page.library_status_label.text() == 'Biblioteka dostępna'
        assert page.change_library_button.text() == 'Zmień lokalizację'
        assert page.full_reset_button.text() == 'Resetuj ALO do czystego stanu'
        assert page.full_reset_button.parentWidget().property('settingsSection') == 'advanced'
    finally:
        page.close()


def test_full_alo_reset_action_is_in_advanced_settings_not_library_manager(tmp_path: Path):
    from audio_library_organizer.storage.library_profiles import LibraryRegistry
    from audio_library_organizer.ui.library_manager import LibraryManagerDialog

    app = _app()
    store = QSettings(str(tmp_path / 'reset-location.ini'), QSettings.Format.IniFormat)
    settings = _settings(tmp_path)
    page = SettingsPage(settings, store)
    manager = LibraryManagerDialog(LibraryRegistry(settings), None)
    requested: list[bool] = []
    page.full_reset_requested.connect(lambda: requested.append(True))
    try:
        page.full_reset_button.click()
        assert requested == [True]
        assert not any(
            button.text() == 'Resetuj ALO do czystego stanu'
            for button in manager.findChildren(QPushButton)
        )
    finally:
        manager.close(); page.close()


def test_library_section_shows_dynamic_unavailable_status(tmp_path: Path):
    app = _app()
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    page = SettingsPage(_settings(tmp_path, create=False), store)
    page.show()
    app.processEvents()
    try:
        assert page.library_status_label.text() == 'Biblioteka niedostępna'
        assert page.library_status_label.property('available') is False
    finally:
        page.close()


def test_change_library_location_requests_dedicated_location_picker(tmp_path: Path):
    app = _app()
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    page = SettingsPage(_settings(tmp_path), store)
    requested: list[bool] = []
    page.change_library_location_requested.connect(lambda: requested.append(True))
    page.show()
    app.processEvents()
    try:
        page.change_library_button.click()
        assert requested == [True]
    finally:
        page.close()


def test_main_library_location_change_keeps_sources_and_updates_persisted_root(tmp_path: Path, monkeypatch):
    from audio_library_organizer.ui.main_window import MainWindow
    from audio_library_organizer.ui.state import load_app_settings

    app = _app()
    source = tmp_path / 'source'; source.mkdir()
    settings = AppSettings((source,), LibraryPaths(tmp_path / 'library'))
    settings.library.ensure_created()
    store = QSettings(str(tmp_path / 'main-window.ini'), QSettings.Format.IniFormat)
    window = MainWindow(settings, store)
    new_root = tmp_path / 'relocated-library'
    old_output = settings.library.ready / 'existing-track.mp3'
    old_output.write_bytes(b'keep')
    monkeypatch.setattr(
        'audio_library_organizer.ui.main_window.QFileDialog.getExistingDirectory',
        lambda *_args, **_kwargs: str(new_root),
    )
    confirmations: list[str] = []
    monkeypatch.setattr(
        'audio_library_organizer.ui.main_window.QMessageBox.question',
        lambda _parent, _title, text, *_args: confirmations.append(text) or QMessageBox.StandardButton.Yes,
    )
    try:
        window._change_main_library_location()
        persisted = load_app_settings(store)
        assert persisted is not None
        assert persisted.library.root == new_root.resolve()
        assert persisted.source_dirs == settings.source_dirs
        assert window.main_settings.library.root == new_root.resolve()
        assert window.library_registry.find('main').library_root == new_root.resolve()
        assert new_root.is_dir()
        assert old_output.read_bytes() == b'keep'
        assert confirmations and 'nie przenosi' in confirmations[0].casefold()
    finally:
        window.close()


def test_main_library_location_is_not_persisted_when_destination_validation_fails(tmp_path: Path, monkeypatch):
    from audio_library_organizer.ui.main_window import MainWindow
    from audio_library_organizer.ui.state import load_app_settings, save_app_settings

    app = _app()
    source = tmp_path / 'source'; source.mkdir()
    settings = AppSettings((source,), LibraryPaths(tmp_path / 'library'))
    settings.library.ensure_created()
    store = QSettings(str(tmp_path / 'main-window-invalid.ini'), QSettings.Format.IniFormat)
    save_app_settings(store, settings)
    window = MainWindow(settings, store)
    new_root = tmp_path / 'invalid-library'
    monkeypatch.setattr(
        'audio_library_organizer.ui.main_window.QFileDialog.getExistingDirectory',
        lambda *_args, **_kwargs: str(new_root),
    )
    monkeypatch.setattr(
        'audio_library_organizer.ui.main_window.QMessageBox.question',
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        'audio_library_organizer.ui.main_window.QMessageBox.warning',
        lambda _parent, _title, text, *_args: warnings.append(str(text)) or QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        'audio_library_organizer.ui.main_window.LibraryRepository.initialize',
        lambda _self: (_ for _ in ()).throw(OSError('destination unavailable')),
    )
    try:
        window._change_main_library_location()
        persisted = load_app_settings(store)
        assert persisted is not None
        assert persisted.library.root == settings.library.root
        assert window.main_settings.library.root == settings.library.root
        assert warnings and 'destination unavailable' in warnings[0]
    finally:
        window.close()


def test_main_library_location_rejects_overlap_with_another_profile(tmp_path: Path, monkeypatch):
    from audio_library_organizer.ui.main_window import MainWindow

    app = _app()
    settings = _settings(tmp_path)
    store = QSettings(str(tmp_path / 'main-window-collision.ini'), QSettings.Format.IniFormat)
    window = MainWindow(settings, store)
    other_root = tmp_path / 'other-library'
    other_source = tmp_path / 'other-source'; other_source.mkdir()
    window.library_registry.add_library('Other', (other_source,), other_root)
    destinations = iter((other_root / 'nested', other_source / 'nested'))
    monkeypatch.setattr(
        'audio_library_organizer.ui.main_window.QFileDialog.getExistingDirectory',
        lambda *_args, **_kwargs: str(next(destinations)),
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        'audio_library_organizer.ui.main_window.QMessageBox.warning',
        lambda _parent, _title, text, *_args: warnings.append(str(text)) or QMessageBox.StandardButton.Ok,
    )
    try:
        window._change_main_library_location()
        window._change_main_library_location()
        assert window.main_settings.library.root == settings.library.root
        assert len(warnings) == 2
        assert all('koliduje' in warning.casefold() for warning in warnings)
    finally:
        window.close()


def test_safe_defaults_reset_only_non_destructive_preferences(tmp_path: Path):
    from audio_library_organizer.domain import preferences as preferences_module

    assert hasattr(preferences_module, 'restore_safe_defaults')
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    store.setValue('ui/language', 'en')
    store.setValue('ui/theme', 'light')
    store.setValue('ui/normalize_names', False)
    store.setValue('ui/name_normalization_rules', '[{"find":"x","replacement":"y"}]')
    store.setValue('ui/filename_template', '{Title}')
    store.setValue('ui/folder_organization', 'genre')
    store.setValue('providers/auto_identify', True)
    store.setValue('providers/acoustid_key', 'secret-acoustid')
    store.setValue('providers/discogs_token', 'secret-discogs')
    store.setValue('providers/musicbrainz_contact', 'private@example.test')
    store.setValue('libraries/active', 'main')
    store.setValue('libraries/profiles', '[{"id":"main"}]')
    store.setValue('library/root', str(tmp_path / 'music'))
    store.setValue('history/last_scan', 'keep-me')
    library_file = tmp_path / 'music' / '.alo' / 'library.sqlite3'
    output_file = tmp_path / 'music' / 'GOTOWE' / 'Artist - Track.mp3'
    library_file.parent.mkdir(parents=True)
    output_file.parent.mkdir(parents=True)
    library_file.write_bytes(b'database-sentinel')
    output_file.write_bytes(b'audio-sentinel')

    preferences_module.restore_safe_defaults(store)

    assert store.value('ui/language') == 'en'
    assert store.value('ui/theme') == 'dark'
    assert store.value('ui/normalize_names', type=bool) is True
    assert json.loads(store.value('ui/name_normalization_rules')) == [
        rule.to_dict() for rule in default_name_rules()
    ]
    assert store.value('ui/filename_template') == DEFAULT_FILENAME_TEMPLATE
    assert store.value('ui/folder_organization') == 'none'
    assert store.value('providers/auto_identify', type=bool) is False
    assert store.value('providers/acoustid_key') == 'secret-acoustid'
    assert store.value('providers/discogs_token') == 'secret-discogs'
    assert store.value('providers/musicbrainz_contact') == 'private@example.test'
    assert store.value('libraries/active') == 'main'
    assert store.value('libraries/profiles') == '[{"id":"main"}]'
    assert store.value('library/root') == str(tmp_path / 'music')
    assert store.value('history/last_scan') == 'keep-me'
    assert library_file.read_bytes() == b'database-sentinel'
    assert output_file.read_bytes() == b'audio-sentinel'


def test_reorganized_settings_save_existing_options_in_their_original_keys(tmp_path: Path):
    app = _app()
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    page = SettingsPage(_settings(tmp_path), store)
    page.show()
    app.processEvents()
    try:
        page.filename_template.setText('{Artist} - {Title}')
        page.folder_org_buttons['artist'].setChecked(True)
        page.auto.setChecked(True)
        page.normalize_names.setChecked(False)
        page._save()

        provider = ProviderSettings.from_store(store)
        assert provider.filename_template == '{Artist} - {Title}'
        assert provider.folder_organization == 'artist'
        assert provider.auto_identify_after_scan is True
        assert store.value('ui/normalize_names', type=bool) is False
    finally:
        page.close()


def test_settings_sections_and_safe_reset_dialog_are_fully_translated(tmp_path: Path):
    app = _app()
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    page = SettingsPage(_settings(tmp_path), store)
    apply_static_language(page, 'en')
    page.show()
    app.processEvents()
    try:
        visible_text = {label.text() for label in page.findChildren(QLabel)}
        assert 'Library' in visible_text
        assert 'Filename naming' in visible_text
        assert 'Online identification' in visible_text
        assert 'Integrations and API keys' in visible_text
        assert 'Interface' in visible_text
        assert 'Advanced' in visible_text
        assert 'Library available' in visible_text
        assert page.change_library_button.text() == 'Change location'
        assert page.restore_defaults_button.text() == 'Restore default settings'

        page.refresh_main_settings(page.app_settings)
        app.processEvents()
        assert page.library_status_label.text() == 'Library available'
        assert page.change_library_button.text() == 'Change location'

        dialog = page.create_restore_defaults_dialog()
        apply_static_language(dialog, 'en')
        assert dialog.windowTitle() == 'Restore default settings'
        button_texts = {button.text() for button in dialog.findChildren(QPushButton)}
        assert 'Restore defaults' in button_texts
        assert 'Cancel' in button_texts
        dialog.close()
    finally:
        page.close()
