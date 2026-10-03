import os
import ctypes
import subprocess
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


@pytest.mark.parametrize('fill_succeeds', [True, False])
def test_native_erase_initializes_only_unpainted_editor_surface(tmp_path, monkeypatch, fill_succeeds):
    # Model the OS drawing boundary, while driving the real Qt show/paint lifecycle.
    # A missing initial fill leaves this newly allocated native surface white.
    from ctypes import wintypes
    from types import SimpleNamespace
    from audio_library_organizer.ui import metadata_editor as module

    class NativeFunction:
        def __init__(self, action):
            self.action = action

        def __call__(self, *args):
            return self.action(*args)

    pixels = [[(255, 255, 255)] * 4 for _ in range(3)]
    brushes = {}
    released = []
    hwnd, hdc, brush = 0x123456789, 0x23456789A, 0x3456789AB

    def client_rect(window, rectangle):
        assert window == hwnd
        rect = rectangle._obj
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, 4, 3
        return 1

    def create_brush(color):
        brushes[brush] = (color & 255, (color >> 8) & 255, (color >> 16) & 255)
        return brush

    def fill(device, rectangle, selected_brush):
        assert device == hdc
        if not fill_succeeds:
            return 0
        rect = rectangle._obj
        for y in range(rect.top, rect.bottom):
            for x in range(rect.left, rect.right):
                pixels[y][x] = brushes[selected_brush]
        return 1

    libraries = {
        'user32': SimpleNamespace(GetClientRect=NativeFunction(client_rect), FillRect=NativeFunction(fill)),
        'gdi32': SimpleNamespace(CreateSolidBrush=NativeFunction(create_brush),
                                DeleteObject=NativeFunction(lambda handle: released.append(handle) or 1)),
    }
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'native.mp3'))
    try:
        editor.winId()  # create the native window before its first exposed paint
        msg = wintypes.MSG(hWnd=hwnd, message=0x0014, wParam=hdc)
        pointer = ctypes.addressof(msg)
        with monkeypatch.context() as patch:
            patch.setattr(sys, 'platform', 'win32')
            patch.setattr(ctypes, 'WinDLL', lambda name, **_kwargs: libraries[name], raising=False)
            handled, result = editor.nativeEvent(b'windows_generic_MSG', pointer)
        assert handled == fill_succeeds
        if fill_succeeds:
            assert result == 1
            assert pixels == [[(16, 20, 26)] * 4 for _ in range(3)]
        else:
            assert pixels == [[(255, 255, 255)] * 4 for _ in range(3)]
        assert released == [brush]
        editor.show()
        app.processEvents()
        editor.artist.setText('Visible content')
        before = editor.grab().toImage()
        with monkeypatch.context() as patch:
            patch.setattr(sys, 'platform', 'win32')
            patch.setattr(ctypes, 'WinDLL', lambda *_args, **_kwargs: pytest.fail('erase after first paint'),
                          raising=False)
            assert editor.nativeEvent(b'windows_generic_MSG', pointer)[0] is False
        assert editor.grab().toImage() == before
    finally:
        editor._force_closing = True
        editor.close()
        app.setStyleSheet(previous)


