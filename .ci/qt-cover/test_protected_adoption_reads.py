"""External Windows evidence: observe the selected adoption check as it runs."""

import ctypes
import os
import sys
from threading import get_ident, local

import pytest

from audio_adoption_fixtures import mp3_samples
from conftest import release_test_windows
from test_legacy_adoption_v0427 import library
from test_output_contract_windows_v0427 import owners
from test_output_session_ui_v0427 import adopted_window, assert_completed_observation, pump
from test_windows_output_native_v0427 import diagnostic_window, record

from audio_library_organizer.jobs import adopted_output
from audio_library_organizer.safety import windows_file_identity as native
from audio_library_organizer.safety.windows_output_lease import WindowsOutputLease


pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Real Windows x64 and local NTFS required')


def test_actual_adoption_reads_share_one_native_owner_and_deny_both_replacements(
    diagnostic_window, owners, monkeypatch, mp3_samples, tmp_path,
):
    assert ctypes.sizeof(ctypes.c_void_p) == 8
    window, (repo, _, track, output), binding = diagnostic_window
    source = track.path
    pair = (source, output)
    paths = tuple(map(str, pair))
    database_path = str(repo.database_path)
    original_bytes = tuple(path.read_bytes() for path in pair)
    replacement_bytes = mp3_samples['different_tail'].read_bytes()
    assert all(data != replacement_bytes for data in original_bytes)
    replacements = (tmp_path / 'replace-source.mp3', tmp_path / 'replace-result.mp3')
    for replacement in replacements:
        replacement.write_bytes(replacement_bytes)

    gui_thread = get_ident()
    scope = local()
    events, captures, reads, refusals, callback_owners, failures = [], [], [], [], [], []
    actual_assess = adopted_output.assess_adopted_mp3
    actual_capture = native.capture
    actual_inspect = adopted_output.inspect_audio

    def protected():
        assert len(owners) == 1
        owner = owners[0]
        assert type(owner) is WindowsOutputLease
        assert owner._owner == get_ident() != gui_thread
        assert window._output_operation.owns_windows_lease(owner)
        assert owner.active and owner.owned_count > 0
        assert owner.paths == paths and owner.active_for(paths, owner.material)
        assert tuple(proof.path for proof in owner.material) == paths
        assert all(proof.leaf.filesystem == 'NTFS' and proof.leaf.drive_type == 3 for proof in owner.material)
        return owner

    def observe_assess(*args, **kwargs):
        assert not getattr(scope, 'in_adapter', False)
        scope.in_adapter = True
        try:
            return actual_assess(*args, **kwargs)
        except BaseException as exc:
            failures.append(exc)
            raise
        finally:
            scope.in_adapter = False

    def observe_capture(path, *, mutable=False):
        observing = getattr(scope, 'in_adapter', False)
        if observing:
            protected()
        proof = actual_capture(path, mutable=mutable)
        if observing:
            events.append(('native-db' if mutable else 'native', str(path)))
            captures.append(proof)
        return proof

    def observe_inspect(path, *args, **kwargs):
        assert getattr(scope, 'in_adapter', False)
        events.append(('before-read', str(path)))
        owner = protected()
        callback_owners.append(owner)
        if str(path) == paths[1]:
            assert len(reads) == 1 and reads[0][0] == paths[0]
            for candidate, target, before in zip(replacements, pair, original_bytes):
                # Real MoveFileExW through os.replace, on the worker thread,
                # after source inspection returned and before result inspection.
                with pytest.raises(OSError) as denied:
                    os.replace(candidate, target)
                assert denied.value.winerror in (5, 32)
                assert candidate.read_bytes() == replacement_bytes
                assert target.read_bytes() == before
                refusals.append((str(target), denied.value.winerror))
                events.append(('replace-denied', str(target)))
        proof = actual_inspect(path, *args, **kwargs)
        callback_owners.append(protected())
        events.append(('after-read', str(path)))
        reads.append((str(path), proof))
        return proof

    monkeypatch.setattr(adopted_output, 'assess_adopted_mp3', observe_assess)
    monkeypatch.setattr(native, 'capture', observe_capture)
    monkeypatch.setattr(adopted_output, 'inspect_audio', observe_inspect)

    window.review_btn.click()
    pump(lambda: window._thread is None)
    if failures:
        raise failures[0]

    assert events == [
        ('native-db', database_path), ('native', paths[0]), ('native', paths[1]),
        ('before-read', paths[0]), ('after-read', paths[0]),
        ('before-read', paths[1]), ('replace-denied', paths[0]), ('replace-denied', paths[1]),
        ('after-read', paths[1]), ('native', paths[0]), ('native', paths[1]), ('native-db', database_path),
    ]
    assert [path for path, _ in refusals] == list(paths)
    assert [path for path, _ in reads] == list(paths)
    for (_, proof), full_sha in zip(reads, (track.sha256, binding.expected_sha256)):
        assert proof.status == 'VALID' and proof.full_sha256 == full_sha
        assert proof.algorithm == binding.audio_algorithm and proof.audio_digest == binding.audio_digest
    assert_completed_observation(window, track)
    assert len(owners) == 1
    owner = owners[0]
    assert callback_owners == [owner] * 4
    result = window.last_reconciliation_result
    delivery = result.output_delivery
    assert not result.cancelled and delivery.windows_lease is owner
    assert delivery.pending.request.binding_id == binding.binding_id
    assert delivery.pending.request.library_id == repo.library_id
    guard = delivery.pending.assessment.guard
    assert guard.windows_material == tuple(captures[1:3]) == owner.material == delivery.windows_material
    assert all(native.same_material(before, after) for before, after in zip(captures[1:3], captures[3:5]))
    assert native.same_database(guard.windows_database, captures[0])
    assert native.same_database(guard.windows_database, captures[5])
    assert native.same_database(guard.windows_database, delivery.windows_database)
    assert repo.list_managed_bindings() == (binding,)
    assert tuple(path.read_bytes() for path in pair) == original_bytes
    assert owner.accepted and not owner.active and owner.owned_count == 0 and not owner.failed_handles
    assert window._worker is None and window._thread is None

    # Same exact operations succeed after release, isolating the sharing rule.
    for candidate, target, old_proof in zip(replacements, pair, owner.material):
        os.replace(candidate, target)
        assert not candidate.exists() and target.read_bytes() == replacement_bytes
        assert native.capture(target).leaf.object_identity != old_proof.leaf.object_identity
    record('real-adoption-reads-and-between-read-replacements', events=events, refusals=refusals,
           paths=paths, file_ids=[proof.leaf.file_id for proof in owner.material],
           digests=[(proof.full_sha256, proof.audio_digest) for _, proof in reads],
           protected_callbacks=len(callback_owners), accepted=owner.accepted, owned_end=owner.owned_count,
           same_replacements_succeed_after_release=True, worker_finished=True)
