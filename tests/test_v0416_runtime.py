import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.candidates import MetadataCandidate
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.matching.resolver import _text_query_tracks, apply_candidate
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_metadata_editor_builds_new_compact_workspace_without_network(tmp_path: Path):
    _app()
    track = TrackRecord(
        path=tmp_path / '12-07-56 - RELOCATE - Built To Last (Ferry Tayle rmx).mp3',
        artist='RELOCATE',
        title='Built To Last (Ferry Tayle Remix)',
        bpm=138,
        status='review',
        field_sources={'artist': 'Nazwa pliku', 'title': 'Nazwa pliku', 'bpm': 'Analiza audio'},
        field_source_values={
            'artist': {'Nazwa pliku': 'RELOCATE'},
            'title': {'Nazwa pliku': 'Built To Last (Ferry Tayle Remix)'},
            'bpm': {'Analiza audio': 138},
        },
    )
    dialog = MetadataEditorDialog(track)
    try:
        assert dialog.artist.text() == 'RELOCATE'
        assert dialog.source_table.columnCount() == 6
        assert dialog.source_legend_button.text() == ''
        assert not dialog.source_legend_button.icon().isNull()
        assert dialog.source_legend_button.property('iconStyle') == 'thin'
        assert dialog.cover_main_preview.width() == 248
        assert dialog.status_button.text() == 'DO SPRAWDZENIA'
        assert not hasattr(dialog, 'ready_button')
        assert dialog.status_icons['artist'].text() == ''
        assert dialog.status_icons['artist'].pixmap() is not None and not dialog.status_icons['artist'].pixmap().isNull()
        assert dialog.status_icons['year'].text() == ''
        assert dialog.status_icons['year'].pixmap() is not None and not dialog.status_icons['year'].pixmap().isNull()
        assert dialog.recognition_bar.height() == 6
    finally:
        dialog._force_closing = True
        dialog.close()


def test_timestamped_radio_fragment_stays_review_even_for_strong_match(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path / '12-07-56 - RELOCATE - Built To Last (Ferry Tayle rmx).mp3',
        artist='RELOCATE',
        title='Built To Last (Ferry Tayle Remix)',
        duration_seconds=316,
        status='review',
    )
    candidate = MetadataCandidate(
        source='apple',
        artist='Re:Locate',
        title='Built To Last (Ferry Tayle Remix)',
        duration_seconds=417,
        score=0.97,
        reasons=('strong match',),
    )
    apply_candidate(track, candidate)
    assert track.status == 'review'
    assert any('fragment audycji' in reason for reason in track.match_reasons)
    assert any('Długość pliku' in reason for reason in track.match_reasons)


def test_compact_source_comparison_hides_bpm_only_analysis_row(tmp_path: Path):
    _app()
    track = TrackRecord(
        path=tmp_path / '12-07-56 - RELOCATE - Built To Last (Ferry Tayle rmx).mp3',
        artist='12-07-56',
        title='Relocate - Built To Last (Ferry Tayle Rmx)',
        bpm=138,
        field_source_values={
            'artist': {'Nazwa pliku': '12-07-56'},
            'title': {'Nazwa pliku': 'Relocate - Built To Last (Ferry Tayle Rmx)'},
            'bpm': {'Analiza audio': 138},
        },
    )
    dialog = MetadataEditorDialog(track)
    try:
        assert dialog._source_rows() == ['Nazwa pliku']
        assert dialog.source_table.rowCount() == 1
    finally:
        dialog._force_closing = True
        dialog.close()


def test_legacy_timestamp_metadata_uses_clean_filename_identity_first(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path / '12-07-56 - RELOCATE - Built To Last (Ferry Tayle rmx).mp3',
        artist='12-07-56',
        title='Relocate - Built To Last (Ferry Tayle Rmx)',
    )
    variants = _text_query_tracks(track)
    assert variants[0].artist == 'RELOCATE'
    assert variants[0].title == 'Built To Last (Ferry Tayle Remix)'
    assert variants[1].artist == '12-07-56'
