import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog


def _close(editor):
    editor._force_closing = True
    editor.close()


def _cover(path, color, width=50, height=30):
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(color))
    assert pixmap.save(str(path))


def test_full_online_gallery_keeps_no_cover_visible_and_selectable(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    sources = {f'Provider {n}': f'https://example.test/{n}.png' for n in range(6)}
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3',
                                              field_source_values={'__cover__': sources}))
    try:
        assert list(editor._cover_candidate_urls) == [f'external:Provider {n}' for n in range(5)]
        assert list(editor._cover_proposal_labels)[-1] == 'placeholder'
        assert editor.cover_proposals_grid.count() == 4
        assert [editor.cover_proposals_grid.getItemPosition(n)[:2] for n in range(4)] == [
            (0, 0), (0, 1), (1, 0), (1, 1)]
        assert editor.findChild(QPushButton, 'CoverShowMoreAction') is None
        editor._cover_proposal_labels['placeholder'].clicked.emit()
        assert editor._selected_cover_key == 'placeholder'
        assert not editor.cover_save_state()['has_cover']
    finally:
        _close(editor)


def test_last_two_manual_slots_keep_old_choices_and_update_selected_cover(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3'))
    original = {}
    for n in range(3):
        key = f'external:Source {n}'
        original[key] = f'https://example.test/{n}.jpg'
        pixmap = QPixmap(40 + n, 30)
        pixmap.fill(QColor('#345678'))
        editor._cover_candidate_pixmaps[key] = pixmap
    editor._cover_candidate_urls = original
    editor._rebuild_cover_proposals()
    editor._select_cover_choice('external:Source 1', record_undo=False)
    first = tmp_path / 'fifth.png'
    second = tmp_path / 'sixth.png'
    _cover(first, '#336699')
    _cover(second, '#993366', 60, 35)
    files = iter((str(first), str(second)))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (next(files), ''))
    try:
        editor.show()
        app.processEvents()
        editor.choose_cover_button.click()
        assert len(editor._cover_proposal_labels) == 4
        assert list(editor._cover_candidate_urls) == list(original)
        assert editor.cover_info_values['source'].text() == 'Ręcznie'
        assert editor.cover_info_values['resolution'].text() == '50 × 30 px'
        editor.choose_cover_button.click()
        manual_keys = list(editor._manual_cover_paths)
        assert len(manual_keys) == 2
        assert len(editor._cover_proposal_labels) == 4
        assert all(key in editor._cover_candidate_pixmaps for key in original)
        assert [editor.cover_proposals_grid.getItemPosition(n)[:2] for n in range(4)] == [
            (0, 0), (0, 1), (1, 0), (1, 1)]
        assert editor.cover_proposal_count.text() == 'Propozycje (4)'
        for key, resolution, expected_path in ((manual_keys[0], '50 × 30 px', first),
                                               (manual_keys[1], '60 × 35 px', second)):
            editor._select_cover_choice(key, record_undo=False)
            editor._select_cover_choice('placeholder', record_undo=False)
            editor._cover_proposal_labels[key].clicked.emit()
            assert editor._selected_cover_key == key
            assert editor.cover_info_values['resolution'].text() == resolution
            assert editor.manual_cover_path == str(expected_path)
            assert editor.cover_save_state()['manual_cover_path'] == str(expected_path)
            card = editor._cover_proposal_labels[key].parentWidget()
            assert card.property('selected') is True
            assert not card.findChild(QLabel, 'CoverProposalSelectedMarker').isHidden()
        images = {key: editor._cover_candidate_pixmaps[key].toImage() for key in (*original, *manual_keys)}
        assert not editor.choose_cover_button.isEnabled()
        editor.choose_cover_button.click()
        assert len(editor._cover_proposal_labels) == 4
        for key, image in images.items():
            assert editor._cover_candidate_pixmaps[key].toImage() == image
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
        assert table.columnWidth(1) >= 300
        assert 260 <= table.columnWidth(2) < 400
        assert table.columnWidth(3) >= 220
        assert table.columnWidth(4) <= 72
        assert table.columnWidth(6) <= 130
        assert table.columnWidth(1) > table.columnWidth(2) > table.columnWidth(3)
        assert table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert not table.verticalScrollBar().isVisible()
        for row, source in enumerate(sources):
            assert table.item(row, 0).data(Qt.ItemDataRole.UserRole) == source
            assert table.item(row, 1).text() == f'Artist {row}'
            assert table.item(row, 2).text() == f'Title {row}'
            assert table.item(row, 3).text() == f'Album {row}'
            assert table.cellWidget(row, 0) is None
            assert table.cellWidget(row, 6).findChild(QPushButton, 'UseSourceDataButton').text() == 'Użyj danych'
    finally:
        _close(editor)
