"""Read-only music reconciliation; only disposable observation cache is written.

Inventory is not import. SHA equality is content evidence, never ownership.
Historical managed facts cannot supply a current physical binding. A caller may
provide explicit, current attestations (synthetic in Stage 2.2 tests); production
has no binding producer yet. All undecided candidates stay in this report.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
import hashlib
import json
import ntpath
import os
from pathlib import Path
import sqlite3
import stat
import time
from uuid import uuid4

from audio_library_organizer.domain.file_state import (
    ConflictReason, FileAvailability, FileFacts, FileObservation, FileState, FileStateEvaluation,
    Ownership, evaluate_file_state,
)
from audio_library_organizer.storage.source_registry import canonical_locator
from .scanner import SourceScanStatus, UnsafeSourcePath, scan_audio_sources, scoped_stat


@dataclass(frozen=True, slots=True)
class StatEvidence:
    size_bytes: int
    mtime_ns: int
    ctime_ns: int
    device: int
    inode: int
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class SourceCheckResult:
    source_id: str
    library_id: str
    root: str
    status: SourceScanStatus
    observed_count: int
    authoritative_count: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class FileCheckResult:
    track_id: str
    source: FileObservation
    facts: FileFacts
    evaluation: FileStateEvaluation
    technical: StatEvidence | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FileCandidate:
    source_id: str | None
    locator: str
    checked_at: int
    technical: StatEvidence
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PossibleMove:
    track_id: str
    source_id: str | None
    old_locator: str
    candidates: tuple[FileCandidate, ...]
    uncertainty: str
    reason: str = 'POSSIBLE_MOVED_SOURCE'


@dataclass(frozen=True, slots=True)
class DecisionCase:
    reason: str
    track_ids: tuple[str, ...] = ()
    locators: tuple[str, ...] = ()
    certainty: str = 'UNRESOLVED'


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    present: int
    missing: int
    offline: int
    uncertain: int
    new_sources: int
    possible_moves: int
    orphan_managed: int
    confirmed_conflicts: int


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    library_id: str
    operation_id: str
    checked_at: int
    summary: ReconciliationSummary
    sources: tuple[SourceCheckResult, ...]
    files: tuple[FileCheckResult, ...]
    new_source_candidates: tuple[FileCandidate, ...]
    possible_moves: tuple[PossibleMove, ...]
    orphan_managed_candidates: tuple[FileCandidate, ...]
    conflicts: tuple[DecisionCase, ...]
    unresolved: tuple[DecisionCase, ...]
    reason_codes: tuple[str, ...]
    cancelled: bool
    completed: int
    skipped: int
    cache_saved: int


def _technical(info, digest=None):
    return StatEvidence(info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                        info.st_dev, info.st_ino, digest)


def _stat_token(info):
    return [info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino]


def _observation_reason(code, info=None, digest=None):
    if info is None:
        return code
    # Versioned technical evidence, not a new FileState/binding/journal. Reuse a
    # digest only after a fresh stat confirms every token on the same locator.
    return json.dumps({'version': 1, 'code': code, 'stat': _stat_token(info), 'sha256': digest},
                      sort_keys=True, separators=(',', ':'))


def _cached_digest(cached, info, track, locator):
    if cached is None or cached.evaluation.reason == 'TRACK_BINDING_CHANGED':
        return None
    obs = cached.facts.source
    if obs is None or (obs.locator, obs.source_id) != (locator, track.source_id):
        return None
    try:
        data = json.loads(obs.reason)
        digest = data.get('sha256')
        if data.get('version') == 1 and data.get('stat') == _stat_token(info) and _valid_digest(digest):
            return digest
    except (ValueError, TypeError, AttributeError, RecursionError):
        pass
    return None


def _valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _stat_changed(cached, info, track, locator):
    if (info.st_size, info.st_mtime_ns) != (track.size_bytes, track.mtime_ns):
        return True
    previous = track.original_tags.get('__alo_scan_stat_v1__')
    if isinstance(previous, dict) and set(previous) == {'size', 'mtime_ns', 'ctime_ns', 'device', 'inode'}:
        return previous != dict(zip(('size', 'mtime_ns', 'ctime_ns', 'device', 'inode'), _stat_token(info)))
    if cached is not None and cached.facts.source is not None:
        try:
            data = json.loads(cached.facts.source.reason)
            token = data.get('stat')
            if data.get('version') == 1 and isinstance(token, list) and len(token) == 5:
                return (token != _stat_token(info) or data.get('code') == 'SOURCE_STAT_CHANGED'
                        or _cached_digest(cached, info, track, locator) not in (None, track.sha256))
        except (ValueError, TypeError, AttributeError, RecursionError):
            pass
    return False


def _hash_file(path, *, root, root_stat, expected_stat, cancelled):
    """Cancellable, read-only content evidence; a racing locator is unresolved."""
    scoped_stat(path, root, root_stat)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or _stat_token(before) != _stat_token(expected_stat):
            raise UnsafeSourcePath('FILE_CHANGED_DURING_CHECK')
        digest = hashlib.sha256()
        while True:
            if cancelled():
                raise InterruptedError('CANCELLED')
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(stream.fileno())
        current = scoped_stat(path, root, root_stat)
        if _stat_token(before) != _stat_token(after) or _stat_token(before) != _stat_token(current):
            raise UnsafeSourcePath('FILE_CHANGED_DURING_CHECK')
        return digest.hexdigest()


def _observe(track_id, locator, source_id, at, root, root_result, root_stat, *, physical_locator=None):
    """Negative evidence requires complete inventory and a still accessible root."""
    availability, code, info = FileAvailability.UNKNOWN, 'SOURCE_NOT_ACTIVE', None
    if root is not None:
        if root_result.status == SourceScanStatus.UNAVAILABLE:
            availability, code = FileAvailability.OFFLINE, 'SOURCE_ROOT_UNAVAILABLE'
        elif root_result.status == SourceScanStatus.CANCELLED:
            code = 'CANCELLED'
        elif root_result.status == SourceScanStatus.ERROR:
            availability, code = FileAvailability.ERROR, 'INCOMPLETE_SOURCE_INVENTORY'
        else:
            try:
                info = scoped_stat(Path(physical_locator or locator), Path(root), root_stat)
                if not stat.S_ISREG(info.st_mode):
                    raise UnsafeSourcePath('NOT_A_REGULAR_FILE')
                availability, code = FileAvailability.PRESENT, 'SOURCE_PRESENT'
            except FileNotFoundError:
                if root_result.status == SourceScanStatus.SUCCESS:
                    try:
                        scoped_stat(Path(root), Path(root), root_stat)
                        availability, code = FileAvailability.MISSING, 'SOURCE_MISSING'
                    except FileNotFoundError:
                        availability, code = FileAvailability.OFFLINE, 'SOURCE_ROOT_UNAVAILABLE'
                    except (OSError, RuntimeError, ValueError):
                        availability, code = FileAvailability.ERROR, 'ROOT_CHANGED_OR_UNREADABLE'
                else:
                    code = 'INCOMPLETE_SOURCE_INVENTORY'
            except (OSError, RuntimeError, ValueError) as exc:
                availability, code = FileAvailability.ERROR, 'FILE_UNREADABLE_OR_ALIAS'
                if isinstance(exc, UnsafeSourcePath):
                    code = 'ALIAS_OR_MOUNT_UNRESOLVED'
    observation = FileObservation(track_id, locator, availability, at, source_id,
                                  _observation_reason(code, info), is_current=True)
    return observation, info, code


def _within_scope(locator, root):
    path = Path(locator)
    return (path.is_absolute() and root.is_absolute() and '..' not in path.parts
            and '..' not in root.parts and path.is_relative_to(root))


def _declared_root(raw):
    # Keep foreign Windows/UNC identity visible to scanner's platform guard.
    text = str(raw)
    if os.name != 'nt' and (ntpath.splitdrive(text)[0] or text.startswith('\\\\')):
        return Path(text)
    return Path(raw).expanduser().absolute()


def _facts(track, source, at, cached, prepared, managed_context, *, cancelled=False):
    if cancelled:
        baseline = prepared or (cached.facts if cached and cached.facts.checked_at <= at else FileFacts(track.track_id, at))
        return replace(baseline, source=source, checked_at=at, is_current=False)
    if prepared is not None:
        facts = replace(prepared, source=source)
        if prepared.managed is not None:
            locator = prepared.managed.locator
            roots, results, stats = managed_context
            indexes = [i for i, root in enumerate(roots) if _within_scope(locator, root)]
            if indexes:
                index = max(indexes, key=lambda i: len(roots[i].parts))
                observed, _, _ = _observe(track.track_id, locator, None, at,
                                         roots[index], results[index], stats[index])
                facts = replace(facts, managed=replace(observed, reason=observed.reason.replace('SOURCE_', 'MANAGED_')))
            else:
                facts = replace(facts, managed=replace(prepared.managed, availability=FileAvailability.UNKNOWN,
                                                      reason='MANAGED_SCOPE_UNAVAILABLE', checked_at=at))
        return facts
    if cached is not None and cached.facts.checked_at <= at:
        # Preserve every historical managed input/observation exactly, including
        # its watermark. Updating a source stat cannot revalidate ownership or
        # desired/applied output. Cache history is taken from SQLite at commit.
        return replace(cached.facts, checked_at=at, source=source, is_current=False)
    return FileFacts(track.track_id, at, source=source)


def check_library(repository, *, library_id=None, operation_id=None, checked_at=None,
                  cancelled=None, progress=None, managed_roots=(), prepared_facts=(),
                  prepared_library_id=None) -> ReconciliationResult:
    """Check active registry scope and return candidates without accepting them.

    ``prepared_facts`` is an explicit current evidence boundary, never a cache
    revalidation shortcut. It requires library identity and this check's time.
    Production UI does not provide attestations before managed binding exists.
    Cancellation returns a partial report and rolls back the entire cache batch.
    """
    is_cancelled = cancelled or (lambda: False)
    at = time.time_ns() if checked_at is None else checked_at
    # Validate the same timestamp contract as the authoritative pure model.
    FileFacts('check-context', at)
    operation_id = operation_id or str(uuid4())
    snapshot = repository.file_check_snapshot()
    if library_id is not None and library_id != snapshot.library_id:
        raise ValueError('Library identity does not match check context.')
    supplied = tuple(prepared_facts)
    if supplied and prepared_library_id != snapshot.library_id:
        raise ValueError('Prepared facts belong to another library context.')
    prepared = {}
    known_ids = {track.track_id for track in snapshot.tracks}
    for facts in supplied:
        if (facts.track_id not in known_ids or facts.track_id in prepared or not facts.is_current
                or facts.checked_at != at or any(o and o.track_id != facts.track_id for o in (facts.source, facts.managed))
                or (facts.managed is not None and facts.managed.source_id is not None)):
            raise ValueError('Prepared facts identity/freshness is not valid for this check.')
        prepared[facts.track_id] = facts
    explicit_managed = tuple(_declared_root(root) for root in managed_roots)
    managed_owners = defaultdict(list)
    for facts in supplied:
        if (facts.managed is not None and facts.managed_expected is True
                and facts.ownership == Ownership.CONFIRMED and facts.owner_track_id is not None
                and any(_within_scope(facts.managed.locator, root) for root in explicit_managed)):
            # Lexical comparison avoids probing an attested locator before its
            # scope/availability check. Ownership itself comes only from input.
            key = os.path.normcase(os.path.normpath(facts.managed.locator))
            managed_owners[key].append(facts)
    for bindings in managed_owners.values():
        if len({f.owner_track_id for f in bindings}) > 1:
            for facts in bindings:
                prepared[facts.track_id] = replace(facts, conflict=ConflictReason.MULTIPLE_OWNERS)
    active = tuple(s for s in snapshot.sources if s.active)
    inventory = scan_audio_sources((Path(s.root_path) for s in active), cancelled=is_cancelled, conservative=True)
    sources = tuple(SourceCheckResult(s.source_id, s.library_id, s.root_path, o.status, o.files,
                    o.files if o.status == SourceScanStatus.SUCCESS else None, o.reason)
                    for s, o in zip(active, inventory.outcomes))
    source_index = {s.source_id: i for i, s in enumerate(active)}
    roots = tuple(Path(s.root_path) for s in active)
    managed_inventory = scan_audio_sources(explicit_managed, cancelled=is_cancelled, conservative=True)
    managed_context = (explicit_managed, managed_inventory.outcomes, managed_inventory.root_stats)
    cached = dict(snapshot.cached)
    damaged = dict(snapshot.cache_errors)
    unresolved, conflicts, reason_codes = [], [], set()
    for track_id in damaged:
        unresolved.append(DecisionCase('INVALID_OPTIONAL_CACHE', (track_id,)))
    if not supplied:
        reason_codes.add('MANAGED_BINDING_UNAVAILABLE')
    for outcome in (*inventory.outcomes, *managed_inventory.outcomes):
        if 'FOREIGN_PLATFORM_LOCATOR' in outcome.reason:
            reason_codes.add('FOREIGN_PLATFORM_LOCATOR')
        if 'ALIAS_OR_MOUNT_UNRESOLVED' in outcome.reason or 'ROOT_IDENTITY_CHANGED' in outcome.reason:
            reason_codes.add('ALIAS_OR_MOUNT_UNRESOLVED')
        if outcome.status != SourceScanStatus.SUCCESS:
            reason_codes.add('INCOMPLETE_SOURCE_INVENTORY')
    file_stats = dict(inventory.file_stats)
    memberships = dict(inventory.file_roots)
    known_keys = set(dict(snapshot.path_keys).values())
    new_candidates, candidate_context = [], {}
    for path in inventory.files:
        if is_cancelled():
            break
        key = canonical_locator(path)[1]
        if key in known_keys:
            continue
        indexes = memberships[path]
        index = max(indexes, key=lambda i: len(roots[i].parts))
        try:
            info = scoped_stat(path, roots[index], inventory.root_stats[index])
            if _stat_token(info) != _stat_token(file_stats[path]):
                raise UnsafeSourcePath('FILE_CHANGED_DURING_CHECK')
            candidate = FileCandidate(active[index].source_id, str(path), at, _technical(info), 'NEW_SOURCE_CANDIDATE')
            new_candidates.append(candidate)
            candidate_context[candidate.locator] = (index, info)
        except (OSError, RuntimeError, ValueError):
            unresolved.append(DecisionCase('CANDIDATE_UNREADABLE_OR_CHANGED', locators=(str(path),)))
    files, completed = [], 0
    locators = dict(snapshot.locators)
    for track in snapshot.tracks:
        locator = locators[track.track_id]
        # path_key is an indexed historical lookup key, not today's physical
        # target. Preserve raw spelling/case and inspect its actual alias chain.
        physical_locator = Path(locator).expanduser().absolute()
        if is_cancelled():
            source = FileObservation(track.track_id, locator, FileAvailability.UNKNOWN, at,
                                     track.source_id, 'CANCELLED')
            info, code = None, 'CANCELLED'
        else:
            index = source_index.get(track.source_id)
            source, info, code = _observe(track.track_id, locator, track.source_id, at,
                roots[index] if index is not None else None,
                sources[index] if index is not None else None,
                inventory.root_stats[index] if index is not None else None, physical_locator=physical_locator)
            if info is not None and _stat_changed(cached.get(track.track_id), info, track, locator):
                code = 'SOURCE_STAT_CHANGED'
                digest = _cached_digest(cached.get(track.track_id), info, track, locator)
                if _valid_digest(track.sha256) and digest is None:
                    try:
                        digest = _hash_file(Path(physical_locator), root=roots[index], root_stat=inventory.root_stats[index],
                                            expected_stat=info, cancelled=is_cancelled)
                    except InterruptedError:
                        source = replace(source, availability=FileAvailability.UNKNOWN, reason='CANCELLED')
                        info, code = None, 'CANCELLED'
                    except (OSError, RuntimeError, ValueError):
                        source = replace(source, availability=FileAvailability.ERROR, reason='FILE_CHANGED_OR_UNREADABLE')
                        info, code = None, 'FILE_CHANGED_OR_UNREADABLE'
                if info is not None:
                    if digest is not None:
                        code = 'SOURCE_CONTENT_CHANGED' if digest != track.sha256 else 'SOURCE_CONTENT_UNCHANGED'
                    source = replace(source, reason=_observation_reason(code, info, digest))
                    unresolved.append(DecisionCase(code, (track.track_id,), (locator,), 'SUSPECTED'))
            if source.availability in (FileAvailability.PRESENT, FileAvailability.MISSING):
                completed += 1
        facts = _facts(track, source, at, cached.get(track.track_id), prepared.get(track.track_id), managed_context,
                       cancelled=is_cancelled())
        evaluation = evaluate_file_state(facts)
        files.append(FileCheckResult(track.track_id, source, facts, evaluation,
                                     _technical(info) if info is not None else None, (code,)))
        reason_codes.add(code)
        if evaluation.is_confirmed and evaluation.state == FileState.CONFLICT:
            conflicts.append(DecisionCase(evaluation.reason, (track.track_id,), certainty='CONFIRMED'))
        elif source.availability in (FileAvailability.UNKNOWN, FileAvailability.ERROR, FileAvailability.OFFLINE):
            unresolved.append(DecisionCase(code, (track.track_id,), (locator,)))
        if progress and code != 'CANCELLED':
            progress(len(files), len(snapshot.tracks), track.path.name)
    moves, shared, digest_memo = [], defaultdict(list), {}
    by_size, by_name = defaultdict(list), defaultdict(list)
    for candidate in new_candidates:
        by_size[candidate.technical.size_bytes].append(candidate)
        by_name[Path(candidate.locator).name.casefold()].append(candidate)
    for track, item in zip(snapshot.tracks, files):
        if is_cancelled():
            break
        if item.source.availability != FileAvailability.MISSING:
            continue
        matches = []
        has_digest = _valid_digest(track.sha256)
        possible = by_size[track.size_bytes] if has_digest else by_name[track.path.name.casefold()]
        for candidate in possible:
            if is_cancelled():
                break
            evidence = ('FILENAME_MATCH',) if Path(candidate.locator).name.casefold() == track.path.name.casefold() else ()
            if has_digest:
                if candidate.locator not in digest_memo:
                    index, info = candidate_context[candidate.locator]
                    try:
                        digest_memo[candidate.locator] = _hash_file(Path(candidate.locator), root=roots[index],
                            root_stat=inventory.root_stats[index], expected_stat=info, cancelled=is_cancelled)
                    except InterruptedError:
                        break
                    except (OSError, RuntimeError, ValueError):
                        digest_memo[candidate.locator] = None
                        unresolved.append(DecisionCase('CANDIDATE_HASH_UNAVAILABLE', (track.track_id,), (candidate.locator,)))
                digest = digest_memo.get(candidate.locator)
                if digest != track.sha256:
                    if evidence and digest is not None:
                        conflicts.append(DecisionCase('IDENTITY_EVIDENCE_MISMATCH', (track.track_id,),
                                                      (candidate.locator,), 'SUSPECTED'))
                    continue
                evidence += ('SHA256_MATCH',)
                candidate = replace(candidate, technical=replace(candidate.technical, sha256=digest))
            matches.append(replace(candidate, evidence=evidence))
            shared[candidate.locator].append(track.track_id)
        if matches:
            moves.append(PossibleMove(track.track_id, track.source_id, locators[track.track_id], tuple(matches),
                                     'CONTENT_MATCH_REQUIRES_DECISION' if has_digest else 'WEAK_EVIDENCE'))
            if len(matches) > 1:
                unresolved.append(DecisionCase('MULTIPLE_MOVE_CANDIDATES', (track.track_id,), tuple(c.locator for c in matches)))
    for locator, ids in shared.items():
        if len(ids) > 1:
            unresolved.append(DecisionCase('CANDIDATE_SHARED_BY_RECORDS', tuple(ids), (locator,)))
    orphan_candidates = []
    attested_locators = {f.managed.locator for f in supplied if f.managed is not None
                         and f.managed_expected is True and f.ownership == Ownership.CONFIRMED
                         and f.owner_track_id == f.track_id}
    managed_stats = dict(managed_inventory.file_stats)
    for path in managed_inventory.files:
        if is_cancelled():
            break
        if str(path) not in attested_locators:
            orphan_candidates.append(FileCandidate(None, str(path), at, _technical(managed_stats[path]),
                                                    'POTENTIAL_ORPHAN_MANAGED'))
    saved = 0
    if not is_cancelled():
        try:
            eligible = tuple(item.facts for item in files if item.track_id not in damaged)
            evaluations = repository.save_file_facts_batch(eligible, snapshot=snapshot, cancelled=is_cancelled)
            persisted = {facts.track_id: evaluation for facts, evaluation in zip(eligible, evaluations)}
            files = [replace(item, evaluation=persisted.get(item.track_id, item.evaluation)) for item in files]
            saved = len(eligible)
        except InterruptedError:
            reason_codes.add('CANCELLED')
        except (ValueError, sqlite3.Error) as exc:
            reason_codes.add('CACHE_WRITE_REJECTED')
            unresolved.append(DecisionCase('CACHE_WRITE_REJECTED', tuple(item.track_id for item in files)))
    was_cancelled = is_cancelled() or 'CANCELLED' in reason_codes
    if was_cancelled:
        reason_codes.add('CANCELLED')
    reason_codes.update(case.reason for case in (*unresolved, *conflicts))
    availability = [item.source.availability for item in files]
    summary = ReconciliationSummary(availability.count(FileAvailability.PRESENT), availability.count(FileAvailability.MISSING),
        availability.count(FileAvailability.OFFLINE), availability.count(FileAvailability.UNKNOWN) + availability.count(FileAvailability.ERROR),
        len(new_candidates), len(moves), len(orphan_candidates), sum(c.certainty == 'CONFIRMED' for c in conflicts))
    return ReconciliationResult(snapshot.library_id, operation_id, at, summary, sources, tuple(files), tuple(new_candidates),
                                tuple(moves), tuple(orphan_candidates), tuple(conflicts), tuple(unresolved),
                                tuple(sorted(reason_codes)), was_cancelled, completed, len(files) - completed, saved)
