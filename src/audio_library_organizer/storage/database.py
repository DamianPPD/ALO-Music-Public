from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS tracks (
    path TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    duration_seconds REAL,
    bitrate_kbps INTEGER,
    sample_rate_hz INTEGER,
    channels INTEGER,
    codec TEXT,
    artist TEXT,
    title TEXT,
    album TEXT,
    year TEXT,
    genre TEXT,
    bpm REAL,
    bpm_raw REAL,
    bpm_confidence REAL,
    fingerprint TEXT,
    fingerprint_duration INTEGER,
    comment TEXT,
    has_cover INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    confidence REAL,
    proposed_filename TEXT,
    filename_override TEXT,
    original_tags_json TEXT NOT NULL DEFAULT '{}',
    discogs_release_id TEXT,
    discogs_url TEXT,
    musicbrainz_recording_id TEXT,
    musicbrainz_release_id TEXT,
    cover_art_url TEXT,
    manual_cover_path TEXT,
    cover_choice TEXT NOT NULL DEFAULT 'auto',
    match_reasons_json TEXT NOT NULL DEFAULT '[]',
    locked_fields_json TEXT NOT NULL DEFAULT '[]',
    pre_online_metadata_json TEXT NOT NULL DEFAULT '{}',
    field_sources_json TEXT NOT NULL DEFAULT '{}',
    field_source_values_json TEXT NOT NULL DEFAULT '{}',
    is_available INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_tracks_sha256 ON tracks(sha256);
CREATE INDEX IF NOT EXISTS idx_tracks_fingerprint ON tracks(fingerprint);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
'''


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_track_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
    additions = {
        'bpm_raw': 'REAL',
        'bpm_confidence': 'REAL',
        'fingerprint': 'TEXT',
        'fingerprint_duration': 'INTEGER',
        'discogs_release_id': 'TEXT',
        'discogs_url': 'TEXT',
        'musicbrainz_recording_id': 'TEXT',
        'musicbrainz_release_id': 'TEXT',
        'cover_art_url': 'TEXT',
        'manual_cover_path': 'TEXT',
        'cover_choice': "TEXT NOT NULL DEFAULT 'auto'",
        'filename_override': 'TEXT',
        'match_reasons_json': "TEXT NOT NULL DEFAULT '[]'",
        'locked_fields_json': "TEXT NOT NULL DEFAULT '[]'",
        'pre_online_metadata_json': "TEXT NOT NULL DEFAULT '{}'",
        'field_sources_json': "TEXT NOT NULL DEFAULT '{}'",
        'field_source_values_json': "TEXT NOT NULL DEFAULT '{}'",
        'is_available': 'INTEGER NOT NULL DEFAULT 1',
    }
    for name, sql_type in additions.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE tracks ADD COLUMN {name} {sql_type}')
