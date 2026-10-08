"""Durable source identities and locator matching; no scanning or audio I/O."""
from __future__ import annotations

from dataclasses import dataclass
import ntpath
import os
from pathlib import Path, PureWindowsPath, PurePosixPath
import sqlite3
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class SourceRoot:
    source_id: str
    library_id: str
    root_path: str
    canonical_root_key: str
    active: bool


def canonical_locator(raw: str | Path) -> tuple[str, str]:
    text = str(raw)
    if not text or '\x00' in text:
        raise ValueError('Source locator must be a nonempty path.')
    if text.startswith('\\\\?\\UNC\\'):
        text = '\\\\' + text[8:]
    elif text.startswith('\\\\?\\'):
        text = text[4:]
    if ntpath.splitdrive(text)[0] or text.startswith('\\\\'):
        path = PureWindowsPath(ntpath.normpath(text))
        if not path.is_absolute():
            raise ValueError('Windows source locator must be absolute.')
        absolute = str(Path(text).resolve()) if os.name == 'nt' else str(path)
        return absolute, 'windows:' + ntpath.normcase(absolute)
    absolute = str(Path(text).expanduser().resolve())
    return absolute, 'posix:' + absolute


def match_source(locator: str | Path, roots: list[SourceRoot]) -> tuple[str | None, str | None]:
    """Use the deepest containing root; equal-depth owners remain unassigned."""
    absolute, key = canonical_locator(locator)
    windows = key.startswith('windows:')
    path_type = PureWindowsPath if windows else PurePosixPath
    parts = path_type(absolute).parts
    folded = path_type(key.split(':', 1)[1]).parts
    candidates = []
    for source in roots:
        if source.canonical_root_key.split(':', 1)[0] != key.split(':', 1)[0]:
            continue
        root_parts = path_type(source.canonical_root_key.split(':', 1)[1]).parts
        depth = len(root_parts)
        if len(folded) > depth and folded[:depth] == root_parts:
            candidates.append((depth, source.source_id, '/'.join(parts[depth:])))
    if not candidates:
        return None, None
    depth = max(candidate[0] for candidate in candidates)
    deepest = [candidate for candidate in candidates if candidate[0] == depth]
    if len({candidate[1] for candidate in deepest}) != 1:
        return None, None
    return deepest[0][1], deepest[0][2]


def list_sources(conn: sqlite3.Connection, *, active_only: bool = False) -> list[SourceRoot]:
    where = ' WHERE active=1' if active_only else ''
    return [SourceRoot(row['source_id'], row['library_id'], row['root_path'],
                       row['canonical_root_key'], bool(row['active']))
            for row in conn.execute('SELECT * FROM sources' + where + ' ORDER BY rowid')]


def write_sources(conn: sqlite3.Connection, roots, *, replace: bool) -> None:
    # Normalize the complete request before its first write.
    normalized = dict((key, absolute) for absolute, key in map(canonical_locator, roots))
    library_id = conn.execute('SELECT library_id FROM library_metadata WHERE singleton=1').fetchone()[0]
    if replace:
        conn.execute('UPDATE sources SET active=0 WHERE library_id=?', (library_id,))
    for key, absolute in normalized.items():
        conn.execute('''INSERT INTO sources (source_id,library_id,root_path,canonical_root_key,active)
                        VALUES (?,?,?,?,1) ON CONFLICT(library_id,canonical_root_key)
                        DO UPDATE SET active=1''', (str(uuid4()), library_id, absolute, key))
    bind_tracks(conn)
    conn.execute('UPDATE library_metadata SET sources_initialized=1 WHERE singleton=1')


def bind_tracks(conn: sqlite3.Connection) -> None:
    roots = list_sources(conn)
    updates = []
    for row in conn.execute('SELECT track_id,path,source_id,source_relative_path FROM tracks'):
        source_id, relative = match_source(row['path'], roots)
        if (source_id, relative) != (row['source_id'], row['source_relative_path']):
            updates.append((source_id, relative, row['track_id']))
    if updates:
        conn.executemany('UPDATE tracks SET source_id=?,source_relative_path=? WHERE track_id=?', updates)


def create_source_schema(conn: sqlite3.Connection) -> None:
    conn.execute('''CREATE TABLE library_metadata (
        singleton INTEGER NOT NULL PRIMARY KEY CHECK(singleton=1),
        library_id TEXT NOT NULL UNIQUE,
        sources_initialized INTEGER NOT NULL DEFAULT 0 CHECK(sources_initialized IN (0,1)))''')
    conn.execute('INSERT INTO library_metadata (singleton,library_id) VALUES (1,?)', (str(uuid4()),))
    conn.execute('''CREATE TABLE sources (
        source_id TEXT NOT NULL PRIMARY KEY,
        library_id TEXT NOT NULL REFERENCES library_metadata(library_id),
        root_path TEXT NOT NULL, canonical_root_key TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        UNIQUE(library_id,canonical_root_key))''')
    conn.execute('ALTER TABLE tracks ADD COLUMN source_id TEXT REFERENCES sources(source_id)')
    conn.execute('''ALTER TABLE tracks ADD COLUMN source_relative_path TEXT
        CHECK((source_id IS NULL AND source_relative_path IS NULL) OR
              (source_id IS NOT NULL AND source_relative_path IS NOT NULL))''')
    conn.execute('CREATE INDEX idx_tracks_source_id ON tracks(source_id)')
    # Non-unique: legacy aliases may be ambiguous and must remain preserved.
    conn.execute("ALTER TABLE tracks ADD COLUMN path_key TEXT NOT NULL DEFAULT ''")
    rows = conn.execute('SELECT track_id,path FROM tracks').fetchall()
    conn.executemany('UPDATE tracks SET path_key=? WHERE track_id=?',
                     [(canonical_locator(row['path'])[1], row['track_id']) for row in rows])
    conn.execute('CREATE INDEX idx_tracks_path_key ON tracks(path_key)')


def validate_source_schema(conn: sqlite3.Connection) -> None:
    metadata = conn.execute('SELECT * FROM library_metadata').fetchall()
    if len(metadata) != 1 or metadata[0]['singleton'] != 1:
        raise ValueError('Library must have exactly one durable identity.')
    library_id = metadata[0]['library_id']
    UUID(library_id)
    if metadata[0]['sources_initialized'] not in (0, 1):
        raise ValueError('Invalid source registry initialization state.')
    for root in list_sources(conn):
        UUID(root.source_id)
        if root.library_id != library_id:
            raise ValueError('Source belongs to another library.')
        if canonical_locator(root.root_path)[1] != root.canonical_root_key:
            raise ValueError('Source canonical key does not match its root.')
    for row in conn.execute('SELECT path,path_key,source_id,source_relative_path FROM tracks'):
        if row['path_key'] != canonical_locator(row['path'])[1]:
            raise ValueError('Track canonical locator key does not match its path.')
    indexes = conn.execute('PRAGMA index_list(tracks)').fetchall()
    if not any(row[1] == 'idx_tracks_path_key' and not row[2] and not row[4] for row in indexes):
        raise ValueError('Track canonical locator index is missing.')
    if conn.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise ValueError('Library source foreign key integrity failed.')
