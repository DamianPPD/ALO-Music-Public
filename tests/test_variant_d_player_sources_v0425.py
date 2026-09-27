import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QPushButton

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import SOURCE as AUDIO_SOURCE
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.player import CompactPlayerBar, PlayerBar
from audio_library_organizer.ui.theme import style_for_theme


def _app():
    return QApplication.instance() or QApplication([])


def _close(editor):
    editor._force_closing = True
    editor.close()


def test_source_columns_reorder_without_moving_action_or_changing_source_colors(tmp_path):
    app = _app()
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    sources = ('Tag', 'Discogs', 'MusicBrainz', 'Apple / iTunes', AUDIO_SOURCE, 'Ręcznie')
    editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'test.mp3'))
    try:
        for field in ('artist', 'title', 'album', 'year', 'genre'):
            editor._source_values[field] = {source: f'{field} {source}' for source in sources}
        editor._refresh_source_comparison()
        editor.resize(1600, 1060)
        editor.show()
        app.processEvents()
        table = editor.source_table
        assert [table.horizontalHeaderItem(i).text() for i in range(7)] == [
            'Źródło', 'Wykonawca', 'Tytuł / wersja', 'Album / Release', 'Rok', 'Gatunek', 'Akcja',
        ]
        assert table.columnWidth(0) < 220
        assert table.columnWidth(1) >= 200
        assert table.columnWidth(2) >= 260
        assert table.columnWidth(3) >= 200
        rendered = table.viewport().grab().toImage()
        for row, source in enumerate(sources):
            first = table.item(row, 0)
            assert first.data(Qt.ItemDataRole.UserRole) == source
            assert first.foreground().color() == QColor(editor.SOURCE_COLORS[source])
            assert not first.icon().isNull()
            target = QColor(editor.SOURCE_COLORS[source])
            top = table.visualItemRect(first).top()
            assert any(
                all(abs(a - b) <= 24 for a, b in zip(rendered.pixelColor(x, y).getRgb()[:3], target.getRgb()[:3]))
                for y in range(top + 5, top + table.rowHeight(row) - 5)
                for x in range(30, table.columnWidth(0) - 4)
            ), f'Text of {source} is not painted in its source color'
            assert table.columnWidth(0) >= (
                QFontMetrics(first.font()).horizontalAdvance(first.text()) + table.iconSize().width() + 22
            )
            assert table.item(row, 1).text() == f'artist {source}'
            assert table.item(row, 2).text() == f'title {source}'
            assert table.item(row, 3).text() == f'album {source}'
            assert table.item(row, 4).text() == f'year {source}'
            assert table.item(row, 5).text() == f'genre {source}'
            assert table.item(row, 1).foreground().color() != QColor(editor.SOURCE_COLORS[source])
            assert table.cellWidget(row, 0) is None
            assert table.cellWidget(row, 6).findChild(QPushButton, 'UseSourceDataButton')
        table.cellWidget(1, 6).findChild(QPushButton, 'UseSourceDataButton').click()
        assert editor._field_widgets['artist'].text() == 'artist Discogs'
        assert editor._current_sources['title'] == 'Discogs'
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert [table.horizontalHeaderItem(i).text() for i in range(4)] == [
            'Source', 'Artist', 'Title / version', 'Album / Release',
        ]
        audio_row = editor._source_rows().index(AUDIO_SOURCE)
        assert table.item(audio_row, 0).text() == 'AUDIO RECOGNITION'
        assert table.columnWidth(0) >= QFontMetrics(table.item(audio_row, 0).font()).horizontalAdvance('AUDIO RECOGNITION') + 34
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert table.horizontalHeaderItem(1).text() == 'Wykonawca'
    finally:
        _close(editor)
        app.setStyleSheet(previous)


def test_variant_d_uses_one_surface_in_both_places_and_keeps_height_and_order(tmp_path):
    app = _app()
    track = TrackRecord(path=tmp_path / 'test.mp3', title='Long title ' * 14, artist='Performer')
    bar = PlayerBar()
    compact = CompactPlayerBar(bar, track)
    try:
        initial_main_height = bar.minimumHeight()
        initial_editor_height = compact.height()
        bar.resize(1450, initial_main_height)
        compact.resize(1300, initial_editor_height)
        bar.show()
        compact.show()
        app.processEvents()
        assert type(bar.surface) is type(compact.surface)
        assert bar.minimumHeight() == initial_main_height == 114
        assert compact.height() == initial_editor_height == 74
        for surface in (bar.surface, compact.surface):
            widgets = [surface.cover, surface.title, surface.play, surface.elapsed, surface.seek,
                       surface.total, surface.speaker, surface.volume, surface.volume_percent]
            xs = [widget.mapTo(surface, QPoint(0, 0)).x() for widget in widgets]
            assert xs == sorted(xs)
            assert surface.artist.mapTo(surface, QPoint(0, 0)).x() == surface.title.mapTo(surface, QPoint(0, 0)).x()
            assert surface.title.width() >= 300
            assert surface.seek.peaks == []
            assert not surface.play.icon().isNull()
            assert surface.volume_percent.text().endswith('%')
            assert surface.volume_percent is widgets[-1]
            assert all(item not in surface.findChildren(QPushButton) for item in (bar.back, bar.forward, bar.repeat))
            assert not surface.findChildren(QPushButton, 'PlayerOutputDevice')
        assert compact.track_artist.text() == 'Performer'
        assert compact.track_title.toolTip() == track.title
    finally:
        compact.close()
        bar.close()


