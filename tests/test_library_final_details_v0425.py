import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QPoint, QEvent, QCoreApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QFrame

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.library_status_legend import install_library_status_legend, LEGEND_ITEMS
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
        tracks = [TrackRecord(path=tmp_path / f'{i}.mp3', title=str(i)) for i in range(5)]
        page.set_tracks(tracks)
        expected = {page._path_key(t) for t in tracks[:4]}
        page._checked_paths = expected.copy()
        page._update_selection_count()
        assert page._checked_paths == expected
        checked = {page._path_key(page.model.item(row, 0).data(Qt.ItemDataRole.UserRole))
                   for row in range(5) if page.model.item(row, 0).checkState() == Qt.CheckState.Checked}
        assert checked == expected
        assert page.selected_count.text().endswith('4')
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.PartiallyChecked
        assert page.collection_btn.isEnabled() and page.playlist_btn.isEnabled()
        page.resize(1600, 720); page.show()
        QApplication.instance().processEvents()
        pixmap = page.table.viewport().grab()
        rendered = pixmap.toImage()
        ratio = pixmap.devicePixelRatio()
        painted = []
        for row in range(5):
            center = page.table.visualRect(page.model.index(row, 0)).center()
            colors = [rendered.pixelColor(x, y)
                      for y in range(round((center.y() - 6) * ratio), round((center.y() + 7) * ratio))
                      for x in range(round((center.x() - 6) * ratio), round((center.x() + 7) * ratio))]
            painted.append(any(min(c.red(), c.green(), c.blue()) > 220
                               and max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) < 15
                               for c in colors))
        assert painted == [True, True, True, True, False]
        page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        page.refresh(preserve_order=True)
        assert page._visible_checked_paths() == expected
        page.search.setText('nothing')
        assert page._checked_paths == set() and page.selected_count.isHidden()
    finally:
        page.close()


