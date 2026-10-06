import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QHeaderView

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.theme import DARK_STYLE


def settle(app):
    for _ in range(3):
        app.processEvents()


@pytest.fixture
def page(tmp_path):
    app = QApplication.instance() or QApplication([])
    old_style = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    page = LibraryPage()
    track = TrackRecord(path=tmp_path / 'sample.mp3', artist='Loleatta Holloway', title='Stand Up',
                        album='Sample release', year='2008', bpm=99,
                        genre='Euro House; Synth-pop, Disco', codec='MP3', bitrate_kbps=128,
                        sample_rate_hz=44100, channels=2, duration_seconds=529, size_bytes=8493466)
    page.set_tracks([track]); page.table.selectRow(0)
    page.resize(1920, 1080); page.show(); settle(app)
    yield page, track, app
    page.close(); app.setStyleSheet(old_style)


# Catches labels returning, off-center icons, or losing names for icon-only fields.
def test_completeness_has_only_centered_named_icons(page):
    page, _, _ = page
    assert not page.completeness_card.findChildren(QLabel, 'LibraryCompletenessField')
    for key in ('artist', 'title', 'year', 'genre', 'bpm', 'album'):
        icon = page.completeness_field_icons[key]
        tile = icon.parentWidget()
        assert abs(icon.geometry().center().x() - tile.rect().center().x()) <= 1
        assert abs(icon.geometry().center().y() - tile.rect().center().y()) <= 1
        assert icon.accessibleName() and icon.toolTip()


# Catches regressions in hierarchy, full-width genre, and the 2-by-3 technical grid.
@pytest.mark.parametrize('language', ['pl', 'en'])
@pytest.mark.parametrize('size', [(1920, 1080), (1536, 864), (1280, 720)])
def test_split_cards_fit_in_both_languages(page, language, size):
    page, track, app = page
    page.resize(*size); apply_static_language(page, language); page._show_detail(); settle(app)
    card = page.findChild(QFrame, 'LibraryTrackDataCard')
    assert not card.findChildren(QLabel, 'LibraryFieldIcon')
    tiles = {key: page.detail_labels[key].parentWidget() for key in ('artist', 'title', 'album', 'year', 'bpm', 'genre')}
    assert tiles['year'].y() == tiles['bpm'].y()
    assert tiles['year'].geometry().right() < tiles['bpm'].x()
    assert tiles['genre'].y() > tiles['year'].geometry().bottom()
    assert len({tiles[key].width() for key in ('artist', 'title', 'album', 'genre')}) == 1
    assert page.detail_labels['artist'].font().pointSizeF() > page.detail_labels['album'].font().pointSizeF()
    assert page.detail_labels['title'].font().pointSizeF() > page.detail_labels['genre'].font().pointSizeF()
    assert page.detail_labels['genre'].text() == 'Euro House / Synth-pop / Disco'
    for value in page.detail_labels.values():
        assert value.parentWidget().rect().contains(value.geometry())
        assert value.height() >= value.heightForWidth(value.width())
    rows = [('format', 'bitrate', 'sample_rate'), ('channels', 'duration', 'size')]
    for keys in rows:
        hosts = [page.detail_labels[key].parentWidget() for key in keys]
        assert len({host.y() for host in hosts}) == 1
        assert max(host.width() for host in hosts) - min(host.width() for host in hosts) <= 1
        assert all(host.findChildren(QLabel, 'LibraryFieldIcon') for host in hosts)
    assert page.detail_labels['channels'].parentWidget().y() > page.detail_labels['format'].parentWidget().geometry().bottom()
    assert page.cover.size().width() == page.cover.size().height() == 218
    assert page.detail.minimumWidth() == 640 and page.detail.maximumWidth() == 940
    assert page.detail_scroll.horizontalScrollBar().maximum() == 0


# Catches optional/core field state diverging from the six-field completeness card.
@pytest.mark.parametrize('missing,state,count', [((), 'complete', '6/6'), (('album',), 'partial', '5/6'),
                                                (('year', 'album'), 'incomplete', '4/6')])
