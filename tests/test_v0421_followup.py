import os
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.matching.resolver import IdentificationService, _text_query_tracks
from audio_library_organizer.metadata import filename_hints
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog


def _app():
    return QApplication.instance() or QApplication([])


def _close(dialog: MetadataEditorDialog) -> None:
    dialog._force_closing = True
    dialog.close()


@pytest.mark.parametrize(
    'value',
    (
        'WWW.FREEHOUSETRACKS.NET',
        'https://example.org/music/download?id=1',
        'Downloaded from Best Music Service',
        'Ripped by DJ-PROMO-TEAM',
        'Visit music-download.example.com',
    ),
)
def test_suspicious_metadata_detector_rejects_web_and_watermark_values(value: str):
    detector = getattr(filename_hints, 'is_suspicious_metadata_value', None)
    assert detector is not None
    assert detector(value)


def test_suspicious_metadata_detector_keeps_normal_artist_name():
    detector = getattr(filename_hints, 'is_suspicious_metadata_value', None)
    assert detector is not None
    assert not detector('BT feat. Jes')


def test_suspicious_metadata_detector_keeps_dotted_artist_name():
    detector = getattr(filename_hints, 'is_suspicious_metadata_value', None)
    assert detector is not None
    assert not detector('will.i.am')


def test_dotted_artist_tags_keep_priority_over_filename_identity(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path / 'Other Artist - Other Song.mp3',
        artist='will.i.am',
        title='Scream & Shout',
    )

    variants = _text_query_tracks(track)

    assert (variants[0].artist, variants[0].title) == ('will.i.am', 'Scream & Shout')


def test_garbage_artist_uses_artist_title_identity_without_mutating_metadata(tmp_path: Path):
    garbage = 'WWW.FREEHOUSETRACKS.NET'
    track = TrackRecord(
        path=tmp_path / 'Bt Feat. Jes - Every Other Way (Armin Van Buuren Remix).mp3',
        artist=garbage,
        title='Bt Feat. Jes - Every Other Way (Armin Van Buuren Remix)',
        album=garbage,
        genre=garbage,
        comment=garbage,
    )

    variants = _text_query_tracks(track)

    assert (variants[0].artist, variants[0].title) == (
        'Bt Feat. Jes',
        'Every Other Way (Armin Van Buuren Remix)',
    )
    assert track.artist == garbage
    assert track.title == 'Bt Feat. Jes - Every Other Way (Armin Van Buuren Remix)'


def test_valid_tags_keep_priority_over_different_filename_identity(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path / 'Wrong Filename Artist - Wrong Filename Title.mp3',
        artist='Correct Artist',
        title='Correct Title (Extended Mix)',
    )

    variants = _text_query_tracks(track)

    assert (variants[0].artist, variants[0].title) == ('Correct Artist', 'Correct Title (Extended Mix)')


def test_musicbrainz_query_falls_back_to_clean_identity_and_stops_after_match(tmp_path: Path):
    from audio_library_organizer.domain.candidates import MusicBrainzRecording

    class FakeMusicBrainz:
        def __init__(self):
            self.queries = []

        def search_recordings(self, artist, title, limit=3):
            self.queries.append((artist, title))
            if (artist, title) == ('Bt Feat. Jes', 'Every Other Way (Armin Van Buuren Remix)'):
                return [MusicBrainzRecording('mb1', artist, title, 420.0)]
            return []

    garbage = 'WWW.FREEHOUSETRACKS.NET'
    track = TrackRecord(
        path=tmp_path / 'Bt Feat. Jes - Every Other Way (Armin Van Buuren Remix).mp3',
        artist=garbage,
        title='Bt Feat. Jes - Every Other Way (Armin Van Buuren Remix)',
        album=garbage,
        genre=garbage,
        comment=garbage,
    )
    provider = FakeMusicBrainz()

    rows = IdentificationService(musicbrainz=provider)._records_from_text(track)

    assert rows and rows[0][0].recording_id == 'mb1'
    assert provider.queries[0] == ('Bt Feat. Jes', 'Every Other Way (Armin Van Buuren Remix)')
    assert len(provider.queries) == 1
    assert track.artist == garbage


