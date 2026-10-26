"""Stage6.1B: rendered category state survives blur; legend copy is secondary."""
from copy import deepcopy
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from audio_library_organizer.ui.i18n import apply_static_language
from test_library_legend_filters_v0427 import page, open_legend


def border_colors(combo):
    QApplication.processEvents()
    image = combo.grab().toImage()
    ratio = combo.devicePixelRatioF()
    return [image.pixelColor(x, 0).name()
            for x in range(round(12 * ratio), round((combo.width() - 24) * ratio))]


def click_table(page):
    QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton,
                     pos=page.table.visualRect(page.model.index(0, 2)).center())
    QApplication.processEvents()
    assert page.table.hasFocus() and not page.status.hasFocus()


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_legend_secondary_copy_is_muted_while_names_icons_and_layout_stay_intact(page, language):
    p, _ = page
    apply_static_language(p, language)
    _, d = open_legend(p)
    names = d.findChildren(QLabel, 'LibraryLegendName')
    details = d.findChildren(QLabel, 'LibraryLegendDescription')
    assert len(names) == len(details) == 11
    assert len(d.findChildren(QLabel, 'LibraryLegendIcon')) == 5
    for label in details + [d.findChild(QLabel, 'LibraryLegendUnconfirmed')]:
        assert label.palette().color(QPalette.ColorRole.WindowText).name() == '#9daab9'
        assert label.isVisible() and label.height() >= label.heightForWidth(label.width())
    for name, detail in zip(names, details):
        assert name.contentsRect().width() >= name.fontMetrics().horizontalAdvance(name.text())
        assert detail.mapTo(d, detail.rect().topLeft()).x() - name.mapTo(d, name.rect().topRight()).x() >= 18
    assert names[0].palette().color(QPalette.ColorRole.WindowText).name() == '#35d893'
    assert names[5].palette().color(QPalette.ColorRole.WindowText).name() == '#6dcda0'
    assert d.width() <= 820 and d.height() < 600
    QTest.keyClick(d, Qt.Key.Key_Escape)
    assert not d.isVisible()


@pytest.mark.parametrize('key,accent', [
    ('ready', '#6de6a5'), ('duplicate', '#bd9bf7'), ('review', '#f4bd75'),
    ('no_cover', '#f4bd75'), ('not_selected', '#bdcbd3'),
])
def test_category_border_remains_after_table_other_focus_hover_and_popup_cancel(page, key, accent):
    p, tracks = page
    before = deepcopy(tracks)
    p.status.setCurrentIndex(p.status.findData(key))
    visible = [str(t.path) for t in p.visible_tracks()]
    size = p.status.size()
    p.status.setFocus()
    focused = border_colors(p.status)
    # The strongest outer pixel covers half a logical dashed stroke, scaled
    # by DPR. Allow one 8-bit quantization level, never an arbitrary hue.
    ink, background = QColor(accent), QColor('#151b23')
    coverage = min(1.0, p.status.devicePixelRatioF() / 2)
    expected_stroke = [round(b + (a - b) * coverage) for a, b in
                       zip(ink.getRgb()[:3], background.getRgb()[:3])]
    assert p.status.hasFocus() and any(
        all(abs(a - b) <= 1 for a, b in zip(QColor(color).getRgb()[:3], expected_stroke))
        for color in focused)
    assert '#151b23' in focused, 'Keyboard focus must retain the visible dashed pattern'
    click_table(p)
    blurred = border_colors(p.status)
    assert set(blurred) == {accent}, 'Selected category needs its own persistent border, not focus-only green'
    assert focused != blurred, 'Keyboard focus must remain visually distinguishable'
    QTest.mouseClick(p.search, Qt.MouseButton.LeftButton)
    assert not p.status.hasFocus() and set(border_colors(p.status)) == {accent}
    QTest.mouseMove(p.status, p.status.rect().center())
    assert accent in border_colors(p.status)
    p.status.showPopup()
    QApplication.processEvents()
    QTest.keyClick(p.status.view(), Qt.Key.Key_Escape)
    QApplication.processEvents()
    assert not p.status.view().isVisible() and p.status.currentData() == key
    QTest.mouseClick(p.search, Qt.MouseButton.LeftButton)
    assert set(border_colors(p.status)) == {accent}
    assert p.status.size() == size and [str(t.path) for t in p.visible_tracks()] == visible
    assert tracks == before


def test_real_keyboard_cover_duplicate_and_reset_keep_state_accent_and_results(page):
    p, _ = page
    p.status.setFocus()
    QTest.keyClick(p.status, Qt.Key.Key_End)
    QTest.keyClick(p.status, Qt.Key.Key_Up)
    assert p.status.currentData() == 'no_cover'
    click_table(p)
    assert set(border_colors(p.status)) == {'#f4bd75'}
    assert {t.path.name for t in p.visible_tracks()} == {'a.mp3', 'b.flac', 'c.wav', 'd.m4a', 'e.weird', 'dup.mp3', 'skip.mp3'}
    p.status.setFocus()
    QTest.keyClick(p.status, Qt.Key.Key_Tab)
    QApplication.processEvents()
    assert not p.status.hasFocus() and set(border_colors(p.status)) == {'#f4bd75'}
    p.status.setFocus()
    QTest.keyClick(p.status, Qt.Key.Key_Home)
    QTest.keyClick(p.status, Qt.Key.Key_Down)
    QTest.keyClick(p.status, Qt.Key.Key_Down)
    assert p.status.currentData() == 'duplicate'
    click_table(p)
    assert set(border_colors(p.status)) == {'#bd9bf7'}
    assert [t.path.name for t in p.visible_tracks()] == ['dup.mp3']
    p.reset_view_btn.click()
    QTest.mouseClick(p.search, Qt.MouseButton.LeftButton)
    assert p.status.currentData() == 'all'
    assert set(border_colors(p.status)) == {'#2d3744'}
    assert len(p.visible_tracks()) == 7


def test_neutral_choice_retains_keyboard_focus_and_other_combos_are_not_restyled(page):
    p, _ = page
    other = [(w.styleSheet(), w.size(), w.currentData()) for w in (p.format_filter, p.file_filter)]
    p.status.setCurrentIndex(p.status.findData('no_cover'))
    p.status.setCurrentIndex(p.status.findData('all'))
    p.status.setFocus()
    assert p.status.hasFocus() and '#43d17d' in border_colors(p.status)
    click_table(p)
    assert set(border_colors(p.status)) == {'#2d3744'}
    assert [(w.styleSheet(), w.size(), w.currentData()) for w in (p.format_filter, p.file_filter)] == other
