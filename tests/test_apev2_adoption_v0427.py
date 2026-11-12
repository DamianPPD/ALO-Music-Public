"""Historical MP3 ownership evidence across a real application restart."""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import textwrap

import pytest

from audio_adoption_fixtures import mp3_samples
from audio_library_organizer.audio.identity import inspect_audio
from audio_library_organizer.jobs.legacy_adoption import (
    _snapshot_value, adopt_legacy_output, inventory_legacy_outputs,
)
from test_apev2_identity_v0427 import ID3V1, _ape_item, _ape_tag, _ape_with_false_id3v1, mp3_bytes
from test_legacy_adoption_v0427 import library


def _file_snapshot(path):
    return path.read_bytes(), path.stat().st_mtime_ns


def _binding_row(database):
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        row, = connection.execute('SELECT * FROM managed_bindings').fetchall()
        return row


def _approve(library, content, expected_title):
    repo, root, track, output = library
    output.write_bytes(content)
    original_source, original_output = _file_snapshot(track.path), _file_snapshot(output)
    source_proof, proof = inspect_audio(track.path), inspect_audio(output)
    assert source_proof.status == proof.status == 'VALID', (source_proof.reason, proof.reason)
    assert proof.audio_digest == source_proof.audio_digest
    assert proof.full_sha256 == hashlib.sha256(original_output[0]).hexdigest() != track.sha256
    assert proof.tag_snapshot['title'] == expected_title

    proposal, = inventory_legacy_outputs(repo, library_root=root).proposals
    assert proposal.status == 'CANDIDATE' and proposal.can_adopt
    assert repo.list_managed_bindings() == ()
    binding = adopt_legacy_output(repo, proposal.proposal_id, confirmed=True, library_root=root)
    assert binding.expected_sha256 == proof.full_sha256
    assert binding.audio_digest == proof.audio_digest
    assert binding.applied_snapshot['tag_snapshot'] == proof.tag_snapshot
    assert repo.list_managed_bindings() == (binding,)
    assert (_file_snapshot(track.path), _file_snapshot(output)) == (original_source, original_output)
    return binding


def _check_in_new_process(root, *, gui=False):
    script = textwrap.dedent('''
        import json
        import os
        from pathlib import Path
        import sys
        from uuid import uuid4

        from audio_library_organizer.jobs.adopted_output import AssessmentRequest
        from audio_library_organizer.jobs.file_reconciliation import check_library
        from audio_library_organizer.storage.repository import LibraryRepository

        root = Path(sys.argv[1])
        repo = LibraryRepository(root / '.alo' / 'library.sqlite3')
        repo.initialize()
        binding, = repo.list_managed_bindings()
        if sys.argv[2] == 'gui':
            from time import monotonic
            from PySide6.QtCore import QSettings
            from PySide6.QtWidgets import QApplication
            from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
            from audio_library_organizer.ui.main_window import MainWindow

            app = QApplication([])
            store = QSettings(str(root.parent / 'restart.ini'), QSettings.Format.IniFormat)
            window = MainWindow(AppSettings((), LibraryPaths(root)), store)
            try:
                window.library.select_track(repo.get_track(binding.track_id))
                assert window.repository.list_managed_bindings() == (binding,)
                window.review_btn.click()
                deadline = monotonic() + 20
                while window._thread is not None and monotonic() < deadline:
                    app.processEvents()
                assert window._thread is None, 'GUI check did not finish'
                checked = window.last_reconciliation_result
            finally:
                window.close()
                app.processEvents()
        else:
            request = AssessmentRequest(repo.library_id, binding.track_id, binding.binding_id,
                                        str(uuid4()), 0, 'restart-regression')
            checked = check_library(repo, library_root=root, include_adoption=True,
                                    library_id=request.library_id, operation_id=request.operation_id,
                                    output_request=request, current_output_request=lambda: request)
        assert not checked.cancelled
        assessment = checked.pending_output_assessment.assessment
        item, = checked.files
        print(json.dumps({'pid': os.getpid(), 'reason': assessment.reason,
                          'confirmed': assessment.evaluation.is_confirmed,
                          'managed_reason': item.facts.managed.reason,
                          'library_id': repo.library_id, 'binding_id': binding.binding_id,
                          'track_id': binding.track_id}))
    ''')
    source = Path(__file__).resolve().parents[1] / 'src'
    result = subprocess.run([sys.executable, '-c', script, str(root), 'gui' if gui else 'backend'],
                            capture_output=True, text=True, timeout=45,
                            env={'QT_QPA_PLATFORM': 'offscreen', **os.environ, 'PYTHONPATH': str(source)})
    assert result.returncode == 0, (result.stdout, result.stderr)
    checked = json.loads(result.stdout)
    assert checked['pid'] != os.getpid()
    return checked


def test_unchanged_ape_binary_tag_adoption_remains_confirmed_after_restart(library):
    repo, root, track, output = library
    tail = _ape_with_false_id3v1()
    assert tail[-128:-125] == b'TAG'  # ID3v1 offset, but inside the APEv2 value.
    binding = _approve(library, track.path.read_bytes() + tail, '')
    before = _binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)

    checked = _check_in_new_process(root)

    assert (_binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)) == before
    assert (checked['library_id'], checked['track_id'], checked['binding_id']) == (
        binding.library_id, binding.track_id, binding.binding_id)
    assert checked['reason'] == 'CONFIRMED_FIELD_DIFFERENCE', checked
    assert checked['confirmed'] is True


