import hashlib
import importlib
import importlib.util

import pytest

from audio_adoption_fixtures import mp3_samples, copy_audio


def identity(path, **kwargs):
    name = 'audio_library_organizer.audio.identity'
    assert importlib.util.find_spec(name) is not None, 'Missing versioned audio identity contract'
    api = importlib.import_module(name)
    return api.inspect_audio(path, **kwargs)


@pytest.mark.parametrize('version', [3, 4])
def test_tag_and_cover_changes_keep_audio_identity(tmp_path, mp3_samples, version):
    source = copy_audio(mp3_samples['original'], tmp_path/'source.mp3')
    target = copy_audio(source, tmp_path/'target.mp3', title='Changed tags', cover=True, id3_version=version)
    before, after = identity(source), identity(target)
    assert before.status == after.status == 'VALID'
    assert before.full_sha256 != after.full_sha256
    assert before.audio_digest == after.audio_digest
    assert before.algorithm == after.algorithm == 'mp3-layer3-frames-sha256/v1'
    assert after.tag_snapshot['title'] == 'Changed tags'
    assert after.tag_snapshot['cover_sha256']


def test_changed_audio_and_tail_with_same_filename_are_rejected(tmp_path, mp3_samples):
    a = copy_audio(mp3_samples['original'], tmp_path/'a'/'same.mp3')
    b = copy_audio(mp3_samples['different_tail'], tmp_path/'b'/'same.mp3')
    assert identity(a).audio_digest != identity(b).audio_digest


def test_identical_copies_have_same_audio_digest_but_not_ownership(tmp_path, mp3_samples):
    a = copy_audio(mp3_samples['original'], tmp_path/'a.mp3')
    b = copy_audio(a, tmp_path/'b.mp3')
    left, right = identity(a), identity(b)
    assert left.status == right.status == 'VALID'
    assert left.audio_digest == right.audio_digest
    assert left.full_sha256 == right.full_sha256 == hashlib.sha256(a.read_bytes()).hexdigest()
    assert left.stat_identity != right.stat_identity
    assert not hasattr(left, 'owner_track_id')


@pytest.mark.parametrize('cut', [1, 137, 418, 16000])
def test_truncated_mp3_never_has_valid_audio_identity(tmp_path, mp3_samples, cut):
    path = tmp_path/'truncated.mp3'
    path.write_bytes(mp3_samples['original'].read_bytes()[:-cut])
    result = identity(path)
    assert result.status == 'ERROR'
    assert result.audio_digest is None


def test_corrupted_mp3_is_error(tmp_path):
    path = tmp_path/'broken.mp3'; path.write_bytes(b'not an MP3 stream')
    result = identity(path)
    assert result.status == 'ERROR' and result.audio_digest is None


def test_missing_decoder_never_claims_validation(tmp_path, mp3_samples):
    result = identity(mp3_samples['original'], decoder=tmp_path/'no-decoder')
    assert result.status == 'UNAVAILABLE' and result.audio_digest is None


def test_other_format_is_explicitly_unsupported(tmp_path):
    path = tmp_path/'other.flac'; path.write_bytes(b'fLaC')
    result = identity(path)
    assert result.status == 'UNSUPPORTED' and result.audio_digest is None


def test_cancelled_identity_is_not_a_proof(mp3_samples):
    result = identity(mp3_samples['original'], cancelled=lambda: True)
    assert result.status == 'CANCELLED' and result.audio_digest is None


def test_identity_is_read_only_and_deterministic(mp3_samples):
    path = mp3_samples['original']; before = path.read_bytes(); stat = path.stat()
    a, b = identity(path), identity(path)
    assert a.audio_digest == b.audio_digest and a.full_sha256 == b.full_sha256
    assert path.read_bytes() == before and path.stat().st_mtime_ns == stat.st_mtime_ns


def test_failed_tag_analysis_is_error_not_a_partial_proof(mp3_samples,monkeypatch):
    api=importlib.import_module('audio_library_organizer.audio.identity')
    from mutagen import MutagenError
    def unavailable(*args,**kwargs):
        raise MutagenError('ID3 analysis unavailable')
    monkeypatch.setattr(api,'ID3',unavailable)
    result=identity(mp3_samples['original'])
    assert result.status=='ERROR' and result.audio_digest is None
