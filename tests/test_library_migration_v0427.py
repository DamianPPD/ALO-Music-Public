"""Contract tests on synthetic databases; never open a user music library."""
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

import pytest

from audio_library_organizer.storage.repository import LibraryRepository


# Frozen pre-UUID schema, independent of the production schema being migrated.
LEGACY_COLUMNS = {
    'path': 'TEXT PRIMARY KEY', 'size_bytes': 'INTEGER NOT NULL',
    'mtime_ns': 'INTEGER NOT NULL', 'duration_seconds': 'REAL',
    'bitrate_kbps': 'INTEGER', 'sample_rate_hz': 'INTEGER', 'channels': 'INTEGER',
    'codec': 'TEXT', 'artist': 'TEXT', 'title': 'TEXT', 'album': 'TEXT',
    'year': 'TEXT', 'genre': 'TEXT', 'bpm': 'REAL', 'bpm_raw': 'REAL',
    'bpm_confidence': 'REAL', 'fingerprint': 'TEXT', 'fingerprint_duration': 'INTEGER',
    'comment': 'TEXT', 'has_cover': 'INTEGER NOT NULL DEFAULT 0', 'sha256': 'TEXT',
    'status': "TEXT NOT NULL DEFAULT 'new'", 'confidence': 'REAL',
    'proposed_filename': 'TEXT', 'filename_override': 'TEXT',
    'original_tags_json': "TEXT NOT NULL DEFAULT '{}'", 'discogs_release_id': 'TEXT',
    'discogs_url': 'TEXT', 'musicbrainz_recording_id': 'TEXT',
    'musicbrainz_release_id': 'TEXT', 'cover_art_url': 'TEXT',
    'manual_cover_path': 'TEXT', 'cover_choice': "TEXT NOT NULL DEFAULT 'auto'",
    'match_reasons_json': "TEXT NOT NULL DEFAULT '[]'",
    'locked_fields_json': "TEXT NOT NULL DEFAULT '[]'",
    'pre_online_metadata_json': "TEXT NOT NULL DEFAULT '{}'",
    'field_sources_json': "TEXT NOT NULL DEFAULT '{}'",
    'field_source_values_json': "TEXT NOT NULL DEFAULT '{}'",
    'audio_recognition_json': "TEXT NOT NULL DEFAULT '{}'",
    'is_available': 'INTEGER NOT NULL DEFAULT 1',
}