def test_valid_tag_query_stops_before_filename_fallback(tmp_path: Path):
    from audio_library_organizer.domain.candidates import MusicBrainzRecording

    class FakeMusicBrainz:
        def __init__(self):
            self.queries = []

        def search_recordings(self, artist, title, limit=3):
            self.queries.append((artist, title))
            return [MusicBrainzRecording('mb-valid', artist, title, 240.0)]

    track = TrackRecord(
        path=tmp_path / 'Filename Artist - Filename Title.mp3',
        artist='Tagged Artist',
        title='Tagged Title',
    )
    provider = FakeMusicBrainz()

    rows = IdentificationService(musicbrainz=provider)._records_from_text(track)

    assert rows and rows[0][0].recording_id == 'mb-valid'
    assert provider.queries == [('Tagged Artist', 'Tagged Title')]


def test_cover_panel_has_one_online_search_and_four_visible_tiles_including_no_cover(tmp_path: Path, monkeypatch):
    app = _app()
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    sources = {f'Source {index}': f'https://example.test/{index}.jpg' for index in range(6)}
    dialog = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3',
                                               field_source_values={'__cover__': sources}))
    try:
        dialog.show()
        app.processEvents()

        assert dialog.search_cover_button.text() == 'Szukaj okładki online'
        assert not hasattr(dialog, 'more_covers_button')
        assert not hasattr(dialog, 'show_more_covers_button')
        assert list(dialog._cover_candidate_urls) == [f'external:Source {n}' for n in range(5)]
        assert list(dialog._cover_proposal_labels)[-1] == 'placeholder'
        assert list(dialog._cover_proposal_labels) == [f'external:Source {n}' for n in range(3)] + ['placeholder']
        assert dialog.cover_proposals_grid.count() == 4
    finally:
        _close(dialog)


def test_fewer_online_covers_still_include_no_cover_without_extra_controls(tmp_path: Path, monkeypatch):
    app = _app()
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    sources = {f'Source {index}': f'https://example.test/{index}.jpg' for index in range(4)}
    dialog = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3',
                                               field_source_values={'__cover__': sources}))
    try:
        dialog.show()
        app.processEvents()
        assert not hasattr(dialog, 'show_more_covers_button')
        assert list(dialog._cover_candidate_urls) == [f'external:Source {n}' for n in range(4)]
        assert dialog.cover_proposals_grid.count() == 4
        assert 'placeholder' in dialog._cover_proposal_labels
    finally:
        _close(dialog)


def test_online_lock_is_compact_toggle_next_to_online_actions(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3'))
    try:
        dialog.show()
        app.processEvents()
        unlocked_icon = dialog.online_lock.icon().cacheKey()

        assert dialog.online_lock.text() == ''
        assert dialog.online_lock.toolTip() == 'Rozpoznawanie online odblokowane'
        assert dialog.online_lock.width() < dialog.restore_pre_online_button.width()
        lock_center = dialog.online_lock.mapTo(dialog, dialog.online_lock.rect().center()).y()
        scan_center = dialog.scan_online_button.mapTo(dialog, dialog.scan_online_button.rect().center()).y()
        assert abs(lock_center - scan_center) <= 2

        dialog.online_lock.click()

        assert dialog.online_lock.toolTip() == 'Dane chronione przed ponownym rozpoznaniem online'
        assert dialog.online_lock.icon().cacheKey() != unlocked_icon
        assert not dialog.scan_online_button.isEnabled()
    finally:
        _close(dialog)


def test_source_name_text_uses_same_provider_color_as_dot(tmp_path: Path):
    app = _app()
    colors = {
        'Tag': '#5ca3ff',
        'Discogs': '#43d17d',
        'MusicBrainz': '#b36cff',
        'Apple / iTunes': '#e88abd',
        'Ręcznie': '#ffb84d',
        'Analiza audio': '#ef5b64',
    }
    display_names = {
        'Tag': 'TAG',
        'Discogs': 'Discogs',
        'MusicBrainz': 'MusicBrainz',
        'Apple / iTunes': 'Apple / iTunes',
        'Ręcznie': 'RĘCZNIE',
        'Analiza audio': 'ANALIZA AUDIO',
    }
    track = TrackRecord(
        path=tmp_path / 'track.mp3',
        field_source_values={'title': {source: f'Title {index}' for index, source in enumerate(colors)}},
    )
    dialog = MetadataEditorDialog(track)
    try:
        dialog.show()
        app.processEvents()
        for row, source in enumerate(dialog._source_rows()):
            if source not in colors:
                continue
            item = dialog.source_table.item(row, 0)
            assert dialog.source_table.cellWidget(row, 0) is None
            assert item.text() == display_names[source]
            assert item.foreground().color() == QColor(colors[source])
            assert not item.icon().isNull()
    finally:
        _close(dialog)
