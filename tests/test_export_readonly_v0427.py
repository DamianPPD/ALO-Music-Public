"""Writable generated copies; only synthetic audio and private test folders."""
import json
import os
import stat
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3

from audio_adoption_fixtures import mp3_samples, copy_audio
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs import exporter
from audio_library_organizer.safety import copy_pipeline


def snapshot(path):
    info = path.stat()
    return copy_pipeline.sha256_file(path), stat.S_IMODE(info.st_mode), info.st_mtime_ns


@pytest.fixture(params=['mp3', 'flac'])
def audio_source(request, tmp_path, mp3_samples):
    source = tmp_path / ('synthetic-source.' + request.param)
    if request.param == 'mp3':
        copy_audio(mp3_samples['original'], source, title='Original source tags', cover=True)
    else:
        import numpy as np
        import soundfile as sf
        sf.write(source, np.zeros(4410, dtype=np.float32), 44100, format='FLAC')
        tags = FLAC(source)
        tags['title'] = ['Original source tags']
        tags.save()
    return source


def plan_for(source, tmp_path):
    paths = LibraryPaths(tmp_path / 'isolated-library')
    paths.ensure_created()
    track = TrackRecord(path=source, artist='Synthetic artist', title='Generated output',
                        album='Synthetic album', year='2001', genre='House', bpm=128,
                        status='ready', sha256=copy_pipeline.sha256_file(source))
    return exporter.ExportPlan.from_tracks([track], paths), paths


def require_readonly_enforcement(path):
    # A chmod-only test under an unrestricted root would not prove a write denial.
    try:
        with path.open('r+b'):
            pass
    except PermissionError:
        return
    pytest.skip('This filesystem/credential combination bypasses read-only permissions.')


def test_readonly_original_exports_with_real_mutagen_and_unchanged_source(audio_source, tmp_path):
    audio_source.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    require_readonly_enforcement(audio_source)
    before = snapshot(audio_source)
    plan, paths = plan_for(audio_source, tmp_path)
    preparation = []

    def observe(event):
        if event.phase == 'tagging':
            preparation.append({'mode': oct(stat.S_IMODE(event.destination.stat().st_mode)),
                                'private': event.destination.parent.name.startswith('.alo-copy-')})

    result = exporter.execute_copy_plan(plan, event=observe)
    print(json.dumps({'format': audio_source.suffix, 'source_mode': oct(before[1]),
                      'preparation': preparation, 'created': result.created,
                      'statuses': [outcome.status for outcome in result.outcomes],
                      'errors': result.errors, 'cleanup_warnings': result.cleanup_warnings}))
    assert snapshot(audio_source) == before
    assert result.created == 1 and result.failed == 0, result.errors
    assert result.status == 'success' and not result.cleanup_warnings
    output = result.copied[0]
    assert preparation and preparation[0]['private']
    assert output.stat().st_mode & stat.S_IWUSR
    if output.suffix == '.mp3':
        assert str(ID3(output)['TIT2']) == 'Generated output [128bpm]'
        assert ID3(output).getall('APIC')
    else:
        assert FLAC(output)['title'] == ['Generated output [128bpm]']
    assert result.outcomes[0].final_sha256 == copy_pipeline.sha256_file(output)
    assert result.verified[0].raw_copy_sha256_match
    assert not list(paths.ready.glob('.alo-copy-*'))


def test_generated_copy_keeps_fresh_mode_and_time_instead_of_source_attributes(tmp_path):
    source = tmp_path / 'synthetic.bin'
    source.write_bytes(b'synthetic payload')
    source.chmod(0o555)
    os.utime(source, ns=(1_000_000_000, 1_000_000_000))
    before = snapshot(source)
    destination = tmp_path / 'output'
    destination.mkdir()
    probe = destination / 'fresh-mode-probe'
    probe.touch()
    fresh_mode = stat.S_IMODE(probe.stat().st_mode)
    observed = []
    output = copy_pipeline.copy_without_overwrite(
        source, destination,
        prepare=lambda staged: observed.append((stat.S_IMODE(staged.stat().st_mode), staged.stat().st_mtime_ns)))
    assert observed[0][0] == fresh_mode
    assert observed[0][1] != before[2]
    assert stat.S_IMODE(output.stat().st_mode) == fresh_mode
    assert output.read_bytes() == source.read_bytes()
    assert snapshot(source) == before


