"""Authoritative adopted bindings, separate from disposable file-state knowledge."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
from uuid import UUID


TABLE_SQL = {
    'source_audio_references': '''CREATE TABLE source_audio_references (
        track_id TEXT NOT NULL PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
        library_id TEXT NOT NULL,
        context_digest TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        observed_at INTEGER NOT NULL CHECK(observed_at >= 0))''',
    'legacy_adoption_runs': '''CREATE TABLE legacy_adoption_runs (
        run_id TEXT NOT NULL PRIMARY KEY,
        library_id TEXT NOT NULL,
        context_digest TEXT NOT NULL,
        context_json TEXT NOT NULL,
        checked_at INTEGER NOT NULL CHECK(checked_at >= 0))''',
    'legacy_adoption_proposals': '''CREATE TABLE legacy_adoption_proposals (
        proposal_id TEXT NOT NULL PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES legacy_adoption_runs(run_id) ON DELETE CASCADE,
        track_id TEXT REFERENCES tracks(track_id) ON DELETE CASCADE,
        locator_key TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('CANDIDATE','CONFLICT','UNRESOLVED','UNSUPPORTED','ALREADY_BOUND')),
        proposal_json TEXT NOT NULL)''',
    'managed_bindings': '''CREATE TABLE managed_bindings (
        track_id TEXT NOT NULL PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
        library_id TEXT NOT NULL,
        binding_id TEXT NOT NULL UNIQUE,
        relative_path TEXT NOT NULL,
        locator_key TEXT NOT NULL UNIQUE,
        expected_sha256 TEXT NOT NULL CHECK(length(expected_sha256)=64),
        audio_algorithm TEXT NOT NULL,
        audio_digest TEXT NOT NULL CHECK(length(audio_digest)=64),
        device INTEGER NOT NULL,
        inode INTEGER NOT NULL,
        stat_json TEXT NOT NULL,
        source_binding_json TEXT NOT NULL,
        applied_snapshot_json TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        adopted_at INTEGER NOT NULL CHECK(adopted_at >= 0),
        UNIQUE(device,inode))''',
}


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def evidence_digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def valid_digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def safe_relative(value):
    if not isinstance(value, str) or not value or any(c in value for c in '\\:\x00'):
        raise ValueError('Unsafe managed relative locator.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value or value == '.':
        raise ValueError('Unsafe managed relative locator.')
    return path


def create_managed_schema(conn: sqlite3.Connection):
    for sql in TABLE_SQL.values():
        conn.execute(sql)
    conn.execute('CREATE INDEX idx_adoption_track ON legacy_adoption_proposals(track_id,status)')


def validate_managed_schema(conn: sqlite3.Connection):
    # Exact versioned layouts: do not quietly accept a table missing ownership
    # uniqueness, foreign keys, checks, or a column added by an unknown writer.
    normalize = lambda sql: ' '.join(sql.split()).lower()
    for name, definition in TABLE_SQL.items():
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        if row is None or normalize(row[0]) != normalize(definition):
            raise ValueError(f'Unsupported adoption schema: {name}.')
        if conn.execute(f'PRAGMA foreign_key_check({name})').fetchone() is not None:
            raise ValueError(f'Adoption foreign key integrity failed: {name}.')


@dataclass(frozen=True, slots=True)
class ManagedBinding:
    library_id: str
    track_id: str
    binding_id: str
    relative_path: str
    locator_key: str
    expected_sha256: str
    audio_algorithm: str
    audio_digest: str
    stat_identity: tuple
    source_binding: dict
    applied_snapshot: dict
    evidence: dict
    adopted_at: int

    def locator(self, root):
        return str(Path(root).joinpath(*safe_relative(self.relative_path).parts))

    def read_proof(self, root):
        from audio_library_organizer.jobs.managed_files import ManagedReadBinding, lexical_locator
        if lexical_locator(self.locator(root)) != self.locator_key:
            raise ValueError('Managed binding belongs to another library root.')
        return ManagedReadBinding(self.library_id, self.track_id, self.locator(root),
                                  self.expected_sha256, self.binding_id)


def read_managed_bindings(conn):
    library_id = conn.execute('SELECT library_id FROM library_metadata WHERE singleton=1').fetchone()[0]
    bindings = []
    for row in conn.execute('SELECT * FROM managed_bindings ORDER BY track_id'):
        UUID(row['library_id']); UUID(row['track_id']); UUID(row['binding_id'])
        safe_relative(row['relative_path'])
        if row['library_id'] != library_id or not valid_digest(row['expected_sha256']) or not valid_digest(row['audio_digest']):
            raise ValueError('Invalid adopted binding identity/digest.')
        token = tuple(json.loads(row['stat_json']))
        if len(token) != 6 or not all(type(v) is int for v in token) or token[:2] != (row['device'], row['inode']):
            raise ValueError('Invalid adopted binding physical evidence.')
        payloads = [json.loads(row[name]) for name in ('source_binding_json','applied_snapshot_json','evidence_json')]
        if not all(isinstance(v, dict) for v in payloads):
            raise ValueError('Invalid adopted binding snapshot/evidence.')
        bindings.append(ManagedBinding(row['library_id'], row['track_id'], row['binding_id'],
            row['relative_path'], row['locator_key'], row['expected_sha256'], row['audio_algorithm'],
            row['audio_digest'], token, *payloads, row['adopted_at']))
    return tuple(bindings)