def test_unchanged_ape_binary_tag_adoption_survives_main_window_restart(library):
    repo, root, track, output = library
    _approve(library, track.path.read_bytes() + _ape_with_false_id3v1(), '')
    before = _binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)

    checked = _check_in_new_process(root, gui=True)

    assert (_binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)) == before
    assert checked['reason'] == 'CONFIRMED_FIELD_DIFFERENCE', checked
    assert checked['confirmed'] is True


@pytest.mark.parametrize(('metadata', 'title'), [
    ('ape', ''), ('ape-id3v1', 'APE fixture title'), ('id3v1', 'APE fixture title'),
    ('id3v2', 'Legacy title'), ('untagged', ''),
])
def test_valid_metadata_stays_consistent_in_reopened_adoption(library, mp3_bytes, metadata, title):
    repo, root, track, output = library
    _, frames = mp3_bytes
    content = {
        'ape': frames + _ape_tag(_ape_item()),
        'ape-id3v1': frames + _ape_with_false_id3v1() + ID3V1,
        'id3v1': frames + ID3V1,
        'id3v2': output.read_bytes(),
        'untagged': frames,
    }[metadata]
    _approve(library, content, title)
    before = _binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)

    checked = _check_in_new_process(root)

    assert (_binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)) == before
    assert checked['reason'] == 'CONFIRMED_FIELD_DIFFERENCE', checked
    assert checked['confirmed'] is True


def test_reopened_adoption_refuses_conflicting_historical_snapshot(library):
    repo, root, track, output = library
    binding = _approve(library, track.path.read_bytes() + _ape_with_false_id3v1(), '')
    # Simulate an old evidence row that treated opaque APE bytes as ID3v1.
    # Recompute its internal token so only a comparison to the real tags can reject it.
    snapshot = dict(binding.applied_snapshot)
    snapshot['tag_snapshot'] = {**snapshot['tag_snapshot'], 'title': 'y' * 30}
    snapshot['value'] = _snapshot_value(snapshot['tag_snapshot'], binding.relative_path)
    with closing(sqlite3.connect(repo.database_path)) as connection, connection:
        connection.execute('UPDATE managed_bindings SET applied_snapshot_json=? WHERE binding_id=?',
                           (json.dumps(snapshot), binding.binding_id))
    before = _binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)

    checked = _check_in_new_process(root)

    assert (_binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)) == before
    assert checked['reason'] == 'APPLIED_TAGS_INCONSISTENT', checked
    assert checked['confirmed'] is False


@pytest.mark.parametrize('damage', ['bad-footer', 'truncated-footer'])
def test_malformed_ape_never_creates_an_approved_binding(library, damage):
    repo, root, track, output = library
    tail = _ape_tag(_ape_item())
    tail = tail[:-1] + b'X' if damage == 'bad-footer' else tail[:-5]
    output.write_bytes(track.path.read_bytes() + tail)
    before = _file_snapshot(track.path), _file_snapshot(output)

    result = inventory_legacy_outputs(repo, library_root=root)

    assert result.proposals and not any(proposal.can_adopt for proposal in result.proposals)
    assert repo.list_managed_bindings() == ()
    assert (_file_snapshot(track.path), _file_snapshot(output)) == before


@pytest.mark.parametrize('changed', ['metadata', 'mpeg', 'physical-file'])
def test_reopened_adoption_refuses_changed_ape_material(library, mp3_samples, changed):
    repo, root, track, output = library
    ape = _ape_with_false_id3v1()
    content = track.path.read_bytes() + ape + ID3V1
    binding = _approve(library, content, 'APE fixture title')
    original = inspect_audio(output)
    if changed == 'metadata':
        edited_title = b'External metadata edit'.ljust(30, b'\0')
        output.write_bytes(content[:-125] + edited_title + content[-95:])
    elif changed == 'mpeg':
        output.write_bytes(mp3_samples['different_tail'].read_bytes() + ape + ID3V1)
    else:
        original_stat = output.stat()
        replacement = output.with_name('replacement.tmp')
        replacement.write_bytes(content)
        os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        assert replacement.stat().st_ino != original_stat.st_ino
        replacement.replace(output)
    edited = inspect_audio(output)
    assert edited.status == 'VALID', edited.reason
    assert (edited.full_sha256 == original.full_sha256) == (changed == 'physical-file')
    assert (edited.audio_digest == original.audio_digest) == (changed != 'mpeg')
    assert edited.tag_snapshot['title'] == ('External metadata edit' if changed == 'metadata' else 'APE fixture title')
    before = _binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)

    checked = _check_in_new_process(root)

    assert (_binding_row(repo.database_path), _file_snapshot(track.path), _file_snapshot(output)) == before
    assert checked['binding_id'] == binding.binding_id
    assert checked['confirmed'] is False
    if changed == 'physical-file':
        assert checked['reason'] == 'MANAGED_MATERIAL_CHANGED', checked
    else:
        assert checked['managed_reason'] == 'MANAGED_IDENTITY_CHANGED', checked
        assert checked['reason'] == 'RECONCILIATION_PRIORITY_OR_SOURCE_UNCERTAIN', checked