def test_detail_field_accents_follow_completeness(page, missing, state, count):
    page, track, app = page
    for key in missing:
        setattr(track, key, None)
    page._show_detail(); settle(app)
    assert page.completeness_card.property('state') == state
    assert page.completeness_count.text() == count
    for key in ('artist', 'title', 'album', 'year', 'bpm', 'genre'):
        tile = page.detail_labels[key].parentWidget()
        color = tile.grab().toImage().pixelColor(1, tile.height() // 2)
        if key not in missing:
            assert color.green() > color.red() and color.green() > color.blue()
        elif key == 'album':
            assert page.detail_labels[key].text() == '—'
            assert color.red() > color.blue() and color.green() > color.blue()
        else:
            assert color.red() > color.green() and color.red() > color.blue()


def sort_tracks(tmp_path):
    return [
        TrackRecord(path=tmp_path / 'a.mp3', artist='Zulu', title='Zulu', year='9', bpm=87,
                    genre='Euro House / Zulu', duration_seconds=200, bitrate_kbps=320, codec='FLAC', status='ready'),
        TrackRecord(path=tmp_path / 'b.wav', artist='alpha', title='alpha', year='100', bpm=130,
                    genre='Euro House / Alpha', duration_seconds=660, bitrate_kbps=99, codec='MP3', status='ready'),
        TrackRecord(path=tmp_path / 'c.flac', artist='Beta', title='Beta', year='20', bpm=99,
                    genre='Disco / Trance', duration_seconds=242, bitrate_kbps=128, codec='WAV', status='ready'),
        TrackRecord(path=tmp_path / 'd.aiff', status='ready'),
    ]


# Catches sorting formatted strings, full genre lists, case-sensitive names, or unstable missing values.
@pytest.mark.parametrize('column,ascending,descending', [
    (2, ['d.aiff', 'b.wav', 'c.flac', 'a.mp3'], ['a.mp3', 'c.flac', 'b.wav', 'd.aiff']),
    (3, ['d.aiff', 'b.wav', 'c.flac', 'a.mp3'], ['a.mp3', 'c.flac', 'b.wav', 'd.aiff']),
    (4, ['d.aiff', 'a.mp3', 'c.flac', 'b.wav'], ['b.wav', 'c.flac', 'a.mp3', 'd.aiff']),
    (5, ['d.aiff', 'c.flac', 'a.mp3', 'b.wav'], ['a.mp3', 'b.wav', 'c.flac', 'd.aiff']),
    (6, ['d.aiff', 'a.mp3', 'c.flac', 'b.wav'], ['b.wav', 'c.flac', 'a.mp3', 'd.aiff']),
    (7, ['d.aiff', 'a.mp3', 'c.flac', 'b.wav'], ['b.wav', 'c.flac', 'a.mp3', 'd.aiff']),
    (8, ['d.aiff', 'b.wav', 'c.flac', 'a.mp3'], ['a.mp3', 'c.flac', 'b.wav', 'd.aiff']),
    (9, ['d.aiff', 'c.flac', 'a.mp3', 'b.wav'], ['b.wav', 'a.mp3', 'c.flac', 'd.aiff']),
])
def test_sorting_uses_raw_model_values(page, tmp_path, column, ascending, descending):
    page, _, _ = page
    page.set_tracks(sort_tracks(tmp_path))
    for order, expected in [(Qt.SortOrder.AscendingOrder, ascending), (Qt.SortOrder.DescendingOrder, descending)]:
        page.table.sortByColumn(column, order)
        assert [t.path.name for t in page.visible_tracks()] == expected


@pytest.mark.parametrize('column,field', [(4, 'year'), (6, 'bpm'), (7, 'duration_seconds'), (8, 'bitrate_kbps')])
def test_missing_invalid_and_nonfinite_numeric_values_sort_deterministically(page, tmp_path, column, field):
    page, _, _ = page
    tracks = [TrackRecord(path=tmp_path / f'{i}.mp3', status='ready') for i in range(5)]
    for track, value in zip(tracks, [None, 'invalid' if field == 'year' else float('nan'), 0, 99, 130]):
        setattr(track, field, value)
    # Invalid numeric display strings remain outside the model's sort key.
    if field == 'duration_seconds':
        tracks[1].duration_seconds = None
    page.set_tracks(tracks)
    page.table.sortByColumn(column, Qt.SortOrder.AscendingOrder)
    assert [t.path.name for t in page.visible_tracks()] == ['0.mp3', '1.mp3', '2.mp3', '3.mp3', '4.mp3']
    page.table.sortByColumn(column, Qt.SortOrder.DescendingOrder)
    assert [t.path.name for t in page.visible_tracks()] == ['4.mp3', '3.mp3', '2.mp3', '0.mp3', '1.mp3']


# Catches fixed data columns, zero-width columns, and resizing one column squeezing another.
def test_all_data_separators_resize_and_fixed_columns_stay_fixed(page):
    page, _, app = page
    header = page.table.horizontalHeader()
    assert header.sectionResizeMode(0) == header.sectionResizeMode(1) == QHeaderView.ResizeMode.Fixed
    original_fixed = [header.sectionSize(i) for i in (0, 1)]
    for col in range(2, 10):
        assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.Interactive
        header.resizeSection(col, 80)
    for col in range(10):
        x = header.sectionViewportPosition(col) + header.sectionSize(col) - 1
        before = header.sectionSize(col)
        widths = [header.sectionSize(i) for i in range(10)]
        QTest.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, header.height() // 2))
        QTest.mouseMove(header.viewport(), QPoint(x + 14, header.height() // 2))
        QTest.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x + 14, header.height() // 2))
        settle(app)
        assert header.sectionSize(col) == (before if col < 2 else before + 14)
        assert [header.sectionSize(i) for i in range(10) if i != col] == [widths[i] for i in range(10) if i != col]
    for col in range(2, 10):
        header.resizeSection(col, 0); settle(app)
        assert header.sectionSize(col) >= 48
        header.resizeSection(col, 140)
        assert header.sectionSize(col) == 140
    assert [header.sectionSize(i) for i in (0, 1)] == original_fixed


def test_wide_table_scrolls_and_keeps_widths_after_refresh_and_language(page):
    page, track, app = page
    header = page.table.horizontalHeader()
    for col, width in enumerate([36, page.table.columnWidth(1), 500, 680, 60, 100, 60, 70, 90, 60]):
        header.resizeSection(col, width)
    widths = [header.sectionSize(i) for i in range(10)]
    settle(app)
    bar = page.table.horizontalScrollBar()
    assert bar.isVisible() and bar.maximum() > 0
    bar.setValue(bar.maximum()); pos = bar.value()
    page.table.scrollTo(page.model.index(0, 3)); settle(app)
    assert bar.value() == pos
    page.resize(1536, 864); apply_static_language(page, 'en'); page.refresh(preserve_order=True); settle(app)
    assert [header.sectionSize(i) for i in range(10)] == widths
    assert bar.maximum() > 0


def test_native_separator_double_click_fits_title(page):
    page, track, app = page
    track.title = 'A long title with an extended version name'
    page.refresh(); settle(app)
    header = page.table.horizontalHeader(); header.resizeSection(3, 60)
    x = header.sectionViewportPosition(3) + header.sectionSize(3) - 1
    QTest.mouseDClick(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, header.height() // 2))
    settle(app)
    assert header.sectionSize(3) >= page.table.fontMetrics().horizontalAdvance(track.title)


def test_header_click_toggles_order_and_filters_preserve_sort(page, tmp_path):
    page, _, app = page
    tracks = sort_tracks(tmp_path); page.set_tracks(tracks)
    header = page.table.horizontalHeader()
    x = header.sectionViewportPosition(6) + header.sectionSize(6) // 2
    for expected in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
        QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, header.height() // 2))
        assert header.sortIndicatorSection() == 6 and header.sortIndicatorOrder() == expected
        assert header.isSortIndicatorShown()
    page.genre_filter.setText('Euro House'); page.bpm_min.setText('80'); page.bpm_max.setText('140')
    page.search.setText('a'); page.status.setCurrentIndex(page.status.findData('ready'))
    page.format_filter.setCurrentIndex(page.format_filter.findData('WAV'))
    assert [t.path.name for t in page.visible_tracks()] == ['b.wav']
    page.format_filter.setCurrentIndex(0); page.search.clear()
    assert [t.path.name for t in page.visible_tracks()] == ['b.wav', 'a.mp3']
    page.bpm_max.setText('100')
    assert [t.path.name for t in page.visible_tracks()] == ['a.mp3']


# Catches sorting triggering a refresh, path lookup, tag reads, cover reads or online work.
def test_13000_cached_records_sort_without_file_or_network_io(page, tmp_path, monkeypatch):
    page, _, app = page
    tracks = [TrackRecord(path=tmp_path / f'{i:05}.mp3', artist=f'Artist {13000-i:05}', title=f'Track {i:05}',
                          year=str(2000+i % 25), bpm=80+i % 81, genre='Euro House / Disco',
                          duration_seconds=180+i, bitrate_kbps=128+i % 193, status='ready') for i in range(13000)]
    page.set_tracks(tracks); page.table.selectRow(100); settle(app)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('Sorting must use cached model values only')
    with monkeypatch.context() as guard:
        import builtins, requests
        guard.setattr(builtins, 'open', forbidden)
        for name in ('open', 'stat', 'resolve', 'exists'):
            guard.setattr(Path, name, forbidden)
        guard.setattr(requests.sessions.Session, 'request', forbidden)
        guard.setattr('audio_library_organizer.ui.library_page.extract_embedded_cover', forbidden)
        for column in range(2, 10):
            page.table.sortByColumn(column, Qt.SortOrder.AscendingOrder)
            page.table.sortByColumn(column, Qt.SortOrder.DescendingOrder)
        page.table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
        settle(app)
        assert calls == []
        assert page.model.rowCount() == 13000
        assert page.model.item(0, 0).data(Qt.ItemDataRole.UserRole).path.name == '12999.mp3'
