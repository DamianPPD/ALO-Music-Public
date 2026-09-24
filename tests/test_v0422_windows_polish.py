from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QFrame, QStyleOptionViewItem

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.main_window import MainWindow, SettingsPage


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication(['alo-v0422-windows-polish'])
    return _APP


def _settings(tmp_path: Path) -> AppSettings:
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    return AppSettings(source_dirs=(), library=paths)


def test_library_status_column_fits_full_review_label_with_icon_at_large_font(tmp_path: Path):
    app = _app()
    original_font = QFont(app.font())
    scaled_font = QFont(original_font)
    scaled_font.setPointSizeF(max(13.5, original_font.pointSizeF() * 1.5))
    app.setFont(scaled_font)
    page = LibraryPage()
    try:
        page.resize(1400, 760)
        page.set_tracks([
            TrackRecord(
                path=tmp_path / 'example.mp3',
                artist='Artist',
                title='Title',
                status='review',
            )
        ])
        page.show()
        app.processEvents()

        text_width = QFontMetrics(page.table.font()).horizontalAdvance('DO SPRAWDZENIA')
        required_width = text_width + 15 + 12 + 24
        assert page.table.columnWidth(0) >= required_width
        assert page.model.item(0, 0).text() == 'DO SPRAWDZENIA'
        assert page.model.item(0, 0).toolTip() == 'DO SPRAWDZENIA'
        assert page.model.item(0, 0).font().pointSizeF() >= scaled_font.pointSizeF()

        option = QStyleOptionViewItem()
        option.initFrom(page.table)
        index = page.model.index(0, 0)
        page.table.itemDelegate().initStyleOption(option, index)
        assert page.table.columnWidth(0) >= page.table.itemDelegate().sizeHint(option, index).width()

        larger_font = QFont(page.table.font())
        larger_font.setPointSizeF(18.0)
        page.table.setFont(larger_font)
        app.processEvents()
        dynamic_required = QFontMetrics(larger_font).horizontalAdvance('DO SPRAWDZENIA') + 15 + 12 + 24
        assert page.table.columnWidth(0) >= dynamic_required

        page._restore_view_state({'column_widths': [80] * len(page.HEADERS)})
        assert page.table.columnWidth(0) >= dynamic_required
    finally:
        page.close()
        app.setFont(original_font)
        app.processEvents()


def test_integrations_render_as_four_separate_provider_cards_with_accents(tmp_path: Path):
    app = _app()
    settings = _settings(tmp_path)
    store = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    page = SettingsPage(settings, store)
    page.show()
    app.processEvents()

    assert page.integration_card.layout().spacing() >= 14
    cards = page.integration_card.findChildren(QFrame, 'ProviderCard')
    assert len(cards) == 4
    expected = {
        'acoustid': '#57d8ff',
        'discogs': '#43d17d',
        'musicbrainz': '#b86cff',
        'apple': '#ff6670',
    }
    assert set(page.provider_cards) == set(expected)
    for key, color in expected.items():
        card = page.provider_cards[key]
        assert card.minimumHeight() >= 116
        accent = card.findChild(QFrame, 'ProviderAccent')
        assert accent is not None
        assert accent.property('providerColor') == color
        assert page.provider_names[key].property('providerColor') == color
        assert color in page.provider_names[key].styleSheet()
    page.close()


def test_cancel_scan_and_online_buttons_use_negative_local_style(tmp_path: Path):
    app = _app()
    settings = _settings(tmp_path)
    store = QSettings(str(tmp_path / 'main.ini'), QSettings.Format.IniFormat)
    window = MainWindow(settings, store)
    try:
        window._set_busy(True, kind='scan')
        scan_style = window.scan_btn.styleSheet().lower()
        assert window.scan_btn.objectName() == 'CancelScanAction'
        assert '#e45f68' in scan_style
        assert '#32181c' in scan_style
        assert '#18c878' not in scan_style
        assert '#2be294' not in scan_style

        window._set_busy(False, kind='scan')
        window._set_busy(True, kind='online')
        online_style = window.identify_btn.styleSheet().lower()
        assert window.identify_btn.objectName() == 'CancelOnlineAction'
        assert '#e45f68' in online_style
        assert '#32181c' in online_style
        assert '#23885f' not in online_style
        assert '#2dd990' not in online_style
    finally:
        window.close()
        app.processEvents()
