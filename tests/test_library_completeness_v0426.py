import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.icons import library_icon
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.theme import DARK_STYLE


@pytest.fixture
def detail_page(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    page = LibraryPage()
    track = TrackRecord(path=tmp_path / 'track.mp3', artist='Artist', title='Title (Mix)',
                        album='Album', year='2008', genre='House', bpm=125)
    page.set_tracks([track]); page.table.selectRow(0)
    page.resize(1280, 720); page.show(); app.processEvents()
    yield app, page, track
    page.close(); app.setStyleSheet(previous)


# Catches treating optional Album as a core field, or using count alone for status.
@pytest.mark.parametrize('missing,count,pl,en', [
    ((), '6/6', 'Dane kompletne', 'Complete data'),
    (('album',), '5/6', 'Dane częściowe', 'Partial data'),
    (('year',), '5/6', 'Dane niekompletne', 'Incomplete data'),
    (('year', 'album'), '4/6', 'Dane niekompletne', 'Incomplete data'),
    (('title',), '5/6', 'Dane niekompletne', 'Incomplete data'),
])
@pytest.mark.parametrize('language', ['pl', 'en'])
def test_six_fields_have_three_distinct_states(detail_page, missing, count, pl, en, language):
    app, page, track = detail_page
    for key in missing:
        setattr(track, key, None)
    apply_static_language(page, language); page._show_detail(); app.processEvents()
    assert page.completeness_title.text() == (pl if language == 'pl' else en)
    assert page.completeness_count.text() == count
    assert {k for k, label in page.completeness_fields.items() if not label.property('complete')} == set(missing)
    assert not any('Brakuje:' in label.text() or 'Missing:' in label.text()
                   for label in page.completeness_card.findChildren(QLabel))


# Catches live language refresh reverting Partial data to the old two-state status.
def test_live_partial_language_and_field_colors(detail_page):
    app, page, track = detail_page
    track.album = None
    for language, title, artist in [('pl', 'Dane częściowe', 'Wykonawca'),
                                    ('en', 'Partial data', 'Artist'),
                                    ('pl', 'Dane częściowe', 'Wykonawca')]:
        apply_static_language(page, language); page._show_detail(); app.processEvents()
        assert page.completeness_title.text() == title
        assert page.completeness_fields['artist'].text() == artist
        assert page.completeness_title.palette().color(QPalette.ColorRole.WindowText) == QColor('#e5b86a')
        assert page.completeness_fields['artist'].palette().color(QPalette.ColorRole.WindowText) == QColor('#84e8c4')
        assert page.completeness_fields['album'].palette().color(QPalette.ColorRole.WindowText) == QColor('#e5b86a')
    track.year = None; page._show_detail(); app.processEvents()
    assert page.completeness_title.palette().color(QPalette.ColorRole.WindowText) == QColor('#ff927c')
    assert page.completeness_fields['year'].palette().color(QPalette.ColorRole.WindowText) == QColor('#ff927c')
    assert page.completeness_fields['artist'].palette().color(QPalette.ColorRole.WindowText) == QColor('#84e8c4')


# Catches substituting checkmark/status icons for the six semantic field icons.
def test_semantic_fields_share_one_row_and_album_is_separated(detail_page):
    app, page, track = detail_page
    keys = ['artist', 'title', 'year', 'genre', 'bpm', 'album']
    assert list(page.completeness_fields) == keys
    points = [page.completeness_field_icons[k].mapTo(page.completeness_card, QPoint(0, 0)) for k in keys]
    assert len({p.y() for p in points}) == 1
    assert [p.x() for p in points] == sorted(p.x() for p in points)
    for key, glyph in zip(keys, ['artist', 'music_note', 'calendar', 'tag', 'waveform', 'album']):
        icon = page.completeness_field_icons[key]
        assert icon.width() == icon.height() == 24
        assert icon.pixmap().toImage() == library_icon(glyph, '#84e8c4', 24).pixmap(24, 24).toImage()
        assert icon.width() > page.completeness_icon.pixmap().width() / page.completeness_icon.pixmap().devicePixelRatio()
    separator = page.completeness_card.findChild(QFrame, 'LibraryCompletenessAlbumSeparator')
    assert separator is not None and separator.width() == 1
    x = separator.mapTo(page.completeness_card, QPoint()).x()
    assert points[4].x() < x < points[5].x()
    assert all('✓' not in label.text() for label in page.completeness_card.findChildren(QLabel))


# Hand-measured frozen-main geometry: catches a larger sizeHint shifting cover/data/splitter.
@pytest.mark.parametrize('width,height,card_width,data_width', [
    (1920, 1080, 510, 741), (1536, 864, 387, 618),
    (1280, 720, 373, 604), (960, 540, 373, 604),
])
def test_panel_preserves_frozen_main_geometry(detail_page, width, height, card_width, data_width):
    app, page, track = detail_page
    page.resize(width, height); app.processEvents()
    assert page.cover.width() == page.cover.height() == 218
    assert (page.completeness_card.x(), page.completeness_card.y(), page.completeness_card.width(), page.completeness_card.height()) == (231, 0, card_width, 218)
    assert page.completeness_card.sizeHint().height() <= 202
    card = page.findChild(QFrame, 'LibraryTrackDataCard')
    assert (card.x(), card.y(), card.width(), card.height()) == (10, 234, data_width, 198)
    assert page.detail.minimumWidth() == 640 and page.detail.maximumWidth() == 940
    assert page.detail_title.parentWidget().height() == 50
    assert page.detail_title.x() == 49
    for language in ['en', 'pl']:
        apply_static_language(page, language); page._show_detail(); app.processEvents()
        for label in page.completeness_fields.values():
            assert page.completeness_card.rect().contains(label.mapTo(page.completeness_card, label.rect().bottomRight()))
            assert label.height() >= label.heightForWidth(label.width())


def test_details_header_reuses_two_line_section_mark(detail_page):
    app, page, _ = detail_page
    mark = page.detail_title_icon.findChild(QLabel, 'LibrarySectionMark')
    assert mark is not None and (mark.width(), mark.height()) == (20, 7)
    assert not mark.pixmap() or mark.pixmap().isNull()
    assert page.detail_title_icon.width() == 29
