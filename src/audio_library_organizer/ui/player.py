from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QUrl, Signal, QTimer, QSize, QThreadPool, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
    QGraphicsDropShadowEffect, QSizePolicy, QComboBox,
)

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.artwork import extract_embedded_cover
from audio_library_organizer.ui.widgets import ClickableCoverLabel, ElidedLabel, show_cover_preview
from audio_library_organizer.ui.assets import asset_path
from audio_library_organizer.ui.icons import alo_icon, editor_icon
from audio_library_organizer.ui.i18n import ui_text
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

        card = QFrame()
        card.setObjectName('PlayerCard')
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, -1)
        shadow.setColor(Qt.GlobalColor.black)
        card.setGraphicsEffect(shadow)
        card_lay = QHBoxLayout(card)
        card_lay.setContentsMargins(16, 14, 16, 14)
        card_lay.setSpacing(16)
        content = QVBoxLayout()
        content.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(11)

        self.cover = ClickableCoverLabel('♪')
        self.cover.setObjectName('PlayerCover')
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setFixedSize(86, 86)
        self.cover.clicked.connect(
            lambda: show_cover_preview(
                self, self._cover_pixmap, title='Okładka odtwarzanego utworu', note=self._cover_note
            )
        )
        card_lay.addWidget(self.cover)

        info = QVBoxLayout()
        info.setSpacing(1)
        self.playback_status = QLabel('Gotowy')
        self.playback_status.setObjectName('PlaybackStatus')
        self.playback_status.setVisible(False)
        self.artist = QLabel('ALO Music')
        self.artist.setObjectName('PlayerArtist')
        self.title = QPushButton('Wybierz utwór w Bibliotece, aby rozpocząć odsłuch')
        self.title.setObjectName('PlayerTitleLink')
        self.title.setFlat(True)
        self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title.clicked.connect(self._activate_current_track)
        info.addWidget(self.title)
        info.addWidget(self.artist)
        self.meta = QLabel('Odtwarzacz jest gotowy')
        self.meta.setObjectName('PlayerMeta')
        info.addWidget(self.meta)
        self.source_label = QLabel(f"{ui_text(self, 'Źródło:')} —")
        self.source_label.setObjectName('PlayerSource')
        self.source_label.setVisible(False)
        info.addWidget(self.source_label)
        self.queue_label = QLabel(f"{ui_text(self, 'Następny:')} —")
        self.queue_label.setObjectName('PlayerQueue')
        self.queue_label.setVisible(False)
        info.addWidget(self.queue_label)
        top.addLayout(info, 4)
        for label in (self.artist, self.title, self.meta, self.queue_label):
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        transport = QHBoxLayout()
        transport.setSpacing(6)
        transport.addStretch(1)
        self.back = QPushButton()
        self.back.setObjectName('PlayerIconButton')
        self.back.setIcon(alo_icon('rewind', '#dfe8ee', 20))
        self.back.setIconSize(QSize(20, 20))
        self.back.setToolTip('Cofnij 10 sekund')
        self.play = QPushButton()
        self.play.setObjectName('PlayButton')
        self.play.setIcon(alo_icon('play', '#ffffff', 25))
        self.play.setIconSize(QSize(25, 25))
        self.play.setFixedSize(58, 58)
        self.play.setToolTip('Odtwórz / pauza')
        self.forward = QPushButton()
        self.forward.setObjectName('PlayerIconButton')
        self.forward.setIcon(alo_icon('forward', '#dfe8ee', 20))
        self.forward.setIconSize(QSize(20, 20))
        self.forward.setToolTip('Przewiń 10 sekund')
        self.repeat = QPushButton()
        self.repeat.setObjectName('PlayerIconButton')
        self.repeat.setIcon(alo_icon('repeat', '#dfe8ee', 18))
        self.repeat.setIconSize(QSize(18, 18))
        self.repeat.setCheckable(True)
        self.repeat.setToolTip('Powtarzaj aktualny utwór')
        for button in (self.back, self.forward, self.repeat):
            button.setFixedSize(44, 44)
        transport.addWidget(self.back)
        transport.addWidget(self.play)
        transport.addWidget(self.forward)
        transport.addWidget(self.repeat)
        transport.addStretch(1)
        top.addLayout(transport, 3)
        self.output_device = QComboBox()
        self.output_device.setObjectName('PlayerOutputDevice')
        self.output_device.setFixedWidth(190)
        self.output_device.setToolTip(ui_text(self, 'Wyjście audio'))
        self.output_device.currentIndexChanged.connect(self._select_audio_device)
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self._refresh_audio_devices)
        self._refresh_audio_devices()
        top.addWidget(self.output_device)

        volume_box = QHBoxLayout()
        volume_box.setSpacing(6)
        self.speaker = QLabel()
        self.speaker.setPixmap(alo_icon('speaker', '#b9ccd5', 18).pixmap(18, 18))
        self.speaker.setObjectName('PlayerMeta')
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName('VolumeSlider')
        self.volume.setRange(0, 100)
        self.volume.setValue(75)
        self.volume.setFixedWidth(130)
        self.volume_percent = QLabel('75%')
        self.volume_percent.setObjectName('PlayerTime')
        self.volume_percent.setFixedWidth(34)
        volume_box.addWidget(self.speaker)
        volume_box.addWidget(self.volume)
        volume_box.addWidget(self.volume_percent)
        content.addLayout(top)

        timeline = QHBoxLayout()
        timeline.setSpacing(7)
        self.elapsed = QLabel('00:00')
        self.elapsed.setObjectName('PlayerTime')
        self.elapsed.setFixedWidth(42)
        self.seek = WaveformSlider()
        self.seek.setObjectName('SeekSlider')
        self.seek.setRange(0, 0)
        self.seek.setMinimumWidth(180)
        self.total = QLabel('00:00')
        self.total.setObjectName('PlayerTime')
        self.total.setFixedWidth(42)
        timeline.addWidget(self.elapsed)
        timeline.addWidget(self.seek, 1)
        timeline.addWidget(self.total)
        timeline.addSpacing(12)
        timeline.addLayout(volume_box)
        content.addLayout(timeline)
        card_lay.addLayout(content, 1)

        outer.addWidget(card)

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
        same_track = False
        if self.current_path is not None:
            try:
                same_track = self.current_path.resolve() == Path(track.path).resolve()
            except OSError:
                same_track = self.current_path == Path(track.path)
        self.current_track = track
        self.current_source_label = source_label or '—'
        artist, title, meta = track_display_lines(track)
        self.artist.setText(artist)
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
        self.queue_label.setText(f"{ui_text(self, 'Następny:')} {artist} — {title}")
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
            self.cover.setPixmap(QPixmap())
            self.cover.setText('♪')
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
            self.meta.setText('Najpierw wybierz utwór w Bibliotece lub Duplikatach.')
            self.playback_status.setText('Brak wybranego utworu')
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
            pix = QPixmap(str(asset_path('no_cover.png')))
            self._cover_note = 'Brak potwierdzonej okładki — grafika zastępcza ALO Music.'
        else:
            self._cover_note = ''
        self._cover_pixmap = pix
        if pix.isNull():
            self.cover.setPixmap(QPixmap())
            self.cover.setText('BRAK')
        else:
            self.cover.setText('')
            self.cover.setPixmap(
                pix.scaled(
                    self.cover.width() - 4, self.cover.height() - 4,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play.setIcon(alo_icon('pause' if playing else 'play', '#ffffff', 25))
        self.playback_status.setText(
            'Odtwarzanie' if playing else ('Pauza' if self.current_path else 'Gotowy')
        )

    def _volume_changed(self, value: int):
        self.audio.setVolume(value / 100)
        self.volume_percent.setText(f'{value}%')

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
            self.meta.setText(f'Błąd odtwarzania: {text}')
            self.playback_status.setText('Błąd odtwarzania')

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

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 5, 10, 5)
        row.setSpacing(9)

        self.track_cover = QLabel()
        self.track_cover.setObjectName('PlayerCover')
        self.track_cover.setFixedSize(48, 48)
        self.track_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.track_cover.setPixmap(editor_icon('music', '#38dcac', 30).pixmap(30, 30))
        row.addWidget(self.track_cover)
        track_info = QVBoxLayout()
        track_info.setSpacing(2)
        self.track_title = ElidedLabel(track.title or track.path.stem)
        self.track_title.setObjectName('CompactTrackTitle')
        self.track_title.setMaximumWidth(250)
        self.track_artist = ElidedLabel(track.artist or '—')
        self.track_artist.setObjectName('CompactTrackArtist')
        self.track_artist.setMaximumWidth(250)
        track_info.addWidget(self.track_title)
        track_info.addWidget(self.track_artist)
        row.addLayout(track_info)

        self.play = QPushButton()
        self.play.setObjectName('CompactPlayButton')
        self.play.setIcon(editor_icon('play', '#ffffff', 20))
        self.play.setIconSize(QSize(20, 20))
        self.play.setFixedSize(40, 40)
        self.play.setToolTip('Odtwórz / pauza')
        self.play.clicked.connect(self._toggle)
        row.addWidget(self.play)

        self.elapsed = QLabel('00:00')
        self.elapsed.setObjectName('CompactPlayerTime')
        self.elapsed.setFixedWidth(40)
        row.addWidget(self.elapsed)

        self.seek = WaveformSlider()
        self.seek.setObjectName('CompactSeekSlider')
        self.seek.setRange(0, max(0, self.player_bar.player.duration()))
        self.seek.setMinimumWidth(160)
        self.seek.sliderMoved.connect(self._seek_edited_track)
        row.addWidget(self.seek, 1)

        self.total = QLabel('00:00')
        self.total.setObjectName('CompactPlayerTime')
        self.total.setFixedWidth(40)
        row.addWidget(self.total)

        speaker = QLabel()
        speaker.setPixmap(editor_icon('speaker', '#b9ccd5', 18).pixmap(18, 18))
        speaker.setObjectName('CompactPlayerMeta')
        row.addWidget(speaker)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName('CompactVolumeSlider')
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(112)
        self.volume.setValue(self.player_bar.volume.value())
        self.volume.valueChanged.connect(self.player_bar.volume.setValue)
        row.addWidget(self.volume)
        self.volume_percent = QLabel(f'{self.player_bar.volume.value()}%')
        self.volume_percent.setObjectName('CompactPlayerTime')
        self.volume_percent.setFixedWidth(34)
        row.addWidget(self.volume_percent)

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
        self.play.setIcon(editor_icon('pause' if playing else 'play', '#ffffff', 20))
