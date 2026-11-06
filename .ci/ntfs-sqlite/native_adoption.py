"""Real MP3/SQLite adoption on Windows Server 2022 and high-serial local NTFS.

Run from candidate root with PYTHONPATH=src, ALO_EVIDENCE, TMP and TEMP set.
"""
from argparse import ArgumentParser
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import UUID

from mutagen.id3 import ID3, ID3NoHeaderError, TIT2
from audio_library_organizer.audio.identity import ALGORITHM, _find_decoder, inspect_audio, stat_identity
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.legacy_adoption import KnownLibrary, adopt_legacy_output, inventory_legacy_outputs
from audio_library_organizer.jobs.managed_files import MaterialKind, ReadPurpose, read_material, resolve_read_path
from audio_library_organizer.storage.database import SCHEMA_VERSION
from audio_library_organizer.storage.repository import LibraryRepository


def digest(data):
    return sha256(data).hexdigest()


def connect(repo):
    return closing(sqlite3.connect(repo.database_path.absolute().as_uri() + "?mode=ro", uri=True))


def state(repo):
    with connect(repo) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        tables = conn.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()
        return {table: conn.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall() for (table,) in tables}


def status(repo, proposal):
    with connect(repo) as conn:
        return conn.execute("SELECT status FROM legacy_adoption_proposals WHERE proposal_id=?",
                            (proposal.proposal_id,)).fetchone()[0]


def reject(repo, root, proposal, confirmed, phrase):
    try:
        adopt_legacy_output(repo, proposal.proposal_id, confirmed=confirmed, library_root=root)
    except ValueError as error:
        assert phrase in str(error).lower(), error
        return str(error)
    raise AssertionError("Unexpected approval")


def library(area, name, sample):
    root = area / name
    source = area / (name + "-source") / "Source.mp3"
    source.parent.mkdir()
    shutil.copyfile(sample, source)
    repo = LibraryRepository(root / ".alo" / "library.sqlite3")
    repo.initialize()
    repo.bootstrap_sources([source.parent])
    st = source.stat()
    track = TrackRecord(path=source, size_bytes=st.st_size, mtime_ns=st.st_mtime_ns,
                        sha256=digest(source.read_bytes()), title="Manual title", artist="Manual artist",
                        locked_fields={"title"}, field_sources={"title": "manual"},
                        status="duplicate", original_tags={"synthetic": True})
    repo.upsert_track(track)
    return repo, root, repo.get_track(track.track_id)


def known(repo, root):
    return KnownLibrary(str(root), str(repo.database_path), repo.library_id)


def native_volume(path):
    from audio_library_organizer.safety.windows_file_identity import capture
    leaf = capture(str(path)).leaf
    device, inode, *_ = stat_identity(path.stat())
    assert leaf.filesystem == "NTFS" and leaf.drive_type == 3, leaf
    assert 2**63 <= device < 2**64 and 0 < inode < 2**64, (device, inode)
    return dict(filesystem=leaf.filesystem, drive_type=leaf.drive_type, volume_serial=leaf.volume_serial,
                volume_guid=leaf.volume_guid, file_id=leaf.file_id.hex(), st_dev=device, st_ino=inode)


def check_lease(repo, source, output):
    from audio_library_organizer.safety.windows_output_lease import acquire_output_lease
    owner = acquire_output_lease(str(source), str(output))
    denied = []
    try:
        acquired = owner.owned_count
        assert acquired and owner.active
        for path in (source, output):
            target = path.with_name(path.name + ".probe")
            try:
                path.rename(target)
            except OSError as error:
                assert error.winerror in (5, 32), error
                denied.append(error.winerror)
            else:
                target.rename(path)
                raise AssertionError(f"Live lease did not block rename: {path}")
    finally:
        owner.close()
    assert owner.owned_count == 0 and not owner.active and not owner.failed_handles
    for path in (source, output, source.parent, output.parent, repo.database_path):
        target = path.with_name(path.name + ".probe")
        path.rename(target)
        target.rename(path)
    return dict(acquired=acquired, owned_end=owner.owned_count, rename_denied_during=denied,
                renames_succeeded_after=["source", "output", "source parent", "output parent", "database"])


def binding_row(repo, root, output, expected):
    binding, = repo.list_managed_bindings()
    track = repo.get_track(expected["track_id"])
    values = (repo.library_id, binding.library_id, binding.track_id, binding.binding_id,
              binding.source_binding["source_id"], track.source_id, binding.evidence["proposal_id"])
    assert all(str(UUID(value)) == value for value in values)
    library_id, track_id, binding_id, source_id, proposal_id = (expected[key] for key in
        ("library_id", "track_id", "binding_id", "source_id", "proposal_id"))
    assert values == (library_id, library_id, track_id, binding_id, source_id, source_id, proposal_id)
    assert binding.evidence["confirmed"] is True
    assert Path(binding.locator(root)) == output and binding.expected_sha256 == expected["sha256"]
    assert binding.audio_algorithm == ALGORITHM
    assert binding.audio_digest == binding.evidence["source_audio_digest"] == expected["audio_digest"]
    physical = tuple(expected["stat_identity"])
    assert binding.stat_identity == physical
    assert (track.title, track.artist, track.locked_fields, track.field_sources, track.status, track.original_tags) == (
        "Manual title", "Manual artist", {"title"}, {"title": "manual"}, "duplicate", {"synthetic": True})
    with connect(repo) as conn:
        dev, ino, dev_type, ino_type, raw = conn.execute(
            "SELECT device,inode,typeof(device),typeof(inode),stat_json FROM managed_bindings").fetchone()
    assert (dev_type, ino_type) == ("integer", "integer")
    assert (dev, ino) == tuple(value - 2**64 if value >= 2**63 else value for value in physical[:2])
    assert tuple(json.loads(raw)) == physical
    assert len(state(repo)["managed_bindings"]) == 1
    return dict(device=dev, inode=ino, stat_json=physical)


