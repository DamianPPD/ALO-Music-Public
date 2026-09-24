from __future__ import annotations


class PendingPlaybackPosition:
    """Retryable seek request used when switching between audio sources.

    Some multimedia backends briefly expose state changes from the previous
    source after a new source has already been selected. Each request therefore
    gets a monotonically increasing generation so stale queued callbacks cannot
    consume or modify a newer A/B seek.
    """

    def __init__(self, *, end_margin_ms: int = 250, confirm_tolerance_ms: int = 180):
        self.end_margin_ms = max(0, int(end_margin_ms))
        self.confirm_tolerance_ms = max(0, int(confirm_tolerance_ms))
        self._position_ms: int | None = None
        self._effective_target_ms: int | None = None
        self._generation = 0

    def request(self, position_ms: int) -> int:
        self._generation += 1
        self._position_ms = max(0, int(position_ms))
        self._effective_target_ms = None
        return self._generation

    def clear(self) -> None:
        self._position_ms = None
        self._effective_target_ms = None

    def target_for_duration(self, duration_ms: int, *, generation: int | None = None) -> int | None:
        """Return the current target without consuming it.

        When ``generation`` is supplied, stale callbacks are ignored.
        """
        if generation is not None and generation != self._generation:
            return None
        if self._position_ms is None:
            return None
        duration_ms = max(0, int(duration_ms))
        if duration_ms <= 0:
            return None
        target = min(self._position_ms, max(0, duration_ms - self.end_margin_ms))
        self._effective_target_ms = target
        return target

    def confirm_position(self, position_ms: int, *, generation: int | None = None) -> bool:
        """Consume the pending seek only after the backend confirms the target."""
        if generation is not None and generation != self._generation:
            return False
        if self._position_ms is None:
            return False
        target = self._effective_target_ms
        if target is None:
            target = self._position_ms
        if abs(max(0, int(position_ms)) - target) > self.confirm_tolerance_ms:
            return False
        self.clear()
        return True

    def take_for_duration(self, duration_ms: int) -> int | None:
        """Legacy one-shot helper kept for non-player callers/tests."""
        target = self.target_for_duration(duration_ms)
        if target is not None:
            self.clear()
        return target