def test_bad_metadata_keeps_real_exception_and_never_publishes(audio_source, tmp_path):
    plan, paths = plan_for(audio_source, tmp_path)
    plan.items[0].track.title = 'Invalid surrogate \ud800'
    before = snapshot(audio_source)
    result = exporter.execute_copy_plan(plan)
    assert (result.created, result.failed, result.processed) == (0, 1, 1)
    assert result.outcomes[0].status == 'tag_error'
    assert 'surrogate' in result.outcomes[0].error
    assert result.errors and result.status == 'problems'
    assert not list(paths.ready.glob('*.mp3')) and not list(paths.ready.glob('*.flac'))
    assert snapshot(audio_source) == before


def test_real_writer_denial_is_reported_without_publishing(audio_source, tmp_path, monkeypatch):
    plan, paths = plan_for(audio_source, tmp_path)
    before = snapshot(audio_source)
    original = exporter.write_resolved_tags
    entered = []

    def deny_private_write(staged, *args, **kwargs):
        assert staged.parent.name.startswith('.alo-copy-') and staged != audio_source
        staged.chmod(0o444)
        require_readonly_enforcement(staged)
        entered.append(staged)
        return original(staged, *args, **kwargs)

    monkeypatch.setattr(exporter, 'write_resolved_tags', deny_private_write)
    result = exporter.execute_copy_plan(plan)
    assert len(entered) == 1
    assert (result.created, result.failed) == (0, 1)
    assert result.outcomes[0].status == 'tag_error'
    assert 'Permission denied' in result.outcomes[0].error
    assert result.errors and not result.copied and not result.verified
    assert not list(paths.ready.glob('*.mp3')) and not list(paths.ready.glob('*.flac'))
    assert snapshot(audio_source) == before


def test_cover_failure_precedes_tag_writer_and_preserves_full_error(tmp_path, mp3_samples, monkeypatch):
    source = copy_audio(mp3_samples['original'], tmp_path / 'synthetic.mp3')
    plan, paths = plan_for(source, tmp_path)
    before = snapshot(source)
    plan.items[0].track.cover_art_url = 'https://synthetic.invalid/cover.png'
    plan.items[0].track.cover_choice = 'external'

    class RefusedArtwork:
        def fetch_url(self, url):
            assert url == 'https://synthetic.invalid/cover.png'
            raise OSError('controlled cover preparation failure; no network used')

    monkeypatch.setattr(exporter, 'write_resolved_tags', lambda *a, **k: pytest.fail('writer must not run'))
    result = exporter.execute_copy_plan(plan, artwork_client=RefusedArtwork())
    assert (result.created, result.failed) == (0, 1)
    assert result.outcomes[0].status == 'tag_error'
    assert 'controlled cover preparation failure; no network used' in result.errors[0]
    assert not list(paths.ready.glob('*.mp3'))
    assert snapshot(source) == before


def test_export_does_not_clean_older_prefix_named_user_directory(tmp_path, mp3_samples):
    source = copy_audio(mp3_samples['original'], tmp_path / 'synthetic.mp3')
    plan, paths = plan_for(source, tmp_path)
    old = paths.ready / '.alo-copy-user-owned'
    old.mkdir()
    unknown = old / 'foreign.txt'
    unknown.write_bytes(b'preserve unknown user data')
    before = snapshot(unknown)
    result = exporter.execute_copy_plan(plan)
    assert result.created == 1 and result.failed == 0
    assert old.is_dir() and snapshot(unknown) == before
    assert list(paths.ready.glob('.alo-copy-*')) == [old]
