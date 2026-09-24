import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.icons import alo_icon
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
PLAYER = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def _app():
    return QApplication.instance() or QApplication([])


def test_alo_icons_are_self_drawn_and_available():
    _app()
    for name in (
        'home', 'library', 'duplicate', 'folder', 'help', 'settings',
        'scan', 'search', 'review', 'export', 'plus', 'info',
        'metadata', 'status', 'image', 'sources', 'fingerprint',
        'disc', 'brain', 'music', 'play', 'pause', 'repeat', 'close', 'warning', 'upload', 'check',
    ):
        assert not alo_icon(name, '#ffffff', 20).isNull()


def test_navigation_and_players_do_not_depend_on_qt_standard_icons():
    assert 'QStyle.StandardPixmap' not in MAIN
    assert 'QStyle.StandardPixmap' not in PLAYER
    assert 'QStyle.StandardPixmap' not in EDITOR
    assert "self.nav_icon_ids = ('home', 'library', 'duplicate', 'folder', 'help', 'settings')" in MAIN
    assert "(self.scan_btn, 'scan')" in MAIN
    assert "(self.identify_btn, 'search')" in MAIN
    assert "alo_icon('play', '#ffffff'" in PLAYER


def test_metadata_editor_status_colors_and_source_action_are_visible(tmp_path: Path):
    _app()
    track = TrackRecord(
        path=tmp_path / 'Example.mp3',
        artist='Artist',
        title='Title',
        year=None,
        genre='Trance',
        bpm=138,
        status='review',
        field_sources={'artist': 'Tag', 'title': 'Tag'},
        field_source_values={'artist': {'Tag': 'Artist'}, 'title': {'Tag': 'Title'}},
    )
    dialog = MetadataEditorDialog(track)
    try:
        assert '#63e39a' in dialog.status_labels['artist'].styleSheet()
        assert '#f5b64f' in dialog.status_labels['year'].styleSheet()
        assert dialog.source_table.columnWidth(5) == 126
        assert dialog.source_table.cellWidget(0, 5).objectName() == 'UseSourceDataCell'
        assert dialog.source_table.verticalHeader().defaultSectionSize() == 31
        assert dialog.source_table.horizontalHeader().height() == 27
        assert dialog.source_legend_button.text() == ''
        assert not dialog.source_legend_button.icon().isNull()
    finally:
        dialog._force_closing = True
        dialog.close()


def test_mockup_card_language_and_provider_cards_are_kept():
    for name in (
        'PrimaryMetadataCard', 'MetadataStatusCompact', 'RecognitionInfoCompact',
        'CoverGallery', 'FilenamePreviewCard', 'SourceComparisonCard',
    ):
        assert f'QFrame#{name}' in THEME
    for provider in ('acoustid', 'discogs', 'musicbrainz', 'apple'):
        assert f"setProperty('providerKind', '{provider}')" in MAIN
    assert "_icon_label('fingerprint'" in MAIN
    assert "_icon_label('disc'" in MAIN
    assert "_icon_label('brain'" in MAIN
    assert "_icon_label('music'" in MAIN


def test_private_branch_theme_matches_approved_colored_workflow_reference():
    assert 'QFrame#ToolbarFrame QPushButton#Primary {' in THEME
    assert 'background:#116b45;' in THEME
    assert 'QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction {' in THEME
    assert 'QFrame#ToolbarFrame QPushButton#ReviewAction {' in THEME
    assert 'QFrame#ToolbarFrame QPushButton#ExportAction {' in THEME
    assert 'background:#0b2330;' in THEME
    assert 'QFrame#ToolbarFrame QPushButton#AddFilesAction {' in THEME
    assert 'background:#0a1e35;' in THEME