def read_back(payload):
    expected = json.loads(payload.read_text(encoding="utf-8"))
    assert os.getpid() != expected["parent_pid"]
    root, output = Path(expected["root"]), Path(expected["output"])
    repo = LibraryRepository(root / ".alo" / "library.sqlite3")
    repo.initialize()
    row = binding_row(repo, root, output, expected)
    track = repo.get_track(expected["track_id"])
    assert not track.path.exists()
    ctx = repo.read_context(root)
    for purpose in ReadPurpose:
        plan = resolve_read_path(track, ctx, purpose)
        assert plan.kind == MaterialKind.MANAGED and Path(plan.locator) == output
        material = read_material(plan, lambda path: path.read_bytes())
        assert material.resolution.is_verified and material.resolution.kind == MaterialKind.MANAGED
        assert digest(material.value) == expected["sha256"] and material.value == output.read_bytes()
    proof = inspect_audio(output)
    assert proof.status == "VALID" and proof.full_sha256 == expected["sha256"], proof
    assert proof.audio_digest == expected["audio_digest"] and proof.algorithm == ALGORITHM, proof
    print(json.dumps(dict(child_pid=os.getpid(), source_missing=True,
                          read_purposes=[purpose.value for purpose in ReadPurpose], row=row,
                          sqlite_integrity_check="ok", sqlite_foreign_key_check=[], **expected)))