def test_variant_d_shares_volume_mute_and_waveform_without_extra_controls(tmp_path):
    _app()
    track = TrackRecord(path=tmp_path / 'test.mp3', title='Title', artist='Artist')
    bar = PlayerBar()
    compact = CompactPlayerBar(bar, track)
    try:
        compact.volume.setValue(58)
        assert bar.volume.value() == 58
        assert bar.audio.volume() == pytest.approx(.58)
        assert bar.volume_percent.text() == compact.volume_percent.text() == '58%'
        compact.speaker.click()
        assert bar.audio.isMuted()
        assert compact.speaker.icon().pixmap(22, 22).toImage() == bar.speaker.icon().pixmap(22, 22).toImage()
        bar.speaker.click()
        assert not bar.audio.isMuted()
        assert bar.volume.value() == compact.volume.value() == 58
        bar.current_path = track.path
        bar.track_changed.emit(track)
        bar._waveform_ready(bar._waveform_generation, [.2, .7, .3])
        assert compact.seek.peaks == bar.seek.peaks == [.2, .7, .3]
        assert compact.seek.isEnabled()
        assert compact.play.isEnabled() and bar.play.isEnabled()
    finally:
        compact.close()
        bar.close()


def test_variant_d_buttons_control_existing_playback_and_seek(tmp_path, monkeypatch):
    _app()
    track = TrackRecord(path=tmp_path / 'test.mp3', title='Title', artist='Artist')
    bar = PlayerBar()
    compact = CompactPlayerBar(bar, track)
    actions = []
    state = [QMediaPlayer.PlaybackState.StoppedState]
    monkeypatch.setattr(bar.player, 'play', lambda: (actions.append('play'), state.__setitem__(0, QMediaPlayer.PlaybackState.PlayingState)))
    monkeypatch.setattr(bar.player, 'pause', lambda: (actions.append('pause'), state.__setitem__(0, QMediaPlayer.PlaybackState.PausedState)))
    monkeypatch.setattr(bar.player, 'playbackState', lambda: state[0])
    monkeypatch.setattr(bar.player, 'setPosition', lambda position: actions.append(position))
    try:
        bar.current_path = track.path
        bar.current_track = track
        bar.play.click()
        assert actions[-1] == 'play'
        bar.player.playbackStateChanged.emit(state[0])
        assert bar.surface.play.property('playing') is True
        compact.play.click()
        assert actions[-1] == 'pause'
        bar.player.playbackStateChanged.emit(state[0])
        assert compact.surface.play.property('playing') is False
        bar.seek.sliderMoved.emit(2500)
        compact.seek.sliderMoved.emit(6000)
        assert actions[-2:] == [2500, 6000]
    finally:
        compact.close()
        bar.close()


def test_variant_d_mute_tooltips_follow_live_pl_en(tmp_path):
    _app()
    bar = PlayerBar()
    track = TrackRecord(path=tmp_path / 'test.mp3')
    editor = MetadataEditorDialog(track, player_bar=bar)
    try:
        assert bar.speaker.toolTip() == editor.compact_player.speaker.toolTip() == 'Wycisz'
        apply_static_language(bar, 'en')
        bar.refresh_language()
        apply_static_language(editor, 'en')
        editor.refresh_audio_language()
        assert bar.speaker.toolTip() == editor.compact_player.speaker.toolTip() == 'Mute'
        editor.compact_player.speaker.click()
        assert bar.speaker.toolTip() == editor.compact_player.speaker.toolTip() == 'Unmute'
        apply_static_language(bar, 'pl')
        bar.refresh_language()
        apply_static_language(editor, 'pl')
        editor.refresh_audio_language()
        assert bar.speaker.toolTip() == editor.compact_player.speaker.toolTip() == 'Włącz dźwięk'
    finally:
        _close(editor)
        bar.close()


