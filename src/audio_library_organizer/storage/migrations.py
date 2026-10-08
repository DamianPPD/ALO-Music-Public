"""Versioned, transactional migration of the library; no audio-file operations."""
from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from uuid import UUID, uuid4

from .database import (
    SCHEMA_VERSION, TRACK_COLUMNS, TRACK_INDEXES, check_integrity,
    create_tracks_sql, ensure_track_columns, quoted, schema_version, snapshot_database,
)
from .source_registry import create_source_schema, validate_source_schema


class MigrationError(RuntimeError):
    def __init__(self, path: Path, cause: Exception, backup_path: Path | None = None):
        self.database_path = path
        self.backup_path = backup_path
        message = f'Library migration failed for {path}: {cause}'
        if backup_path is not None:
            message += f' (pre-migration backup: {backup_path})'
        super().__init__(message)


def validate_track_ids(conn: sqlite3.Connection) -> None:
    columns = conn.execute('PRAGMA table_info(tracks)').fetchall()
    if [row[1] for row in columns if row[5]] != ['track_id']:
        raise ValueError('Unsupported UUID schema: track_id is not the primary key.')
    if not next(row[3] for row in columns if row[1] == 'track_id'):
        raise ValueError('Unsupported UUID schema: track_id must be NOT NULL.')
    for row in conn.execute('SELECT track_id FROM tracks'):
        UUID(row[0])
    # Path must remain a unique, required locator for the transitional repository.
    if not next((row[3] for row in columns if row[1] == 'path'), False):
        raise ValueError('Unsupported UUID schema: path must be NOT NULL.')
    unique_path = False
    for index in conn.execute('PRAGMA index_list(tracks)'):
        if index[2] and not index[4]:
            names = [r[2] for r in conn.execute(f'PRAGMA index_info({quoted(index[1])})')]
            unique_path |= names == ['path']
    if not unique_path:
        raise ValueError('Unsupported UUID schema: path must be UNIQUE.')
    missing = set(TRACK_COLUMNS) - {row[1] for row in columns}
    if missing:
        raise ValueError(f'Unsupported UUID schema: missing columns {sorted(missing)}.')


def _legacy_schema(conn: sqlite3.Connection) -> list[str]:
    """Fail closed for layouts whose constraints/data would be lost in rebuild."""
    columns = conn.execute('PRAGMA table_xinfo(tracks)').fetchall()
    unknown = {r[1] for r in columns} - set(TRACK_COLUMNS) - {'track_id'}
    if unknown or any(r[6] for r in columns):
        raise ValueError(f'Unsupported custom tracks columns: {sorted(unknown)}.')
    pk = [r[1] for r in columns if r[5]]
    if pk not in (['path'], ['track_id']):
        raise ValueError(f'Unsupported legacy primary key: {pk}.')
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND lower(name)='tracks'").fetchone()[0]
    if re.search(r'\b(CHECK|COLLATE|REFERENCES|STRICT)\b|\bWITHOUT\s+ROWID\b', sql, re.I):
        raise ValueError('Unsupported custom tracks constraints/options.')
    for table in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        foreign_keys = conn.execute(f'PRAGMA foreign_key_list({quoted(table[0])})').fetchall()
        if (table[0].lower() == 'tracks' and foreign_keys) or any(r[2].lower() == 'tracks' for r in foreign_keys):
            raise ValueError('Unsupported foreign key dependency on tracks.')
    for index in conn.execute('PRAGMA index_list(tracks)').fetchall():
        if index[3] == 'u':
            names = [r[2] for r in conn.execute(f'PRAGMA index_info({quoted(index[1])})')]
            if names not in (['path'], ['track_id']):
                raise ValueError('Unsupported implicit UNIQUE constraint on tracks.')
    return [r[1] for r in columns if r[1] != 'track_id']


def _migrate_tracks(conn: sqlite3.Connection) -> None:
    legacy_fields = _legacy_schema(conn)
    schema_objects = conn.execute("SELECT sql FROM sqlite_master WHERE lower(tbl_name)='tracks' AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name").fetchall()
    ensure_track_columns(conn)
    has_id = any(r[1] == 'track_id' for r in conn.execute('PRAGMA table_info(tracks)'))
    if has_id:
        for row in conn.execute("SELECT track_id FROM tracks WHERE track_id IS NOT NULL AND track_id != ''"):
            UUID(row[0])
    conn.execute(create_tracks_sql('tracks_uuid_v1'))
    fields = ','.join(quoted(name) for name in TRACK_COLUMNS)
    conn.create_function('alo_uuid4', 0, lambda: str(uuid4()))
    identity = "CASE WHEN track_id IS NULL OR track_id='' THEN alo_uuid4() ELSE track_id END" if has_id else 'alo_uuid4()'
    try:
        conn.execute(f'INSERT INTO tracks_uuid_v1 (track_id,{fields}) SELECT {identity},{fields} FROM tracks')
    finally:
        conn.create_function('alo_uuid4', 0, None)
    old_count = conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0]
    new_count = conn.execute('SELECT COUNT(*) FROM tracks_uuid_v1').fetchone()[0]
    if old_count != new_count:
        raise ValueError('Migration changed the record count.')
    preserved = ','.join(quoted(name) for name in legacy_fields)
    for old, new in (('tracks', 'tracks_uuid_v1'), ('tracks_uuid_v1', 'tracks')):
        difference = conn.execute(f'SELECT {preserved} FROM {old} EXCEPT SELECT {preserved} FROM {new} LIMIT 1').fetchone()
        if difference is not None:
            raise ValueError('Migration changed legacy field values.')
    conn.execute('DROP TABLE tracks')
    conn.execute('ALTER TABLE tracks_uuid_v1 RENAME TO tracks')
    for row in schema_objects:
        conn.execute(row[0])
    for sql in TRACK_INDEXES:
        conn.execute(sql)


def migrate_library(conn: sqlite3.Connection, database_path: Path) -> Path | None:
    """Upgrade v0/v1 to v2 atomically. Retry never regenerates saved IDs."""
    backup_path = None
    try:
        version = schema_version(conn)
        if version > SCHEMA_VERSION:
            raise ValueError(f'Unsupported newer schema version {version}; supported version is {SCHEMA_VERSION}.')
        if conn.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'off':
            raise ValueError('journal_mode=OFF cannot guarantee migration rollback.')
        conn.execute('BEGIN IMMEDIATE')
        version = schema_version(conn)  # Recheck under the write reservation.
        if version > SCHEMA_VERSION:
            raise ValueError(f'Unsupported newer schema version {version}.')
        check_integrity(conn)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if version < SCHEMA_VERSION and tables:
            snapshot = database_path.parent / 'migration-backups' / f'pre-v{SCHEMA_VERSION}-{uuid4().hex}.sqlite3'
            snapshot_database(database_path, snapshot)
            backup_path = snapshot
        if version == SCHEMA_VERSION:
            validate_track_ids(conn)
            validate_source_schema(conn)
        elif version in (0, 1):
            if version == 0:
                if any(row[0].lower() == 'tracks' for row in tables):
                    _migrate_tracks(conn)
                else:
                    conn.execute(create_tracks_sql())
                    for sql in TRACK_INDEXES:
                        conn.execute(sql)
            validate_track_ids(conn)
            create_source_schema(conn)
            validate_source_schema(conn)
            check_integrity(conn)
            conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        else:
            raise ValueError(f'Unsupported schema version {version}.')
        conn.commit()
        return backup_path
    except Exception as cause:
        conn.rollback()
        raise MigrationError(database_path, cause, backup_path) from cause
