import json
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QLabel, QToolButton, QFrame

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.genre_input import GenreChipInput
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.main_window import MainWindow, SettingsPage
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    previous = instance.styleSheet()
    instance.setStyleSheet(style_for_theme('dark'))
    yield instance
    instance.setStyleSheet(previous)


def test_controlled_genres_persist_exact_custom_names_without_duplicates(tmp_path):
    from audio_library_organizer.domain.genres import ALO_GENRES, GenreSettings

    store = QSettings(str(tmp_path / 'genres.ini'), QSettings.Format.IniFormat)
    store.setValue('providers/discogs_token', 'untouched')
    values = ('  Polish Club  ', 'polish club', 'HOUSE', '', 'R&B / Soul 90s', 'Tech-House 2.0')
    settings = GenreSettings(values)
    assert settings.custom_genres == ('Polish Club', 'R&B / Soul 90s', 'Tech-House 2.0')
    assert {'House', 'Electro House', 'Uplifting Trance', 'Hands Up', 'Psytrance', 'Other'} <= set(ALO_GENRES)
    assert len(ALO_GENRES) == len({name.casefold() for name in ALO_GENRES})
    assert 50 <= len(ALO_GENRES) <= 90
    settings.save(store)
    restarted = GenreSettings.from_store(QSettings(store.fileName(), QSettings.Format.IniFormat))
    assert restarted.custom_genres == settings.custom_genres
    assert set(restarted.suggestions()) == set(ALO_GENRES) | set(settings.custom_genres)
    assert store.value('providers/discogs_token') == 'untouched'
    assert GenreSettings().custom_genres == ()


@pytest.mark.parametrize('payload', ['broken JSON', '"House"', '{"genre": "Trance"}', '[null, 2, "Club 2000", "club 2000"]'])
def test_corrupt_custom_settings_do_not_break_genre_suggestions(tmp_path, payload):
    from audio_library_organizer.domain.genres import GenreSettings

    store = QSettings(str(tmp_path / 'corrupt.ini'), QSettings.Format.IniFormat)
    store.setValue('genres/custom', payload)
    settings = GenreSettings.from_store(store)
    assert settings.custom_genres == (('Club 2000',) if payload.startswith('[null') else ())
    assert 'House' in settings.suggestions()


def test_settings_genres_add_remove_filter_translate_and_survive_other_saves(app, tmp_path):
    settings = AppSettings((), LibraryPaths(tmp_path / 'library'))
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    page = SettingsPage(settings, store)
    page.resize(1050, 800)
    page.show()
    app.processEvents()
    try:
        section = page.settings_sections['genres']
        widget = page.genre_settings
        assert widget.parentWidget() is section
        assert widget.tabs.count() == 2
        assert not widget.base_host.findChildren(QToolButton, 'GenreTagRemove')
        for tag in widget.base_host.findChildren(QFrame, 'GenreChip'):
            assert widget.base_host.rect().contains(tag.geometry()), (widget.base_host.size(), tag.geometry())
        widget.tabs.setCurrentIndex(1)
        for name in ('  Polish Club  ', 'polish club', 'house', '', 'R&B / Soul 90s'):
            widget.custom_edit.setText(name)
            widget.add_button.click()
        assert widget.settings.custom_genres == ('Polish Club', 'R&B / Soul 90s')
        widget.search.setText('polish')
        app.processEvents()
        tags = widget.custom_host.findChildren(QFrame, 'GenreChip')
        assert [tag.property('genreName') for tag in tags if not tag.isHidden()] == ['Polish Club']
        tags[0].findChild(QToolButton, 'GenreTagRemove').click()
        assert widget.settings.custom_genres == ('R&B / Soul 90s',)
        assert json.loads(store.value('genres/custom')) == ['R&B / Soul 90s']
        widget.search.clear()
        for language, title in [('en', 'My genres'), ('pl', 'Moje gatunki'), ('en', 'My genres')]:
            apply_static_language(page, language)
            assert widget.tabs.tabText(1) == f'{title}  1'
            assert widget.notice.text() == ''
            if language == 'en':
                widget.custom_edit.setText('New Club & Dance')
                widget.add_button.click()
                added = next(tag for tag in widget.custom_host.findChildren(QFrame, 'GenreChip')
                             if tag.property('genreName') == 'New Club & Dance')
                remove = added.findChild(QToolButton, 'GenreTagRemove')
                assert remove.toolTip() == 'Remove genre'
                apply_static_language(page, 'pl')
                assert remove.toolTip() == 'Usuń gatunek'
                apply_static_language(page, 'en')
                assert remove.toolTip() == 'Remove genre'
                remove.click()
        page._save_language()
        page._save()
        assert json.loads(store.value('genres/custom')) == ['R&B / Soul 90s']
    finally:
        page.close()
    reopened = SettingsPage(settings, QSettings(store.fileName(), QSettings.Format.IniFormat))
    try:
        assert reopened.genre_settings.settings.custom_genres == ('R&B / Soul 90s',)
    finally:
        reopened.close()


