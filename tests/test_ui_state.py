from pathlib import Path
import json
import pytest

from audio_library_organizer.ui.state import build_library_root, filter_track_rows, DuplicatePlaybackState


def test_build_library_root_uses_user_chosen_parent_and_name(tmp_path: Path):
    assert build_library_root(tmp_path, 'Moja Muzyka') == (tmp_path/'Moja Muzyka').resolve()


def test_build_library_root_rejects_empty_or_invalid_name(tmp_path: Path):
    with pytest.raises(ValueError):
        build_library_root(tmp_path, '   ')
    with pytest.raises(ValueError):
        build_library_root(tmp_path, 'A/B')


def test_filter_rows_searches_multiple_fields():
    rows = [
        {'artist':'Armani & Ghost','title':'Airport','status':'ready','genre':'Hard House'},
        {'artist':'Adele','title':'Rumour Has It','status':'review','genre':'House'},
    ]
    assert [r['title'] for r in filter_track_rows(rows, 'hard')] == ['Airport']
    assert [r['title'] for r in filter_track_rows(rows, 'adele')] == ['Rumour Has It']
    assert [r['title'] for r in filter_track_rows(rows, '', status='review')] == ['Rumour Has It']


def test_duplicate_playback_switch_preserves_position_with_bounds():
    state = DuplicatePlaybackState(index=0, position_ms=155000)
    switched = state.switch_to(1, target_duration_ms=120000)
    assert switched.index == 1
    assert switched.position_ms == 119500


