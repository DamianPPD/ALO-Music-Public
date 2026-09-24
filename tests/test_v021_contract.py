from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.provider_settings import ProviderSettings
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs.exporter import ExportPlan
from audio_library_organizer.ui.state import metadata_completeness, library_status_text, status_presentation


class Store:
    def __init__(self):
        self.d = {}
    def value(self, key, default=None):
        return self.d.get(key, default)
    def setValue(self, key, value):
        self.d[key] = value


def complete_track(tmp_path: Path, **overrides):
    data = dict(
        path=tmp_path / 'track.mp3', artist='Artist', title='Title (Mix)', year='2000',
        genre='Trance / Progressive Trance', bpm=132, has_cover=True, status='ready',
    )
    data.update(overrides)
    return TrackRecord(**data)


def test_core_metadata_missing_year_or_genre_blocks_ready_status(tmp_path: Path):
    track = complete_track(tmp_path, year=None, genre=None, status='ready')
    completeness = metadata_completeness(track)
    assert completeness['missing_core'] == ['Rok', 'Gatunek']
    assert completeness['ready_for_manual_approval'] is False
    assert library_status_text(track) == 'DO SPRAWDZENIA'


def test_optional_album_discogs_comment_do_not_block_ready(tmp_path: Path):
    track = complete_track(tmp_path, album=None, discogs_url=None, discogs_release_id=None, comment=None)
    completeness = metadata_completeness(track)
    assert completeness['missing_core'] == []
    assert {'Album / Release', 'Discogs URL', 'Komentarz'} <= set(completeness['missing_optional'])
    assert completeness['ready_for_manual_approval'] is True
    assert library_status_text(track) == 'GOTOWE'


def test_not_selected_is_first_class_library_status(tmp_path: Path):
    track = complete_track(tmp_path, status='not_selected')
    presentation = status_presentation(track.status)
    assert presentation.label == 'NIE WYBIERAM'


def test_duplicate_manual_decisions_lock_status_and_update_library_state(tmp_path: Path):
    from audio_library_organizer.duplicates.grouper import apply_duplicate_decision

    keep = complete_track(tmp_path, path=tmp_path/'keep.mp3', status='duplicate')
    duplicate = complete_track(tmp_path, path=tmp_path/'dup.mp3', status='ready')
    rejected = complete_track(tmp_path, path=tmp_path/'reject.mp3', status='ready')

    apply_duplicate_decision(keep, 'keep')
    apply_duplicate_decision(duplicate, 'duplicate')
    apply_duplicate_decision(rejected, 'not_selected')

    assert keep.status == 'ready'
    assert duplicate.status == 'duplicate'
    assert rejected.status == 'not_selected'
    assert '__status__' in keep.locked_fields
    assert '__status__' in duplicate.locked_fields
    assert '__status__' in rejected.locked_fields


def test_potential_duplicate_groups_include_same_artist_title_with_different_duration(tmp_path: Path):
    from audio_library_organizer.duplicates.grouper import group_potential_duplicates

    short = complete_track(tmp_path, path=tmp_path/'short.mp3', duration_seconds=220, bpm=132)
    long = complete_track(tmp_path, path=tmp_path/'long.mp3', duration_seconds=410, bpm=128)
    groups = group_potential_duplicates([short, long])
    assert len(groups) == 1
    assert {t.filename for t in groups[0]} == {'short.mp3', 'long.mp3'}


def test_genres_are_normalized_to_at_most_three_entries(tmp_path: Path):
    from audio_library_organizer.metadata.genre import normalize_genre_list

    assert normalize_genre_list('Electronic / Trance / Progressive Trance / Dance / Trance') == 'Electronic / Trance / Progressive Trance'
    assert normalize_genre_list('House; Deep House; Tech House; Dance') == 'House / Deep House / Tech House'


def test_provider_settings_persist_ready_folder_organization_choice():
    store = Store()
    cfg = ProviderSettings(folder_organization='artist')
    cfg.save(store)
    assert ProviderSettings.from_store(store).folder_organization == 'artist'


def test_export_routes_ready_into_optional_artist_subfolder_and_nonselected_to_nie_wybrane(tmp_path: Path):
    lib = LibraryPaths(tmp_path/'Library')
    lib.ensure_created()
    ready = complete_track(tmp_path, path=tmp_path/'ready.mp3', artist='4 Strings', proposed_filename='ready.mp3')
    rejected = complete_track(tmp_path, path=tmp_path/'reject.mp3', status='not_selected', proposed_filename='reject.mp3')
    duplicate = complete_track(tmp_path, path=tmp_path/'dup.mp3', status='duplicate', proposed_filename='dup.mp3')

    plan = ExportPlan.from_tracks([ready, rejected, duplicate], lib, folder_organization='artist')
    by_name = {item.filename: item.destination_dir for item in plan.items}
    assert by_name['ready.mp3'] == lib.ready / '4 Strings'
    assert by_name['reject.mp3'] == lib.not_selected
    assert by_name['dup.mp3'] == lib.not_selected


def test_library_paths_use_nie_wybrane_instead_of_duplicate_folder(tmp_path: Path):
    lib = LibraryPaths(tmp_path/'Library')
    assert lib.not_selected.name == 'NIE_WYBRANE'
    assert lib.duplicates == lib.not_selected


def test_cover_choice_is_persistable_on_track_record(tmp_path: Path):
    track = complete_track(tmp_path, cover_choice='placeholder')
    assert track.cover_choice == 'placeholder'


def test_bpm_display_rounds_for_library(tmp_path: Path):
    from audio_library_organizer.ui.state import display_bpm
    assert display_bpm(126.1) == '126'
    assert display_bpm(139.6) == '140'
    assert display_bpm(None) == ''


def test_duplicate_decision_changes_only_the_selected_file(tmp_path: Path):
    from audio_library_organizer.duplicates.grouper import apply_duplicate_decision

    a = complete_track(tmp_path, path=tmp_path/'a.mp3', status='duplicate')
    b = complete_track(tmp_path, path=tmp_path/'b.mp3', status='duplicate')
    c = complete_track(tmp_path, path=tmp_path/'c.mp3', status='review')

    apply_duplicate_decision(b, 'keep')

    assert a.status == 'duplicate'
    assert b.status == 'ready'
    assert c.status == 'review'
    assert '__status__' not in a.locked_fields
    assert '__status__' in b.locked_fields


def test_same_artist_title_but_materially_different_version_is_for_review_not_silent_ready(tmp_path: Path):
    from audio_library_organizer.duplicates.grouper import mark_duplicate_statuses

    short = complete_track(tmp_path, path=tmp_path/'short.mp3', duration_seconds=210, bpm=132, status='ready')
    long = complete_track(tmp_path, path=tmp_path/'long.mp3', duration_seconds=420, bpm=126, status='ready')

    mark_duplicate_statuses([short, long])

    assert short.status == 'review'
    assert long.status == 'review'
    assert all(any('Możliwa inna wersja' in reason for reason in t.match_reasons) for t in (short, long))
