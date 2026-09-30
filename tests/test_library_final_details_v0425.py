import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QFrame

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.theme import DARK_STYLE


def _page(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = LibraryPage()
    track = TrackRecord(path=tmp_path / 'careless.mp3', artist='Discofreunde',
                        title='Careless Whisper (Club Edit)', album='Eurochart',
                        year='2008', bpm=130, genre='Trance', confidence=0.22,
                        duration_seconds=448, bitrate_kbps=320, sample_rate_hz=44100,
                        channels=2, size_bytes=17_930_000, status='review',
                        sha256='a' * 64, comment='private note', discogs_url='https://discogs.com/private')
    page.set_tracks([track])
    page.table.selectRow(0)
    app.processEvents()
    return page, track


def test_selection_is_reconciled_with_visible_checkbox_model(tmp_path):
    page, track = _page(tmp_path)
    try:
        key = page._path_key(track)
        page._checked_paths.add(key)  # simulate stale state seen after a Windows reload
        page._update_selection_count()
        assert page._checked_paths == set()
        assert page.selected_count.isHidden()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
        assert not page.collection_btn.isEnabled() and not page.playlist_btn.isEnabled()

        with QSignalBlocker(page.model):
            page.model.item(0, 0).setCheckState(Qt.CheckState.Checked)
        page._update_selection_count()
        assert page._checked_paths == {key}
        assert page.selected_count.text().endswith('1')
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Checked
        page.search.setText('nothing')
        assert page._checked_paths == set() and page.selected_count.isHidden()
    finally:
        page.close()


def test_toolbar_filters_and_category_palette(tmp_path):
    page, track = _page(tmp_path)
    try:
        assert not hasattr(page, 'edit_main')
        assert page.collection_btn.isEnabled() is False
        assert page.playlist_btn.isEnabled() is False
        assert page.reset_view_btn.parentWidget() is page
        assert page.details_btn.parentWidget().parentWidget() is page.detail
        for category, color in page.CATEGORY_COLORS.items():
            index = page.status.findData(category)
            assert index >= 0
            assert page.status.model().item(index).foreground().color().name() == color
            assert not page.status.itemIcon(index).isNull()
        page.search.setText('wrong')
        page.reset_view_btn.click()
        assert page.search.text() == '' and page.model.rowCount() == 1
    finally:
        page.close()


def test_details_match_final_sections_and_one_edit_action(tmp_path):
    page, track = _page(tmp_path)
    try:
        assert not page.detail_title_icon.pixmap().isNull()
        assert page.detail_title.text() == 'Szczegóły utworu'
        assert {h.text() for h in page.detail_section_titles} == {
            'Rodzina wersji', 'Dane utworu', 'Pewność dopasowania', 'Dane techniczne'}
        assert len(page.detail_section_marks) == 4
        assert all(mark.objectName() == 'LibrarySectionMark' for mark in page.detail_section_marks)
        assert page.detail_labels['album'].text() == 'Eurochart'
        assert [page.detail_labels[name].text() for name in ('year', 'bpm', 'genre')] == ['2008', '130', 'Trance']
        assert page.confidence_percent.text() == '22%'
        assert page.confidence_bar.value() == 22
        assert page.detail_labels['format'].text() == 'MP3'
        assert page.detail_labels['bitrate'].text() == '320 kb/s'
        assert page.detail_labels['sample_rate'].text() == '44.1 kHz'
        assert page.detail_labels['channels'].text() == 'Stereo'
        assert page.detail_labels['duration'].text() == '7:28'
        assert page.detail_labels['size'].text().endswith('MB')
        assert not any(label.text() in {'DANE DODATKOWE', 'ŹRÓDŁA DANYCH', 'SHA-256', 'KOMENTARZ', 'DISCOGS URL'}
                       for label in page.detail.findChildren(QLabel))
        assert len([b for b in page.findChildren(QPushButton) if b.text() == 'Edytuj metadane']) == 1
        edits = []
        page.edit_requested.connect(edits.append)
        page.detail_edit.click()
        assert edits == [track]
        assert 'QWidget#LibraryPage QPushButton#LibraryDetailEdit' in DARK_STYLE
    finally:
        page.close()


def test_completeness_uses_six_mockup_fields_not_editor_core_checks(tmp_path):
    page, track = _page(tmp_path)
    try:
        assert page.completeness_count.text() == '6/6'
        assert page.completeness_title.text() == 'Dane kompletne'
        track.album = None
        track.year = None
        page._show_detail()
        assert page.completeness_count.text() == '4/6'
        assert page.completeness_title.text() == 'Dane niekompletne'
        assert {name for name, label in page.completeness_fields.items() if label.property('complete') is False} == {'album', 'year'}
        assert 'Rok' in page.completeness_hint.text() and 'Album' in page.completeness_hint.text()
    finally:
        page.close()


def test_family_disclosure_and_details_header_toggle(tmp_path):
    page, track = _page(tmp_path)
    try:
        page.show()
        QApplication.instance().processEvents()
        sibling = TrackRecord(path=tmp_path / 'careless-remix.mp3', artist=track.artist,
                              title='Careless Whisper (Remix)', duration_seconds=419)
        page.set_tracks([track, sibling])
        page.select_track(track)
        assert page.version_family_card.isVisible()
        assert page.family_toggle.text().startswith('Rodzina wersji')
        assert page.version_family_rows_layout.count() == 2
        assert any(row.property('current') is True for row in page.version_family_rows.findChildren(QFrame))
        page.family_toggle.click()
        assert not page.version_family_rows.isVisible()
        page.family_arrow.click()
        assert page.version_family_rows.isVisible()
        page.details_btn.click()
        assert not page.detail_scroll.isVisible()
        assert not page.detail_title.isVisible()
        assert page.details_btn.geometry().top() < 50
        assert page.detail.width() == 52
        page.details_btn.click()
        assert page.detail_scroll.isVisible()
        assert page.detail_title.isVisible()
    finally:
        page.close()


def test_new_details_text_translates_on_live_switch(tmp_path):
    page, track = _page(tmp_path)
    try:
        apply_static_language(page, 'en')
        page._show_detail()
        assert page.detail_title.text() == 'Track details'
        assert page.completeness_title.text() == 'Complete data'
        assert page.completeness_hint.text() == 'All data is complete.'
        assert page.detail_section_titles[1].text() == 'Track data'
        assert page.detail_section_titles[2].text() == 'Match confidence'
        assert page.detail_section_titles[3].text() == 'Technical data'
        assert page.confidence_description.text() == 'Low confidence — review the data'
        apply_static_language(page, 'pl')
        page._show_detail()
        assert page.detail_title.text() == 'Szczegóły utworu'
        assert page.completeness_title.text() == 'Dane kompletne'
        track.album = None
        apply_static_language(page, 'en')
        page._show_detail()
        assert page.completeness_title.text() == 'Incomplete data'
        assert page.completeness_hint.text() == 'Missing: Album'
    finally:
        page.close()


def test_detail_geometry_and_scroll_at_supported_logical_dpi_widths(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(DARK_STYLE)
    page, track = _page(tmp_path)
    try:
        sibling = TrackRecord(path=tmp_path / 'careless-remix.mp3', artist=track.artist,
                              title='Careless Whisper (Remix)', duration_seconds=419)
        page.set_tracks([track, sibling])
        page.show()
        page.select_track(track)
        assert page.version_family_card.isVisible()
        for width, height in ((1920, 1080), (1536, 864), (1280, 720), (960, 540)):
            page.resize(width, height)
            QApplication.instance().processEvents()
            cover = page.cover.geometry()
            complete = page.completeness_card.geometry()
            assert cover.right() < complete.left() and cover.top() == complete.top()
            track_card = page.findChild(QFrame, 'LibraryTrackDataCard')
            assert page.completeness_card.mapTo(page.detail_scroll.widget(), page.completeness_card.rect().bottomLeft()).y() < (
                track_card.mapTo(page.detail_scroll.widget(), track_card.rect().topLeft()).y())
            metrics = [page.detail_labels[key].mapTo(page.detail_scroll.widget(),
                       page.detail_labels[key].rect().topLeft())
                       for key in ('year', 'bpm', 'genre')]
            assert len({point.y() for point in metrics}) == 1
            for key in ('year', 'bpm', 'genre', 'sample_rate', 'channels'):
                value = page.detail_labels[key]
                assert value.fontMetrics().horizontalAdvance(value.text()) <= value.width()
            technical = page.technical_panel
            first = page.detail_labels['sample_rate']
            second = page.detail_labels['size']
            assert first.mapTo(technical, first.rect().bottomLeft()).y() < second.mapTo(
                technical, second.rect().topLeft()).y()
            assert second.mapTo(technical, second.rect().bottomLeft()).y() < technical.height()
            assert page.detail_edit.geometry().right() < page.detail.width()
            assert page.detail_scroll.verticalScrollBar().maximum() >= 0
    finally:
        page.close()
        app.setStyleSheet('')
