"""The SQLite ownership boundary for real producer and adoption operations."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from audio_adoption_fixtures import copy_audio, mp3_samples
from audio_library_organizer.audio import identity
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs import created_output, legacy_adoption
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.ui.workers import ExportWorker
from test_export_preflight_v0427 import preflight
from test_legacy_adoption_v0427 import inventory, library


WINDOWS_DEVICE = 13418630465436060951
HIGH_BIT = 1 << 63
MODULUS = 1 << 64


@pytest.fixture
def large_file_ids(monkeypatch):
    original = identity.stat_identity

    def observed(info):
        _, inode, *rest = original(info)
        return WINDOWS_DEVICE, inode | HIGH_BIT, *rest

    # Supply the same observed IDs at every stat-token boundary. All MP3, Qt
    # worker, database transactions and no-follow filesystem checks stay real.
    for module in (identity, created_output, legacy_adoption):
        monkeypatch.setattr(module, 'stat_identity', observed)
    return observed


def assert_binding_round_trip(repo, track_id, output, expected):
    reopened = LibraryRepository(repo.database_path)
    reopened.initialize()
    binding = next(b for b in reopened.list_managed_bindings() if b.track_id == track_id)
    assert binding.stat_identity == expected
    assert binding.expected_sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    assert binding.audio_digest == identity.inspect_audio(output).audio_digest
    with sqlite3.connect(repo.database_path) as conn:
        dev, ino, token = conn.execute(
            'SELECT device,inode,stat_json FROM managed_bindings WHERE track_id=?', (track_id,)).fetchone()
        assert (dev, ino) == tuple(value - MODULUS if value >= HIGH_BIT else value for value in expected[:2])
        assert tuple(json.loads(token)) == expected
        assert conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    return binding


def test_producer_registers_large_device_and_inode(preflight, large_file_ids):
    _, repo, _, worker, results, errors, _ = preflight
    worker.run()
    assert not errors and len(results) == 1
    result = results[0]
    assert result.created == 2, result.errors
    tracks = {track.path: track for track in repo.list_tracks()}
    for outcome in result.outcomes:
        track = tracks[outcome.source]
        assert_binding_round_trip(repo, track.track_id, outcome.destination,
                                  large_file_ids(outcome.destination.stat()))


def test_adoption_registers_large_device_and_inode(library, large_file_ids):
    repo, root, track, output = library
    proposal = inventory(library).proposals[0]
    assert proposal.status == 'CANDIDATE' and not repo.list_managed_bindings()
    with pytest.raises(ValueError, match='confirmation'):
        legacy_adoption.adopt_legacy_output(repo, proposal.proposal_id, confirmed=False, library_root=root)
    saved = legacy_adoption.adopt_legacy_output(repo, proposal.proposal_id, confirmed=True, library_root=root)
    assert saved == assert_binding_round_trip(repo, track.track_id, output, large_file_ids(output.stat()))
    with pytest.raises(ValueError):
        legacy_adoption.adopt_legacy_output(repo, proposal.proposal_id, confirmed=True, library_root=root)
    assert repo.list_managed_bindings() == (saved,)


def test_known_missing_locator_still_reserves_physical_file(library, tmp_path, large_file_ids):
    owner, owner_root, track, output = library
    proposal = inventory(library).proposals[0]
    saved = legacy_adoption.adopt_legacy_output(owner, proposal.proposal_id, confirmed=True, library_root=owner_root)

    other_root = tmp_path / 'other-library'
    other = LibraryRepository(other_root / '.alo' / 'library.sqlite3')
    other.initialize()
    other.bootstrap_sources([track.path.parent])
    replacement = TrackRecord(path=track.path, size_bytes=track.size_bytes, mtime_ns=track.mtime_ns,
                              sha256=track.sha256, artist=track.artist, title=track.title, status='duplicate')
    other.upsert_track(replacement)
    target = other_root / 'GOTOWE' / output.name
    target.parent.mkdir()
    output.rename(target)
    assert not output.exists() and large_file_ids(target.stat())[:2] == saved.stat_identity[:2]

    known = legacy_adoption.KnownLibrary(str(owner_root), str(owner.database_path), owner.library_id)
    report = legacy_adoption.inventory_legacy_outputs(other, library_root=other_root, known_libraries=(known,))
    assert report.proposals[0].status == 'CONFLICT'
    assert not report.proposals[0].can_adopt and not other.list_managed_bindings()
    assert owner.list_managed_bindings() == (saved,)


@pytest.mark.parametrize('raw', [0, 1, HIGH_BIT - 1, HIGH_BIT, MODULUS - 1, WINDOWS_DEVICE])
def test_sqlite_file_id_boundaries_are_lossless_and_unique(raw):
    from audio_library_organizer.storage.managed_bindings import binding_stat_identity, sqlite_file_ids

    values = [0, 1, HIGH_BIT - 1, HIGH_BIT, MODULUS - 1, WINDOWS_DEVICE]
    other = values[(values.index(raw) + 1) % len(values)]
    device, inode = sqlite_file_ids(raw, other)
    assert -(1 << 63) <= device < HIGH_BIT and -(1 << 63) <= inode < HIGH_BIT
    assert len({sqlite_file_ids(value, 1)[0] for value in values}) == len(values)
    token = (raw, other, 3, 4, 5, 1)
    with sqlite3.connect(':memory:') as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE proof(device INTEGER, inode INTEGER, stat_json TEXT, UNIQUE(device,inode))')
        conn.execute('INSERT INTO proof VALUES (?, ?, ?)', (device, inode, json.dumps(token)))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('INSERT INTO proof VALUES (?, ?, ?)', (device, inode, json.dumps(token)))
        assert binding_stat_identity(conn.execute('SELECT * FROM proof').fetchone()) == token


@pytest.mark.parametrize('bad', [-1, -HIGH_BIT, MODULUS, MODULUS + 1, True, '1', 1.0, None])
def test_rejects_invalid_raw_identifiers(bad):
    from audio_library_organizer.storage.managed_bindings import sqlite_file_ids

    for pair in ((bad, 1), (1, bad)):
        with pytest.raises(ValueError, match='Unsupported physical file identifier'):
            sqlite_file_ids(*pair)


@pytest.mark.parametrize('device,raw', [(-1, -1), (-1, MODULUS), (1, MODULUS - 1), ('x', 1), (1, True)])
def test_rejects_corrupt_binding_identity(device, raw):
    from audio_library_organizer.storage.managed_bindings import binding_stat_identity

    row = dict(device=device, inode=1, stat_json=json.dumps([raw, 1, 3, 4, 5, 1]))
    with pytest.raises(ValueError):
        binding_stat_identity(row)


def test_retry_cannot_overwrite_a_published_file_without_binding(preflight):
    from dataclasses import replace

    _, repo, paths, worker, results, errors, _ = preflight
    worker.plan = replace(worker.plan, items=worker.plan.items[:1])
    source = worker.plan.items[0].track.path
    source_bytes = source.read_bytes()
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute("CREATE TRIGGER deny_binding BEFORE INSERT ON managed_bindings "
                     "BEGIN SELECT RAISE(ABORT, 'injected registration failure'); END")
    worker.run()
    assert not errors and len(results) == 1
    result = results[0]
    assert result.created == 0 and result.failed == 1 and not repo.list_managed_bindings()
    outcome = result.outcomes[0]
    assert outcome.status == 'registration_error' and outcome.raw_verified
    target = outcome.destination
    assert target is not None and target.is_file()
    output_bytes = target.read_bytes()
    assert hashlib.sha256(output_bytes).hexdigest() == outcome.final_sha256
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('DROP TRIGGER deny_binding')

    retry = ExportWorker(worker.plan, adoption_repository=repo, library_root=paths.root)
    finished = []
    retry.finished.connect(finished.append)
    retry.failed.connect(errors.append)
    retry.run()
    assert len(errors) == 1 and not finished
    assert not repo.list_managed_bindings() and list(paths.root.rglob('*.mp3')) == [target]
    assert target.read_bytes() == output_bytes and source.read_bytes() == source_bytes
