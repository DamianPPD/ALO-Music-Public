import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog


def _close(editor):
    editor._force_closing = True
    editor.close()


def _cover(path, color, width=50, height=30):
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(color))
    assert pixmap.save(str(path))


@pytest.mark.parametrize('count', range(8))
def test_online_cover_suggestions_keep_all_six_real_covers(tmp_path, monkeypatch, count):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    sources = {f'Provider {n}': f'https://example.test/{n}.png' for n in range(count)}
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3',
                                              field_source_values={'__cover__': sources}))
    try:
        assert len(editor._cover_candidate_urls) == count
        visible = [key for key in editor._cover_proposal_labels if key.startswith('external:')]
        assert visible == [f'external:Provider {n}' for n in range(min(count, 6))]
        assert 'placeholder' in editor._cover_candidate_pixmaps
        if count >= 6:
            assert editor.cover_proposals_grid.count() == 6
            assert [editor.cover_proposals_grid.getItemPosition(n)[:2] for n in range(6)] == [
                (0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]
            editor.show()
            QApplication.instance().processEvents()
            assert editor.show_more_covers_button.isVisible()
            editor.show_more_covers_button.click()
            assert 'placeholder' in editor._cover_proposal_labels
            assert len([key for key in editor._cover_proposal_labels if key.startswith('external:')]) == count
    finally:
        _close(editor)


def test_add_fifth_and_sixth_cover_keeps_old_choices_and_seventh_is_rejected(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3'))
    four = {}
    for n in range(4):
        key = f'external:Source {n}'
        four[key] = f'https://example.test/{n}.jpg'
        pixmap = QPixmap(40 + n, 30)
        pixmap.fill(QColor('#345678'))
        editor._cover_candidate_pixmaps[key] = pixmap
    editor._cover_candidate_urls = four
    editor._rebuild_cover_proposals()
    editor._select_cover_choice('external:Source 1', record_undo=False)
    first = tmp_path / 'fifth.png'
    second = tmp_path / 'sixth.png'
    _cover(first, '#336699')
    _cover(second, '#993366', 60, 35)
    files = iter((str(first), str(second)))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (next(files), ''))
    notices = []
    monkeypatch.setattr(QMessageBox, 'information', lambda parent, title, message: notices.append((title, message)))
    try:
        editor.show()
        app.processEvents()
        editor.choose_cover_button.click()
        assert len([key for key in editor._cover_proposal_labels if key != 'placeholder']) == 5
        assert list(editor._cover_candidate_urls) == list(four)
        assert editor.cover_info_values['source'].text() == 'Ręcznie'
        assert editor.cover_info_values['resolution'].text() == '50 × 30 px'
        editor.choose_cover_button.click()
        manual_keys = [key for key in editor._cover_proposal_labels if key.startswith('manual')]
        assert len(manual_keys) == 2
        assert len([key for key in editor._cover_proposal_labels if key != 'placeholder']) == 6
        assert all(key in editor._cover_proposal_labels for key in four)
        assert [editor.cover_proposals_grid.getItemPosition(n)[:2] for n in range(6)] == [
            (0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]
        assert editor.cover_proposal_count.text() == 'Propozycje (6)'
        for key, resolution, expected_path in ((manual_keys[0], '50 × 30 px', first),
                                               (manual_keys[1], '60 × 35 px', second)):
            editor._cover_proposal_labels[key].clicked.emit()
            assert editor._selected_cover_key == key
            assert editor.cover_info_values['resolution'].text() == resolution
            assert editor.manual_cover_path == str(expected_path)
            assert editor.cover_save_state()['manual_cover_path'] == str(expected_path)
            card = editor._cover_proposal_labels[key].parentWidget()
            assert card.property('selected') is True
            assert not card.findChild(QLabel, 'CoverProposalSelectedBadge').isHidden()
        original = {key: editor._cover_candidate_pixmaps[key].toImage() for key in (*four, *manual_keys)}
        editor.choose_cover_button.click()
        assert notices == [('Okładka', 'Maksymalnie 6 propozycji okładek.')]
        assert len([key for key in editor._cover_proposal_labels if key != 'placeholder']) == 6
        for key, image in original.items():
            assert editor._cover_candidate_pixmaps[key].toImage() == image
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert editor.cover_proposal_count.text() == 'Suggestions (6)'
        editor.choose_cover_button.click()
        assert notices[-1] == ('Cover art', 'Maximum of 6 cover suggestions.')
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        editor.choose_cover_button.click()
        assert notices[-1] == ('Okładka', 'Maksymalnie 6 propozycji okładek.')
    finally:
        _close(editor)


def test_source_comparison_distributes_width_to_album_and_artist_without_moving_actions(tmp_path):
    app = QApplication.instance() or QApplication([])
    sources = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', 'Rozpoznanie audio', 'Ręcznie')
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3'))
    try:
        editor._source_values['title'] = {name: f'Title {n}' for n, name in enumerate(sources)}
        editor._source_values['album'] = {name: f'Album {n}' for n, name in enumerate(sources)}
        editor._source_values['artist'] = {name: f'Artist {n}' for n, name in enumerate(sources)}
        editor._refresh_source_comparison()
        editor.resize(1600, 1060)
        editor.show()
        app.processEvents()
        table = editor.source_table
        assert table.columnWidth(1) < 400
        assert table.columnWidth(2) >= 250
        assert table.columnWidth(3) >= 220
        assert table.columnWidth(4) <= 72
        assert table.columnWidth(6) <= 130
        assert table.columnWidth(1) > table.columnWidth(2) > table.columnWidth(3)
        assert table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert not table.verticalScrollBar().isVisible()
        for row, source in enumerate(sources):
            assert table.item(row, 0).data(Qt.ItemDataRole.UserRole) == source
            assert table.item(row, 1).text() == f'Title {row}'
            assert table.item(row, 2).text() == f'Album {row}'
            assert table.item(row, 3).text() == f'Artist {row}'
            assert table.cellWidget(row, 0) is None
            assert table.cellWidget(row, 6).findChild(QPushButton, 'UseSourceDataButton').text() == 'Użyj danych'
    finally:
        _close(editor)
