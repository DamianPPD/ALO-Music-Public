"""Approved outline artwork stays readable through the real UI loaders."""

import math
from pathlib import Path
from xml.etree import ElementTree

import pytest
from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer.ui.icons import alo_icon, library_icon, start_icon


ASSETS = Path(__file__).resolve().parents[1] / 'src/audio_library_organizer/assets/icons'
ARTWORK = [
    ('start_c', 'nav_library', start_icon),
    ('library_a', 'empty_check', library_icon),
    ('library_a', 'file_size', library_icon),
    ('library_a', 'review', library_icon),
    ('a1', 'export', alo_icon),
    ('a1', 'recognize', alo_icon),
    ('a1', 'control_more', alo_icon),
    ('a1', 'control_close', alo_icon),
]


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('family,name,loader', ARTWORK, ids=[item[1] for item in ARTWORK])
@pytest.mark.parametrize('size', [16, 20, 24, 32])
@pytest.mark.parametrize('dpr', [1.0, 1.25, 1.5, 2.0])
def test_approved_outline_renders_recolored_with_gutters_at_common_sizes(app, family, name, loader, size, dpr):
    path = ASSETS / family / (name + '.svg')
    assert path.is_file(), name
    root = ElementTree.parse(path).getroot()
    assert root.attrib['viewBox'] == '0 0 24 24'
    assert root.attrib['fill'] == 'none'
    assert all(element.attrib.get('fill', 'none') == 'none' for element in root.iter())
    assert root.attrib['stroke'] == 'currentColor'
    assert 1.6 <= float(root.attrib['stroke-width']) <= 1.8
    assert root.attrib['stroke-linecap'] == root.attrib['stroke-linejoin'] == 'round'
    assert not root.findall('.//{http://www.w3.org/2000/svg}text')
    assert QSvgRenderer(str(path)).isValid()
    for color in ('#8fb9c8', '#bd88cc'):
        expected = QColor(color)
        picture = loader(name, color, size).pixmap(QSize(size, size), dpr).toImage()
        assert not picture.isNull()
        # Thin diagonals/dots can have no fully opaque pixel at 16 px. Qt's
        # premultiplied-alpha conversion also rounds RGB by one channel unit.
        assert any(picture.pixelColor(x, y).alpha() >= 180 and
                   all(abs(channel - wanted) <= 2 for channel, wanted in zip(
                       picture.pixelColor(x, y).getRgb()[:3], expected.getRgb()[:3]))
                   for y in range(picture.height()) for x in range(picture.width()))
        edges = ([picture.pixelColor(x, y) for x in range(picture.width())
                  for y in (0, picture.height() - 1)] +
                 [picture.pixelColor(x, y) for y in range(picture.height())
                  for x in (0, picture.width() - 1)])
        assert all(pixel.alpha() == 0 for pixel in edges), (name, size, dpr)


def _picture(loader, name):
    return loader(name, '#8fb9c8', 96).pixmap(96, 96).toImage()


def _ink(image, x, y):
    return image.pixelColor(round(x * 4), round(y * 4)).alpha() > 160


def test_library_navigation_has_three_full_spines_instead_of_a_bar_chart(app):
    image = _picture(start_icon, 'nav_library')
    assert _ink(image, 3, 5) and _ink(image, 9, 5)
    assert _ink(image, 4.5, 4) and _ink(image, 10.5, 4)
    assert not _ink(image, 11, 2)


def test_empty_status_has_separated_ring_segments_and_an_empty_center(app):
    image = _picture(library_icon, 'empty_check')
    ring = [_ink(image, 12 + 8.5 * math.cos(angle * math.tau / 72),
                 12 + 8.5 * math.sin(angle * math.tau / 72)) for angle in range(72)]
    assert 15 < sum(ring) < 65
    assert not _ink(image, 12, 12)


def test_file_size_has_visible_size_letters_inside_the_document(app):
    image = _picture(library_icon, 'file_size')
    assert _ink(image, 5, 5)
    assert any(_ink(image, x, y) for x in (7, 8, 9, 10) for y in (13, 14, 15, 16, 17))
    assert any(_ink(image, x, y) for x in (13, 14, 15, 16) for y in (13, 14, 15, 16, 17))


def test_review_is_a_document_with_a_small_magnifier(app):
    image = _picture(library_icon, 'review')
    assert _ink(image, 5, 4) and _ink(image, 5, 20)
    assert _ink(image, 15.5, 11.5) and _ink(image, 20, 20)
    assert not _ink(image, 15.5, 15.5)


def test_export_arrow_leaves_the_document_to_the_right(app):
    image = _picture(alo_icon, 'export')
    assert _ink(image, 4, 5)
    assert _ink(image, 21, 15) and _ink(image, 19.5, 13.5)


def test_recognize_has_three_audio_bars_inside_the_magnifier(app):
    image = _picture(alo_icon, 'recognize')
    assert _ink(image, 7, 11) and _ink(image, 10, 12.5) and _ink(image, 13, 11)
    assert _ink(image, 19, 19)


def test_settings_online_artwork_remains_the_original_geometry(current_start_window):
    # Literal protected artwork from the approved baseline, independent of the loader.
    original = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
                'viewBox="0 0 24 24" fill="none" stroke="#57d8ff" stroke-width="1.15" '
                'stroke-linecap="round" stroke-linejoin="round"><circle cx="10.5" '
                'cy="10.5" r="5.5"/><path d="m14.5 14.5 5 5"/>'
                '<path d="M10.5 6v9M7.5 9h6"/></svg>')
    expected = QPixmap(60, 60)
    expected.fill(Qt.GlobalColor.transparent)
    painter = QPainter(expected)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(original.encode())).render(painter, QRectF(0, 0, 60, 60))
    painter.end()
    expected.setDevicePixelRatio(3)
    expected_image = QIcon(expected).pixmap(20, 20).toImage()
    section = current_start_window.settings_page.settings_sections['online']
    actual = section.findChild(QLabel, 'ProviderIcon').pixmap().toImage()
    assert actual == expected_image


def test_library_navigation_keeps_hover_active_and_disabled_states(app):
    from audio_library_organizer.ui.main_window import StartNavButton
    button = StartNavButton('Biblioteka', 'nav_library')
    button.setCheckable(True)
    button.show()
    app.processEvents()
    normal = button.icon().pixmap(20, 20).toImage()
    QTest.mouseMove(button, button.rect().center())
    QTest.qWait(180)
    hovered = button.icon().pixmap(20, 20).toImage()
    assert normal != hovered
    button.setChecked(True)
    assert button.icon().pixmap(20, 20).toImage() == start_icon('nav_library', '#4cde96', 20).pixmap(20, 20).toImage()
    button.setEnabled(False)
    assert not button.icon().pixmap(20, 20, QIcon.Mode.Disabled).isNull()
    button.close()
