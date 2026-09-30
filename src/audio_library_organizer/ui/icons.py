from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_A1_ROOT = Path(__file__).resolve().parent.parent / 'assets' / 'icons' / 'a1'
_START_C_ROOT = Path(__file__).resolve().parent.parent / 'assets' / 'icons' / 'start_c'
_LIBRARY_A_ROOT = Path(__file__).resolve().parent.parent / 'assets' / 'icons' / 'library_a'

# Public icon names used by the existing UI remain stable. Their artwork is
# now supplied by A1 SVG, so the visual change does not alter button wiring.
_A1_ALIASES = {
    'home': 'start',
    'duplicate': 'duplicates',
    'search': 'recognize',
    'review': 'check_library',
    'plus': 'add_tracks',
    'image': 'cover',
    'sources': 'compare',
    'database': 'library',
    'key': 'api_key',
    'speaker': 'volume',
    'close': 'cancel',
    'check': 'status',
    'upload': 'export',
    'rewind': 'chevron_left',
    'forward': 'chevron_right',
    'repeat': 'refresh',
    'chevron-left': 'chevron_left',
    'chevron-right': 'chevron_right',
    # Provider marks stay recognisable through their established colours,
    # while their geometry follows the same thin-line family.
    'fingerprint': 'provider_acoustid',
    'disc': 'provider_discogs',
    'brain': 'provider_musicbrainz',
    'music': 'provider_apple',
}


@lru_cache(maxsize=96)
def _svg_source(name: str, color: str) -> bytes:
    asset_name = _A1_ALIASES.get(name, name).replace('-', '_')
    path = _A1_ROOT / f'{asset_name}.svg'
    if not path.is_file():
        path = _A1_ROOT / 'info.svg'
    # SVG expects #RRGGBB (or #RRGGBBAA), while Qt's HexArgb is #AARRGGBB.
    # All A1 UI icons are opaque, so the six-digit form is unambiguous.
    safe_color = QColor(color).name(QColor.NameFormat.HexRgb)
    return path.read_text(encoding='utf-8').replace('currentColor', safe_color).encode('utf-8')


def _a1_icon(name: str, color: str, size: int) -> QIcon:
    logical = max(12, int(size))
    # Three physical pixels per logical pixel preserve the 1.15 px strokes
    # cleanly with Windows scaling at 100%, 125% and 150%.
    scale = 3
    pixels = logical * scale
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_svg_source(name, color)))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    pixmap.setDevicePixelRatio(float(scale))
    return QIcon(pixmap)


def alo_icon(name: str, color: str = '#c8d4df', size: int = 20) -> QIcon:
    """Return an A1 Ultra Thin icon without relying on system fonts."""

    return _a1_icon(name, color, size)


def editor_icon(name: str, color: str = '#c8d4df', size: int = 20) -> QIcon:
    """Metadata-editor alias using the application-wide A1 system."""

    return _a1_icon(name, color, size)


@lru_cache(maxsize=128)
def _start_c_source(name: str, color: str) -> bytes:
    asset_name = {'search': 'recognize'}.get(name, name).replace('-', '_')
    path = _START_C_ROOT / f'{asset_name}.svg'
    safe_color = QColor(color).name(QColor.NameFormat.HexRgb)
    return path.read_text(encoding='utf-8').replace('currentColor', safe_color).encode('utf-8')


def start_icon(name: str, color: str = '#dbe8e2', size: int = 20) -> QIcon:
    """The approved C outline family, scoped to the Start dashboard."""

    logical = max(12, int(size))
    scale = 3
    pixels = logical * scale
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_start_c_source(name, color)))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    pixmap.setDevicePixelRatio(float(scale))
    return QIcon(pixmap)


@lru_cache(maxsize=128)
def _library_a_source(name: str, color: str) -> bytes:
    path = _LIBRARY_A_ROOT / f'{name}.svg'
    safe_color = QColor(color).name(QColor.NameFormat.HexRgb)
    return path.read_text(encoding='utf-8').replace('currentColor', safe_color).encode('utf-8')


def library_icon(name: str, color: str = '#cbd8df', size: int = 20) -> QIcon:
    """Scoped Minimal Outline icons for the Library page."""
    logical = max(12, int(size))
    pixels = logical * 3
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(QByteArray(_library_a_source(name, color))).render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    pixmap.setDevicePixelRatio(3.0)
    return QIcon(pixmap)
