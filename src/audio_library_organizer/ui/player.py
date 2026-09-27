from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QUrl, Signal, QTimer, QSize, QThreadPool, Slot, QPoint, QRect
from PySide6.QtGui import QPixmap, QColor, QPainter, QLinearGradient
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
    QSizePolicy, QComboBox,
)

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.artwork import extract_embedded_cover
from audio_library_organizer.ui.widgets import ClickableCoverLabel, ElidedLabel, show_cover_preview
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.icons import alo_icon, editor_icon
from audio_library_organizer.ui.i18n import ui_text, localized_no_cover_name
from audio_library_organizer.ui.playback_sync import PendingPlaybackPosition
from audio_library_organizer.ui.waveform import WaveformSlider, WaveformJob, read_waveform


def track_display_lines(track: TrackRecord) -> tuple[str, str, str]:
    artist = track.artist or 'Nieznany wykonawca'
    title = track.title or track.path.stem
    bits: list[str] = []
    if track.genre:
        bits.append(track.genre)
    if track.bpm is not None:
        bits.append(f'{int(round(track.bpm))} BPM')
    quality = ' · '.join(
        x for x in [track.codec or '', f'{track.bitrate_kbps} kb/s' if track.bitrate_kbps else ''] if x
    )
    if quality:
        bits.append(quality)
    return artist, title, '  •  '.join(bits)