def test_clicked_checkbox_enums_paint_and_uncheck_consistently(tmp_path):
    page, _ = _page(tmp_path)
    app = QApplication.instance()
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    tracks = [TrackRecord(path=tmp_path / f'click-{i}.mp3', title=str(i)) for i in range(5)]
    page.set_tracks(tracks); page.resize(1600, 720); page.show(); app.processEvents()
    def painted_checks():
        app.processEvents()
        pixmap = page.table.viewport().grab(); rendered = pixmap.toImage(); ratio = pixmap.devicePixelRatio()
        painted = []
        for row in range(5):
            center = page.table.visualRect(page.model.index(row, 0)).center()
            colors = [rendered.pixelColor(x, y)
                      for y in range(round((center.y() - 6) * ratio), round((center.y() + 7) * ratio))
                      for x in range(round((center.x() - 6) * ratio), round((center.x() + 7) * ratio))]
            painted.append(any(min(c.red(), c.green(), c.blue()) > 220
                               and max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) < 15
                               for c in colors))
        return painted

    try:
        assert painted_checks() == [False] * 5
        assert page.selected_count.isHidden()
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.Unchecked
        for row in range(4):
            QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton,
                             pos=page.table.visualRect(page.model.index(row, 0)).center())
            if row == 0:
                assert painted_checks() == [True, False, False, False, False]
                assert page.selected_count.text().endswith('1')
        assert len(page._checked_paths) == 4
        assert page.selected_count.text().endswith('4')
        assert page.table.horizontalHeader().checkState() == Qt.CheckState.PartiallyChecked
        assert painted_checks() == [True, True, True, True, False]
        QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=page.table.visualRect(page.model.index(0, 0)).center())
        assert len(page._checked_paths) == 3
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Unchecked
        # QVariant may contain either the enum or the integer from setCheckState.
        page.model.setData(page.model.index(0, 0), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        assert page.table.itemDelegate()._check_state(page.model.index(0, 0)) == Qt.CheckState.Checked
    finally:
        page.close()
        app.setStyleSheet(previous)


def test_details_toggle_is_above_panel_and_collapse_uses_full_table_width(tmp_path):
    page, _ = _page(tmp_path)
    page.resize(1600, 900); page.show(); QApplication.instance().processEvents()
    try:
        button = page.details_btn.geometry().translated(page.details_btn.parentWidget().mapTo(page, QPoint(0, 0)))
        panel = page.detail.geometry().translated(page.detail.parentWidget().mapTo(page, QPoint(0, 0)))
        assert button.bottom() < panel.top()
        assert abs(button.right() - panel.right()) <= 1
        expanded_width = page.table.width()
        page.details_btn.click(); QApplication.instance().processEvents()
        assert not page.detail.isVisible() and page.details_btn.isVisible()
        assert page.table.width() == page.split.width()
        assert page.table.width() > expanded_width
        page.details_btn.click(); QApplication.instance().processEvents()
        assert page.detail.isVisible() and page.detail_scroll.isVisible()
        assert page.table.width() == expanded_width
    finally:
        page.close()


def test_select_all_notifies_row_views_after_signal_blocked_batch(tmp_path):
    page, track = _page(tmp_path)
    try:
        spy = QSignalSpy(page.model.dataChanged)
        page.table.horizontalHeader().toggleVisibleChecks()
        assert spy.count() > 0
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Checked
        assert page.selected_count.text().endswith('1')
        page.table.horizontalHeader().toggleVisibleChecks()
        assert page.selected_count.isHidden()
        assert page.model.item(0, 0).checkState() == Qt.CheckState.Unchecked
    finally:
        page.close()


def test_toolbar_filters_and_category_palette(tmp_path):
    page, track = _page(tmp_path)
    try:
        assert not hasattr(page, 'edit_main')
        assert page.collection_btn.isEnabled() is False
        assert page.playlist_btn.isEnabled() is False
        assert page.reset_view_btn.parentWidget() is page
        assert page.details_btn.parentWidget() is page
        for category, color in page.CATEGORY_COLORS.items():
            index = page.status.findData(category)
            assert index >= 0
            expected = '#6de6a5' if category == page.status.currentData() else color
            assert page.status.model().item(index).foreground().color().name() == expected
            assert not page.status.itemIcon(index).isNull()
        page.search.setText('wrong')
        page.reset_view_btn.click()
        assert page.search.text() == '' and page.model.rowCount() == 1
    finally:
        page.close()


def test_details_match_final_sections_and_one_edit_action(tmp_path):
    page, track = _page(tmp_path)
    try:
        assert page.detail_title_icon.findChild(QLabel, 'LibrarySectionMark') is not None
        assert page.detail_title.text() == 'Szczegóły utworu'
        assert {h.text() for h in page.detail_section_titles} == {
            'Rodzina wersji', 'Dane utworu', 'Dane techniczne'}
        assert len(page.detail_section_marks) == 3
        assert all(mark.objectName() == 'LibrarySectionMark' for mark in page.detail_section_marks)
        assert page.detail_labels['album'].text() == 'Eurochart'
        assert [page.detail_labels[name].text() for name in ('year', 'bpm', 'genre')] == ['2008', '130', 'Trance']
        assert page.detail.findChild(QFrame, 'LibraryConfidenceCard') is None
        assert track.confidence == .22
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
    app = QApplication.instance()
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    try:
        page.show()
        app.processEvents()
        assert page.completeness_count.text() == '6/6'
        assert page.completeness_title.text() == 'Dane kompletne'
        assert page.completeness_title.palette().color(QPalette.ColorRole.WindowText) == QColor('#64e8bc')
        track.album = None
        track.year = None
        page._show_detail()
        assert page.completeness_count.text() == '4/6'
        assert page.completeness_title.text() == 'Dane niekompletne'
        assert {name for name, label in page.completeness_fields.items() if label.property('complete') is False} == {'album', 'year'}
        assert not any('Brakuje:' in label.text() for label in page.completeness_card.findChildren(QLabel))
        app.processEvents()
        assert page.completeness_title.palette().color(QPalette.ColorRole.WindowText) == QColor('#ff927c')
        field = page.completeness_fields['year']
        border = field.grab().toImage().pixelColor(0, field.height() // 2)
        assert border.red() > border.green() and border.red() > border.blue()
    finally:
        page.close()
        app.setStyleSheet(previous)


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
        QApplication.instance().processEvents()
        assert not page.detail_scroll.isVisible()
        assert not page.detail_title.isVisible()
        assert page.details_btn.geometry().bottom() < page.split.geometry().top()
        assert page.details_btn.isVisible()
        assert page.details_btn.text() == 'Rozwiń szczegóły'
        assert page.details_btn.width() >= page.details_btn.sizeHint().width()
        page.details_btn.click()
        assert page.detail_scroll.isVisible()
        assert page.detail_title.isVisible()
        assert page.details_btn.text() == 'Zwiń szczegóły'
    finally:
        page.close()


def test_new_details_text_translates_on_live_switch(tmp_path):
    page, track = _page(tmp_path)
    try:
        apply_static_language(page, 'en')
        page._show_detail()
        assert page.detail_title.text() == 'Track details'
        assert page.completeness_title.text() == 'Complete data'
        assert not hasattr(page, 'completeness_hint')
        assert page.detail_section_titles[1].text() == 'Track data'
        assert page.detail_section_titles[2].text() == 'Technical data'
        assert page.details_btn.text() == 'Collapse details'
        page.details_btn.click()
        assert page.details_btn.text() == 'Expand details'
        apply_static_language(page, 'pl')
        page._show_detail()
        assert page.details_btn.text() == 'Rozwiń szczegóły'
        assert page.detail_title.text() == 'Szczegóły utworu'
        assert page.completeness_title.text() == 'Dane kompletne'
        track.album = None
        apply_static_language(page, 'en')
        page._show_detail()
        assert page.completeness_title.text() == 'Partial data'
        assert page.completeness_count.text() == '5/6'
        assert not any('Missing:' in label.text() for label in page.completeness_card.findChildren(QLabel))
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
            assert metrics[0].y() == metrics[1].y() < metrics[2].y()
            for key in ('year', 'bpm', 'genre', 'sample_rate', 'channels'):
                value = page.detail_labels[key]
                assert value.fontMetrics().horizontalAdvance(value.text()) <= value.width()
            metric_hosts = [page.detail_labels[key].parentWidget() for key in ('year', 'bpm')]
            assert max(host.width() for host in metric_hosts) - min(host.width() for host in metric_hosts) <= 1
            assert page.detail_labels['genre'].parentWidget().width() > metric_hosts[0].width()
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


def test_legend_stays_at_upper_right_when_toolbar_reflows(tmp_path):
    app = QApplication.instance() or QApplication([])
    page, track = _page(tmp_path)
    try:
        legend = install_library_status_legend(page)
        assert install_library_status_legend(page) is legend
        assert len(legend.menu().actions()) == len(LEGEND_ITEMS)
        for width in (1920, 960, 800):
            page.resize(width, 720)
            page.show()
            app.processEvents()
            assert page._filters_top.indexOf(legend) == page._filters_top.count() - 1
            box = legend.geometry().translated(legend.parentWidget().mapTo(page, QPoint(0, 0)))
            assert box.right() >= page.width() - 12
            assert box.bottom() < page.split.geometry().top()
            assert legend.isVisible()
        legend.menu().popup(legend.mapToGlobal(legend.rect().bottomLeft()))
        app.processEvents()
        assert legend.menu().isVisible()
        legend.menu().hide()
    finally:
        page.close()


def test_pending_table_style_refresh_is_cancelled_when_page_is_destroyed(tmp_path, capsys):
    app = QApplication.instance() or QApplication([])
    page, track = _page(tmp_path)
    QCoreApplication.sendEvent(page.table, QEvent(QEvent.Type.StyleChange))
    page.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert 'already deleted' not in capsys.readouterr().err


def test_select_all_reconciles_once_even_when_batch_notification_emits_item_changed(tmp_path, monkeypatch):
    page, track = _page(tmp_path)
    try:
        page.set_tracks([TrackRecord(path=tmp_path / f'{i}.mp3') for i in range(30)])
        calls = []
        original = page._update_selection_count
        def counted():
            calls.append(1)
            original()
        monkeypatch.setattr(page, '_update_selection_count', counted)
        page.table.horizontalHeader().toggleVisibleChecks()
        assert len(calls) == 1
        assert len(page._visible_checked_paths()) == 30
        assert page.selected_count.text().endswith('30')
    finally:
        page.close()


def test_collapsed_details_fit_after_live_english_to_polish_switch(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    page, track = _page(tmp_path)
    try:
        page.resize(1280, 720); page.show()
        apply_static_language(page, 'en')
        page.details_btn.click()
        app.processEvents()
        apply_static_language(page, 'pl')
        app.processEvents()
        assert page.details_btn.text() == 'Rozwiń szczegóły'
        assert page.details_btn.width() >= page.details_btn.sizeHint().width()
    finally:
        page.close()
        app.setStyleSheet(previous)