def legacy_database(path: Path, *, variant='full', wal=False):
    columns = dict(LEGACY_COLUMNS)
    if variant == 'no_fingerprint':
        columns.pop('fingerprint')
        columns.pop('fingerprint_duration')
    elif variant == 'minimal':
        columns = {k: columns[k] for k in ('path', 'size_bytes', 'mtime_ns', 'title', 'status')}
    conn = sqlite3.connect(path)
    if wal:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
    conn.execute('CREATE TABLE tracks (' + ','.join(f'"{k}" {v}' for k, v in columns.items()) + ')')
    for i in range(3):
        row = {k: f'{k}: Zażółć 東京 {i}' for k in columns}
        row.update({k: i + 2 for k, v in columns.items() if v.startswith('INTEGER')})
        row.update({k: 123.125 + i for k, v in columns.items() if v.startswith('REAL')})
        row.update(path=f'relative/Źródło {i}.mp3', size_bytes=2**40+i, mtime_ns=2**55+i,
                   title=['Ręczny tytuł', '', None][i], status=['ready', 'review', 'duplicate'][i])
        for k in columns:
            if k.endswith('_json'):
                row[k] = ' ["title", "title", "artist"] ' if k in ('locked_fields_json', 'match_reasons_json') else ' { "b": [1, null, "ą"], "a": {"manual": true} } '
        if 'cover_choice' in row:
            row['cover_choice'] = ['manual', '', 'none'][i]
        conn.execute('INSERT INTO tracks (' + ','.join(f'"{k}"' for k in columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', tuple(row[k] for k in columns))
    conn.execute('CREATE TABLE other_data (payload BLOB)')
    conn.execute('INSERT INTO other_data VALUES (?)', (b'\x00\xffpersist',))
    conn.commit()
    return conn


def raw_rows(path, columns=None):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute('SELECT * FROM tracks ORDER BY path')]
    return [{k: row[k] for k in columns} for row in rows] if columns else rows


@pytest.mark.parametrize('variant', ['full', 'no_fingerprint', 'minimal'])
def test_migration_preserves_every_legacy_field(tmp_path, variant):
    db = tmp_path / 'library.sqlite3'
    legacy_database(db, variant=variant).close()
    before = raw_rows(db)
    columns = list(before[0])
    repo = LibraryRepository(db)
    repo.initialize()
    after = raw_rows(db)
    assert len(before) == len(after) == 3
    assert raw_rows(db, columns) == before
    assert len({row['track_id'] for row in after}) == 3
    assert all(UUID(row['track_id']).version == 4 for row in after)
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 1
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT payload FROM other_data').fetchone()[0] == b'\x00\xffpersist'
        pk = [row[1] for row in conn.execute('PRAGMA table_info(tracks)') if row[5]]
        assert pk == ['track_id']
    backups = list((tmp_path / 'migration-backups').glob('*.sqlite3'))
    assert len(backups) == 1
    assert raw_rows(backups[0]) == before
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 0
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    if variant == 'no_fingerprint':
        assert all(row['fingerprint'] is None for row in after)
        assert all(row['fingerprint_duration'] is None for row in after)


def test_uuid_backfill_is_stable_after_reopen_and_retry(tmp_path):
    db = tmp_path / 'library.sqlite3'
    legacy_database(db).close()
    LibraryRepository(db).initialize()
    first = raw_rows(db)
    for _ in range(3):
        LibraryRepository(db).initialize()
        assert raw_rows(db) == first
    assert len(list((tmp_path / 'migration-backups').glob('*.sqlite3'))) == 1


def test_partial_schema_preserves_existing_uuid_and_backfills_only_missing(tmp_path):
    db = tmp_path / 'library.sqlite3'
    conn = legacy_database(db)
    conn.execute('ALTER TABLE tracks ADD COLUMN track_id TEXT')
    existing = str(uuid4())
    conn.execute('UPDATE tracks SET track_id=? WHERE title=?', (existing, 'Ręczny tytuł'))
    conn.commit()
    conn.close()
    LibraryRepository(db).initialize()
    rows = raw_rows(db)
    assert rows[0]['track_id'] == existing
    assert len({row['track_id'] for row in rows}) == 3


def test_columns_migrate_before_dependent_indexes(tmp_path):
    db = tmp_path / 'library.sqlite3'
    legacy_database(db, variant='no_fingerprint').close()
    LibraryRepository(db).initialize()
    with sqlite3.connect(db) as conn:
        assert 'idx_tracks_fingerprint' in {r[1] for r in conn.execute('PRAGMA index_list(tracks)')}
        assert conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0] == 3


def test_migration_failure_restores_original_database_and_retry(tmp_path, monkeypatch):
    from audio_library_organizer.storage import repository
    db = tmp_path / 'library.sqlite3'
    legacy_database(db).close()
    before = raw_rows(db)
    with sqlite3.connect(db) as conn:
        schema = conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
    real_connect = repository.connect

    def deny_drop(path):
        conn = real_connect(path)
        conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_DROP_TABLE else sqlite3.SQLITE_OK)
        return conn

    monkeypatch.setattr(repository, 'connect', deny_drop)
    with pytest.raises(Exception, match='(?i)migrat'):
        LibraryRepository(db).initialize()
    assert raw_rows(db) == before
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 0
        assert conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall() == schema
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        conn.execute('UPDATE tracks SET title=title')
    assert len(list((tmp_path / 'migration-backups').glob('*.sqlite3'))) == 1
    monkeypatch.setattr(repository, 'connect', real_connect)
    LibraryRepository(db).initialize()
    assert raw_rows(db, list(before[0])) == before
    assert len({r['track_id'] for r in raw_rows(db)}) == 3


def test_backup_includes_committed_wal_data(tmp_path):
    db = tmp_path / 'library.sqlite3'
    writer = legacy_database(db, wal=True)
    try:
        before = raw_rows(db)
        assert Path(str(db) + '-wal').is_file()
        LibraryRepository(db).initialize()
        backup = next((tmp_path / 'migration-backups').glob('*.sqlite3'))
        assert raw_rows(backup) == before
    finally:
        writer.close()