def test_identification_summary_explains_source_confidence_and_reasons(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import identification_summary

    track = TrackRecord(
        path=tmp_path/'x.mp3', confidence=0.94, discogs_release_id='123',
        musicbrainz_recording_id='mb1', match_reasons=['AcoustID 98%', 'długość zgodna']
    )
    summary = identification_summary(track)

    assert summary['confidence'] == '94% — bardzo pewne'
    assert 'Discogs Release 123' in summary['sources']
    assert 'MusicBrainz' in summary['sources']
    assert 'AcoustID 98%' in summary['reasons']

class _FakeStore:
    def __init__(self, data=None):
        self.data = dict(data or {})
    def value(self, key, default=''):
        return self.data.get(key, default)
    def setValue(self, key, value):
        self.data[key] = value
    def remove(self, key):
        self.data.pop(key, None)


def test_app_settings_can_be_saved_and_reset_without_touching_files(tmp_path: Path):
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui.state import save_app_settings, reset_folder_preferences

    source = tmp_path / 'source'; source.mkdir()
    library = tmp_path / 'library'; library.mkdir()
    sentinel = source / 'keep.mp3'; sentinel.write_bytes(b'abc')
    store = _FakeStore()
    settings = AppSettings((source,), LibraryPaths(library))

    save_app_settings(store, settings)
    assert json.loads(store.data['sources']) == [str(source.resolve())]
    assert store.data['library_root'] == str(library.resolve())

    reset_folder_preferences(store)
    assert 'sources' not in store.data
    assert 'library_root' not in store.data
    assert sentinel.read_bytes() == b'abc'


def test_identification_summary_distinguishes_not_run_from_no_match(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import identification_summary

    fresh = TrackRecord(path=tmp_path/'fresh.mp3')
    assert 'nie zostało jeszcze uruchomione' in identification_summary(fresh)['reasons'].casefold()

    attempted = TrackRecord(path=tmp_path/'attempted.mp3', match_reasons=['Nie znaleziono pewnego dopasowania online'])
    assert 'nie znaleziono' in identification_summary(attempted)['reasons'].casefold()


def test_large_tables_skip_expensive_auto_resize():
    from audio_library_organizer.ui.state import should_autosize_table
    assert should_autosize_table(50) is True
    assert should_autosize_table(1000) is False


def test_status_presentation_makes_ready_review_and_duplicate_visually_distinct():
    from audio_library_organizer.ui.state import status_presentation

    ready = status_presentation('ready')
    review = status_presentation('review')
    duplicate = status_presentation('duplicate')

    assert ready.label == 'GOTOWE'
    assert review.label == 'DO SPRAWDZENIA'
    assert duplicate.label == 'DUPLIKAT'
    assert len({ready.background, review.background, duplicate.background}) == 3
    assert len({ready.accent, review.accent, duplicate.accent}) == 3


def test_live_scan_refresh_is_batched_but_always_shows_first_and_last_item():
    from audio_library_organizer.ui.state import should_refresh_live_scan

    assert should_refresh_live_scan(1, 1000) is True
    assert should_refresh_live_scan(2, 1000) is False
    assert should_refresh_live_scan(5, 1000) is True
    assert should_refresh_live_scan(1000, 1000) is True


def test_metadata_completeness_highlights_exact_missing_fields(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import metadata_completeness

    track = TrackRecord(
        path=tmp_path/'x.mp3', artist='Artist', title='Title (Mix)', album='Release',
        genre='House', bpm=128, has_cover=False, year=None,
        discogs_release_id='123', confidence=0.97,
    )
    info = metadata_completeness(track)

    assert 'Rok' in info['missing']
    assert 'Okładka' not in info['missing']
    assert 'Wykonawca' in info['confirmed']
    assert 'Tytuł / wersja' in info['confirmed']
    assert info['ready_for_manual_approval'] is False


def test_metadata_completeness_treats_manual_cover_as_available(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import metadata_completeness

    track = TrackRecord(
        path=tmp_path/'x.mp3', artist='A', title='T', album='R', year='2000', genre='House', bpm=128,
        has_cover=False, manual_cover_path='C:/covers/x.jpg', discogs_url='https://discogs.example/x'
    )
    info = metadata_completeness(track)
    assert 'Okładka' in info['confirmed']
    assert 'Okładka' not in info['missing']


def test_source_embedded_cover_counts_as_final_fallback_cover(tmp_path: Path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import metadata_completeness

    track = TrackRecord(
        path=tmp_path/'x.mp3', artist='A', title='T', album='R', year='2000', genre='House', bpm=128,
        has_cover=True, discogs_url='https://discogs.example/x'
    )
    info = metadata_completeness(track)
    assert 'Okładka' in info['confirmed']
    assert 'Okładka' not in info['missing']


def test_pending_review_requires_library_check_before_export():
    from audio_library_organizer.ui.state import export_needs_library_review

    assert export_needs_library_review({'review': 3, 'ready': 10, 'duplicate': 2, 'total': 15}) is True
    assert export_needs_library_review({'review': 0, 'ready': 10, 'duplicate': 2, 'total': 12}) is False


def test_metadata_completeness_accepts_existing_embedded_cover_as_fallback(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import metadata_completeness

    track = TrackRecord(path=tmp_path/'a.mp3', artist='A', title='T', album='Album', year='2000', genre='House', bpm=128, has_cover=True, discogs_url='https://discogs.example/release/1')
    result = metadata_completeness(track)
    assert 'Okładka' in result['confirmed']
    assert 'Okładka' not in result['missing']


def test_selected_duplicate_primary_uses_standard_ready_presentation(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import library_status_text, library_status_presentation, status_presentation

    track = TrackRecord(path=tmp_path/'a.mp3', status='ready', artist='A', title='T', year='2000', genre='House', bpm=128)
    track.locked_fields.add('duplicate_primary')
    assert library_status_text(track) == 'GOTOWE'
    assert library_status_presentation(track) == status_presentation('ready')


def test_review_reasons_and_queue_include_review_items_and_exclude_duplicates(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import review_reasons, review_queue

    ready = TrackRecord(path=tmp_path/'ready.mp3', status='ready', artist='A', title='T', year='2000', genre='House', bpm=128, has_cover=True, confidence=.98)
    missing = TrackRecord(path=tmp_path/'missing.mp3', status='ready', artist='A', title='T', year=None, genre='House', bpm=128, has_cover=False, confidence=.97)
    dup = TrackRecord(path=tmp_path/'dup.mp3', status='duplicate', artist='A', title='T', year='2000', genre='House', bpm=128, has_cover=True, confidence=.96)
    uncertain = TrackRecord(path=tmp_path/'uncertain.mp3', status='review', artist='A', title='T', year='2000', genre='House', bpm=128, has_cover=True, confidence=.55)

    assert review_reasons(ready) == []
    assert 'Brak: Rok' in review_reasons(missing)
    assert not any('okład' in x.casefold() for x in review_reasons(missing))
    assert review_reasons(dup) == []
    assert any('Niska pewność' in x for x in review_reasons(uncertain))
    assert [t.path.name for t in review_queue([ready, missing, dup, uncertain])] == ['missing.mp3', 'uncertain.mp3']


def test_quick_library_filters_cover_decisions_missing_fields_and_manual_edits(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import track_matches_quick_filter

    track = TrackRecord(path=tmp_path/'a.mp3', status='ready', artist='A', title='T', year=None, has_cover=False)
    track.locked_fields.add('title')
    assert track_matches_quick_filter(track, 'all') is True
    assert track_matches_quick_filter(track, 'no_cover') is True
    assert track_matches_quick_filter(track, 'no_year') is True
    assert track_matches_quick_filter(track, 'ready') is False
    assert track_matches_quick_filter(track, 'review') is True
    assert track_matches_quick_filter(track, 'manual') is True
    assert track_matches_quick_filter(track, 'duplicate') is False


def test_confidence_label_is_human_readable(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import confidence_label

    assert confidence_label(TrackRecord(path=tmp_path/'a', confidence=.98)) == '98% — bardzo pewne'
    assert confidence_label(TrackRecord(path=tmp_path/'b', confidence=.76)) == '76% — sprawdź wersję'
    assert confidence_label(TrackRecord(path=tmp_path/'c', confidence=.40)) == '40% — wymaga sprawdzenia'
    assert confidence_label(TrackRecord(path=tmp_path/'d', confidence=None)) == '—'


def test_library_filter_requires_all_requested_genres_and_bpm_range(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import track_matches_library_filters

    exact = TrackRecord(path=tmp_path/'a.mp3', genre='Trance / Vocal / Progressive', bpm=139)
    house = TrackRecord(path=tmp_path/'b.mp3', genre='House / Vocal', bpm=128)

    assert track_matches_library_filters(exact, genres_text='Trance, Vocal', bpm_min=138, bpm_max=140) is True
    assert track_matches_library_filters(exact, genres_text='Vocal, Trance', bpm_min=138, bpm_max=140) is True
    assert track_matches_library_filters(exact, genres_text='Trance, House') is False
    assert track_matches_library_filters(house, genres_text='Trance, Vocal') is False
    assert track_matches_library_filters(exact, genres_text='Trance', bpm_min=140, bpm_max=145) is False


def test_suspicious_bpm_moves_unlocked_ready_track_to_review():
    from pathlib import Path
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import effective_status, review_reasons
    track = TrackRecord(path=Path('odd.mp3'), size_bytes=1, mtime_ns=1, status='ready')
    track.artist='A'; track.title='T'; track.year='2020'; track.genre='Trance'; track.bpm=42
    assert effective_status(track) == 'review'
    assert 'Podejrzane BPM' in review_reasons(track)


def test_manually_approved_suspicious_bpm_can_remain_ready():
    from pathlib import Path
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.ui.state import effective_status
    track = TrackRecord(path=Path('odd.mp3'), size_bytes=1, mtime_ns=1, status='ready')
    track.artist='A'; track.title='T'; track.year='2020'; track.genre='Trance'; track.bpm=42
    track.locked_fields.add('__status__')
    assert effective_status(track) == 'ready'