def test_variant_d_ambient_uses_fallback_and_refreshes_when_editor_cover_changes(tmp_path):
    app = _app()
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    track = TrackRecord(path=tmp_path / 'test.mp3', title='Title', artist='Artist')
    bar = PlayerBar()
    editor = MetadataEditorDialog(track, player_bar=bar)
    try:
        editor.show()
        bar.resize(1400, 114)
        bar.show()
        app.processEvents()
        fallback = QPixmap(str(asset_path('no_cover.png')))
        assert not fallback.isNull()
        assert editor.compact_player.surface.cover_pixmap.toImage() == fallback.toImage()
        bar._load_cover(track)
        assert bar.surface.cover_pixmap.toImage() == fallback.toImage()

        filename = tmp_path / 'cover.png'
        changed = QPixmap(220, 180)
        changed.fill(QColor('#bb3030'))
        assert changed.save(str(filename))
        editor._manual_cover_paths['manual'] = str(filename)
        editor._cover_candidate_pixmaps['manual'] = changed
        editor._cover_candidate_states['manual'] = 'ready'
        editor._select_cover_choice('manual', record_undo=False)
        app.processEvents()
        surface = editor.compact_player.surface
        assert surface.cover_pixmap.cacheKey() == changed.cacheKey()
        assert surface.ambient_source.cacheKey() == changed.cacheKey()
        assert surface.cover.pixmap() is not None and not surface.cover.pixmap().isNull()
        assert surface.ambient_end_x() <= surface.play.mapTo(surface, QPoint(surface.play.width(), 0)).x()
        # The generated red ambient ends before the right-hand controls.
        rendered = surface.grab().toImage()
        left = rendered.pixelColor(surface.cover.width() + 26, surface.height() - 8)
        assert left.red() > left.green() + 15
        right = rendered.pixelColor(surface.width() - 8, surface.height() - 8)
        assert right.red() < 80 and right.green() < 80 and right.blue() < 80
        editor._select_cover_choice('placeholder', record_undo=False)
        assert surface.cover_pixmap.toImage() == fallback.toImage()
    finally:
        _close(editor)
        bar.close()
        app.setStyleSheet(previous)


@pytest.mark.parametrize('width', [1020, 1300, 1450])
def test_variant_d_play_sits_near_the_title_without_sacrificing_title_width(tmp_path, width):
    app = _app()
    bar = PlayerBar()
    compact = CompactPlayerBar(bar, TrackRecord(path=tmp_path / 'song.mp3',
                                                title='Newik – My Love (Noise Walkers Remix)', artist='Newik'))
    try:
        for widget in (bar, compact):
            widget.resize(width, 114 if widget is bar else 74)
            widget.show()
            app.processEvents()
            surface = widget.surface
            title_x = surface.title.mapTo(surface, QPoint(0, 0)).x()
            play_x = surface.play.mapTo(surface, QPoint(0, 0)).x()
            waveform_x = surface.seek.mapTo(surface, QPoint(0, 0)).x()
            text_width = QFontMetrics(surface.title.font()).horizontalAdvance(surface.title.text())
            assert surface.title.width() >= 300
            assert 0 < play_x - (title_x + min(text_width, surface.title.width())) <= 125
            assert surface.ambient_end_x() <= play_x + surface.play.width() // 2
            assert surface.ambient_end_x() < waveform_x
            if widget is bar:
                assert widget.minimumHeight() == 114
            else:
                assert widget.height() == 74
    finally:
        compact.close()
        bar.close()


def test_variant_d_ambient_preserves_artwork_shapes_and_fades_before_waveform(tmp_path):
    app = _app()
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    bar = PlayerBar()
    compact = CompactPlayerBar(bar, TrackRecord(path=tmp_path / 'song.mp3', title='Title', artist='Artist'))
    patterned = QPixmap(320, 320)
    patterned.fill(QColor('#050a10'))
    painter = QPainter(patterned)
    for x in range(0, 320, 80):
        painter.fillRect(x, 0, 40, 320, QColor('#f82b27'))
    painter.end()
    try:
        for widget in (bar, compact):
            widget.resize(1300, 114 if widget is bar else 74)
            widget.show()
            widget.surface.set_cover_pixmap(patterned)
            app.processEvents()
            surface = widget.surface
            assert surface.ambient_source.cacheKey() == surface.cover_pixmap.cacheKey()
            rendered = surface.grab().toImage()
            left = surface.cover.mapTo(surface, QPoint(surface.cover.width(), 0)).x()
            red = [rendered.pixelColor(x, surface.height() - 12).red()
                   for x in range(left + 12, min(left + 190, surface.play.x() - 20))]
            assert max(red) - min(red) >= 95
            assert rendered.pixelColor(surface.seek.x() + 15, surface.height() - 12).red() < 80
    finally:
        compact.close()
        bar.close()
        app.setStyleSheet(previous)


def test_variant_d_title_stays_readable_on_a_bright_cover(tmp_path):
    app = _app()
    previous = app.styleSheet()
    app.setStyleSheet(style_for_theme('dark'))
    bar = PlayerBar()
    compact = CompactPlayerBar(bar, TrackRecord(path=tmp_path / 'song.mp3', title='Title', artist='Artist'))
    bright = QPixmap(320, 320)
    bright.fill(QColor('#ffffff'))
    try:
        for widget in (bar, compact):
            widget.resize(1300, 114 if widget is bar else 74)
            widget.show()
            widget.surface.set_cover_pixmap(bright)
            app.processEvents()
            surface = widget.surface
            rendered = surface.grab().toImage()
            x = surface.title.mapTo(surface, QPoint(110, 0)).x()
            title_y = surface.title.mapTo(surface, QPoint(0, surface.title.height() // 2)).y()
            background_at_title = rendered.pixelColor(x, title_y).red()
            background_below_title = rendered.pixelColor(x, surface.height() - 12).red()
            assert background_at_title <= 90
            assert background_below_title >= background_at_title + 15
    finally:
        compact.close()
        bar.close()
        app.setStyleSheet(previous)
