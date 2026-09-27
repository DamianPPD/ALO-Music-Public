import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QColor, QFont, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import SOURCE as AUDIO_SOURCE
from audio_library_organizer.ui import metadata_editor as editor_module
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


def _close(editor):
    editor._force_closing = True
    editor.close()


def _image(path, width=42):
    pixmap = QPixmap(width, 32)
    pixmap.fill(QColor('#4779a1'))
    assert pixmap.save(str(path))


@pytest.mark.parametrize('count', range(8))
def test_online_results_never_exceed_five_covers_plus_no_cover(tmp_path, monkeypatch, count):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    sources = {f'Source {n}': f'https://example.test/{n}.jpg' for n in range(count)}
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3',
                                              field_source_values={'__cover__': sources}))
    try:
        assert list(editor._cover_candidate_urls) == [f'external:Source {n}' for n in range(min(count, 5))]
        assert list(editor._cover_proposal_labels) == [
            *(f'external:Source {n}' for n in range(min(count, 5))), 'placeholder']
        assert editor.cover_proposals_grid.count() == min(count, 5) + 1
        assert editor.cover_proposal_count.text() == f'Propozycje ({min(count, 5) + 1})'
        assert editor.choose_cover_button.isEnabled() == (count < 5)
        assert editor.findChild(QPushButton, 'CoverShowMoreAction') is None
        if count >= 5:
            assert [editor.cover_proposals_grid.getItemPosition(i)[:2] for i in range(6)] == [
                (0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]
            assert editor.cover_proposal_count.text() == 'Propozycje (6)'
    finally:
        _close(editor)


def test_online_slots_reserve_embedded_and_selected_manual_cover(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    path = tmp_path / 'manual.png'
    _image(path)
    monkeypatch.setattr(editor_module, 'extract_embedded_cover', lambda _: (path.read_bytes(), 'image/png'))
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    track = TrackRecord(path=tmp_path / 'track.mp3', manual_cover_path=str(path), cover_choice='manual',
                        field_source_values={'__cover__': {f'Source {n}': f'https://example.test/{n}.jpg'
                                                           for n in range(7)}})
    editor = MetadataEditorDialog(track)
    try:
        assert list(editor._cover_candidate_urls) == [f'external:Source {n}' for n in range(3)]
        assert list(editor._cover_proposal_labels) == [
            'source', 'external:Source 0', 'external:Source 1', 'external:Source 2', 'manual', 'placeholder']
        assert editor._selected_cover_key == 'manual'
        assert not editor.choose_cover_button.isEnabled()
        editor._select_cover_choice('placeholder', record_undo=False)
        assert editor._selected_cover_key == 'placeholder'
    finally:
        _close(editor)


def test_existing_selected_online_cover_stays_available_at_six_tile_limit(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    sources = {f'Source {n}': f'https://example.test/{n}.jpg' for n in range(7)}
    editor = MetadataEditorDialog(TrackRecord(
        path=tmp_path / 'track.mp3', cover_choice='external', cover_art_url=sources['Source 6'],
        field_source_values={'__cover__': sources},
    ))
    try:
        assert list(editor._cover_candidate_urls) == [
            'external:Source 0', 'external:Source 1', 'external:Source 2',
            'external:Source 3', 'external:Source 6',
        ]
        assert editor._selected_cover_key == 'external:Source 6'
        assert len(editor._cover_proposal_labels) == 6
        assert 'placeholder' in editor._cover_proposal_labels
    finally:
        _close(editor)


def test_add_from_computer_fills_slot_five_and_six_then_disables_button(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3'))
    editor._cover_candidate_urls = {f'external:Source {n}': f'https://example.test/{n}.jpg' for n in range(3)}
    for key in editor._cover_candidate_urls:
        pixmap = QPixmap(42, 32)
        pixmap.fill(QColor('#4783a1'))
        editor._cover_candidate_pixmaps[key] = pixmap
    editor._rebuild_cover_proposals()
    fifth, sixth = tmp_path / 'fifth.png', tmp_path / 'sixth.png'
    _image(fifth, 50)
    _image(sixth, 60)
    files = iter((str(fifth), str(sixth)))
    opened = []

    def choose(*_args):
        opened.append(True)
        return next(files), ''

    monkeypatch.setattr(QFileDialog, 'getOpenFileName', choose)
    try:
        editor.show()
        app.processEvents()
        assert editor.cover_proposals_grid.count() == 4
        editor.choose_cover_button.click()
        assert editor.cover_proposals_grid.count() == 5
        assert editor.choose_cover_button.isEnabled()
        assert 'manual' in editor._cover_proposal_labels
        editor.choose_cover_button.click()
        assert editor.cover_proposals_grid.count() == 6
        assert list(editor._cover_proposal_labels)[-1] == 'placeholder'
        assert {'manual', 'manual:1'} <= set(editor._cover_proposal_labels)
        assert all(key in editor._cover_proposal_labels for key in editor._cover_candidate_urls)
        assert editor._selected_cover_key == 'manual:1'
        assert editor.cover_info_values['resolution'].text() == '60 × 32 px'
        assert not editor.choose_cover_button.isEnabled()
        assert editor.choose_cover_button.toolTip() == 'Osiągnięto limit 6 okładek'
        images = {key: editor._cover_candidate_pixmaps[key].toImage()
                  for key in (*editor._cover_candidate_urls, 'manual', 'manual:1')}
        editor.choose_cover_button.click()
        assert len(opened) == 2
        assert editor.cover_proposals_grid.count() == 6
        assert all(editor._cover_candidate_pixmaps[key].toImage() == image for key, image in images.items())
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert editor.choose_cover_button.toolTip() == 'Cover limit of 6 reached'
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert editor.choose_cover_button.toolTip() == 'Osiągnięto limit 6 okładek'
    finally:
        _close(editor)


def test_only_cover_source_value_uses_existing_source_colors(tmp_path):
    app = QApplication.instance() or QApplication([])
    old_style = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3'))
    try:
        editor.show()
        app.processEvents()
        expected = (
            ('source', 'Tag'), ('external:Discogs', 'Discogs'),
            ('external:MusicBrainz', 'MusicBrainz'),
            ('external:Apple / iTunes', 'Apple / iTunes'),
            (f'external:{AUDIO_SOURCE}', AUDIO_SOURCE), ('manual', 'Ręcznie'),
        )
        pixmap = QPixmap(40, 40)
        pixmap.fill(QColor('#365c74'))
        for key, _source in expected:
            editor._cover_candidate_pixmaps[key] = pixmap
            editor._cover_candidate_states[key] = 'ready'
            if key.startswith('external:'):
                editor._cover_candidate_urls[key] = f'https://example.test/{len(editor._cover_candidate_urls)}.png'
        editor._manual_cover_paths['manual'] = str(tmp_path / 'selected.png')
        editor._rebuild_cover_proposals()
        other_values = {key: editor.cover_info_values[key].palette().color(QPalette.ColorRole.WindowText)
                        for key in ('resolution', 'type', 'format', 'size')}
        label_color = editor.cover_info_labels['source'].palette().color(QPalette.ColorRole.WindowText)
        for key, source in expected:
            editor._select_cover_choice(key, record_undo=False)
            assert editor.cover_info_values['source'].palette().color(QPalette.ColorRole.WindowText) == QColor(editor.SOURCE_COLORS[source])
            assert editor.cover_info_labels['source'].palette().color(QPalette.ColorRole.WindowText) == label_color
            assert all(editor.cover_info_values[name].palette().color(QPalette.ColorRole.WindowText) == color
                       for name, color in other_values.items())
        editor._select_cover_choice('placeholder', record_undo=False)
        assert editor.cover_info_values['source'].palette().color(QPalette.ColorRole.WindowText) == other_values['resolution']
    finally:
        _close(editor)
        app.setStyleSheet(old_style)


def test_result_filename_variant_b_is_bright_editable_and_restorable(tmp_path):
    app = QApplication.instance() or QApplication([])
    old_style = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'track.mp3', artist='Example', title='Song'))
    try:
        editor.show()
        app.processEvents()
        field = editor.filename_override
        assert field.text() == 'Example - Song.mp3'
        assert field.palette().color(QPalette.ColorRole.Text) == QColor('#ffffff')
        assert field.palette().color(QPalette.ColorRole.Base).lightness() > editor.title.palette().color(QPalette.ColorRole.Base).lightness()
        assert field.font().pointSizeF() > editor.title.font().pointSizeF()
        assert field.font().weight() >= QFont.Weight.DemiBold
        assert not field.isReadOnly()
        field.setText('My custom name.mp3')
        field.textEdited.emit(field.text())
        assert editor._filename_manual
        editor.findChild(QPushButton, 'RestoreFilenameButton').click()
        assert field.text() == 'Example - Song.mp3'
        assert not editor._filename_manual
    finally:
        _close(editor)
        app.setStyleSheet(old_style)
