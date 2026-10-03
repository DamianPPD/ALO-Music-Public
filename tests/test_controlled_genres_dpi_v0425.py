import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('scale', ['1', '1.25', '1.5', '1.75', '2'])
def test_controlled_settings_tags_source_actions_and_cover_grid_fit_dpi(scale, tmp_path):
    code = r'''
import json
import sys
from pathlib import Path
from PySide6.QtCore import QSettings, QPoint, Qt
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QToolButton, QPushButton
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.main_window import SettingsPage
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.theme import style_for_theme
app = QApplication([])
app.setStyleSheet(style_for_theme('dark'))
path = Path(sys.argv[1])
store = QSettings(str(path / 'dpi.ini'), QSettings.Format.IniFormat)
names = ['Polish Club & Dance / House 90s', 'Gatunek']
store.setValue('genres/custom', json.dumps(names))
page = SettingsPage(AppSettings((), LibraryPaths(path / 'library')), store)
page.show()
for language in ('pl', 'en', 'pl'):
    apply_static_language(page, language)
    for width in (1100, 850):
        page.resize(width, 850)
        for tab, host in ((0, page.genre_settings.base_host), (1, page.genre_settings.custom_host)):
            page.genre_settings.tabs.setCurrentIndex(tab)
            app.processEvents()
            for tag in host.findChildren(QFrame, 'GenreChip'):
                assert host.rect().contains(tag.geometry()), (host.size(), tag.geometry())
                assert 24 <= tag.height() <= 26
                assert tag.findChild(QLabel, 'GenreTagLabel').text() == tag.property('genreName')
            if tab == 0:
                assert not host.findChildren(QToolButton, 'GenreTagRemove')
page.close()
track = TrackRecord(path=path/'dpi.mp3', genre='House / Trance',
                    field_source_values={'title': {'Discogs': 'A', 'MusicBrainz': 'B'},
                                         'artist': {'Discogs': 'Artist A', 'MusicBrainz': 'Artist B'}})
editor = MetadataEditorDialog(track)
image = QPixmap(100, 100)
image.fill(QColor('#345678'))
editor._cover_candidate_pixmaps['source'] = image
editor._cover_candidate_urls = {f'external:{i}': f'https://example.test/{i}.jpg' for i in range(3)}
for key in editor._cover_candidate_urls:
    editor._cover_candidate_pixmaps[key] = image
editor._rebuild_cover_proposals()
editor.show()
for language in ('pl', 'en'):
    apply_static_language(editor, language)
    editor.refresh_audio_language()
    for size in ((1540,1000),(1420,900),(1180,760)):
        editor.resize(*size)
        app.processEvents()
        for source in ('Discogs', 'MusicBrainz', 'Discogs'):
            row = next(row for row in range(editor.source_table.rowCount())
                       if editor.source_table.item(row,0).data(Qt.ItemDataRole.UserRole) == source)
            editor.source_table.cellWidget(row,6).findChild(QPushButton,'UseSourceDataButton').click()
            app.processEvents()
            action = editor.source_table.cellWidget(row,6).findChild(QPushButton,'UseSourceDataButton')
            assert action.isEnabled()
            assert action.width() >= action.fontMetrics().horizontalAdvance(action.text()) + 14
        assert editor.source_comparison_toggle.icon().isNull()
        assert editor.cover_proposals_grid.count() == 4
        assert all(112 <= label.width() <= 117 for label in editor._cover_proposal_labels.values())
        host = editor.cover_proposals_host
        assert 0 <= editor.choose_cover_button.parentWidget().mapTo(editor.cover_gallery,QPoint()).y() - host.mapTo(editor.cover_gallery,host.rect().bottomLeft()).y() <= 14
        assert abs(editor.cover_gallery.height()-editor.metadata_card.height()) <= 1
        before = (editor.choose_cover_button.geometry(), editor.search_cover_button.geometry())
        editor._select_cover_choice('placeholder', record_undo=False)
        app.processEvents()
        assert before == (editor.choose_cover_button.geometry(), editor.search_cover_button.geometry())
editor._force_closing = True
editor.close()
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR=scale,
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env,
                            capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stderr