def test_backup_failure_does_not_change_database_or_claim_nonexistent_backup(tmp_path):
    db = tmp_path / 'library.sqlite3'
    legacy_database(db).close()
    before = raw_rows(db)
    (tmp_path / 'migration-backups').write_text('blocked directory')
    with pytest.raises(Exception, match='(?i)migrat') as error:
        LibraryRepository(db).initialize()
    assert 'pre-v1-' not in str(error.value)
    assert raw_rows(db) == before
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 0


def test_newer_schema_is_rejected_without_any_changes(tmp_path):
    db = tmp_path / 'library.sqlite3'
    conn = legacy_database(db)
    conn.execute('PRAGMA user_version=99')
    conn.commit()
    conn.close()
    original_bytes = db.read_bytes()
    with pytest.raises(Exception, match='(?i)(newer|unsupported|version)'):
        LibraryRepository(db).initialize()
    assert db.read_bytes() == original_bytes
    assert not (tmp_path / 'migration-backups').exists()


@pytest.mark.parametrize('alteration', [
    'ALTER TABLE tracks ADD COLUMN unknown_payload BLOB',
    'ALTER TABLE tracks ADD COLUMN generated_payload TEXT GENERATED ALWAYS AS (title) VIRTUAL',
    'CREATE UNIQUE INDEX extra_unique_title ON tracks(title)',
    'CREATE TABLE child (parent TEXT REFERENCES TRACKS(path))',
])
def test_custom_schema_is_preserved_or_safely_rejected(tmp_path, alteration):
    db = tmp_path / 'library.sqlite3'
    conn = legacy_database(db)
    conn.execute(alteration)
    conn.commit()
    schema = conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
    conn.close()
    before = raw_rows(db)
    try:
        LibraryRepository(db).initialize()
    except Exception:
        assert raw_rows(db) == before
        with sqlite3.connect(db) as conn:
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 0
            assert conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall() == schema
    else:
        assert raw_rows(db, list(before[0])) == before
        assert len({r['track_id'] for r in raw_rows(db)}) == 3
        with sqlite3.connect(db) as conn:
            current = conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
            for item in schema:
                if item[0] in ('index', 'trigger') and item[2]:
                    assert item in current


def test_custom_index_and_trigger_survive_rebuild(tmp_path):
    db = tmp_path / 'library.sqlite3'
    conn = legacy_database(db)
    conn.executescript("CREATE INDEX extra_artist ON tracks(artist); CREATE TABLE audit (title TEXT); CREATE TRIGGER track_audit AFTER UPDATE OF title ON tracks BEGIN INSERT INTO audit VALUES (new.title); END;")
    conn.close()
    LibraryRepository(db).initialize()
    with sqlite3.connect(db) as conn:
        assert 'extra_artist' in {r[1] for r in conn.execute('PRAGMA index_list(tracks)')}
        conn.execute("UPDATE tracks SET title='changed' WHERE title='Ręczny tytuł'")
        assert conn.execute('SELECT title FROM audit').fetchone()[0] == 'changed'


@pytest.mark.parametrize('value', ['not-a-uuid', 'same-uuid'])
def test_invalid_partial_ids_fail_without_losing_data(tmp_path, value):
    db = tmp_path / 'library.sqlite3'
    conn = legacy_database(db)
    conn.execute('ALTER TABLE tracks ADD COLUMN track_id TEXT')
    conn.execute('UPDATE tracks SET track_id=?', (str(uuid4()) if value == 'same-uuid' else value,))
    conn.commit()
    conn.close()
    before = raw_rows(db)
    with pytest.raises(Exception):
        LibraryRepository(db).initialize()
    assert raw_rows(db) == before
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 0


def test_migration_rejects_disabled_rollback_journal(tmp_path, monkeypatch):
    from audio_library_organizer.storage import repository
    db = tmp_path / 'library.sqlite3'
    legacy_database(db).close()
    before = raw_rows(db)
    real_connect = repository.connect

    def unsafe_connect(path):
        conn = real_connect(path)
        conn.execute('PRAGMA journal_mode=OFF')
        return conn

    monkeypatch.setattr(repository, 'connect', unsafe_connect)
    with pytest.raises(Exception, match='(?i)(journal|rollback)'):
        LibraryRepository(db).initialize()
    assert raw_rows(db) == before
