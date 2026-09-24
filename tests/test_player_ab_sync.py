from pathlib import Path
import inspect

from audio_library_organizer.ui.playback_sync import PendingPlaybackPosition


ROOT = Path(__file__).resolve().parents[1]
PLAYER = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')


def test_pending_playback_position_supports_repeated_ab_switches():
    pending = PendingPlaybackPosition(end_margin_ms=250)

    pending.request(200_000)
    assert pending.take_for_duration(300_000) == 200_000
    assert pending.take_for_duration(300_000) is None

    pending.request(207_000)
    assert pending.take_for_duration(300_000) == 207_000
    assert pending.take_for_duration(300_000) is None


def test_pending_playback_position_clamps_to_shorter_track_end():
    pending = PendingPlaybackPosition(end_margin_ms=250)
    pending.request(200_000)

    assert pending.take_for_duration(180_000) == 179_750


def test_pending_playback_position_waits_until_duration_is_known():
    pending = PendingPlaybackPosition(end_margin_ms=250)
    pending.request(123_000)

    assert pending.take_for_duration(0) is None
    assert pending.take_for_duration(240_000) == 123_000


def test_ab_seek_is_retryable_until_player_confirms_target_position():
    pending = PendingPlaybackPosition(end_margin_ms=250)
    pending.request(200_000)

    # Windows multimedia backends can report duration before the new source is
    # actually ready to retain a seek. The target must therefore be retryable.
    assert pending.target_for_duration(300_000) == 200_000
    assert pending.target_for_duration(300_000) == 200_000
    assert pending.confirm_position(0) is False
    assert pending.target_for_duration(300_000) == 200_000
    assert pending.confirm_position(200_120) is True
    assert pending.target_for_duration(300_000) is None


def test_each_ab_seek_request_gets_a_new_generation():
    pending = PendingPlaybackPosition(end_margin_ms=250)

    first = pending.request(120_000)
    second = pending.request(127_000)

    assert isinstance(first, int)
    assert isinstance(second, int)
    assert second == first + 1


def test_stale_ab_callbacks_cannot_consume_the_newer_seek_request():
    pending = PendingPlaybackPosition(end_margin_ms=250)
    target_signature = inspect.signature(pending.target_for_duration)
    confirm_signature = inspect.signature(pending.confirm_position)

    # A queued retry from the previous A/B switch must not touch the request
    # created by the next switch.
    assert 'generation' in target_signature.parameters
    assert 'generation' in confirm_signature.parameters

    old_generation = pending.request(120_000)
    new_generation = pending.request(127_000)

    assert pending.target_for_duration(300_000, generation=old_generation) is None
    assert pending.confirm_position(120_000, generation=old_generation) is False
    assert pending.target_for_duration(300_000, generation=new_generation) == 127_000
    assert pending.confirm_position(127_080, generation=new_generation) is True


def test_player_defers_ab_autoplay_until_pending_seek_can_be_applied():
    assert '_pending_autoplay' in PLAYER
    assert 'target_for_duration' in PLAYER
    assert 'confirm_position' in PLAYER
    assert 'MediaStatus.LoadedMedia' in PLAYER
    assert 'MediaStatus.BufferedMedia' in PLAYER


def test_player_waits_until_new_source_is_seekable_and_scopes_retries_to_generation():
    assert 'seekableChanged.connect(self._seekable_changed)' in PLAYER
    assert 'self.player.isSeekable()' in PLAYER
    assert '_pending_seek_generation' in PLAYER
    assert 'generation=' in PLAYER
