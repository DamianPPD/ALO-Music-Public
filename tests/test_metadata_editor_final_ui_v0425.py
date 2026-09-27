import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from audio_library_organizer.domain.candidates import AcoustIDHit
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import SOURCE
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog


def _editor(tmp_path):
    QApplication.instance() or QApplication([])
    return MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3'))


def _close(editor):
    editor._force_closing = True
    editor.close()


@pytest.mark.parametrize('count', (0, 1, 2, 3, 4, 5))
def test_cover_proposals_fit_two_columns_three_rows_without_extra_placeholders(tmp_path, count):
    editor = _editor(tmp_path)
    try:
        editor._cover_candidate_urls = {f'external:Discogs {i}': f'https://example.test/{i}.jpg' for i in range(count)}
        for key in editor._cover_candidate_urls:
            pix = QPixmap(120, 80)
            pix.fill(QColor('#456789'))
            editor._cover_candidate_pixmaps[key] = pix
        editor._rebuild_cover_proposals()
        positions = [editor.cover_proposals_grid.getItemPosition(i)[:2]
                     for i in range(editor.cover_proposals_grid.count())]
        assert len(positions) <= 6
        assert all(col in (0, 1) and row in (0, 1, 2) for row, col in positions)
        assert len(positions) == count + 1  # "Brak okładki" always occupies a tile.
        assert list(editor._cover_proposal_labels).count('placeholder') == 1
        assert 'placeholder' in editor._cover_candidate_pixmaps
        assert editor.cover_main_preview.size().width() == 248
        if count:
            key = next(iter(editor._cover_candidate_urls))
            editor._select_cover_choice(key, record_undo=False)
            card = editor._cover_proposal_labels[key].parentWidget()
            assert card.property('selected') is True
            assert card.findChild(QLabel, 'CoverProposalSelectedBadge').isVisibleTo(card)
    finally:
        _close(editor)


def test_cover_information_tracks_selection_and_missing_fields(tmp_path):
    editor = _editor(tmp_path)
    try:
        key = 'external:Discogs'
        pix = QPixmap(1200, 1200)
        pix.fill(QColor('#456789'))
        editor._cover_candidate_urls[key] = 'https://example.test/cover.jpg'
        editor._cover_candidate_pixmaps[key] = pix
        editor._cover_candidate_states[key] = 'ready'
        editor._cover_details[key] = {'format': 'JPG', 'bytes': 250880, 'type': 'Okładka główna (Front)'}
        editor._rebuild_cover_proposals()
        editor._select_cover_choice(key, record_undo=False)
        assert editor.cover_info_heading.text() == 'Informacje o okładce'
        assert editor.cover_info_values['source'].text() == 'Discogs'
        assert editor.cover_info_values['resolution'].text() == '1200 × 1200 px'
        assert editor.cover_info_values['type'].text() == 'Okładka główna (Front)'
        assert editor.cover_info_values['format'].text() == 'JPG'
        assert editor.cover_info_values['size'].text() == '245 KB'
        editor._select_cover_choice('placeholder', record_undo=False)
        assert editor.cover_info_values['source'].text() == '—'
        assert editor.cover_info_values['format'].text() == '—'
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert editor.cover_info_heading.text() == 'Cover information'
        assert editor.cover_info_labels['size'].text() == 'File size'
        editor._select_cover_choice(key, record_undo=False)
        assert editor.cover_info_values['type'].text() == 'Front cover'
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert editor.cover_info_values['type'].text() == 'Okładka główna (Front)'
    finally:
        _close(editor)


def test_empty_audio_result_and_error_are_compact_and_retry_is_available(tmp_path):
    app = QApplication.instance() or QApplication([])
    editor = _editor(tmp_path)
    requested = []
    editor.audio_scan_requested.connect(requested.append)
    try:
        editor.show()
        editor.show_audio_candidates([])
        app.processEvents()
        assert not editor.audio_candidate_content.isVisible()
        assert not editor.audio_candidates.isVisible()
        assert not editor.audio_confirm_button.isVisible()
        assert editor.audio_empty_status.isVisible()
        assert editor.audio_empty_heading.text() == 'Brak wyników rozpoznawania audio'
        assert editor.audio_empty_retry.isEnabled()
        editor.audio_empty_retry.click()
        assert requested == [editor]
        editor.start_audio_lookup()
        editor.show_audio_error('Przekroczono czas oczekiwania na AcoustID.')
        assert editor.audio_empty_status.isVisible()
        assert not editor.audio_candidate_content.isVisible()
        assert editor.audio_empty_heading.text() == 'Błąd rozpoznawania audio'
        editor.start_audio_lookup()
        editor.show_audio_candidates([AcoustIDHit('rec', .9, 'Track', 'Artist')])
        assert editor.audio_candidate_content.isVisible()
        assert not editor.audio_empty_status.isVisible()
        assert editor.audio_candidates.rowCount() == 1
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        editor.show_audio_candidates([])
        assert editor.audio_empty_heading.text() == 'No audio recognition results'
        assert editor.audio_empty_message.text() == 'No candidates found.'
    finally:
        _close(editor)


def test_source_comparison_has_album_column_and_action_only_at_last_index(tmp_path):
    editor = _editor(tmp_path)
    try:
        sources = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', SOURCE, 'Ręcznie')
        editor._source_values = {
            'title': {s: f'Title {i}' for i, s in enumerate(sources)},
            'album': {s: f'Album {i}' for i, s in enumerate(sources)},
            'artist': {s: f'Artist {i}' for i, s in enumerate(sources)},
        }
        editor._refresh_source_comparison()
        table = editor.source_table
        assert table.columnCount() == 7
        assert [table.horizontalHeaderItem(i).text() for i in range(7)] == [
            'Źródło', 'Tytuł / wersja', 'Album / Release', 'Wykonawca', 'Rok', 'Gatunek', 'Akcja']
        assert table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        for row, source in enumerate(sources):
            assert table.item(row, 0).data(Qt.ItemDataRole.UserRole) == source
            assert table.item(row, 1).text() == f'Title {row}'
            assert 'Album:' not in table.item(row, 1).text()
            assert table.item(row, 2).text() == f'Album {row}'
            assert table.cellWidget(row, 0) is None
            assert table.cellWidget(row, 6).findChild(QPushButton, 'UseSourceDataButton').text() == 'Użyj danych'
        table.cellWidget(1, 6).findChild(QPushButton, 'UseSourceDataButton').click()
        assert editor._field_widgets['album'].text() == 'Album 1'
        assert editor._current_sources['album'] == 'Discogs'
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert table.horizontalHeaderItem(2).text() == 'Album / Release'
        assert table.horizontalHeaderItem(6).text() == 'Action'
    finally:
        _close(editor)
