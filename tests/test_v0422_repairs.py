from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication, QLabel, QToolButton, QWidgetAction

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.genre_input import GenreChipInput
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme


ROOT = Path(__file__).resolve().parents[1]
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
ASSETS = ROOT / 'src/audio_library_organizer/assets/icons/a1'

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication(['alo-v0422-repairs'])
    return _APP


def _track(tmp_path: Path, **updates) -> TrackRecord:
    values = dict(
        path=tmp_path / 'BT feat. Jes - Every Other Way (Armin Van Buuren Remix).mp3',
        artist='BT feat. Jes',
        title='Every Other Way (Armin Van Buuren Remix)',
        year='2010',
        genre='Trance / Vocal Trance',
        bpm=132,
        duration_seconds=452,
        codec='MP3',
        status='review',
        field_sources={'artist': 'Tag', 'title': 'MusicBrainz', 'year': 'Discogs'},
        field_source_values={
            'artist': {'Tag': 'BT feat. Jes'},
            'title': {'MusicBrainz': 'Every Other Way (Armin van Buuren Remix)'},
            'year': {'Discogs': '2010'},
        },
    )
    values.update(updates)
    return TrackRecord(**values)


def _close(dialog: MetadataEditorDialog) -> None:
    dialog._force_closing = True
    dialog.close()


