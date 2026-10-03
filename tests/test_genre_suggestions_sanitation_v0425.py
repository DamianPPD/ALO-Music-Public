import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.genre import normalize_genre_list
from audio_library_organizer.ui.genre_input import GenreChipInput, build_genre_suggestions
from audio_library_organizer.ui.library_page import LibraryPage


@pytest.mark.parametrize('value', [
    'http://example.com', 'HTTPS://example.com/music/download',
    'www.example.com', 'WWW.EXAMPLE.PL/download', 'ftp://example.org/file',
    'example.com', 'music.example.co.uk', 'example.info', 'example.pl:8080/path',
    'example.com?download=1#track', 'żółć.pl', 'xn--bcher-kva.de', 'example.xn--p1ai',
    'https: / example.com / download',  # stored after the existing slash normalization
    'www.Hard.Trance', 'Hard.Trance/path', 'Techno.com',
])
def test_web_values_and_their_path_fragments_are_not_genre_suggestions(value):
    assert build_genre_suggestions([value]) == build_genre_suggestions([])
    assert build_genre_suggestions([value], query='example') == []


@pytest.mark.parametrize('value', [
    'E.B.M.', 'D.N.B.', 'U.K. Garage', 'Trance 2.0', 'R&B.90s',
    'Hip-Hop', '80s', 'Nu.Disco', 'Drum.Bass', 'Tech-House',
    'Hard.Trance', 'Melodic.Techno', 'Drum.and.Bass', 'Post.Punk',
    'Alternative.Rock', 'Synth.Pop', 'Jazz.Funk',
])
def test_real_genres_with_punctuation_and_digits_remain_available(value):
    assert value in build_genre_suggestions([value])


def test_url_filter_runs_before_slash_split_and_preserves_other_genres():
    raw = ['House / https://example.com/download; Techno',
           'Trance / https: / example.org', 'Rock/Pop', 'Disco;example.info/path']
    before = list(raw)
    expected = build_genre_suggestions(['House', 'Techno', 'Trance', 'Rock/Pop', 'Disco'])
    assert build_genre_suggestions(raw) == expected
    assert raw == before


@pytest.mark.parametrize('value', [
    'www.example.com/download/files', 'example.com/download/files',
    'https://example.com/download',
])
def test_normalized_web_addresses_do_not_leave_path_suggestions(value):
    assert build_genre_suggestions([normalize_genre_list(value)]) == build_genre_suggestions([])


@pytest.mark.parametrize('address', ['www.example.com', 'example.com', 'https://example.com'])
@pytest.mark.parametrize('genre', ['House', 'Melodic Techno', 'Hard.Trance'])
def test_normalized_address_does_not_hide_a_following_music_genre(address, genre):
    normalized = normalize_genre_list(f'{address}; {genre}')
    assert build_genre_suggestions([normalized]) == build_genre_suggestions([genre])


def test_dotted_music_names_can_still_use_normal_genre_separators():
    assert build_genre_suggestions(['Hard.Trance / Melodic Techno']) == build_genre_suggestions([
        'Hard.Trance', 'Melodic Techno'])


@pytest.mark.parametrize('genre,address', [
    ('Hard.Trance', 'example.com'), ('Nu.Disco', 'example.com/download'),
])
def test_dotted_music_name_does_not_hide_a_following_web_address(genre, address):
    normalized = normalize_genre_list(f'{genre}; {address}')
    assert build_genre_suggestions([normalized]) == build_genre_suggestions([genre])


def test_library_values_feed_clean_autocomplete_without_changing_records(tmp_path):
    app = QApplication.instance() or QApplication([])
    tracks = [TrackRecord(path=tmp_path / 'dirty.mp3', genre=normalize_genre_list('https://example.com/download')),
              TrackRecord(path=tmp_path / 'clean.mp3', genre='U.K. Garage / Trance 2.0')]
    original = [track.genre for track in tracks]
    library = LibraryPage()
    library.set_tracks(tracks)
    field = GenreChipInput('www.example.com', suggestions=library.genre_suggestions())
    try:
        suggestions = field.model.stringList()
        assert 'U.K. Garage' in suggestions and 'Trance 2.0' in suggestions
        assert not {'https:', 'example.com', 'download', 'www.example.com'} & set(suggestions)
        assert [track.genre for track in tracks] == original
        assert field.genres() == ('www.example.com',)  # current/manual values remain editable
        field.set_suggestions(['new.example.net', 'E.B.M.'])
        assert 'new.example.net' not in field.model.stringList()
        assert 'E.B.M.' in field.model.stringList()
        assert field.genres() == ('www.example.com',)
    finally:
        field.close()
        library.close()
        app.processEvents()
