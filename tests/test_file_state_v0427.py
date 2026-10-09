"""Stage 2.1 contracts: pure facts and disposable SQLite, never user audio.

Managed facts are synthetic inputs, not a resolver, binding or file operation.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import importlib
import importlib.util
from pathlib import Path
import sqlite3
from uuid import UUID

import pytest

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.storage.repository import LibraryRepository
from test_library_migration_v0427 import LEGACY_COLUMNS, legacy_database, raw_rows


TRACK_ID = str(UUID(int=101))
OTHER_ID = str(UUID(int=102))
SOURCE_ID = str(UUID(int=201))
LIBRARY_ID = str(UUID(int=301))
STATES = ('IN_LIBRARY', 'SOURCE_ONLY', 'NEEDS_UPDATE', 'SOURCE_UNAVAILABLE',
          'MANAGED_FILE_MISSING', 'CONFLICT')
STATUSES = ('ready', 'review', 'error', 'duplicate', 'not_selected')


def api():
    # A missing implementation produces an assertion FAIL in the test body,
    # never an import/collection error. Behavioral RED is also recorded after
    # the fact types exist and before confirmed evaluator branches are added.
    name = 'audio_library_organizer.domain.file_state'
    assert importlib.util.find_spec(name) is not None, 'Missing file-state behavior/API'
    return importlib.import_module(name)


def observation(m, availability='PRESENT', *, managed=False, checked_at=10, **changes):
    values = dict(track_id=TRACK_ID, locator='/synthetic/managed.mp3' if managed else '/synthetic/source.mp3',
                  source_id=None if managed else SOURCE_ID,
                  availability=m.FileAvailability[availability], checked_at=checked_at,
                  reason='Synthetic confirmed check', is_current=True)
    values.update(changes)
    return m.FileObservation(**values)


def state_facts(m, state, *, checked_at=10):
    source = observation(m, checked_at=checked_at)
    managed = observation(m, managed=True, checked_at=checked_at)
    common = dict(track_id=TRACK_ID, checked_at=checked_at, source=source,
                  managed_expected=False)
    if state in ('IN_LIBRARY', 'NEEDS_UPDATE', 'MANAGED_FILE_MISSING', 'CONFLICT'):
        common.update(managed_expected=True, managed=managed,
                      ownership=m.Ownership.CONFIRMED, owner_track_id=TRACK_ID,
                      desired=m.OutputSnapshot('synthetic-output', 1, 'desired-A'),
                      applied=m.OutputSnapshot('synthetic-output', 1, 'desired-A'))
    if state == 'NEEDS_UPDATE':
        common['desired'] = m.OutputSnapshot('synthetic-output', 1, 'desired-B')
    elif state == 'MANAGED_FILE_MISSING':
        common['managed'] = replace(managed, availability=m.FileAvailability.MISSING)
    elif state == 'SOURCE_UNAVAILABLE':
        common['source'] = replace(source, availability=m.FileAvailability.MISSING)
    elif state == 'CONFLICT':
        common['conflict'] = m.ConflictReason.TARGET_COLLISION
    return m.FileFacts(**common)


def history(m, facts):
    return replace(facts, last_confirmed_state=m.FileState.IN_LIBRARY, last_confirmed_at=5)


def test_managed_present_works_without_source():
    m = api()
    facts = replace(state_facts(m, 'IN_LIBRARY'),
                    source=observation(m, 'OFFLINE', reason='Volume disconnected'))
    result = m.evaluate_file_state(facts)
    assert result.state == m.FileState.IN_LIBRARY
    assert result.is_confirmed
    assert result.reason == 'MANAGED_CURRENT'


def test_expected_managed_missing_has_priority_over_source_presence():
    m = api()
    result = m.evaluate_file_state(state_facts(m, 'MANAGED_FILE_MISSING'))
    assert result.state == m.FileState.MANAGED_FILE_MISSING
    assert result.is_confirmed
    assert result.reason == 'EXPECTED_MANAGED_MISSING'


def test_unknown_observation_does_not_claim_deletion():
    m = api()
    facts = history(m, replace(state_facts(m, 'IN_LIBRARY'),
                               managed=observation(m, 'UNKNOWN', managed=True)))
    result = m.evaluate_file_state(facts)
    assert result.state == result.last_confirmed_state == m.FileState.IN_LIBRARY
    assert not result.is_confirmed
    assert result.last_confirmed_at == 5
    assert result.checked_at == 10
    assert result.reason == 'MANAGED_UNKNOWN'
    assert result.requires_revalidation
    assert not result.safe_for_file_mutation


@pytest.mark.parametrize('state', STATES)
@pytest.mark.parametrize('status', STATUSES)
def test_file_state_never_changes_metadata_status(state, status):
    m = api()
    track = TrackRecord(Path('/synthetic/source.mp3'), track_id=TRACK_ID, source_id=SOURCE_ID,
                        status=status, title='Ręczny', locked_fields={'title', '__status__'},
                        field_sources={'title': 'Ręcznie'}, original_tags={'title': ['Original']},
                        filename_override='Manual filename', audio_recognition={'keep': [1, 2]})
    before = deepcopy(asdict(track))
    facts = state_facts(m, state)
    result = m.evaluate_file_state(facts)
    assert result.state == m.FileState[state]
    assert asdict(track) == before
    assert result.requires_revalidation
    assert not result.safe_for_file_mutation


@pytest.mark.parametrize(('state', 'reason'), [
    ('IN_LIBRARY', 'MANAGED_CURRENT'), ('SOURCE_ONLY', 'SOURCE_PRESENT'),
    ('NEEDS_UPDATE', 'MANAGED_OUTPUT_CHANGED'), ('SOURCE_UNAVAILABLE', 'SOURCE_MISSING'),
    ('MANAGED_FILE_MISSING', 'EXPECTED_MANAGED_MISSING'), ('CONFLICT', 'TARGET_COLLISION'),
])
def test_six_state_table(state, reason):
    m = api()
    assert {item.name for item in m.FileState} == set(STATES)
    result = m.evaluate_file_state(state_facts(m, state))
    assert result.state == m.FileState[state]
    assert result.is_confirmed
    assert result.reason == reason
    assert result.last_confirmed_state == result.state
    assert result.last_confirmed_at == 10


@pytest.mark.parametrize('state', ['IN_LIBRARY', 'MANAGED_FILE_MISSING', 'NEEDS_UPDATE'])
@pytest.mark.parametrize('reason', ['AMBIGUOUS_OWNERSHIP', 'MULTIPLE_OWNERS',
                                   'TARGET_COLLISION', 'CONTRADICTORY_FACTS'])
def test_positive_conflict_has_priority(state, reason):
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, state), conflict=m.ConflictReason[reason]))
    assert result.state == m.FileState.CONFLICT
    assert result.is_confirmed
    assert result.reason == reason


def test_confirmed_different_owner_is_conflict_even_when_expected_file_missing():
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, 'MANAGED_FILE_MISSING'), owner_track_id=OTHER_ID))
    assert result.state == m.FileState.CONFLICT
    assert result.is_confirmed
    assert result.reason == 'OWNER_MISMATCH'


def test_confirmed_owned_output_contradicts_confirmed_no_managed_expectation():
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, 'IN_LIBRARY'), managed_expected=False))
    assert result.state == m.FileState.CONFLICT
    assert result.reason == 'CONTRADICTORY_FACTS'


def test_missing_expected_file_needs_no_current_ownership_probe_of_absent_file():
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, 'MANAGED_FILE_MISSING'),
                                           ownership=m.Ownership.UNKNOWN, owner_track_id=None,
                                           desired=None, applied=None))
    assert result.is_confirmed
    assert result.state == m.FileState.MANAGED_FILE_MISSING


@pytest.mark.parametrize('availability', ['UNKNOWN', 'OFFLINE', 'ERROR'])
@pytest.mark.parametrize('managed', [False, True])
def test_inconclusive_availability_never_claims_missing_or_conflict(availability, managed):
    m = api()
    facts = state_facts(m, 'IN_LIBRARY' if managed else 'SOURCE_ONLY')
    field = 'managed' if managed else 'source'
    facts = history(m, replace(facts, **{field: observation(m, availability, managed=managed,
                                                          reason='Permission denied / incomplete check')}))
    result = m.evaluate_file_state(facts)
    assert result.state == m.FileState.IN_LIBRARY
    assert not result.is_confirmed
    assert result.reason == ('MANAGED_' if managed else 'SOURCE_') + availability
    assert not result.safe_for_file_mutation


@pytest.mark.parametrize('managed', [False, True])
def test_stale_absence_is_not_proof_of_deletion(managed):
    m = api()
    facts = state_facts(m, 'MANAGED_FILE_MISSING' if managed else 'SOURCE_UNAVAILABLE')
    field = 'managed' if managed else 'source'
    facts = history(m, replace(facts, **{field: replace(getattr(facts, field), is_current=False)}))
    result = m.evaluate_file_state(facts)
    assert result.state == m.FileState.IN_LIBRARY
    assert not result.is_confirmed
    assert result.reason == ('STALE_MANAGED_OBSERVATION' if managed else 'STALE_SOURCE_OBSERVATION')


def test_stale_conflict_is_not_reconfirmed():
    m = api()
    result = m.evaluate_file_state(history(m, replace(state_facts(m, 'CONFLICT'), is_current=False)))
    assert result.state == m.FileState.IN_LIBRARY
    assert not result.is_confirmed
    assert result.reason == 'STALE_FACTS'


@pytest.mark.parametrize('missing', ['desired', 'applied', 'both'])
def test_unknown_snapshot_does_not_claim_current_or_changed_output(missing):
    m = api()
    changes = {name: None for name in ('desired', 'applied') if missing in (name, 'both')}
    result = m.evaluate_file_state(history(m, replace(state_facts(m, 'IN_LIBRARY'), **changes)))
    assert result.state == m.FileState.IN_LIBRARY
    assert not result.is_confirmed
    assert result.reason == 'OUTPUT_SNAPSHOT_UNKNOWN'


@pytest.mark.parametrize(('namespace', 'version'), [('different-output', 1), ('synthetic-output', 2)])
def test_incomparable_snapshot_is_not_equality_or_dirty(namespace, version):
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, 'IN_LIBRARY'),
                                           applied=m.OutputSnapshot(namespace, version, 'desired-A')))
    assert result.state is None
    assert not result.is_confirmed
    assert result.reason == 'OUTPUT_SNAPSHOT_INCOMPARABLE'


def test_unknown_owner_is_unresolved_even_with_same_name_and_matching_snapshots():
    m = api()
    facts = replace(state_facts(m, 'IN_LIBRARY'), ownership=m.Ownership.UNKNOWN,
                    owner_track_id=TRACK_ID)
    result = m.evaluate_file_state(facts)
    assert result.state is None
    assert result.reason == 'OWNERSHIP_UNCONFIRMED'
    assert not result.is_confirmed


def test_positive_ambiguous_ownership_is_a_concrete_conflict():
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, 'IN_LIBRARY'), ownership=m.Ownership.AMBIGUOUS))
    assert result.state == m.FileState.CONFLICT
    assert result.reason == 'AMBIGUOUS_OWNERSHIP'


def test_unknown_managed_expectation_is_not_source_only():
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, 'SOURCE_ONLY'), managed_expected=None))
    assert result.state is None
    assert result.reason == 'MANAGED_EXPECTATION_UNKNOWN'


@pytest.mark.parametrize(('state', 'field', 'reason'), [
    ('SOURCE_ONLY', 'source', 'SOURCE_UNOBSERVED'),
    ('IN_LIBRARY', 'managed', 'MANAGED_UNOBSERVED'),
])
def test_unobserved_file_without_last_state_remains_unresolved(state, field, reason):
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, state), **{field: None}))
    assert result.state is None
    assert result.last_confirmed_state is None
    assert not result.is_confirmed
    assert result.reason == reason


def test_observation_for_another_record_is_not_accepted_as_evidence():
    m = api()
    result = m.evaluate_file_state(replace(state_facts(m, 'IN_LIBRARY'),
                                           managed=observation(m, 'MISSING', managed=True, track_id=OTHER_ID)))
    assert result.state is None
    assert not result.is_confirmed
    assert result.reason == 'OBSERVATION_IDENTITY_MISMATCH'


def test_evaluator_is_deterministic_and_performs_no_io(monkeypatch):
    m = api()
    facts = [state_facts(m, state) for state in STATES]
    facts.append(history(m, replace(facts[0], managed=observation(m, 'ERROR', managed=True))))
    before = deepcopy(facts)
    import builtins
    import hashlib
    import os
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail('Pure evaluator attempted I/O or file hashing')

    with monkeypatch.context() as guard:
        for name in ('stat', 'exists', 'is_file', 'resolve', 'open', 'unlink', 'mkdir'):
            guard.setattr(Path, name, forbidden)
        for name in ('stat', 'open', 'remove', 'rename'):
            guard.setattr(os, name, forbidden)
        guard.setattr(builtins, 'open', forbidden)
        guard.setattr(sqlite3, 'connect', forbidden)
        guard.setattr(socket, 'socket', forbidden)
        guard.setattr(hashlib, 'sha256', forbidden)
        assert [m.evaluate_file_state(f) for f in facts] == [m.evaluate_file_state(f) for f in facts]
    assert facts == before


@pytest.mark.parametrize('available', [True, False])
def test_legacy_file_health_availability_is_not_confirmed_evidence(available, monkeypatch):
    m = api()
    from audio_library_organizer.jobs import file_health
    adapter = getattr(file_health, 'source_observation_from_track', None)
    assert callable(adapter), 'Missing no-I/O legacy observation adapter'
    track = TrackRecord(Path('/offline/music.mp3'), track_id=TRACK_ID, source_id=SOURCE_ID,
                        is_available=available, artist='Manual', title='Manual', status='ready')
    before = deepcopy(asdict(track))
    with monkeypatch.context() as guard:
        guard.setattr(Path, 'is_file', lambda *a: pytest.fail('Adapter inspected audio filesystem'))
        guard.setattr(Path, 'resolve', lambda *a: pytest.fail('Adapter resolved a locator'))
        obs = adapter(track, checked_at=10)
        facts = m.FileFacts(TRACK_ID, 10, source=obs, managed_expected=False)
        result = m.evaluate_file_state(facts)
        assert file_health.file_health_reasons(track, check_filesystem=False)
    assert obs.availability == m.FileAvailability.UNKNOWN
    assert obs.reason == 'LEGACY_AVAILABILITY_UNCONFIRMED'
    assert not result.is_confirmed
    assert result.state is None
    assert asdict(track) == before


def frozen_v2_database(path, *, wal=False):
    """Frozen v2 SQL/identities; independent of the new migrator/cache schema."""
    conn = legacy_database(path, wal=wal)
    columns = dict(LEGACY_COLUMNS)
    columns['path'] = 'TEXT NOT NULL UNIQUE'
    conn.execute('ALTER TABLE tracks RENAME TO old_tracks')
    conn.execute('''CREATE TABLE library_metadata (
        singleton INTEGER NOT NULL PRIMARY KEY CHECK(singleton=1),
        library_id TEXT NOT NULL UNIQUE,
        sources_initialized INTEGER NOT NULL DEFAULT 0 CHECK(sources_initialized IN (0,1)))''')
    conn.execute('INSERT INTO library_metadata VALUES (1,?,1)', (LIBRARY_ID,))
    conn.execute('''CREATE TABLE sources (
        source_id TEXT NOT NULL PRIMARY KEY,
        library_id TEXT NOT NULL REFERENCES library_metadata(library_id),
        root_path TEXT NOT NULL, canonical_root_key TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), UNIQUE(library_id,canonical_root_key))''')
    source = str(path.parent / 'synthetic-source')
    conn.execute('INSERT INTO sources VALUES (?,?,?,?,0)', (SOURCE_ID, LIBRARY_ID, source, 'posix:' + source))
    conn.execute('CREATE TABLE tracks (track_id TEXT NOT NULL PRIMARY KEY,' +
                 ','.join(f'"{key}" {value}' for key, value in columns.items()) + ''',
                 source_id TEXT REFERENCES sources(source_id),
                 source_relative_path TEXT CHECK((source_id IS NULL AND source_relative_path IS NULL) OR
                    (source_id IS NOT NULL AND source_relative_path IS NOT NULL)),
                 path_key TEXT NOT NULL DEFAULT '')''')
    names = ','.join(f'"{key}"' for key in columns)
    for i, row in enumerate(conn.execute(f'SELECT {names} FROM old_tracks ORDER BY path').fetchall(), 1):
        row = list(row)
        row[list(columns).index('path')] = f'{source}/song-{i}.mp3'
        conn.execute(f'INSERT INTO tracks (track_id,{names},source_id,source_relative_path,path_key) VALUES (' +
                     ','.join('?' for _ in range(len(columns) + 4)) + ')',
                     (str(UUID(int=i)), *row, SOURCE_ID, f'song-{i}.mp3', 'posix:' + row[0]))
    conn.execute('DROP TABLE old_tracks')
    conn.execute('CREATE INDEX idx_tracks_path_key ON tracks(path_key)')
    conn.execute('CREATE INDEX idx_tracks_source_id ON tracks(source_id)')
    conn.execute('CREATE INDEX custom_artist ON tracks(artist)')
    conn.execute('CREATE TABLE custom_audit (title TEXT)')
    conn.execute('''CREATE TRIGGER custom_update AFTER UPDATE OF title ON tracks
                    BEGIN INSERT INTO custom_audit VALUES (new.title); END''')
    conn.execute('PRAGMA user_version=2')
    conn.commit()
    return conn


def raw_table(path, table):
    with sqlite3.connect(path) as conn:
        return conn.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()


def test_v2_migration_adds_cache_without_changing_any_existing_data(tmp_path):
    db = tmp_path / 'library.sqlite3'
    frozen_v2_database(db).close()
    tables = ('tracks', 'sources', 'library_metadata', 'other_data', 'custom_audit')
    before = {table: raw_table(db, table) for table in tables}
    with sqlite3.connect(db) as conn:
        schema = conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
    repo = LibraryRepository(db)
    repo.initialize()
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 3, 'No durable v2→v3 file-state migration'
        assert conn.execute('SELECT COUNT(*) FROM file_state_cache').fetchone()[0] == 0
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        current = conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
        assert all(item in current for item in schema)
    assert {table: raw_table(db, table) for table in tables} == before
    backup = list((tmp_path / 'migration-backups').glob('pre-v3-*.sqlite3'))
    assert len(backup) == 1
    assert {table: raw_table(backup[0], table) for table in tables} == before
    with sqlite3.connect(backup[0]) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    for _ in range(3):
        LibraryRepository(db).initialize()
        assert repo.library_id == LIBRARY_ID
        assert {table: raw_table(db, table) for table in tables} == before
    assert len(list((tmp_path / 'migration-backups').glob('*.sqlite3'))) == 1


def test_v2_migration_failure_after_ddl_rolls_back_and_retry_preserves_ids(tmp_path, monkeypatch):
    from audio_library_organizer.storage import repository as module
    db = tmp_path / 'library.sqlite3'
    frozen_v2_database(db).close()
    before = raw_rows(db)
    with sqlite3.connect(db) as conn:
        schema = conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
    real_connect = module.connect

    def deny_version_commit(path):
        conn = real_connect(path)
        conn.set_authorizer(lambda action, name, value, *_: sqlite3.SQLITE_DENY
                            if action == sqlite3.SQLITE_PRAGMA and name == 'user_version' and value is not None
                            else sqlite3.SQLITE_OK)
        return conn

    monkeypatch.setattr(module, 'connect', deny_version_commit)
    with pytest.raises(Exception, match='(?i)migrat'):
        LibraryRepository(db).initialize()
    assert raw_rows(db) == before
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
        assert conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall() == schema
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    backup = next((tmp_path / 'migration-backups').glob('pre-v3-*.sqlite3'))
    assert raw_rows(backup) == before
    monkeypatch.setattr(module, 'connect', real_connect)
    LibraryRepository(db).initialize()
    assert raw_rows(db) == before
    assert LibraryRepository(db).library_id == LIBRARY_ID


def test_v2_backup_includes_committed_wal_data(tmp_path):
    db = tmp_path / 'library.sqlite3'
    writer = frozen_v2_database(db, wal=True)
    try:
        writer.execute("UPDATE tracks SET title='Ręczny tytuł WAL'")
        writer.commit()
        before = raw_rows(db)
        assert Path(str(db) + '-wal').is_file()
        LibraryRepository(db).initialize()
        backup = list((tmp_path / 'migration-backups').glob('pre-v3-*.sqlite3'))
        assert len(backup) == 1, 'No pre-v3 SQLite backup'
        assert raw_rows(backup[0]) == before == raw_rows(db)
    finally:
        writer.close()


def cache_repo(tmp_path):
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    track = TrackRecord(tmp_path / 'source' / 'song.mp3', track_id=TRACK_ID,
                        title='Ręczny', status='ready', filename_override='Manual',
                        locked_fields={'title'}, field_sources={'title': 'Ręcznie'},
                        original_tags={'title': ['Original']}, audio_recognition={'keep': [1, 2]})
    repo.register_source(tmp_path / 'source')
    repo.upsert_track(track)
    return repo, track


def repo_facts(m, track, state='IN_LIBRARY', *, checked_at=10):
    facts = state_facts(m, state, checked_at=checked_at)
    return replace(facts, source=replace(facts.source, locator=str(track.path), source_id=track.source_id))


def save(repo, facts):
    method = getattr(repo, 'save_file_facts', None)
    assert callable(method), 'Missing atomic file-state observation persistence'
    return method(facts)


def read(repo, track_id):
    method = getattr(repo, 'get_file_state', None)
    assert callable(method), 'Missing read-only file-state cache'
    return method(track_id)


def test_restart_retains_confirmed_state_and_latest_offline_observation(tmp_path):
    m = api()
    repo, track = cache_repo(tmp_path)
    before = raw_rows(repo.database_path)
    first = save(repo, repo_facts(m, track))
    assert first.state == m.FileState.IN_LIBRARY and first.is_confirmed
    later = repo_facts(m, track, checked_at=20)
    later = replace(later, managed=replace(later.managed, availability=m.FileAvailability.OFFLINE,
                                           reason='Unplugged volume'))
    result = save(repo, later)
    assert result.state == m.FileState.IN_LIBRARY
    assert not result.is_confirmed
    assert result.last_confirmed_at == 10
    for _ in range(3):
        reopened = LibraryRepository(repo.database_path)
        reopened.initialize()
        cached = read(reopened, TRACK_ID)
        assert cached.evaluation.state == m.FileState.IN_LIBRARY
        assert cached.evaluation.last_confirmed_at == 10
        assert cached.evaluation.checked_at == 20
        assert not cached.evaluation.is_confirmed
        assert cached.evaluation.requires_revalidation
        assert not cached.evaluation.safe_for_file_mutation
        assert cached.facts.managed.availability == m.FileAvailability.OFFLINE
        assert cached.facts.managed.reason == 'Unplugged volume'
        assert cached.facts.managed.checked_at == 20
        assert cached.last_confirmed_reason == 'MANAGED_CURRENT'
        assert raw_rows(repo.database_path) == before


def test_cache_without_any_confirmed_state_does_not_invent_one(tmp_path):
    m = api()
    repo, track = cache_repo(tmp_path)
    facts = repo_facts(m, track, 'SOURCE_ONLY')
    facts = replace(facts, source=replace(facts.source, availability=m.FileAvailability.ERROR,
                                         reason='Permission denied'))
    assert save(repo, facts).state is None
    cached = read(LibraryRepository(repo.database_path), TRACK_ID)
    assert cached.evaluation.state is None
    assert cached.evaluation.last_confirmed_at is None
    assert cached.facts.source.reason == 'Permission denied'


@pytest.mark.parametrize('state', STATES)
@pytest.mark.parametrize('status', STATUSES)
def test_cache_observation_writes_never_change_metadata_or_source_ids(tmp_path, state, status):
    m = api()
    repo, track = cache_repo(tmp_path)
    track.status = status
    repo.upsert_track(track)
    before = raw_rows(repo.database_path)
    sources = raw_table(repo.database_path, 'sources')
    library = raw_table(repo.database_path, 'library_metadata')
    assert save(repo, repo_facts(m, track, state)).state == m.FileState[state]
    assert read(repo, TRACK_ID).evaluation.state == m.FileState[state]
    assert raw_rows(repo.database_path) == before
    assert raw_table(repo.database_path, 'sources') == sources
    assert raw_table(repo.database_path, 'library_metadata') == library


def test_cached_confirmed_state_is_historical_and_reads_do_not_write(tmp_path, monkeypatch):
    m = api()
    repo, track = cache_repo(tmp_path)
    save(repo, repo_facts(m, track))
    from audio_library_organizer.storage import repository as module
    real_connect = module.connect
    statements = []

    def trace(path):
        conn = real_connect(path)
        conn.set_trace_callback(statements.append)
        return conn

    before = repo.database_path.read_bytes()
    monkeypatch.setattr(module, 'connect', trace)
    for _ in range(4):
        result = read(repo, TRACK_ID).evaluation
        assert result.state == m.FileState.IN_LIBRARY
        assert not result.is_confirmed
        assert result.reason == 'CACHE_REQUIRES_REVALIDATION'
        assert result.requires_revalidation
        assert not result.safe_for_file_mutation
    assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER')) for s in statements)
    assert repo.database_path.read_bytes() == before


def test_cache_ignores_caller_supplied_history_and_uses_durable_history(tmp_path):
    m = api()
    repo, track = cache_repo(tmp_path)
    facts = history(m, repo_facts(m, track, 'SOURCE_ONLY'))
    facts = replace(facts, source=replace(facts.source, availability=m.FileAvailability.UNKNOWN))
    result = save(repo, facts)
    assert result.state is None
    assert result.last_confirmed_at is None


@pytest.mark.parametrize('kind', ['whole_facts', 'managed_observation', 'source_observation', 'equal_changed'])
def test_delayed_or_conflicting_observations_cannot_roll_back_cache(tmp_path, kind):
    m = api()
    repo, track = cache_repo(tmp_path)
    current = repo_facts(m, track, checked_at=20)
    save(repo, current)
    before = raw_table(repo.database_path, 'file_state_cache')
    old = repo_facts(m, track, 'MANAGED_FILE_MISSING', checked_at=30)
    if kind == 'whole_facts':
        old = repo_facts(m, track, 'MANAGED_FILE_MISSING', checked_at=10)
    elif kind == 'managed_observation':
        old = replace(old, managed=replace(old.managed, checked_at=10))
    elif kind == 'source_observation':
        old = replace(old, source=replace(old.source, checked_at=10))
    else:
        old = repo_facts(m, track, 'MANAGED_FILE_MISSING', checked_at=20)
    with pytest.raises(ValueError, match='(?i)stale|conflict|older'):
        save(repo, old)
    assert raw_table(repo.database_path, 'file_state_cache') == before
    assert read(repo, TRACK_ID).evaluation.state == m.FileState.IN_LIBRARY


def test_identical_observation_retry_does_not_write_again(tmp_path, monkeypatch):
    m = api()
    repo, track = cache_repo(tmp_path)
    facts = repo_facts(m, track)
    expected = save(repo, facts)
    from audio_library_organizer.storage import repository as module
    real_connect = module.connect
    statements = []

    def trace(path):
        conn = real_connect(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(module, 'connect', trace)
    assert save(repo, facts) == expected
    assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for s in statements)


@pytest.mark.parametrize('change', ['path', 'source_id', 'track_id'])
def test_stale_binding_observation_cannot_update_cache(tmp_path, change):
    m = api()
    repo, track = cache_repo(tmp_path)
    facts = repo_facts(m, track)
    if change == 'track_id':
        facts = replace(facts, source=replace(facts.source, track_id=OTHER_ID))
    else:
        field = 'locator' if change == 'path' else 'source_id'
        facts = replace(facts, source=replace(facts.source, **{field: '/another/track.mp3' if change == 'path' else OTHER_ID}))
    with pytest.raises(ValueError, match='(?i)identity|locator|source|binding'):
        save(repo, facts)
    assert raw_table(repo.database_path, 'file_state_cache') == []


@pytest.mark.parametrize('source_observed', [True, False])
def test_locator_change_keeps_history_but_invalidates_cached_evidence(tmp_path, source_observed):
    m = api()
    repo, track = cache_repo(tmp_path)
    facts = repo_facts(m, track)
    save(repo, facts if source_observed else replace(facts, source=None))
    before = raw_table(repo.database_path, 'file_state_cache')
    track.path = tmp_path / 'different' / 'song.mp3'
    repo.upsert_track(track)
    cached = read(repo, TRACK_ID)
    assert cached.evaluation.state == m.FileState.IN_LIBRARY
    assert not cached.evaluation.is_confirmed
    assert cached.evaluation.reason == 'TRACK_BINDING_CHANGED'
    assert raw_table(repo.database_path, 'file_state_cache') == before


def test_cache_transaction_failure_preserves_observation_history_and_metadata(tmp_path):
    m = api()
    repo, track = cache_repo(tmp_path)
    save(repo, repo_facts(m, track))
    before = raw_table(repo.database_path, 'file_state_cache')
    metadata = raw_rows(repo.database_path)
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('''CREATE TRIGGER fail_cache BEFORE UPDATE ON file_state_cache
                        BEGIN SELECT RAISE(ABORT, 'injected cache transaction failure'); END''')
    with pytest.raises(sqlite3.DatabaseError, match='injected'):
        save(repo, repo_facts(m, track, 'NEEDS_UPDATE', checked_at=20))
    assert raw_table(repo.database_path, 'file_state_cache') == before
    assert raw_rows(repo.database_path) == metadata
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('DROP TRIGGER fail_cache')
    assert save(repo, repo_facts(m, track, 'NEEDS_UPDATE', checked_at=20)).state == m.FileState.NEEDS_UPDATE


@pytest.mark.parametrize('payload', ['{bad json', '{"version": 999}', '{"version": 1, "facts": {"managed_expected": "false"}}'])
def test_corrupt_optional_cache_is_preserved_and_track_reads_still_work(tmp_path, payload):
    m = api()
    repo, track = cache_repo(tmp_path)
    save(repo, repo_facts(m, track))
    from audio_library_organizer.storage.file_state_cache import FileStateCacheError
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('UPDATE file_state_cache SET facts_json=?', (payload,))
    before = raw_table(repo.database_path, 'file_state_cache')
    LibraryRepository(repo.database_path).initialize()
    assert repo.get_track(TRACK_ID).title == 'Ręczny'
    with pytest.raises(FileStateCacheError):
        read(repo, TRACK_ID)
    with pytest.raises(FileStateCacheError):
        save(repo, repo_facts(m, track, checked_at=20))
    assert raw_table(repo.database_path, 'file_state_cache') == before


def test_read_failure_never_clears_last_confirmed_state(tmp_path, monkeypatch):
    m = api()
    repo, track = cache_repo(tmp_path)
    save(repo, repo_facts(m, track))
    before = raw_table(repo.database_path, 'file_state_cache')
    from audio_library_organizer.storage import repository as module
    real_connect = module.connect

    def deny_read(path):
        conn = real_connect(path)
        conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ else sqlite3.SQLITE_OK)
        return conn

    monkeypatch.setattr(module, 'connect', deny_read)
    with pytest.raises(sqlite3.DatabaseError):
        read(repo, TRACK_ID)
    monkeypatch.setattr(module, 'connect', real_connect)
    assert raw_table(repo.database_path, 'file_state_cache') == before
    assert read(repo, TRACK_ID).evaluation.state == m.FileState.IN_LIBRARY


def test_newer_schema_blocks_cache_writer_without_changes(tmp_path):
    m = api()
    repo, track = cache_repo(tmp_path)
    save(repo, repo_facts(m, track))
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('PRAGMA user_version=4')
    before = repo.database_path.read_bytes()
    with pytest.raises(ValueError, match='(?i)schema|version|unsupported'):
        save(repo, repo_facts(m, track, checked_at=20))
    with pytest.raises(Exception, match='(?i)newer|unsupported|version'):
        repo.initialize()
    assert repo.database_path.read_bytes() == before


def test_file_state_cache_is_isolated_between_libraries(tmp_path):
    m = api()
    first, a = cache_repo(tmp_path / 'first')
    second, b = cache_repo(tmp_path / 'second')
    save(first, repo_facts(m, a, 'IN_LIBRARY'))
    save(second, repo_facts(m, b, 'SOURCE_UNAVAILABLE'))
    assert first.library_id != second.library_id
    assert a.source_id != b.source_id
    assert read(first, TRACK_ID).evaluation.state == m.FileState.IN_LIBRARY
    assert read(second, TRACK_ID).evaluation.state == m.FileState.SOURCE_UNAVAILABLE


def test_unknown_track_has_no_cache_and_cannot_acquire_one(tmp_path):
    m = api()
    repo = LibraryRepository(tmp_path / 'library.sqlite3')
    repo.initialize()
    assert read(repo, TRACK_ID) is None
    with pytest.raises(ValueError, match='(?i)track|record|unknown'):
        save(repo, state_facts(m, 'IN_LIBRARY'))
    assert raw_table(repo.database_path, 'file_state_cache') == []


@pytest.mark.parametrize('field', ['checked_at', 'managed_expected', 'is_current'])
def test_malformed_facts_cannot_be_interpreted_as_confirmed(field):
    m = api()
    facts = state_facts(m, 'SOURCE_ONLY')
    wrong = {'checked_at': -1, 'managed_expected': 'false', 'is_current': 1}[field]
    with pytest.raises(ValueError):
        replace(facts, **{field: wrong})


def test_future_observation_and_incomplete_history_are_rejected():
    m = api()
    with pytest.raises(ValueError, match='(?i)time|observation'):
        replace(state_facts(m, 'SOURCE_ONLY'), source=observation(m, checked_at=11))
    with pytest.raises(ValueError, match='(?i)confirm|history'):
        replace(state_facts(m, 'SOURCE_ONLY'), last_confirmed_state=m.FileState.IN_LIBRARY)


@pytest.mark.parametrize('component', ['source', 'managed'])
@pytest.mark.parametrize('delayed_at', [10, 20])
def test_observation_gap_preserves_ordering_watermark_across_restart(tmp_path, component, delayed_at):
    """Important R1: None must not let old/equal contradictory absence win."""
    m = api()
    repo, track = cache_repo(tmp_path)
    state = 'IN_LIBRARY' if component == 'managed' else 'SOURCE_ONLY'
    initial = repo_facts(m, track, state, checked_at=20)
    save(repo, initial)
    gap = replace(repo_facts(m, track, state, checked_at=30), **{component: None})
    result = save(repo, gap)
    assert not result.is_confirmed
    assert result.state == m.FileState[state]
    assert result.last_confirmed_at == 20
    reopened = LibraryRepository(repo.database_path)
    reopened.initialize()
    absent = repo_facts(m, track, 'MANAGED_FILE_MISSING' if component == 'managed' else 'SOURCE_UNAVAILABLE', checked_at=40)
    absent = replace(absent, **{component: replace(getattr(absent, component), checked_at=delayed_at)})
    before = raw_table(repo.database_path, 'file_state_cache')
    with pytest.raises(ValueError, match='(?i)stale|older|conflict'):
        save(reopened, absent)
    assert raw_table(repo.database_path, 'file_state_cache') == before
    assert read(reopened, TRACK_ID).evaluation.state == m.FileState[state]


@pytest.mark.parametrize('component', ['source', 'managed'])
def test_fresh_observation_after_gap_can_confirm_new_state(tmp_path, component):
    m = api()
    repo, track = cache_repo(tmp_path)
    state = 'IN_LIBRARY' if component == 'managed' else 'SOURCE_ONLY'
    save(repo, repo_facts(m, track, state, checked_at=20))
    save(repo, replace(repo_facts(m, track, state, checked_at=30), **{component: None}))
    absent_state = 'MANAGED_FILE_MISSING' if component == 'managed' else 'SOURCE_UNAVAILABLE'
    result = save(LibraryRepository(repo.database_path), repo_facts(m, track, absent_state, checked_at=40))
    assert result.is_confirmed
    assert result.state == m.FileState[absent_state]
    assert result.last_confirmed_at == 40


def test_cached_facts_cannot_be_reconfirmed_without_fresh_check(tmp_path):
    """Read-time uncertainty travels with the facts, not just the presentation."""
    m = api()
    repo, track = cache_repo(tmp_path)
    save(repo, repo_facts(m, track, checked_at=20))
    cached = read(LibraryRepository(repo.database_path), TRACK_ID)
    assert not cached.evaluation.is_confirmed
    reevaluated = m.evaluate_file_state(cached.facts)
    assert not reevaluated.is_confirmed, 'Historical cached facts were exposed as current evidence'
    assert reevaluated.state == m.FileState.IN_LIBRARY
    assert reevaluated.last_confirmed_at == 20
    assert not reevaluated.safe_for_file_mutation
