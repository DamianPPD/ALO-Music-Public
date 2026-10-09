from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import time

# Application schema version. SQLite's schema_version is an internal DDL counter.
SCHEMA_VERSION = 3
BACKUP_BUSY_TIMEOUT = 5.0

TRACK_COLUMNS = {
    'path': 'TEXT NOT NULL UNIQUE',
    'size_bytes': 'INTEGER NOT NULL DEFAULT 0',
    'mtime_ns': 'INTEGER NOT NULL DEFAULT 0',
    'duration_seconds': 'REAL', 'bitrate_kbps': 'INTEGER', 'sample_rate_hz': 'INTEGER',
    'channels': 'INTEGER', 'codec': 'TEXT', 'artist': 'TEXT', 'title': 'TEXT',
    'album': 'TEXT', 'year': 'TEXT', 'genre': 'TEXT', 'bpm': 'REAL',
    'bpm_raw': 'REAL', 'bpm_confidence': 'REAL', 'fingerprint': 'TEXT',
    'fingerprint_duration': 'INTEGER', 'comment': 'TEXT',
    'has_cover': 'INTEGER NOT NULL DEFAULT 0', 'sha256': 'TEXT',
    'status': "TEXT NOT NULL DEFAULT 'new'", 'confidence': 'REAL',
    'proposed_filename': 'TEXT', 'filename_override': 'TEXT',
    'original_tags_json': "TEXT NOT NULL DEFAULT '{}'", 'discogs_release_id': 'TEXT',
    'discogs_url': 'TEXT', 'musicbrainz_recording_id': 'TEXT',
    'musicbrainz_release_id': 'TEXT', 'cover_art_url': 'TEXT', 'manual_cover_path': 'TEXT',
    'cover_choice': "TEXT NOT NULL DEFAULT 'auto'",
    'match_reasons_json': "TEXT NOT NULL DEFAULT '[]'",
    'locked_fields_json': "TEXT NOT NULL DEFAULT '[]'",
    'pre_online_metadata_json': "TEXT NOT NULL DEFAULT '{}'",
    'field_sources_json': "TEXT NOT NULL DEFAULT '{}'",
    'field_source_values_json': "TEXT NOT NULL DEFAULT '{}'",
    'audio_recognition_json': "TEXT NOT NULL DEFAULT '{}'",
    'is_available': 'INTEGER NOT NULL DEFAULT 1',
}
TRACK_INDEXES = (
    'CREATE INDEX IF NOT EXISTS idx_tracks_sha256 ON tracks(sha256)',
    'CREATE INDEX IF NOT EXISTS idx_tracks_fingerprint ON tracks(fingerprint)',
    'CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status)',
)


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def create_tracks_sql(table: str = 'tracks') -> str:
    fields = ['track_id TEXT NOT NULL PRIMARY KEY']
    fields.extend(f'{quoted(name)} {definition}' for name, definition in TRACK_COLUMNS.items())
    return f'CREATE TABLE {quoted(table)} (' + ','.join(fields) + ')'


SCHEMA = create_tracks_sql().replace('CREATE TABLE ', 'CREATE TABLE IF NOT EXISTS ', 1) + ';\n' + ';\n'.join(TRACK_INDEXES) + ';'


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute('PRAGMA user_version').fetchone()[0])


def require_current_schema(conn: sqlite3.Connection) -> None:
    version = schema_version(conn)
    if version != SCHEMA_VERSION:
        raise ValueError(f'Unsupported schema version {version}; supported version is {SCHEMA_VERSION}.')


def check_integrity(conn: sqlite3.Connection) -> None:
    result = [row[0] for row in conn.execute('PRAGMA integrity_check')]
    if result != ['ok']:
        raise sqlite3.DatabaseError('SQLite integrity_check failed: ' + '; '.join(result))


def ensure_track_columns(conn: sqlite3.Connection) -> None:
    """Add known historical fields before creating any dependent indexes."""
    existing = {row[1] for row in conn.execute('PRAGMA table_info(tracks)')}
    if 'path' not in existing:
        raise ValueError('Unsupported tracks schema: missing path locator.')
    for name, definition in TRACK_COLUMNS.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE tracks ADD COLUMN {quoted(name)} {definition}')


def snapshot_database(source: Path, destination: Path) -> Path:
    """Produce a self-contained SQLite snapshot, including committed WAL pages.

    Always use a separate read connection: backup on a connection holding a write
    transaction can wait indefinitely. Continuous BUSY/LOCKED is bounded.
    The destination is replaced only after a complete, verified snapshot exists.
    """
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('Snapshot destination must differ from source.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.sqlite-snapshot-', suffix='.sqlite3', dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary)
    busy_since = None

    def progress(status: int, remaining: int, total: int) -> None:
        nonlocal busy_since
        if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            now = time.monotonic()
            if busy_since is None:
                busy_since = now
            if now - busy_since >= BACKUP_BUSY_TIMEOUT:
                raise TimeoutError(f'SQLite backup blocked for {BACKUP_BUSY_TIMEOUT:g} seconds: {source}')
        else:
            busy_since = None

    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=0)) as reader:
            with closing(sqlite3.connect(temporary)) as writer:
                reader.backup(writer, pages=256, progress=progress, sleep=0.05)
                check_integrity(writer)
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