def test_editor_suggestions_never_learn_file_or_manual_genres(app, tmp_path, monkeypatch):
    store = QSettings(str(tmp_path / 'window.ini'), QSettings.Format.IniFormat)
    store.setValue('genres/custom', json.dumps(['Polish Club', 'R&B / Soul 90s']))
    settings = AppSettings((), LibraryPaths(tmp_path / 'library'))
    settings.library.ensure_created()
    window = MainWindow(settings, store)
    tracks = [TrackRecord(path=tmp_path / f'{i}.mp3', genre=value)
              for i, value in enumerate(('[DjmcBiT presents]', ':::artMkiss 2009:::', 'www.example.com', 'Trnace'))]
    original = [track.genre for track in tracks]
    window.library.set_tracks(tracks)
    seen = []

    def inspect(dialog):
        before = dialog.genre.model.stringList()
        assert 'Polish Club' in before and 'R&B / Soul 90s' in before
        assert not set(original) & set(before)
        dialog.genre.setText('')
        dialog.genre.edit.setText('My Accidental Genre')
        dialog.genre.edit.returnPressed.emit()
        assert dialog.genre.text() == 'My Accidental Genre'
        assert dialog._preview_track().genre == 'My Accidental Genre'
        assert dialog.genre.model.stringList() == before
        seen.append(before)
        return 0

    monkeypatch.setattr(MetadataEditorDialog, 'exec', inspect)
    try:
        window._open_metadata_editor(tracks[0])
        window._open_metadata_editor(tracks[1])
        assert seen[0] == seen[1]
        assert [track.genre for track in tracks] == original
        assert json.loads(store.value('genres/custom')) == ['Polish Club', 'R&B / Soul 90s']
    finally:
        window.close()


def test_genre_tags_are_compact_neutral_and_only_cross_removes(app):
    field = GenreChipInput('House / Trance', suggestions=('Polish Club',))
    field.show()
    app.processEvents()
    try:
        tags = field.findChildren(QFrame, 'GenreChip')
        assert len(tags) == 2
        assert field.edit.placeholderText() == 'Wpisz lub wybierz gatunek…'
        for tag in tags:
            assert 24 <= tag.height() <= 26
            remove = tag.findChild(QToolButton, 'GenreTagRemove')
            assert remove.text() == '×' and remove.icon().isNull()
            assert remove.width() <= 18
            assert tag.findChild(QLabel, 'GenreTagLabel').textFormat() == Qt.TextFormat.PlainText
            picture = tag.grab().toImage()
            assert picture.pixelColor(1, tag.height() // 2).name() == '#5f7d95'
        tags[1].findChild(QToolButton, 'GenreTagRemove').click()
        assert field.genres() == ('House',)
        assert 'Polish Club' in field.model.stringList()
        assert 'My Accidental Genre' not in field.model.stringList()
        apply_static_language(field, 'en')
        field.edit.setText('Club')
        field.edit.returnPressed.emit()
        for tag in field.findChildren(QFrame, 'GenreChip'):
            remove = tag.findChild(QToolButton, 'GenreTagRemove')
            assert remove.toolTip() == 'Remove genre'
        apply_static_language(field, 'pl')
        for tag in field.findChildren(QFrame, 'GenreChip'):
            assert tag.findChild(QToolButton, 'GenreTagRemove').toolTip() == 'Usuń gatunek'
    finally:
        field.close()


def test_library_genre_filter_keeps_its_existing_default_choices(app):
    from audio_library_organizer.ui.library_page import LibraryPage

    library = LibraryPage()
    try:
        suggestions = library.genre_suggestions()
        assert 'Psy-Trance' in suggestions
        assert 'Hands Up' not in suggestions
    finally:
        library.close()
