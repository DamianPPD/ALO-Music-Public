from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QSettings, QRect
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui import main_window as main_window_ui
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.theme import style_for_theme
from audio_library_organizer.ui.v0411_theme import style_for_v0411
from audio_library_organizer.ui.waveform import read_waveform

main_window_ui.DashboardPage = DashboardPage
MainWindow = main_window_ui.MainWindow


def _solid_cover(color: str, edge: int = 160) -> QPixmap:
    pix = QPixmap(edge, edge)
    pix.fill(QColor(color))
    return pix


def main() -> int:
    app = QApplication.instance() or QApplication(['ALO-UI-reference'])
    app.setStyleSheet(style_for_theme('dark') + style_for_v0411('dark'))

    out = Path('ui_reference')
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='alo-ui-') as td:
        tmp = Path(td)
        settings = AppSettings(source_dirs=(), library=LibraryPaths(tmp / 'library'))
        store = QSettings(str(tmp / 'settings.ini'), QSettings.Format.IniFormat)
        store.setValue('preferences/theme', 'dark')
        store.setValue('preferences/language', 'pl')

        window = MainWindow(settings, store)
        window.resize(1500, 900)
        window.show()
        app.processEvents()
        window.grab(QRect(0, 0, 1500, 155)).save(str(out / 'top_toolbar.png'))
        window._navigate(0)
        app.processEvents()
        window.grab().save(str(out / 'start.png'))
        window._navigate(5)
        window.settings_page.scroll.ensureWidgetVisible(window.settings_page.integration_card, 20, 20)
        app.processEvents()
        window.settings_page.integration_card.grab().save(str(out / 'integrations.png'))
        window._navigate(0)

        track_path = tmp / '12-07-56 - Relocate - Built To Last (Ferry Tayle Rmx).mp3'
        track_path.write_bytes(b'')
        track = TrackRecord(
            path=track_path,
            artist='12-07-56',
            title='Relocate - Built To Last (Ferry Tayle Rmx)',
            album='Built To Last',
            year='2009',
            genre='Trance',
            bpm=138,
            duration_seconds=316,
            bitrate_kbps=320,
            status='review',
            confidence=0.78,
            has_cover=False,
            field_sources={
                'artist': 'Tag',
                'title': 'Tag',
                'year': 'Discogs',
                'genre': 'MusicBrainz',
                'bpm': 'Analiza audio',
                'album': 'Discogs',
            },
            field_source_values={
                'artist': {
                    'Tag': '12-07-56',
                    'Discogs': 'Re:Locate',
                    'MusicBrainz': 'Re:Locate',
                    'Apple / iTunes': 'Re:Locate',
                },
                'title': {
                    'Tag': 'Relocate - Built To Last (Ferry Tayle Rmx)',
                    'Discogs': 'Built To Last (Ferry Tayle Remix)',
                    'MusicBrainz': 'Built To Last (Ferry Tayle Remix)',
                    'Apple / iTunes': 'Built To Last (Ferry Tayle Remix)',
                },
                'year': {'Discogs': '2009', 'MusicBrainz': '2009', 'Apple / iTunes': '2009'},
                'genre': {'Tag': 'Trance', 'Discogs': 'Trance', 'MusicBrainz': 'Progressive Trance', 'Apple / iTunes': 'Trance'},
                'bpm': {'Analiza audio': 138},
                'album': {'Discogs': 'Built To Last'},
            },
        )

        # A deterministic audio fixture exercises the real waveform extractor.
        import numpy as np
        import soundfile as sf
        sample_path = tmp / 'waveform-layout-fixture.wav'
        sample_time = np.arange(8000 * 4) / 8000
        sample = np.sin(2 * np.pi * 220 * sample_time) * (0.1 + 0.8 * np.sin(sample_time * 3) ** 2)
        sf.write(sample_path, sample, 8000)
        window.player.artist.setText('Re:Locate')
        window.player.title.setText('Built To Last (Ferry Tayle Remix)')
        window.player.meta.setText('Trance · 138 BPM')
        window.player._load_cover(track)
        window.player.seek.setRange(0, 4000)
        window.player.seek.setValue(1250)
        window.player.seek.set_peaks(read_waveform(sample_path))
        window.player.elapsed.setText('00:01')
        window.player.total.setText('00:04')
        app.processEvents()
        window.player.grab().save(str(out / 'player.png'))

        dialog = MetadataEditorDialog(track, window, player_bar=window.player)
        dialog.resize(1420, 920)

        # Deterministic local proposal images; layout is what this check verifies.
        dialog._cover_candidate_urls = {
            'external:MusicBrainz': 'local://mb',
            'external:Discogs': 'local://discogs',
            'external:Apple / iTunes': 'local://apple',
        }
        dialog._cover_candidate_pixmaps['external:MusicBrainz'] = _solid_cover('#17415b')
        dialog._cover_candidate_pixmaps['external:Discogs'] = _solid_cover('#40362b')
        dialog._cover_candidate_pixmaps['external:Apple / iTunes'] = _solid_cover('#3b274a')
        dialog._cover_candidate_pixmaps['placeholder'] = _solid_cover('#12171c')
        dialog._rebuild_cover_proposals()
        dialog._select_cover_choice('external:MusicBrainz', record_undo=False)

        dialog.show()
        app.processEvents()
        dialog.grab().save(str(out / 'metadata_editor.png'))

        dialog._force_closing = True
        dialog.close()
        window.close()
        app.processEvents()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