def run(area, log, portable):
    decoder = _find_decoder()
    assert decoder, "Application FFmpeg decoder not found"
    sample = area / "test-tone.mp3"
    subprocess.run([decoder, "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=44100:duration=2", "-ac", "2", "-c:a",
                    "libmp3lame", "-b:a", "128k", str(sample)], check=True, capture_output=True, timeout=30)
    repo, root, track = library(area, "first", sample)
    other, other_root, other_track = library(area, "second", sample)
    assert other.library_id != repo.library_id and other_track.track_id != track.track_id
    output = root / "GOTOWE" / "Legacy output.mp3"
    output.parent.mkdir()
    shutil.copyfile(sample, output)
    try:
        tags = ID3(output)
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(TIT2(encoding=3, text=["Different legacy tags"]))
    tags.save(output)

    if not portable:
        volumes = {name: native_volume(path) for name, path in
                   {"source": track.path, "output": output, "database": repo.database_path}.items()}
        assert len({volume["volume_guid"] for volume in volumes.values()}) == 1
        log("native-local-ntfs", paths=volumes)
    before_audio = track.path.read_bytes(), output.read_bytes()
    src, managed = inspect_audio(track.path), inspect_audio(output)
    assert src.status == managed.status == "VALID", (src, managed)
    assert src.full_sha256 == digest(before_audio[0]) != digest(before_audio[1]) == managed.full_sha256
    assert src.audio_digest == managed.audio_digest and src.algorithm == managed.algorithm == ALGORITHM
    physical = stat_identity(output.stat())
    assert managed.stat_identity == physical
    descriptor = known(other, other_root)
    proposal, = inventory_legacy_outputs(repo, library_root=root, known_libraries=(descriptor,)).proposals
    assert proposal.status == status(repo, proposal) == "CANDIDATE" and proposal.can_adopt, proposal
    assert (proposal.library_id, proposal.track_id, proposal.source_id, Path(proposal.locator)) == (
        repo.library_id, track.track_id, track.source_id, output)
    assert (proposal.full_sha256, proposal.audio_digest, proposal.stat_identity) == (
        managed.full_sha256, managed.audio_digest, physical)
    before, other_before = state(repo), state(other)
    assert not before["managed_bindings"]
    error = reject(repo, root, proposal, False, "confirmation")
    assert state(repo) == before and state(other) == other_before
    log("candidate-and-explicit-false-refusal", proposal_id=proposal.proposal_id, persisted_status=status(repo, proposal),
        refusal=error, bindings=0, physical=physical, source_sha256=src.full_sha256,
        output_sha256=managed.full_sha256, audio_digest=managed.audio_digest)

    binding = adopt_legacy_output(repo, proposal.proposal_id, confirmed=True, library_root=root)
    expected = dict(binding_id=binding.binding_id, library_id=repo.library_id, track_id=track.track_id,
                    source_id=track.source_id, proposal_id=proposal.proposal_id, sha256=managed.full_sha256,
                    audio_digest=managed.audio_digest, stat_identity=physical, parent_pid=os.getpid(),
                    root=str(root), output=str(output))
    row = binding_row(repo, root, output, expected)
    assert repo.get_track(track.track_id) == track and status(repo, proposal) == "ALREADY_BOUND"
    assert (track.path.read_bytes(), output.read_bytes()) == before_audio
    assert stat_identity(output.stat()) == physical and state(other) == other_before
    log("explicit-true-committed", row=row, unchanged_audio=True, unchanged_track=True,
        known_database_attached=True, **expected)

    committed = state(repo)
    error = reject(repo, root, proposal, True, "already bound")
    assert state(repo) == committed and repo.list_managed_bindings() == (binding,)
    repeat, = inventory_legacy_outputs(repo, library_root=root, known_libraries=(descriptor,)).proposals
    assert repeat.status == "ALREADY_BOUND" and not repeat.can_adopt, repeat
    log("repeat-refused", refusal=error, inventory_status=repeat.status, binding_id=binding.binding_id)

    payload = area / "expectations.json"
    payload.write_text(json.dumps(expected), encoding="utf-8")
    offline = track.path.with_name("Offline.mp3")
    track.path.rename(offline)
    try:
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--read-back", str(payload)],
                               capture_output=True, encoding="utf-8", timeout=120)
        assert child.returncode == 0, (child.returncode, child.stdout, child.stderr)
        log("separate-process-persistent-managed-read", **json.loads(child.stdout))
    finally:
        offline.rename(track.path)

    if not portable:
        log("native-lease-cleanup", **check_lease(repo, track.path, output))
    foreign = other_root / "GOTOWE" / "Relocated physical output.mp3"
    foreign.parent.mkdir()
    output.rename(foreign)
    assert not output.exists() and foreign.read_bytes() == before_audio[1]
    moved = stat_identity(foreign.stat())
    assert moved[:2] == physical[:2] and moved[-1] == 1
    control, = inventory_legacy_outputs(other, library_root=other_root, persist=False).proposals
    assert control.can_adopt and control.status == "CANDIDATE", control
    conflict, = inventory_legacy_outputs(other, library_root=other_root,
                                         known_libraries=(known(repo, root),)).proposals
    assert conflict.status == status(other, conflict) == "CONFLICT" and not conflict.can_adopt, conflict
    assert conflict.reason_codes == ("FOREIGN_OWNER",) and conflict.stat_identity[:2] == physical[:2], conflict
    assert Path(conflict.locator) == foreign and conflict.track_id == other_track.track_id
    before_refusal = state(other)
    error = reject(other, other_root, conflict, True, "conflicting")
    assert state(other) == before_refusal and not other.list_managed_bindings()
    assert repo.list_managed_bindings() == (binding,) and len(state(repo)["managed_bindings"]) == 1
    log("cross-library-physical-conflict", former_locator=str(output), former_locator_missing=True,
        new_locator=str(foreign), raw_physical_pair=moved[:2], link_count=moved[-1],
        control_without_known_owner=control.status, status=conflict.status, reasons=conflict.reason_codes,
        refusal=error, owner_library_id=repo.library_id, foreign_library_id=other.library_id,
        owner_bindings=1, foreign_bindings=0, sqlite_integrity_check="ok", sqlite_foreign_key_check=[])


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--read-back", type=Path, help="Internal separate-process verification")
    parser.add_argument("--portable-smoke", action="store_true", help="Development smoke; no native evidence")
    args = parser.parse_args()
    if not __debug__:
        parser.error("Assertions are required")
    if args.read_back:
        read_back(args.read_back)
        return
    evidence = Path(os.environ["ALO_EVIDENCE"])
    evidence.mkdir(parents=True, exist_ok=True)
    suffix = "-portable-smoke" if args.portable_smoke else ""
    with (evidence / f"native-adoption{suffix}.jsonl").open("w", encoding="utf-8") as stream:
        def log(event, **data):
            line = json.dumps(dict(event=event, **data), sort_keys=True)
            stream.write(line + "\n")
            stream.flush()
            print(line, flush=True)
        try:
            win = sys.getwindowsversion() if sys.platform == "win32" else None
            log("environment", native_requested=not args.portable_smoke, python=sys.version,
                implementation=sys.implementation.name, platform=platform.platform(), sqlite=sqlite3.sqlite_version,
                windows_build=win.build if win else None, windows_product_type=win.product_type if win else None,
                tmp=os.environ.get("TMP"), temp=os.environ.get("TEMP"))
            if not args.portable_smoke:
                assert win is not None and win.build == 20348 and win.product_type in (2, 3), win
                assert sys.implementation.name == "cpython" and sys.version_info[:3] == (3, 12, 10)
                assert sys.maxsize == 2**63 - 1
            with TemporaryDirectory(prefix="alo-native-adoption-") as tmp:
                run(Path(tmp).resolve(), log, args.portable_smoke)
        except Exception as error:
            log("failed", error_type=type(error).__name__, error=str(error))
            raise
        log("passed", native_evidence=not args.portable_smoke)


if __name__ == "__main__":
    main()
