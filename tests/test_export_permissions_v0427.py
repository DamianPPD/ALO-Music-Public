"""Synthetic permission regressions and a labeled model of the Windows CSV pattern."""
import errno
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys

import pytest
from mutagen.id3 import ID3

from audio_adoption_fixtures import mp3_samples, copy_audio
from test_export_readonly_v0427 import snapshot, require_readonly_enforcement
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs import exporter
from audio_library_organizer.safety import copy_pipeline


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permission contract; not a Windows ACL test')
@pytest.mark.parametrize('source_mode,creation_mask,expected', [
    (0o600, 0o022, 0o600), (0o640, 0o022, 0o640),
    (0o400, 0o022, 0o600), (0o444, 0o022, 0o644),
    (0o644, 0o077, 0o600), (0o644, 0o022, 0o644),
])
def test_copy_does_not_expand_group_or_other_access(tmp_path, source_mode, creation_mask, expected):
    source = tmp_path / 'synthetic.bin'
    source.write_bytes(b'synthetic private payload')
    source.chmod(source_mode)
    before = snapshot(source)
    old_mask = os.umask(creation_mask)
    observed = []
    try:
        output = copy_pipeline.copy_without_overwrite(
            source, tmp_path / 'output',
            prepare=lambda p: observed.append(stat.S_IMODE(p.stat().st_mode)))
    finally:
        os.umask(old_mask)
    assert observed == [expected]
    assert stat.S_IMODE(output.stat().st_mode) == expected
    assert output.read_bytes() == b'synthetic private payload'
    assert snapshot(source) == before


@pytest.mark.skipif(os.name != 'posix', reason='POSIX fd contract')
def test_copy_cannot_override_a_fresh_file_write_denial(tmp_path, monkeypatch):
    source = tmp_path / 'synthetic.bin'
    source.write_bytes(b'synthetic')
    before = snapshot(source)
    original_open = Path.open

    def filesystem_denied_mode(path, mode='r', *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if mode == 'xb' and path.parent.name.startswith('.alo-copy-'):
            # Fault injection models an observed restrictive creation policy.
            # The copy fd stays open, but reopening must remain denied.
            os.fchmod(handle.fileno(), 0o444)
        return handle

    def prepare(path):
        require_readonly_enforcement(path)
        with path.open('r+b'):
            pytest.fail('Fresh creation write denial was overridden')

    monkeypatch.setattr(Path, 'open', filesystem_denied_mode)
    with pytest.raises(PermissionError):
        copy_pipeline.copy_without_overwrite(source, tmp_path / 'output', prepare=prepare)
    assert snapshot(source) == before
    assert not list((tmp_path / 'output').iterdir())


@pytest.mark.skipif(sys.platform != 'linux' or not hasattr(os, 'setxattr'), reason='Linux POSIX ACL xattr support required')
def test_inherited_named_acl_is_not_unmasked_for_a_private_source(tmp_path):
    source = tmp_path / 'synthetic.bin'
    source.write_bytes(b'private synthetic payload')
    source.chmod(0o600)
    before = snapshot(source)
    destination = tmp_path / 'output'
    destination.mkdir()
    # Use an identity mapped in this process's user namespace. This checks real
    # ACL inheritance/masking, not execution under another user's credentials.
    entries = [(1, 7, 0xffffffff), (2, 6, os.geteuid()), (4, 0, 0xffffffff),
               (16, 7, 0xffffffff), (32, 0, 0xffffffff)]
    acl = struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in entries)
    try:
        os.setxattr(destination, 'system.posix_acl_default', acl)
    except OSError as exc:
        if exc.errno in {errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EPERM}:
            pytest.skip('Filesystem does not support this POSIX ACL test: ' + str(exc))
        raise
    old_mask = os.umask(0o022)
    try:
        output = copy_pipeline.copy_without_overwrite(source, destination)
    finally:
        os.umask(old_mask)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    result = os.getxattr(output, 'system.posix_acl_access')
    decoded = [struct.unpack_from('<HHI', result, offset) for offset in range(4, len(result), 8)]
    assert next(perm for tag, perm, uid in decoded if tag == 16) == 0
    assert snapshot(source) == before


@pytest.mark.skipif(os.name != 'posix', reason='POSIX fd contract')
def test_permission_change_failure_stops_before_payload_or_publication(tmp_path, monkeypatch):
    source = tmp_path / 'synthetic.bin'
    source.write_bytes(b'private synthetic payload')
    source.chmod(0o600)
    before = snapshot(source)

    def refused(fd, mode):
        raise PermissionError(errno.EPERM, 'controlled descriptor permission refusal')

    monkeypatch.setattr(copy_pipeline.os, 'fchmod', refused)
    monkeypatch.setattr(copy_pipeline.shutil, 'copyfileobj',
                        lambda *a, **k: pytest.fail('Payload must not be copied after permission failure'))
    with pytest.raises(PermissionError, match='controlled descriptor permission refusal'):
        copy_pipeline.copy_without_overwrite(source, tmp_path / 'output')
    assert snapshot(source) == before
    assert not list((tmp_path / 'output').iterdir())