@pytest.mark.skipif(sys.platform != 'win32', reason='requires the real Win32 window and GDI backend')
def test_windows_native_erase_paints_dark_pixels_before_first_qt_paint(tmp_path):
    # The rest of the suite uses offscreen; a fresh process must load the real
    # Windows plugin before constructing QApplication and obtaining an HWND.
    code = '''
import runpy
import sys
from pathlib import Path
module = runpy.run_path(sys.argv[1])
module['_assert_windows_native_erase'](Path(sys.argv[2]))
'''
    environment = dict(os.environ, QT_QPA_PLATFORM='windows', QT_SCALE_FACTOR='1',
                       PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', code, str(Path(__file__).resolve()), str(tmp_path)],
                            env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def _assert_windows_native_erase(tmp_path):
    from ctypes import wintypes

    class BitmapHeader(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
                    ('planes', wintypes.WORD), ('bit_count', wintypes.WORD),
                    ('compression', wintypes.DWORD), ('image_size', wintypes.DWORD),
                    ('x_pixels', wintypes.LONG), ('y_pixels', wintypes.LONG),
                    ('colors_used', wintypes.DWORD), ('colors_important', wintypes.DWORD)]

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                     ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.GdiFlush.argtypes = []
    gdi32.GdiFlush.restype = wintypes.BOOL
    app = QApplication.instance() or QApplication([])
    assert app.platformName() == 'windows'
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'windows.mp3'))
    device = gdi32.CreateCompatibleDC(None)
    bitmap, original = None, None
    try:
        assert device
        header = BitmapHeader(size=ctypes.sizeof(BitmapHeader), width=4, height=-3,
                              planes=1, bit_count=32)
        # BITMAPINFO reserves one RGBQUAD after its header even for BI_RGB.
        info = ctypes.create_string_buffer(bytes(header) + b'\x00' * 4)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(device, info, 0, ctypes.byref(bits), None, 0)
        assert bitmap and bits.value
        original = gdi32.SelectObject(device, bitmap)
        pixels = (ctypes.c_uint32 * 12).from_address(bits.value)
        assert gdi32.GdiFlush()
        pixels[:] = [0xffffffff] * 12
        hwnd = int(editor.winId())
        assert user32.SendMessageW(hwnd, 0x0014, device, 0) == 1
        assert gdi32.GdiFlush()
        assert [pixel & 0xffffff for pixel in pixels] == [0x10141a] * 12
        editor.show()
        app.processEvents()
        assert gdi32.GdiFlush()
        pixels[:] = [0xffffffff] * 12
        user32.SendMessageW(hwnd, 0x0014, device, 0)
        assert gdi32.GdiFlush()
        assert list(pixels) == [0xffffffff] * 12  # established content belongs to Qt
    finally:
        if original:
            gdi32.SelectObject(device, original)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if device:
            gdi32.DeleteDC(device)
        editor._force_closing = True
        editor.close()
        app.setStyleSheet(previous)


def test_main_cover_has_neutral_edge_and_small_selected_cover_keeps_marker(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'cover.mp3'))
    try:
        editor.show()
        app.processEvents()
        image = QPixmap(60, 60)
        image.fill(QColor('#345678'))
        editor._cover_candidate_pixmaps['source'] = image
        editor._rebuild_cover_proposals()
        for key in ('source', 'placeholder'):
            editor._select_cover_choice(key, record_undo=False)
            app.processEvents()
            preview = editor.cover_main_preview.grab().toImage()
            color = preview.pixelColor(0, preview.height() // 2)
            assert color.green() - max(color.red(), color.blue()) < 20, color.name()
            markers = editor.cover_gallery.findChildren(QLabel, 'CoverProposalSelectedMarker')
            assert sum(marker.isVisible() for marker in markers) == 1
            assert editor.cover_main_preview.findChild(QLabel, 'CoverSelectedBadge') is None
    finally:
        editor._force_closing = True
        editor.close()
        app.setStyleSheet(previous)


@pytest.mark.parametrize('scale', ['1', '1.25', '1.5', '2'])
@pytest.mark.parametrize('language', ['pl', 'en'])
def test_upper_panels_align_without_enlarging_comment_or_cover_metrics(scale, language):
    code = '''
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme
app = QApplication([])
app.setStyleSheet(style_for_theme('dark'))
editor = MetadataEditorDialog(TrackRecord(path=Path('/tmp/layout.mp3')))
apply_static_language(editor, LANG)
editor.show()
for size in ((1540, 1000), (1420, 900), (1180, 760)):
    editor.resize(*size)
    for _ in range(3):
        app.processEvents()
    host = editor.content_scroll.widget()
    panels = (editor.metadata_card, editor.cover_gallery)
    tops = [p.mapTo(host, QPoint()).y() for p in panels]
    bottoms = [p.mapTo(host, p.rect().bottomLeft()).y() for p in panels]
    assert abs(tops[0] - tops[1]) <= 1, tops
    assert abs(bottoms[0] - bottoms[1]) <= 1, bottoms
    assert 60 <= editor.comment.height() <= 82
    assert editor.cover_info.height() <= 80
    assert editor.cover_main_preview.size().toTuple() == (288, 288)
    before = [p.geometry() for p in panels]
    editor.recognition_details_button.click()
    app.processEvents()
    assert [p.geometry() for p in panels] == before
    editor.recognition_details_popup.hide()
editor._force_closing = True
editor.close()
'''.replace('LANG', repr(language))
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR=scale,
                       PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', code], env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
