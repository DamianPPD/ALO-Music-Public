"""Real filesystem path-budget regressions, not a Windows API simulation."""
import os
from pathlib import Path

import pytest

from audio_library_organizer.safety.copy_pipeline import copy_without_overwrite, sha256_file


def destination_near_path_limit(root, suffix):
    if os.name == 'nt':
        name = 'Synthetic artist - Synthetic title 0 (2000) [128bpm]' + suffix
        final_length = 249
    else:
        name = 'x' * (200 - len(suffix)) + suffix
        final_length = os.pathconf(root, 'PC_PATH_MAX') - 6
    wanted = final_length - len(name) - 1
    parent = root
    assert len(str(parent)) < wanted, 'Use a shorter isolated test root for the path-boundary probe'
    while len(str(parent)) < wanted:
        size = min(120, wanted - len(str(parent)) - 1)
        if size == 0:
            parent = parent.parent / (parent.name + 'x')
        else:
            parent = parent / ('d' * size)
        parent.mkdir(exist_ok=True)
    return parent, name


@pytest.mark.parametrize('suffix', ['.mp3', '.flac'])
def test_valid_final_path_does_not_fail_from_repeating_long_name_in_private_stage(tmp_path_factory, suffix):
    """A copy must not exhaust the path budget merely inside its private stage."""
    root = tmp_path_factory.mktemp('budget')
    source = root / ('source' + suffix)
    source.write_bytes(b'controlled copy-pipeline payload; not a codec test')
    destination, name = destination_near_path_limit(root, suffix)
    target = destination / name
    # Prove the requested final path itself is writable on this actual filesystem.
    target.write_bytes(b'valid final path')
    assert target.read_bytes() == b'valid final path'
    target.unlink()
    digest = sha256_file(source)
    copied = copy_without_overwrite(source, destination, name)
    assert copied == target and copied.read_bytes() == source.read_bytes()
    assert sha256_file(source) == digest
    assert not list(destination.glob('.alo-copy-*'))


def test_private_basename_never_changes_public_name_or_overwrites_existing_files(tmp_path):
    source = tmp_path / 'source.mp3'; source.write_bytes(b'original source bytes')
    destination = tmp_path / 'output'; destination.mkdir()
    foreign = destination / 'f.mp3'; foreign.write_bytes(b'existing unrelated output')
    first = copy_without_overwrite(source, destination, 'requested.mp3')
    second = copy_without_overwrite(source, destination, 'requested.mp3')
    assert first.name == 'requested.mp3' and second.name == 'requested (2).mp3'
    assert first.read_bytes() == second.read_bytes() == b'original source bytes'
    assert foreign.read_bytes() == b'existing unrelated output'
    assert not list(destination.glob('.alo-copy-*'))


def test_prepare_failure_removes_only_its_own_private_stage(tmp_path):
    source = tmp_path / 'source.mp3'; source.write_bytes(b'unchanged source')
    destination = tmp_path / 'output'; destination.mkdir()
    foreign = destination / '.alo-copy-existing'; foreign.mkdir()
    (foreign / 'keep.mp3').write_bytes(b'foreign data')
    def fail(private):
        private.write_bytes(b'partial private result')
        raise RuntimeError('controlled preparation failure')
    with pytest.raises(RuntimeError, match='controlled preparation failure'):
        copy_without_overwrite(source, destination, 'requested.mp3', prepare=fail)
    assert source.read_bytes() == b'unchanged source'
    assert (foreign / 'keep.mp3').read_bytes() == b'foreign data'
    assert sorted(p.name for p in destination.iterdir()) == ['.alo-copy-existing']


def test_partial_copy_io_failure_leaves_no_output_and_only_removes_own_stage(tmp_path, monkeypatch):
    from audio_library_organizer.safety import copy_pipeline
    source = tmp_path / 'source.mp3'; source.write_bytes(b'original source content')
    destination = tmp_path / 'output'; destination.mkdir()
    foreign = destination / '.alo-copy-existing'; foreign.mkdir()
    (foreign / 'keep.mp3').write_bytes(b'foreign file')
    def fail_copy(reader, writer, **kwargs):
        writer.write(reader.read(8))
        raise OSError('controlled partial-copy I/O error')
    monkeypatch.setattr(copy_pipeline.shutil, 'copyfileobj', fail_copy)
    with pytest.raises(OSError, match='controlled partial-copy I/O error'):
        copy_without_overwrite(source, destination, 'requested.mp3')
    assert source.read_bytes() == b'original source content'
    assert (foreign / 'keep.mp3').read_bytes() == b'foreign file'
    assert sorted(p.name for p in destination.iterdir()) == ['.alo-copy-existing']
