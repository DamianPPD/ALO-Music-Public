from pathlib import Path
import os

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.naming import propose_filename, sanitize_windows_component
from audio_library_organizer.safety.copy_pipeline import copy_without_overwrite


def test_propose_filename_uses_artist_title_and_bpm(tmp_path: Path):
    track = TrackRecord(path=tmp_path/'old.mp3', artist='Armani & Ghost', title='Airport (Original Mix)', bpm=139)
    assert propose_filename(track) == 'Armani & Ghost - Airport (Original Mix) [139bpm].mp3'


def test_propose_filename_does_not_invent_missing_metadata(tmp_path: Path):
    track = TrackRecord(path=tmp_path/'34.mp3', bpm=125)
    assert propose_filename(track) == '34 [125bpm].mp3'


def test_windows_sanitization_removes_reserved_characters():
    assert sanitize_windows_component('A:B?C*D<') == 'A-B-C-D-'


def test_copy_without_overwrite_preserves_source_and_uses_collision_suffix(tmp_path: Path):
    src = tmp_path/'src.mp3'; dest_dir = tmp_path/'dest'; dest_dir.mkdir()
    src.write_bytes(b'abc123')
    before_stat = src.stat()
    first = copy_without_overwrite(src, dest_dir, 'Track.mp3')
    second = copy_without_overwrite(src, dest_dir, 'Track.mp3')
    assert first.name == 'Track.mp3'
    assert second.name == 'Track (2).mp3'
    assert src.read_bytes() == b'abc123'
    after_stat = src.stat()
    assert before_stat.st_mtime_ns == after_stat.st_mtime_ns
    assert first.read_bytes() == b'abc123' and second.read_bytes() == b'abc123'


def test_filename_template_supports_title_version_year_bpm_genre_and_album(tmp_path: Path):
    from audio_library_organizer.metadata.naming import render_filename_template

    track = TrackRecord(
        path=tmp_path/'old.mp3', artist='Armani & Ghost', title='Airport (Original Mix)',
        album='Airport', year='2003', genre='Hard House', bpm=139,
    )
    rendered = render_filename_template(
        track, '{Year} - {Artist} - {Title} ({Version}) [{BPM}bpm] - {Genre} - {Album}'
    )
    assert rendered == '2003 - Armani & Ghost - Airport (Original Mix) [139bpm] - Hard House - Airport'


def test_filename_template_removes_empty_optional_groups_cleanly(tmp_path: Path):
    from audio_library_organizer.metadata.naming import render_filename_template

    track = TrackRecord(path=tmp_path/'old.mp3', artist='A', title='Simple Title', bpm=None, year=None)
    rendered = render_filename_template(track, '{Artist} - {Title} ({Version}) [{Year}] [{BPM}bpm]')
    assert rendered == 'A - Simple Title'
    assert '()' not in rendered and '[]' not in rendered and 'bpm' not in rendered.casefold()


def test_propose_filename_uses_per_track_override_before_global_template(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path/'old.mp3', artist='A', title='Track (Club Mix)', bpm=128,
        filename_override='Mój własny zapis',
    )
    assert propose_filename(track, template='{Year} - {Artist}') == 'Mój własny zapis.mp3'


def test_default_template_reconstructs_existing_title_version_format(tmp_path: Path):
    from audio_library_organizer.metadata.naming import DEFAULT_FILENAME_TEMPLATE

    track = TrackRecord(path=tmp_path/'old.mp3', artist='Armani & Ghost', title='Airport (Original Mix)', bpm=139)
    assert propose_filename(track, template=DEFAULT_FILENAME_TEMPLATE) == 'Armani & Ghost - Airport (Original Mix) [139bpm].mp3'


def test_default_template_includes_year_when_available(tmp_path: Path):
    from audio_library_organizer.metadata.naming import DEFAULT_FILENAME_TEMPLATE

    track = TrackRecord(
        path=tmp_path/'old.mp3', artist='4 Strings',
        title='Take Me Away (Dave Darell Remix)', year='2009', bpm=132,
    )
    assert DEFAULT_FILENAME_TEMPLATE == '{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]'
    assert propose_filename(track) == '4 Strings - Take Me Away (Dave Darell Remix) (2009) [132bpm].mp3'


def test_template_from_field_selection_keeps_required_fields_and_order():
    from audio_library_organizer.metadata.naming import template_from_filename_fields

    assert template_from_filename_fields({'Artist', 'Title', 'Version', 'Year', 'BPM'}) == (
        '{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]'
    )
    assert template_from_filename_fields({'Artist', 'Title', 'BPM', 'Genre'}) == (
        '{Artist} - {Title} [{BPM}bpm] [{Genre}]'
    )


def test_filename_fields_from_template_recognizes_enabled_placeholders():
    from audio_library_organizer.metadata.naming import filename_fields_from_template

    fields = filename_fields_from_template('{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]')
    assert fields == {'Artist', 'Title', 'Version', 'Year', 'BPM'}