@pytest.mark.skipif(os.name != 'posix', reason='POSIX fd contract')
def test_permissions_touch_only_the_open_empty_staged_inode(tmp_path, monkeypatch):
    source = tmp_path / 'synthetic.bin'
    source.write_bytes(b'private synthetic payload')
    source.chmod(0o600)
    foreign = tmp_path / 'unrelated.txt'
    foreign.write_bytes(b'leave this unrelated file alone')
    before = {p: snapshot(p) for p in (source, foreign)}
    original, observed = os.fchmod, []

    def owned_fd_only(fd, mode):
        info = os.fstat(fd)
        assert info.st_size == 0
        assert all((info.st_dev, info.st_ino) != (p.stat().st_dev, p.stat().st_ino)
                   for p in (source, foreign))
        observed.append(info.st_ino)
        return original(fd, mode)

    monkeypatch.setattr(copy_pipeline.os, 'fchmod', owned_fd_only)
    monkeypatch.setattr(copy_pipeline.os, 'chmod', lambda *a, **k: pytest.fail('No path-based chmod allowed'))
    output = copy_pipeline.copy_without_overwrite(source, tmp_path / 'output')
    assert observed == [output.stat().st_ino]
    assert all(snapshot(p) == old for p, old in before.items())


@pytest.mark.parametrize('inject_former_copystat', [True, False], ids=['former-readonly-pattern', 'current-copy'])
def test_six_real_mp3_writes_match_or_remove_the_csv_failure_pattern(
        tmp_path, mp3_samples, monkeypatch, inject_former_copystat):
    # The identifiers map to the six CSV plan positions. Audio and metadata are
    # synthetic. This is NOT native Windows execution or the user's audio.
    indices = [3, 25, 38, 74, 82, 95]
    library = LibraryPaths(tmp_path / 'isolated-library')
    library.ensure_created()
    tracks = []
    for index in indices:
        source = copy_audio(mp3_samples['original'], tmp_path / f'synthetic-{index:03}.mp3')
        source.chmod(0o444)
        require_readonly_enforcement(source)
        tracks.append(TrackRecord(path=source, artist='Synthetic artist', title=f'Synthetic case {index}',
                                  year='2001', genre='House', bpm=128, status='ready',
                                  sha256=copy_pipeline.sha256_file(source)))
    before = {t.path: snapshot(t.path) for t in tracks}
    original_copy = exporter.copy_without_overwrite
    original_cleanup = copy_pipeline.shutil.rmtree

    if inject_former_copystat:
        def former_copy(source, *args, prepare, **kwargs):
            def former_prepare(path):
                # Sole former behavior injected at its original phase boundary.
                shutil.copystat(source, path)
                return prepare(path)
            return original_copy(source, *args, prepare=former_prepare, **kwargs)
        monkeypatch.setattr(exporter, 'copy_without_overwrite', former_copy)

    def cleanup_model(path):
        # POSIX unlink ordinarily permits a 0444 child. Only this cleanup denial
        # is modeled, to reproduce the Windows-shaped pair without claiming Win32.
        for child in path.iterdir():
            if child.is_file() and not child.stat().st_mode & stat.S_IWUSR:
                raise PermissionError(errno.EACCES, 'controlled read-only cleanup denial (model)', str(child))
        return original_cleanup(path)

    monkeypatch.setattr(copy_pipeline.shutil, 'rmtree', cleanup_model)
    result = exporter.execute_copy_plan(exporter.ExportPlan.from_tracks(tracks, library))
    assert all(snapshot(path) == old for path, old in before.items())
    assert result.processed == 6 and all(o.raw_verified for o in result.outcomes)
    if inject_former_copystat:
        assert result.created == 0 and result.failed == 6 and result.status == 'problems'
        assert len(result.cleanup_warnings) == 6
        assert len(list(library.ready.glob('.alo-copy-*/*.mp3'))) == 6
        assert not list(library.ready.glob('*.mp3'))
        assert all(o.status == 'tag_error' and 'Permission denied' in o.error for o in result.outcomes)
        assert all('controlled read-only cleanup denial (model)' in w for w in result.cleanup_warnings)
    else:
        assert result.created == 6 and result.failed == 0 and result.status == 'success'
        assert not result.cleanup_warnings and not list(library.ready.glob('.alo-copy-*'))
        for path, track in zip(result.copied, tracks):
            assert str(ID3(path)['TIT2']) == f'{track.title} [128bpm]'
    print(json.dumps({'former_copystat': inject_former_copystat, 'cases': indices,
                      'created': result.created, 'tag_errors': result.failed,
                      'cleanup_warnings': len(result.cleanup_warnings),
                      'scope': 'real Linux MP3 writes; cleanup denial modeled, NOT Windows'}))