class _TrackTitleButton(QPushButton):
    """Keep the complete title accessible while using only the available width."""

    def __init__(self, title: str = '', parent=None):
        super().__init__(parent)
        self._full_title = ''
        self.setText(title)

    def setText(self, title: str) -> None:  # noqa: N802 - Qt API
        self._full_title = str(title or '')
        self.setToolTip(self._full_title)
        self._elide()

    def _elide(self):
        width = max(0, self.contentsRect().width() - 4)
        super().setText(self.fontMetrics().elidedText(self._full_title, Qt.TextElideMode.ElideRight, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class VariantDPlayerSurface(QFrame):
    """One visual player for the library footer and the metadata editor."""

    def __init__(self, title: str = '', artist: str = '', parent=None):
        super().__init__(parent)
        self.setObjectName('VariantDPlayerSurface')
        self.cover_pixmap = QPixmap()
        self.ambient_source = QPixmap()
        self._ambient_cache = QPixmap()
        self._ambient_cache_size = (0, 0)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 5, 12, 5)
        row.setSpacing(8)

        self.cover = ClickableCoverLabel('')
        self.cover.setObjectName('VariantDCover')
        self.cover.setFixedSize(52, 52)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignVCenter)

        info = QWidget(self)
        info.setObjectName('VariantDIdentity')
        info.setMinimumWidth(0)
        info.setMaximumWidth(350)
        info.setMaximumHeight(52)
        labels = QVBoxLayout(info)
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(1)
        self.title = _TrackTitleButton(title)
        self.title.setObjectName('VariantDTitle')
        self.title.setFlat(True)
        self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.artist = ElidedLabel(artist)
        self.artist.setObjectName('VariantDArtist')
        labels.addWidget(self.title)
        labels.addWidget(self.artist)
        row.addWidget(info, 4, Qt.AlignmentFlag.AlignVCenter)

        self.play = QPushButton()
        self.play.setObjectName('VariantDPlayButton')
        self.play.setFixedSize(50, 50)
        self.play.setIconSize(QSize(46, 46))
        self.play.setToolTip('Odtwórz / pauza')
        self.set_playing(False)
        row.addWidget(self.play, 0, Qt.AlignmentFlag.AlignVCenter)

        self.elapsed = QLabel('00:00')
        self.elapsed.setObjectName('VariantDTime')
        self.elapsed.setFixedWidth(42)
        row.addWidget(self.elapsed)
        self.seek = WaveformSlider()
        self.seek.setObjectName('VariantDWaveform')
        self.seek.setMinimumWidth(120)
        row.addWidget(self.seek, 3)
        self.total = QLabel('00:00')
        self.total.setObjectName('VariantDTime')
        self.total.setFixedWidth(42)
        row.addWidget(self.total)

        self.speaker = QPushButton()
        self.speaker.setObjectName('VariantDSpeaker')
        self.speaker.setFixedSize(28, 32)
        self.speaker.setIconSize(QSize(22, 22))
        self.set_muted(False)
        row.addWidget(self.speaker)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName('VariantDVolume')
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(88)
        row.addWidget(self.volume)
        self.volume_percent = QLabel('75%')
        self.volume_percent.setObjectName('VariantDTime')
        self.volume_percent.setFixedWidth(38)
        row.addWidget(self.volume_percent)

        self.set_cover_pixmap(QPixmap())

    def set_playing(self, playing: bool) -> None:
        self.play.setIcon(alo_icon('pause' if playing else 'play', '#4ce5cf', 46))
        self.play.setProperty('playing', playing)
        self.play.style().unpolish(self.play)
        self.play.style().polish(self.play)

    def set_muted(self, muted: bool) -> None:
        self.speaker.setIcon(alo_icon('mute' if muted else 'speaker', '#26d5c5' if muted else '#b9ccd5', 22))
        tooltip = 'Włącz dźwięk' if muted else 'Wycisz'
        self.speaker.setProperty('_alo_pl_tooltip', tooltip)
        self.speaker.setToolTip(ui_text(self, tooltip))

    def set_cover_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            pixmap = QPixmap(str(asset_path(localized_no_cover_name(self))))
        self.cover_pixmap = pixmap
        self.ambient_source = pixmap
        self._ambient_cache = QPixmap()
        self._ambient_cache_size = (0, 0)
        self.cover.setText('' if not pixmap.isNull() else '—')
        self.cover.setPixmap(pixmap.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation) if not pixmap.isNull() else QPixmap())
        self.update()

    def ambient_end_x(self) -> int:
        return self.play.mapTo(self, QPoint(self.play.width() // 2, 0)).x()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.ambient_source.isNull():
            return
        end = max(0, min(self.width(), self.ambient_end_x()))
        if not end:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setClipRect(QRect(0, 0, end, self.height()))
        # Scale down only slightly: preserve recognizable cover shapes in the ambient.
        if self._ambient_cache_size != (end, self.height()):
            enlarged = self.ambient_source.scaled(end, self.height(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                   Qt.TransformationMode.SmoothTransformation)
            left = max(0, (enlarged.width() - end) // 2)
            top = max(0, (enlarged.height() - self.height()) // 2)
            self._ambient_cache = enlarged.copy(left, top, end, self.height()).scaled(
                max(32, end // 3), max(20, self.height() // 2), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._ambient_cache_size = (end, self.height())
        painter.drawPixmap(QRect(0, 0, end, self.height()), self._ambient_cache)
        fade = QLinearGradient(0, 0, end, 0)
        fade.setColorAt(0, QColor(9, 16, 20, 140))
        fade.setColorAt(.35, QColor(9, 16, 20, 150))
        fade.setColorAt(.68, QColor(9, 16, 20, 195))
        fade.setColorAt(1, QColor(15, 21, 29, 255))
        painter.fillRect(QRect(0, 0, end, self.height()), fade)
        # Keep title and artist legible even when the enlarged cover is bright.
        text_shade = QLinearGradient(0, 0, 0, self.height())
        text_shade.setColorAt(0, QColor(9, 16, 20, 0))
        text_shade.setColorAt(.25, QColor(9, 16, 20, 75))
        text_shade.setColorAt(.60, QColor(9, 16, 20, 75))
        text_shade.setColorAt(.75, QColor(9, 16, 20, 0))
        painter.fillRect(QRect(self.cover.x() + self.cover.width(), 0,
                               max(0, end - self.cover.x() - self.cover.width()), self.height()), text_shade)
        painter.end()


class PlayerBar(QWidget):
    track_activated = Signal(object)
    track_changed = Signal(object)
    waveform_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('PlayerBar')
        self.setMinimumHeight(114)
        self._waveform_generation = 0
        self._waveform_cancel = Event()
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.75)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.current_path: Path | None = None
        self.current_track: TrackRecord | None = None
        self._playback_error_text = ''
        self._cover_pixmap = QPixmap()
        self._cover_note = ''
        self._pending_seek = PendingPlaybackPosition(end_margin_ms=250)
        self._pending_seek_generation: int | None = None
        self._pending_source_url: QUrl | None = None
        self._pending_source_changed = False
        self._pending_autoplay = False
        self._pending_source_ready = False
        self._pending_seek_retry_count = 0
        self._pending_seek_retry_scheduled = False
        self.current_source_label = '—'
        self.queued_track: TrackRecord | None = None
        self.queued_source_label = 'Biblioteka'

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 4, 10, 8)
        outer.setSpacing(4)
        separator = QFrame()
        separator.setObjectName('FooterSeparator')
        separator.setFixedHeight(1)
        outer.addWidget(separator)
        self.surface = VariantDPlayerSurface('Wybierz utwór w Bibliotece, aby rozpocząć odsłuch', 'ALO Music', self)
        outer.addWidget(self.surface, 1)
        self.cover = self.surface.cover
        self.title = self.surface.title
        self.artist = self.surface.artist
        self.play = self.surface.play
        self.elapsed = self.surface.elapsed
        self.seek = self.surface.seek
        self.seek.setRange(0, 0)
        self.total = self.surface.total
        self.speaker = self.surface.speaker
        self.volume = self.surface.volume
        self.volume.setValue(75)
        self.volume_percent = self.surface.volume_percent
        self.cover.clicked.connect(lambda: show_cover_preview(
            self, self._cover_pixmap, title='Okładka odtwarzanego utworu', note=self._cover_note
        ))
        self.title.clicked.connect(self._activate_current_track)

        # Keep existing playback state/queue and audio-device synchronization;
        # these controls are not part of the Variant D visual surface.
        self.playback_status = QLabel('Gotowy', self)
        self.playback_status.hide()
        self.meta = QLabel('Odtwarzacz jest gotowy', self)
        self.meta.hide()
        self.source_label = QLabel(f"{ui_text(self, 'Źródło:')} —", self)
        self.source_label.hide()
        self.queue_label = QLabel(f"{ui_text(self, 'Następny:')} —", self)
        self.queue_label.hide()
        self.back = QPushButton(self)
        self.back.setObjectName('PlayerIconButton')
        self.back.hide()
        self.forward = QPushButton(self)
        self.forward.setObjectName('PlayerIconButton')
        self.forward.hide()
        self.repeat = QPushButton(self)
        self.repeat.setObjectName('PlayerIconButton')
        self.repeat.setCheckable(True)
        self.repeat.hide()
        self.output_device = QComboBox(self)
        self.output_device.setObjectName('PlayerOutputDevice')
        self.output_device.hide()
        self.output_device.setToolTip(ui_text(self, 'Wyjście audio'))
        self.output_device.currentIndexChanged.connect(self._select_audio_device)
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self._refresh_audio_devices)
        self._refresh_audio_devices()

        self.play.clicked.connect(self.toggle)
        self.back.clicked.connect(
            lambda: self.player.setPosition(max(0, self.player.position() - 10000))
        )
        self.forward.clicked.connect(
            lambda: self.player.setPosition(
                min(self.player.duration(), self.player.position() + 10000)
            )
        )
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.volume.valueChanged.connect(self._volume_changed)
        self.speaker.clicked.connect(self._toggle_mute)
        self.audio.mutedChanged.connect(self._mute_changed)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._state)
        self.player.sourceChanged.connect(self._source_changed)
        self.player.seekableChanged.connect(self._seekable_changed)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._error)

    def _activate_current_track(self):
        if self.current_track is not None:
            self.track_activated.emit(self.current_track)

    def _refresh_audio_devices(self):
        selected_id = self.audio.device().id()
        devices = QMediaDevices.audioOutputs()
        self.output_device.blockSignals(True)
        self.output_device.clear()
        selected_index = -1
        for index, device in enumerate(devices):
            self.output_device.addItem(device.description(), device)
            if device.id() == selected_id:
                selected_index = index
        if not devices:
            self.output_device.addItem(ui_text(self, 'Brak wyjścia audio'))
        else:
            if selected_index < 0:
                default_id = QMediaDevices.defaultAudioOutput().id()
                selected_index = next((i for i, d in enumerate(devices) if d.id() == default_id), 0)
            self.output_device.setCurrentIndex(selected_index)
        self.output_device.setEnabled(bool(devices))
        self.output_device.blockSignals(False)
        if devices:
            self._select_audio_device(selected_index)

    def _select_audio_device(self, index):
        device = self.output_device.itemData(index)
        if device is not None:
            self.audio.setDevice(device)
            self.output_device.setToolTip(device.description())

    def load_track(self, track: TrackRecord, *, position_ms: int = 0, autoplay: bool = True, source_label: str = 'Biblioteka'):
        self._playback_error_text = ''
        same_track = False
        if self.current_path is not None:
            try:
                same_track = self.current_path.resolve() == Path(track.path).resolve()
            except OSError:
                same_track = self.current_path == Path(track.path)
        self.current_track = track
        self.current_source_label = source_label or '—'
        artist, title, meta = track_display_lines(track)
        self.artist.setText(ui_text(self, artist))
        self.title.setText(title)
        self.title.setToolTip(title)
        self.meta.setText(meta or track.path.name)
        self.source_label.setText(f"{ui_text(self, 'Źródło:')} {ui_text(self, self.current_source_label)}")
        self._load_cover(track)
        if same_track:
            self._clear_pending_seek_state()
            self.player.setPosition(max(0, int(position_ms)))
            if autoplay:
                self.player.play()
        else:
            self.load(track.path, position_ms=position_ms, autoplay=autoplay, keep_display=True)
        self.track_changed.emit(track)

    def queue_next(self, track: TrackRecord, *, source_label: str = 'Biblioteka'):
        self.queued_track = track
        self.queued_source_label = source_label or 'Biblioteka'
        artist = track.artist or 'Nieznany wykonawca'
        title = track.title or track.path.stem
        self.queue_label.setText(f"{ui_text(self, 'Następny:')} {ui_text(self, artist)} — {title}")
        self.queue_label.setToolTip(str(track.path))
        self.queue_label.setVisible(True)

    def clear_queue(self):
        self.queued_track = None
        self.queue_label.setText(f"{ui_text(self, 'Następny:')} —")
        self.queue_label.setVisible(False)

    def _clear_pending_seek_state(self):
        self._pending_seek.clear()
        self._pending_seek_generation = None
        self._pending_source_url = None
        self._pending_source_changed = False
        self._pending_autoplay = False
        self._pending_source_ready = False
        self._pending_seek_retry_count = 0
        self._pending_seek_retry_scheduled = False

    def load(self, path: Path, *, position_ms: int = 0, autoplay: bool = True, keep_display: bool = False):
        self._playback_error_text = ''
        self.current_path = Path(path)
        self._waveform_cancel.set()
        self._waveform_cancel = Event()
        self.destroyed.connect(self._waveform_cancel.set)
        self._waveform_generation += 1
        self.seek.set_peaks([])
        self.waveform_changed.emit([])
        job = WaveformJob(self.current_path, self._waveform_generation, self._waveform_cancel)
        job.signals.ready.connect(self._waveform_ready, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(job)
        requested_position = max(0, int(position_ms))
        self._pending_seek_generation = self._pending_seek.request(requested_position)
        self._pending_autoplay = bool(autoplay and requested_position > 0)
        self._pending_source_ready = False
        self._pending_source_changed = False
        self._pending_seek_retry_count = 0
        self._pending_seek_retry_scheduled = False
        source_url = QUrl.fromLocalFile(str(self.current_path.resolve()))
        self._pending_source_url = source_url
        if not keep_display:
            self.current_track = None
            self.current_source_label = 'Plik lokalny'
            self.artist.setText(ui_text(self, 'Plik lokalny'))
            self.title.setText(self.current_path.stem)
            self.meta.setText(str(self.current_path))
            self.source_label.setText(f"{ui_text(self, 'Źródło:')} {ui_text(self, 'Plik lokalny')}")
            self._cover_pixmap = QPixmap()
            self.surface.set_cover_pixmap(QPixmap())
        self.player.setSource(source_url)
        if requested_position <= 0:
            self._clear_pending_seek_state()
            if autoplay:
                self.player.play()

    @Slot(int, object)
    def _waveform_ready(self, generation, peaks):
        if generation == self._waveform_generation:
            self.seek.set_peaks(peaks)
            self.waveform_changed.emit(peaks)

    def toggle(self):
        if self.current_path is None:
            self.meta.setText(ui_text(self, 'Najpierw wybierz utwór w Bibliotece lub Duplikatach.'))
            self.playback_status.setText(ui_text(self, 'Brak wybranego utworu'))
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        generation = self._pending_seek_generation
        if generation is not None and self._pending_seek.target_for_duration(
            self.player.duration(), generation=generation
        ) is not None:
            self._pending_autoplay = True
            self._apply_pending_position(generation=generation)
        else:
            self.player.play()

    def _source_changed(self, source: QUrl):
        if self._pending_source_url is None or source != self._pending_source_url:
            return
        self._pending_source_changed = True
        self._pending_source_ready = False

    def _seekable_changed(self, seekable: bool):
        generation = self._pending_seek_generation
        if generation is None or not seekable or not self._pending_source_changed:
            return
        if seekable != self.player.isSeekable():
            return
        if self._pending_source_url is None or self.player.source() != self._pending_source_url:
            return
        self._pending_source_ready = True
        self._apply_pending_position(generation=generation)

    def _schedule_pending_seek_retry(self, generation: int):
        if generation != self._pending_seek_generation:
            return
        if self._pending_seek_retry_scheduled or not self._pending_source_ready:
            return
        if not self.player.isSeekable() or self._pending_seek_retry_count >= 20:
            return
        self._pending_seek_retry_count += 1
        self._pending_seek_retry_scheduled = True
        QTimer.singleShot(40, lambda generation=generation: self._retry_pending_position(generation))

    def _retry_pending_position(self, generation: int):
        if generation != self._pending_seek_generation:
            return
        self._pending_seek_retry_scheduled = False
        if self._pending_source_ready and self.player.isSeekable():
            self._apply_pending_position(generation=generation)

    def _apply_pending_position(self, duration_ms: int | None = None, *, generation: int | None = None):
        generation = self._pending_seek_generation if generation is None else generation
        if generation is None or generation != self._pending_seek_generation:
            return
        if not self._pending_source_ready or not self.player.isSeekable():
            return
        if self._pending_source_url is None or self.player.source() != self._pending_source_url:
            return
        duration = self.player.duration() if duration_ms is None else duration_ms
        target = self._pending_seek.target_for_duration(duration, generation=generation)
        if target is not None:
            self.player.setPosition(target)
            self._schedule_pending_seek_retry(generation)

    def _media_status(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if status != self.player.mediaStatus():
                return
            generation = self._pending_seek_generation
            if (
                generation is not None
                and self._pending_source_changed
                and self._pending_source_url is not None
                and self.player.source() == self._pending_source_url
                and self.player.isSeekable()
            ):
                self._pending_source_ready = True
                self._apply_pending_position(generation=generation)
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.repeat.isChecked() and self.current_path is not None:
                self.player.setPosition(0)
                self.player.play()
            elif self.queued_track is not None:
                track = self.queued_track
                source = self.queued_source_label
                self.clear_queue()
                self.load_track(track, autoplay=True, source_label=source)

    def _load_cover(self, track: TrackRecord):
        pix = QPixmap()
        if track.manual_cover_path:
            pix = QPixmap(track.manual_cover_path)
        if pix.isNull():
            embedded = extract_embedded_cover(track.path)
            if embedded:
                pix.loadFromData(embedded[0])
        if pix.isNull():
            pix = QPixmap(str(asset_path(localized_no_cover_name(self))))
            self._cover_note = 'Brak potwierdzonej okładki — grafika zastępcza ALO Music.'
        else:
            self._cover_note = ''
        self._cover_pixmap = pix
        self.surface.set_cover_pixmap(pix)

    def _state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.surface.set_playing(playing)
        self.playback_status.setText(ui_text(self,
            'Odtwarzanie' if playing else ('Pauza' if self.current_path else 'Gotowy')
        ))

    def _volume_changed(self, value: int):
        self.audio.setVolume(value / 100)
        self.volume_percent.setText(f'{value}%')

    def _toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())

    def _mute_changed(self, muted: bool):
        self.surface.set_muted(muted)

    def _duration_changed(self, value: int):
        self.seek.setMaximum(max(0, value))
        self.total.setText(self._fmt(value))
        generation = self._pending_seek_generation
        if generation is not None and self._pending_source_ready:
            self._apply_pending_position(value, generation=generation)

    def _position(self, value: int):
        if not self.seek.isSliderDown():
            self.seek.setValue(value)
        self.elapsed.setText(self._fmt(value))
        self.total.setText(self._fmt(self.player.duration()))
        generation = self._pending_seek_generation
        if (
            generation is not None
            and self._pending_source_ready
            and value == self.player.position()
            and self._pending_seek.confirm_position(value, generation=generation)
        ):
            autoplay = self._pending_autoplay
            self._clear_pending_seek_state()
            if autoplay:
                QTimer.singleShot(0, self.player.play)

    def _error(self, _error, text: str):
        self._clear_pending_seek_state()
        if text:
            self._playback_error_text = text
            self.meta.setText(f'{ui_text(self, "Błąd odtwarzania:")} {text}')
            self.playback_status.setText(ui_text(self, 'Błąd odtwarzania'))

    def refresh_language(self) -> None:
        self.surface.set_muted(self.audio.isMuted())
        if self.current_track is not None and self._cover_note == 'Brak potwierdzonej okładki — grafika zastępcza ALO Music.':
            self._load_cover(self.current_track)
        if self.current_track is not None:
            artist, _, _ = track_display_lines(self.current_track)
            self.artist.setText(ui_text(self, artist))
        if self.current_path is not None:
            self.source_label.setText(f"{ui_text(self, 'Źródło:')} {ui_text(self, self.current_source_label)}")
        if self.queued_track is not None:
            artist = ui_text(self, self.queued_track.artist or 'Nieznany wykonawca')
            title = self.queued_track.title or self.queued_track.path.stem
            self.queue_label.setText(f"{ui_text(self, 'Następny:')} {artist} — {title}")
        if self._playback_error_text:
            self.meta.setText(f'{ui_text(self, "Błąd odtwarzania:")} {self._playback_error_text}')
            self.playback_status.setText(ui_text(self, 'Błąd odtwarzania'))
        else:
            self._state(self.player.playbackState())

    @staticmethod
    def _fmt(ms: int) -> str:
        sec = max(0, ms // 1000)
        return f'{sec//60:02d}:{sec%60:02d}'


class CompactPlayerBar(QFrame):
    """Minimal transport inside the metadata editor, sharing the main player."""

    def __init__(self, player_bar: PlayerBar, track: TrackRecord, parent=None):
        super().__init__(parent)
        self.player_bar = player_bar
        self.track = track
        self.setObjectName('CompactPlayerBar')
        self.setFixedHeight(74)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.surface = VariantDPlayerSurface(track.title or track.path.stem, track.artist or '—', self)
        layout.addWidget(self.surface)
        self.track_cover = self.surface.cover
        self.track_title = self.surface.title
        self.track_artist = self.surface.artist
        self.play = self.surface.play
        self.elapsed = self.surface.elapsed
        self.seek = self.surface.seek
        self.seek.setRange(0, max(0, self.player_bar.player.duration()))
        self.total = self.surface.total
        self.speaker = self.surface.speaker
        self.volume = self.surface.volume
        self.volume.setValue(self.player_bar.volume.value())
        self.volume_percent = self.surface.volume_percent
        self.volume_percent.setText(f'{self.volume.value()}%')
        self.play.clicked.connect(self._toggle)
        self.seek.sliderMoved.connect(self._seek_edited_track)
        self.speaker.clicked.connect(self.player_bar._toggle_mute)
        self.player_bar.audio.mutedChanged.connect(self.surface.set_muted)
        self.volume.valueChanged.connect(self.player_bar.volume.setValue)
        selected = QPixmap(track.manual_cover_path) if track.manual_cover_path else QPixmap()
        if selected.isNull():
            embedded = extract_embedded_cover(track.path)
            if embedded:
                selected.loadFromData(embedded[0])
        self.surface.set_cover_pixmap(selected)

        self.player_bar.player.positionChanged.connect(self._position_changed)
        self.player_bar.player.durationChanged.connect(self._duration_changed)
        self.player_bar.player.playbackStateChanged.connect(self._state_changed)
        self.player_bar.volume.valueChanged.connect(self._volume_changed)
        self.player_bar.track_changed.connect(self._sync_from_player)
        self.player_bar.player.sourceChanged.connect(self._sync_from_player)
        self.player_bar.waveform_changed.connect(self._waveform_changed)
        self._sync_from_player()

    def _is_edited_track_loaded(self) -> bool:
        current = self.player_bar.current_path
        if current is None:
            return False
        try:
            return current.resolve() == Path(self.track.path).resolve()
        except OSError:
            return current == Path(self.track.path)

    def _toggle(self):
        if not self._is_edited_track_loaded():
            self.player_bar.load_track(self.track, autoplay=True, source_label='Edytor metadanych')
        else:
            self.player_bar.toggle()
        self._sync_from_player()

    def _sync_from_player(self, *_):
        player = self.player_bar.player
        active = self._is_edited_track_loaded()
        self.seek.setEnabled(active)
        self.seek.setMaximum(max(0, player.duration()) if active else 0)
        self._waveform_changed(self.player_bar.seek.peaks)
        self._position_changed(player.position())
        self._state_changed(player.playbackState())
        self._volume_changed(self.player_bar.volume.value())

    def _duration_changed(self, value: int):
        self.seek.setMaximum(max(0, value) if self._is_edited_track_loaded() else 0)
        self._position_changed(self.player_bar.player.position())

    def _position_changed(self, value: int):
        active = self._is_edited_track_loaded()
        self.seek.setEnabled(active)
        if not active:
            value = 0
        if not self.seek.isSliderDown():
            self.seek.setValue(value)
        self.elapsed.setText(PlayerBar._fmt(value))
        self.total.setText(PlayerBar._fmt(self.player_bar.player.duration() if active else 0))

    def _seek_edited_track(self, value: int):
        if self._is_edited_track_loaded():
            self.player_bar.player.setPosition(value)

    def _waveform_changed(self, peaks):
        self.seek.set_peaks(peaks if self._is_edited_track_loaded() else [])

    def _volume_changed(self, value: int):
        if self.volume.value() != value:
            self.volume.blockSignals(True)
            self.volume.setValue(value)
            self.volume.blockSignals(False)
        self.volume_percent.setText(f'{value}%')

    def _state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState and self._is_edited_track_loaded()
        self.surface.set_playing(playing)
