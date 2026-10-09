"""Physical file knowledge, independent of metadata status and file operations.

Inputs are prepared evidence. MISSING means absence confirmed on an accessible
location, never a failed exists()/probe. Timestamps are supplied Unix nanoseconds;
freshness is supplied by the collector. This module performs no I/O or clock reads.
Managed facts are a contract for future producers, not a managed-file binding.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FileState(StrEnum):
    IN_LIBRARY = 'IN_LIBRARY'
    SOURCE_ONLY = 'SOURCE_ONLY'
    NEEDS_UPDATE = 'NEEDS_UPDATE'
    SOURCE_UNAVAILABLE = 'SOURCE_UNAVAILABLE'
    MANAGED_FILE_MISSING = 'MANAGED_FILE_MISSING'
    CONFLICT = 'CONFLICT'


class FileAvailability(StrEnum):
    """Internal observations, not additional public file states."""
    PRESENT = 'PRESENT'
    MISSING = 'MISSING'
    UNKNOWN = 'UNKNOWN'
    OFFLINE = 'OFFLINE'
    ERROR = 'ERROR'


class Ownership(StrEnum):
    UNKNOWN = 'UNKNOWN'
    CONFIRMED = 'CONFIRMED'
    AMBIGUOUS = 'AMBIGUOUS'


class ConflictReason(StrEnum):
    """Positive evidence; unknown availability is never conflict evidence."""
    AMBIGUOUS_OWNERSHIP = 'AMBIGUOUS_OWNERSHIP'
    MULTIPLE_OWNERS = 'MULTIPLE_OWNERS'
    TARGET_COLLISION = 'TARGET_COLLISION'
    CONTRADICTORY_FACTS = 'CONTRADICTORY_FACTS'


def _text(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{field} must be nonempty text.')


def _time(value, field):
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValueError(f'{field} must be a nonnegative integer timestamp.')


@dataclass(frozen=True, slots=True)
class FileObservation:
    track_id: str
    locator: str
    availability: FileAvailability
    checked_at: int
    source_id: str | None = None
    reason: str = ''
    is_current: bool = True

    def __post_init__(self):
        _text(self.track_id, 'track_id')
        _text(self.locator, 'locator')
        if self.source_id is not None:
            _text(self.source_id, 'source_id')
        if not isinstance(self.availability, FileAvailability):
            raise ValueError('availability must be a FileAvailability.')
        _time(self.checked_at, 'observation checked_at')
        if type(self.is_current) is not bool or not isinstance(self.reason, str):
            raise ValueError('Observation freshness/reason is invalid.')


@dataclass(frozen=True, slots=True)
class OutputSnapshot:
    """Opaque comparable token, not a full OutputSpec or audio fingerprint.

    Only equal namespace and version permit comparison. The later output-spec
    producer is responsible for calculating a token from actual desired/applied
    output; an absent token is not an empty spec or a match.
    """
    namespace: str
    version: int
    value: str

    def __post_init__(self):
        _text(self.namespace, 'snapshot namespace')
        _text(self.value, 'snapshot value')
        if type(self.version) is not int or self.version < 1:
            raise ValueError('Snapshot version must be a positive integer.')


@dataclass(frozen=True, slots=True)
class FileFacts:
    track_id: str
    checked_at: int
    source: FileObservation | None = None
    managed: FileObservation | None = None
    # None means absence of knowledge, False explicitly means no assignment.
    managed_expected: bool | None = None
    ownership: Ownership = Ownership.UNKNOWN
    owner_track_id: str | None = None
    desired: OutputSnapshot | None = None
    applied: OutputSnapshot | None = None
    conflict: ConflictReason | None = None
    is_current: bool = True
    last_confirmed_state: FileState | None = None
    last_confirmed_at: int | None = None

    def __post_init__(self):
        _text(self.track_id, 'track_id')
        _time(self.checked_at, 'facts checked_at')
        if self.managed_expected is not None and type(self.managed_expected) is not bool:
            raise ValueError('managed_expected must be bool or None.')
        if type(self.is_current) is not bool or not isinstance(self.ownership, Ownership):
            raise ValueError('Facts freshness/ownership is invalid.')
        if self.owner_track_id is not None:
            _text(self.owner_track_id, 'owner_track_id')
        if self.conflict is not None and not isinstance(self.conflict, ConflictReason):
            raise ValueError('conflict must be positive ConflictReason evidence.')
        for obs in (self.source, self.managed):
            if obs is not None:
                if not isinstance(obs, FileObservation):
                    raise ValueError('File observation is invalid.')
                if obs.checked_at > self.checked_at:
                    raise ValueError('Observation time exceeds facts time.')
        for snapshot in (self.desired, self.applied):
            if snapshot is not None and not isinstance(snapshot, OutputSnapshot):
                raise ValueError('Output snapshot is invalid.')
        if (self.last_confirmed_state is None) != (self.last_confirmed_at is None):
            raise ValueError('Confirmed history requires both state and time.')
        if self.last_confirmed_state is not None:
            if not isinstance(self.last_confirmed_state, FileState):
                raise ValueError('Confirmed history has an invalid state.')
            _time(self.last_confirmed_at, 'last confirmed time')
            if self.last_confirmed_at > self.checked_at:
                raise ValueError('Confirmed history time exceeds facts time.')


@dataclass(frozen=True, slots=True)
class FileStateEvaluation:
    state: FileState | None
    is_confirmed: bool
    reason: str
    checked_at: int
    last_confirmed_state: FileState | None
    last_confirmed_at: int | None

    @property
    def requires_revalidation(self) -> bool:
        """Even confirmed knowledge is no substitute for operation preflight."""
        return True

    @property
    def safe_for_file_mutation(self) -> bool:
        """Stage 2.1 evaluates knowledge; it never authorizes physical writes."""
        return False


def _unresolved(facts: FileFacts, reason: str) -> FileStateEvaluation:
    return FileStateEvaluation(facts.last_confirmed_state, False, reason,
                               facts.checked_at, facts.last_confirmed_state, facts.last_confirmed_at)


def _confirmed(facts: FileFacts, state: FileState, reason: str) -> FileStateEvaluation:
    return FileStateEvaluation(state, True, reason, facts.checked_at, state, facts.checked_at)


def _observation_uncertainty(obs: FileObservation | None, label: str) -> str | None:
    if obs is None:
        return f'{label}_UNOBSERVED'
    if not obs.is_current:
        return f'STALE_{label}_OBSERVATION'
    if obs.availability in (FileAvailability.UNKNOWN, FileAvailability.OFFLINE, FileAvailability.ERROR):
        return f'{label}_{obs.availability.value}'
    return None


def evaluate_file_state(facts: FileFacts) -> FileStateEvaluation:
    """Evaluate sufficient evidence in priority order, retaining history otherwise.

    Confirmed conflict > expected missing > changed output > current output >
    source present > source missing. Insufficient evidence never falls through
    from a managed expectation to a source-only state.
    """
    if not facts.is_current:
        return _unresolved(facts, 'STALE_FACTS')
    if any(obs is not None and obs.track_id != facts.track_id for obs in (facts.source, facts.managed)):
        return _unresolved(facts, 'OBSERVATION_IDENTITY_MISMATCH')
    if facts.managed is not None and facts.managed.source_id is not None:
        return _unresolved(facts, 'OBSERVATION_IDENTITY_MISMATCH')
    if facts.conflict is not None:
        return _confirmed(facts, FileState.CONFLICT, facts.conflict.value)
    if facts.ownership == Ownership.AMBIGUOUS:
        return _confirmed(facts, FileState.CONFLICT, 'AMBIGUOUS_OWNERSHIP')
    if (facts.ownership == Ownership.CONFIRMED and facts.owner_track_id is not None
            and facts.owner_track_id != facts.track_id):
        return _confirmed(facts, FileState.CONFLICT, 'OWNER_MISMATCH')
    if facts.managed_expected is None:
        return _unresolved(facts, 'MANAGED_EXPECTATION_UNKNOWN')
    if facts.managed_expected:
        uncertainty = _observation_uncertainty(facts.managed, 'MANAGED')
        if uncertainty:
            return _unresolved(facts, uncertainty)
        if facts.managed.availability == FileAvailability.MISSING:
            return _confirmed(facts, FileState.MANAGED_FILE_MISSING, 'EXPECTED_MANAGED_MISSING')
        if facts.ownership != Ownership.CONFIRMED or facts.owner_track_id != facts.track_id:
            return _unresolved(facts, 'OWNERSHIP_UNCONFIRMED')
        if facts.desired is None or facts.applied is None:
            return _unresolved(facts, 'OUTPUT_SNAPSHOT_UNKNOWN')
        if (facts.desired.namespace, facts.desired.version) != (facts.applied.namespace, facts.applied.version):
            return _unresolved(facts, 'OUTPUT_SNAPSHOT_INCOMPARABLE')
        if facts.desired.value != facts.applied.value:
            return _confirmed(facts, FileState.NEEDS_UPDATE, 'MANAGED_OUTPUT_CHANGED')
        return _confirmed(facts, FileState.IN_LIBRARY, 'MANAGED_CURRENT')
    if facts.managed is not None or facts.ownership != Ownership.UNKNOWN or facts.owner_track_id is not None:
        if (facts.managed is not None and facts.managed.is_current
                and facts.managed.availability == FileAvailability.PRESENT
                and facts.ownership == Ownership.CONFIRMED and facts.owner_track_id == facts.track_id):
            return _confirmed(facts, FileState.CONFLICT, 'CONTRADICTORY_FACTS')
        return _unresolved(facts, 'INCONSISTENT_MANAGED_FACTS')
    uncertainty = _observation_uncertainty(facts.source, 'SOURCE')
    if uncertainty:
        return _unresolved(facts, uncertainty)
    if facts.source.availability == FileAvailability.PRESENT:
        return _confirmed(facts, FileState.SOURCE_ONLY, 'SOURCE_PRESENT')
    return _confirmed(facts, FileState.SOURCE_UNAVAILABLE, 'SOURCE_MISSING')