def _png_bytes(color: str = '#345678') -> bytes:
    image = QImage(32, 32, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    data = QBuffer()
    data.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(data, 'PNG')
    return bytes(data.data())


class _FakeReply:
    def __init__(self, *, error=QNetworkReply.NetworkError.NoError, payload=b''):
        self._error = error
        self._payload = payload
        self.deleted = False
        self.aborted = False

    def error(self):
        return self._error

    def readAll(self):
        return self._payload

    def deleteLater(self):
        self.deleted = True

    def abort(self):
        self.aborted = True


def test_genre_chips_always_show_full_name_and_remove_only_clicked_genre():
    app = _app()
    field = GenreChipInput('Trance / Vocal Trance')
    field.show()
    app.processEvents()
    chips = field.findChildren(QToolButton, 'GenreChip')
    assert [chip.text() for chip in chips] == ['Trance ×', 'Vocal Trance ×']
    assert all(chip.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon for chip in chips)
    chips[1].click()
    assert field.genres() == ('Trance',)
    assert field.text() == 'Trance'
    field.close()


def test_user_genre_chip_changes_are_manual_undoable_and_slash_is_parsed(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        dialog.show()
        app.processEvents()
        before = len(dialog._undo_stack)
        chips = dialog.genre.findChildren(QToolButton, 'GenreChip')
        chips[1].click()
        assert dialog.genre.genres() == ('Trance',)
        assert dialog._current_sources['genre'] == 'Ręcznie'
        assert len(dialog._undo_stack) > before

        dialog.genre.edit.setText('Progressive Trance / Vocal Trance')
        dialog.genre.edit.returnPressed.emit()
        assert dialog.genre.genres() == ('Trance', 'Progressive Trance', 'Vocal Trance')
    finally:
        _close(dialog)


def test_status_panel_and_field_markers_use_green_amber_and_red_a1_states(tmp_path: Path):
    app = _app()
    dialog = MetadataEditorDialog(_track(tmp_path, artist=None, year=None))
    try:
        dialog.show()
        app.processEvents()
        assert dialog.status_icons['title'].property('statusKind') == 'ok'
        assert dialog.status_icons['year'].property('statusKind') == 'warning'
        assert dialog.status_icons['artist'].property('statusKind') == 'critical'
        assert dialog.status_icons['title'].pixmap().width() >= 18
        assert dialog.status_icons['year'].pixmap().width() >= 18
        assert dialog.status_icons['artist'].pixmap().width() >= 18
        assert dialog._field_status_icons['year'].property('statusKind') == 'warning'
        assert dialog._field_status_icons['artist'].property('statusKind') == 'critical'
        assert not dialog._field_status_icons['year'].pixmap().isNull()
        assert not dialog._field_status_icons['artist'].pixmap().isNull()
    finally:
        _close(dialog)


def test_status_warning_uses_a1_exclamation_circle_asset():
    svg = (ASSETS / 'alert_circle.svg').read_text(encoding='utf-8')
    assert 'viewBox="0 0 24 24"' in svg
    assert 'stroke="currentColor"' in svg
    assert '<circle' in svg
    assert 'M12 7.5v6' in svg


def test_first_external_cover_leaves_loading_state_after_success(tmp_path: Path):
    _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    key = 'external:MusicBrainz'
    try:
        dialog._cover_request_serial += 1
        serial = dialog._cover_request_serial
        dialog._cover_candidate_urls = {key: 'https://example.test/cover.png'}
        dialog._cover_candidate_pixmaps[key] = QPixmap()
        dialog._cover_candidate_states[key] = 'loading'
        dialog._selected_cover_key = key
        reply = _FakeReply(payload=_png_bytes())
        dialog._candidate_cover_finished(reply, key, serial)
        assert dialog._cover_candidate_states[key] == 'ready'
        assert not dialog._cover_candidate_pixmaps[key].isNull()
        assert not dialog.cover_main_preview.pixmap().isNull()
        assert dialog.cover_main_preview.text() == ''
    finally:
        _close(dialog)


def test_failed_cover_request_ends_with_neutral_error_instead_of_loading(tmp_path: Path):
    _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    key = 'external:Discogs'
    try:
        dialog._cover_request_serial += 1
        serial = dialog._cover_request_serial
        dialog._cover_candidate_urls = {key: 'https://example.test/missing.jpg'}
        dialog._cover_candidate_pixmaps[key] = QPixmap()
        dialog._cover_candidate_states[key] = 'loading'
        dialog._selected_cover_key = key
        dialog.cover_choice = 'external'
        dialog._selected_external_url = dialog._cover_candidate_urls[key]
        reply = _FakeReply(error=QNetworkReply.NetworkError.ContentNotFoundError)
        dialog._candidate_cover_finished(reply, key, serial)
        assert dialog._cover_candidate_states[key] == 'error'
        assert dialog.cover_main_preview.text() == 'Nie udało się pobrać okładki'
        assert dialog._cover_proposal_labels.get(key) is None or dialog._cover_proposal_labels[key].text() != '…'
        assert dialog.status_icons['cover'].property('statusKind') == 'warning'
        assert dialog.selected_cover_available() is False
        assert dialog.selected_cover_url() is None
        assert dialog.cover_save_state() is None
        assert 'cover_update = dialog.cover_save_state()' in MAIN
        assert 'if cover_update is not None:' in MAIN
    finally:
        _close(dialog)


def test_reloading_gallery_aborts_old_cover_requests(tmp_path: Path):
    _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        pending = _FakeReply()
        dialog._cover_pending_replies.add(pending)
        dialog._cancel_pending_cover_requests()
        assert pending.aborted is True
        assert not dialog._cover_pending_replies
    finally:
        _close(dialog)


def test_cover_timeout_replaces_loading_with_error_and_aborts_reply(tmp_path: Path):
    _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    key = 'external:Apple'
    try:
        reply = _FakeReply()
        dialog._cover_request_serial += 1
        serial = dialog._cover_request_serial
        dialog._cover_pending_replies.add(reply)
        dialog._cover_candidate_states[key] = 'loading'
        dialog._cover_candidate_pixmaps[key] = QPixmap()
        dialog._selected_cover_key = key
        dialog._cover_request_timed_out(reply, key, serial)
        assert reply.aborted is True
        assert dialog._cover_candidate_states[key] == 'error'
        assert dialog.cover_main_preview.text() == 'Nie udało się pobrać okładki'
    finally:
        _close(dialog)


def test_loading_cover_does_not_request_overwrite_of_existing_cover(tmp_path: Path):
    _app()
    dialog = MetadataEditorDialog(_track(tmp_path, cover_art_url='https://example.test/existing.jpg', has_cover=True))
    key = 'external:MusicBrainz'
    try:
        dialog._cover_candidate_urls[key] = 'https://example.test/new.jpg'
        dialog._cover_candidate_pixmaps[key] = QPixmap()
        dialog._cover_candidate_states[key] = 'loading'
        dialog._selected_cover_key = key
        dialog.cover_choice = 'external'
        dialog._selected_external_url = dialog._cover_candidate_urls[key]
        assert dialog.selected_cover_available() is False
        assert dialog.cover_save_state() is None

        dialog._selected_cover_key = 'placeholder'
        dialog.cover_choice = 'placeholder'
        update = dialog.cover_save_state()
        assert update is not None
        assert update['cover_choice'] == 'placeholder'
        assert update['cover_art_url'] is None
        assert update['has_cover'] is False
    finally:
        _close(dialog)


def test_locked_online_button_has_red_icon_and_red_state(tmp_path: Path):
    app = _app()
    app.setStyleSheet(style_for_theme('dark'))
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        dialog.online_lock.setChecked(True)
        app.processEvents()
        image = dialog.online_lock.icon().pixmap(24, 24).toImage()
        colored = [
            image.pixelColor(x, y)
            for y in range(image.height()) for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 0
        ]
        assert any(color.red() > color.blue() + 40 for color in colored)
        assert dialog.online_lock.property('lockedOnline') is True
        assert 'chronione' in dialog.online_lock.toolTip()
        assert 'QPushButton#OnlineLockButton[lockedOnline="true"]' in THEME
        assert '#e45f68' in THEME
    finally:
        _close(dialog)


def test_source_legend_colors_provider_text_not_whole_row(tmp_path: Path):
    _app()
    dialog = MetadataEditorDialog(_track(tmp_path))
    try:
        widgets = [
            action.defaultWidget()
            for action in dialog.source_legend_button.menu().actions()
            if isinstance(action, QWidgetAction)
        ]
        names = {
            widget.findChild(QLabel, 'SourceMenuProvider').text():
            widget.findChild(QLabel, 'SourceMenuProvider').display_color()
            for widget in widgets
        }
        assert names == {
            'TAG': '#5ca3ff',
            'Discogs': '#43d17d',
            'MusicBrainz': '#b36cff',
            'Apple': '#ff6670',
            'RĘCZNIE': '#ffb84d',
            'ANALIZA': '#ef5b64',
            'NAZWA': '#9aa6b2',
        }
    finally:
        _close(dialog)


def test_start_cards_keep_neutral_headers_and_color_only_final_path_segment(tmp_path: Path):
    app = _app()
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    page = DashboardPage(AppSettings(source_dirs=(), library=paths))
    page.show()
    app.processEvents()
    expected = {
        'root': '#58c9f3',
        'ready': '#55d98b',
        'review': '#f0b44d',
        'not_selected': '#b987ff',
        'custom_folders': '#50d1c4',
        'reports': '#75bfff',
    }
    assert {key: card.property('accentColor') for key, card in page.location_cards.items()} == expected
    for key, card in page.location_cards.items():
        assert not hasattr(card, 'accent_line')
        assert card.title_label.property('accentColor') is None
        assert expected[key] not in card.title_label.styleSheet()
        assert card.path_label.property('pathAccent') == expected[key]
        assert card.path.name in card.path_label.text()
        assert expected[key] in card.path_label.text()
        parent_text = str(card.path.parent)
        assert parent_text not in card.path_label.text() or '#8fa7b4' in card.path_label.text()
    assert page.statistics_separator.objectName() == 'DashboardStatisticsSeparator'
    assert page.statistics_separator_icon.pixmap() is not None
    assert not page.statistics_separator_icon.pixmap().isNull()
    assert page.statistics_separator_title.text() == 'Statystyki biblioteki'
    assert page.statistics_separator.minimumHeight() >= 42
    assert page.statistics_separator.layout().contentsMargins().top() >= 8
    assert page.statistics_separator.layout().contentsMargins().bottom() >= 8
    assert page.quick_access_layout.contentsMargins().bottom() >= 12
    page.close()


def test_cancel_actions_have_full_negative_button_style():
    required = (
        'QPushButton#CancelScanAction',
        'QPushButton#CancelOnlineAction',
        'QFrame#ToolbarFrame QPushButton#CancelScanAction',
        'QFrame#ToolbarFrame QPushButton#CancelOnlineAction',
        'background:#32181c',
        'border:1px solid #e45f68',
        'color:#ffe4e6',
    )
    for marker in required:
        assert marker in THEME


def test_light_theme_has_v0422_repair_parity():
    light = style_for_theme('light')
    assert 'v0.4.22 repair parity — light' in light
    for selector in (
        'QPushButton#CancelScanAction',
        'QPushButton#CancelOnlineAction',
        'QPushButton#OnlineLockButton[lockedOnline="true"]',
        'QFrame#QuickAccessCard',
        'QFrame#DashboardStatisticsSeparator',
        'QLabel#MetadataStatusText[statusKind="warning"]',
        'QLabel#MetadataStatusText[statusKind="critical"]',
    ):
        assert selector in light
