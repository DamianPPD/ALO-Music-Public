"""Optional, atomic file-state knowledge; no managed binding or file I/O.

The latest observation and the last confirmed public state have separate
lifetimes. A cache read is historical evidence and always needs revalidation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import json
import sqlite3

from audio_library_organizer.domain.file_state import (
    ConflictReason, FileAvailability, FileFacts, FileObservation, FileState,
    FileStateEvaluation, OutputSnapshot, Ownership, evaluate_file_state,
)


class FileStateCacheError(ValueError):
    """Malformed optional cache is retained; callers may still read tracks."""


@dataclass(frozen=True, slots=True)
class CachedFileState:
    facts: FileFacts
    evaluation: FileStateEvaluation
    last_confirmed_reason: str | None


def create_file_state_schema(conn: sqlite3.Connection) -> None:
    conn.execute('''CREATE TABLE file_state_cache (
        track_id TEXT NOT NULL PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
        source_locator TEXT NOT NULL,
        source_id TEXT,
        facts_json TEXT NOT NULL,
        observation_at INTEGER NOT NULL CHECK(observation_at >= 0),
        source_observed_at INTEGER CHECK(source_observed_at >= 0 AND source_observed_at <= observation_at),
        managed_observed_at INTEGER CHECK(managed_observed_at >= 0 AND managed_observed_at <= observation_at),
        last_confirmed_state TEXT CHECK(last_confirmed_state IN (
            'IN_LIBRARY','SOURCE_ONLY','NEEDS_UPDATE','SOURCE_UNAVAILABLE','MANAGED_FILE_MISSING','CONFLICT')),
        last_confirmed_at INTEGER CHECK(last_confirmed_at >= 0 AND last_confirmed_at <= observation_at),
        last_confirmed_reason TEXT,
        CHECK((last_confirmed_state IS NULL AND last_confirmed_at IS NULL AND last_confirmed_reason IS NULL) OR
              (last_confirmed_state IS NOT NULL AND last_confirmed_at IS NOT NULL AND last_confirmed_reason IS NOT NULL)))''')


def validate_file_state_schema(conn: sqlite3.Connection) -> None:
    expected = {
        'track_id': ('TEXT', 1, 1), 'source_locator': ('TEXT', 1, 0), 'source_id': ('TEXT', 0, 0),
        'facts_json': ('TEXT', 1, 0), 'observation_at': ('INTEGER', 1, 0),
        'source_observed_at': ('INTEGER', 0, 0), 'managed_observed_at': ('INTEGER', 0, 0),
        'last_confirmed_state': ('TEXT', 0, 0), 'last_confirmed_at': ('INTEGER', 0, 0),
        'last_confirmed_reason': ('TEXT', 0, 0),
    }
    actual = {row[1]: (row[2], row[3], row[5]) for row in conn.execute('PRAGMA table_info(file_state_cache)')}
    if actual != expected:
        raise ValueError('Unsupported file-state cache schema.')
    references = [(row[2], row[3], row[4], row[6]) for row in conn.execute('PRAGMA foreign_key_list(file_state_cache)')]
    if references != [('tracks', 'track_id', 'track_id', 'CASCADE')]:
        raise ValueError('File-state cache identity foreign key is missing.')
    if conn.execute('PRAGMA foreign_key_check(file_state_cache)').fetchone() is not None:
        raise ValueError('File-state cache foreign key integrity failed.')
    # Optional JSON is decoded on an explicit cache read, not during library
    # opening. Its corruption must not prevent ordinary metadata access.


def _facts_json(facts: FileFacts) -> str:
    data = asdict(facts)
    # History comes only from this database, never from a worker/caller cache.
    data.pop('last_confirmed_state')
    data.pop('last_confirmed_at')
    return json.dumps({'version': 1, 'facts': data}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _structure(data, model):
    if not isinstance(data, dict) or set(data) != {field.name for field in fields(model)}:
        raise ValueError(f'Invalid {model.__name__} cache structure.')
    return dict(data)


def _decode_facts(payload: str) -> FileFacts:
    data = json.loads(payload)
    if (not isinstance(data, dict) or set(data) != {'version', 'facts'}
            or type(data['version']) is not int or data['version'] != 1):
        raise ValueError('Unsupported file-state cache format.')
    names = {field.name for field in fields(FileFacts)} - {'last_confirmed_state', 'last_confirmed_at'}
    if not isinstance(data['facts'], dict) or set(data['facts']) != names:
        raise ValueError('Invalid FileFacts cache structure.')
    values = dict(data['facts'])
    for name in ('source', 'managed'):
        if values[name] is not None:
            obs = _structure(values[name], FileObservation)
            obs['availability'] = FileAvailability(obs['availability'])
            values[name] = FileObservation(**obs)
    for name in ('desired', 'applied'):
        if values[name] is not None:
            values[name] = OutputSnapshot(**_structure(values[name], OutputSnapshot))
    values['ownership'] = Ownership(values['ownership'])
    if values['conflict'] is not None:
        values['conflict'] = ConflictReason(values['conflict'])
    return FileFacts(**values)


def _decode_row(row) -> tuple[FileFacts, str | None]:
    try:
        facts = _decode_facts(row['facts_json'])
        if facts.track_id != row['track_id'] or facts.checked_at != row['observation_at']:
            raise ValueError('File-state cache identity/time mismatch.')
        for name in ('source', 'managed'):
            watermark = row[name + '_observed_at']
            obs = getattr(facts, name)
            if watermark is not None and (type(watermark) is not int or not 0 <= watermark <= facts.checked_at):
                raise ValueError(f'Invalid {name} observation watermark.')
            if obs is not None and watermark != obs.checked_at:
                raise ValueError(f'{name} observation watermark contradicts its facts.')
        state = FileState(row['last_confirmed_state']) if row['last_confirmed_state'] is not None else None
        facts = replace(facts, last_confirmed_state=state, last_confirmed_at=row['last_confirmed_at'])
        reason = row['last_confirmed_reason']
        if (state is None and reason is not None) or (state is not None and (not isinstance(reason, str) or not reason)):
            raise ValueError('Invalid confirmed-history reason.')
        evaluation = evaluate_file_state(facts)
        if evaluation.is_confirmed and (evaluation.state, evaluation.last_confirmed_at, evaluation.reason) != (
                state, row['last_confirmed_at'], reason):
            raise ValueError('Confirmed cache history contradicts its facts.')
        return facts, reason
    except (ValueError, TypeError, KeyError, RecursionError) as cause:
        raise FileStateCacheError(f'Invalid file-state cache for {row["track_id"]}: {cause}') from cause


def _check_associations(facts: FileFacts, track) -> None:
    if facts.track_id != track['track_id']:
        raise ValueError('File-state track identity does not match the record.')
    if facts.source is not None and (facts.source.track_id, facts.source.locator, facts.source.source_id) != (
            track['track_id'], track['path'], track['source_id']):
        raise ValueError('Source observation identity/locator/binding is stale.')
    if facts.managed is not None and (facts.managed.track_id != track['track_id'] or facts.managed.source_id is not None):
        raise ValueError('Managed observation identity is invalid.')


def _check_order(facts: FileFacts, previous: FileFacts, row) -> None:
    if facts.checked_at < previous.checked_at:
        raise ValueError('Stale file-state facts are older than the saved observation.')
    for name in ('source', 'managed'):
        old, new = getattr(previous, name), getattr(facts, name)
        watermark = row[name + '_observed_at']
        if watermark is not None and new is not None:
            # None is current uncertainty, not deletion of ordering evidence.
            # After a gap equal-time content cannot be proven identical, so it
            # is rejected conservatively until there is a genuinely new check.
            if new.checked_at < watermark or (new.checked_at == watermark and new != old):
                raise ValueError(f'Stale or conflicting {name} observation.')


def write_file_facts(conn: sqlite3.Connection, facts: FileFacts) -> FileStateEvaluation:
    """Called inside the repository's IMMEDIATE transaction; never write tracks."""
    track = conn.execute('SELECT track_id,path,source_id FROM tracks WHERE track_id=?', (facts.track_id,)).fetchone()
    if track is None:
        raise ValueError('Unknown track; file-state cache cannot create a record.')
    _check_associations(facts, track)
    row = conn.execute('SELECT * FROM file_state_cache WHERE track_id=?', (facts.track_id,)).fetchone()
    previous, previous_reason = _decode_row(row) if row is not None else (None, None)
    payload = _facts_json(facts)
    if previous is not None:
        _check_order(facts, previous, row)
        if facts.checked_at == previous.checked_at:
            if payload != row['facts_json'] or (row['source_locator'], row['source_id']) != (track['path'], track['source_id']):
                raise ValueError('Conflicting facts at the same observation time.')
            return evaluate_file_state(previous)
    effective = replace(facts, last_confirmed_state=previous.last_confirmed_state if previous else None,
                        last_confirmed_at=previous.last_confirmed_at if previous else None)
    evaluation = evaluate_file_state(effective)
    confirmed_reason = evaluation.reason if evaluation.is_confirmed else previous_reason
    watermarks = []
    for name in ('source', 'managed'):
        obs = getattr(facts, name)
        watermarks.append(obs.checked_at if obs is not None else row[name + '_observed_at'] if row is not None else None)
    conn.execute('''INSERT INTO file_state_cache
        (track_id,source_locator,source_id,facts_json,observation_at,source_observed_at,managed_observed_at,
         last_confirmed_state,last_confirmed_at,last_confirmed_reason)
        VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET
        source_locator=excluded.source_locator,source_id=excluded.source_id,
        facts_json=excluded.facts_json,observation_at=excluded.observation_at,
        source_observed_at=excluded.source_observed_at,managed_observed_at=excluded.managed_observed_at,
        last_confirmed_state=excluded.last_confirmed_state,last_confirmed_at=excluded.last_confirmed_at,
        last_confirmed_reason=excluded.last_confirmed_reason''',
        (facts.track_id, track['path'], track['source_id'], payload, facts.checked_at, *watermarks,
         evaluation.last_confirmed_state, evaluation.last_confirmed_at, confirmed_reason))
    return evaluation


def read_file_state(conn: sqlite3.Connection, track_id: str) -> CachedFileState | None:
    row = conn.execute('SELECT * FROM file_state_cache WHERE track_id=?', (track_id,)).fetchone()
    if row is None:
        return None
    facts, reason = _decode_row(row)
    track = conn.execute('SELECT track_id,path,source_id FROM tracks WHERE track_id=?', (track_id,)).fetchone()
    binding_changed = track is None or (row['source_locator'], row['source_id']) != (track['path'], track['source_id'])
    if not binding_changed:
        try:
            _check_associations(facts, track)
        except ValueError:
            binding_changed = True
    facts = replace(facts, is_current=False)
    evaluation = evaluate_file_state(facts)
    evaluation = replace(evaluation, reason='TRACK_BINDING_CHANGED' if binding_changed else 'CACHE_REQUIRES_REVALIDATION')
    return CachedFileState(facts, evaluation, reason)
