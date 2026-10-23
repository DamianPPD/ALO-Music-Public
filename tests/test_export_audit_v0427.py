"""Read-only audit of the existing copy contract, on synthetic material only."""
import errno
import stat

from audio_adoption_fixtures import mp3_samples, copy_audio
from test_export_preflight_v0427 import preflight
from test_export_window_v0427 import export_window, until, no_unhandled_qt_errors
from audio_library_organizer.jobs import exporter, legacy_adoption
from audio_library_organizer.safety import copy_pipeline
from audio_library_organizer.ui.workers import ExportWorker


def test_audit_tags_are_written_only_in_fresh_private_copy_and_cleanup_finishes(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    before = {item.track.path: item.track.path.read_bytes() for item in worker.plan.items}
    original, inspected = exporter.write_resolved_tags, []

    def tags(staged, track, **kwargs):
        assert staged.parent.name.startswith('.alo-copy-')
        assert staged.parent.parent == paths.ready
        assert staged != track.path
        assert stat.S_IMODE(staged.stat().st_mode) == stat.S_IMODE(track.path.stat().st_mode)
        assert not (paths.ready / staged.name).exists()
        inspected.append(staged)
        return original(staged, track, **kwargs)

    monkeypatch.setattr(exporter, 'write_resolved_tags', tags)
    worker.run()
    assert not errors and results[0].created == 2 and len(inspected) == 2
    assert not list(paths.ready.glob('.alo-copy-*'))
    assert all(path.read_bytes() == data for path, data in before.items())
    assert not repo.list_managed_bindings()  # A copy is not automatic ownership approval.


def test_audit_tag_failure_plus_cleanup_failure_preserves_error_and_exposes_staging_to_inventory(preflight, monkeypatch):
    _, repo, paths, worker, results, errors, events = preflight
    before = {item.track.path: item.track.path.read_bytes() for item in worker.plan.items}

    def refused_tags(*args, **kwargs):
        raise PermissionError(errno.EACCES, 'controlled metadata write denied')

    def refused_cleanup(path):
        raise PermissionError(errno.EACCES, 'controlled private cleanup denied', str(path))

    monkeypatch.setattr(exporter, 'write_resolved_tags', refused_tags)
    monkeypatch.setattr(copy_pipeline.shutil, 'rmtree', refused_cleanup)
    worker.run()
    assert not errors and len(results) == 1
    result = results[0]
    assert (result.created, result.failed, result.processed) == (0, 2, 2)
    assert {outcome.status for outcome in result.outcomes} == {'tag_error'}
    assert all('controlled metadata write denied' in outcome.error for outcome in result.outcomes)
    assert len(result.cleanup_warnings) == 2
    assert all('controlled private cleanup denied' in warning for warning in result.cleanup_warnings)
    staged = set(paths.ready.glob('.alo-copy-*/*.mp3'))
    assert len(staged) == 2 and not list(paths.ready.glob('*.mp3'))
    scanned, observations = legacy_adoption._physical_inventory(paths.root, lambda: False)
    assert staged <= set(scanned)  # Confirmed scope issue to report, not repair here.
    assert all(path.read_bytes() == data for path, data in before.items())


def test_audit_repeat_worker_blocks_existing_outputs_while_low_level_copy_uses_unique_names(preflight):
    _, repo, paths, worker, results, errors, events = preflight
    worker.run()
    assert not errors and results[0].created == 2
    first = {path: path.read_bytes() for path in results[0].copied}
    assert worker.plan.preview_metrics() == {'name_conflicts': 0, 'existing_targets': 2, 'will_overwrite': 0}
    second = ExportWorker(worker.plan, adoption_repository=repo, library_root=paths.root)
    again, refusals = [], []
    second.finished.connect(again.append)
    second.failed.connect(refusals.append)
    second.run()
    assert not again and len(refusals) == 1 and 'creation blocked' in refusals[0]
    assert set(paths.ready.glob('*.mp3')) == set(first)
    assert not repo.list_managed_bindings()
    # This is a low-level engine contract, not a bypass used by MainWindow.
    raw_engine = exporter.execute_copy_plan(worker.plan)
    assert raw_engine.created == 2 and set(raw_engine.copied).isdisjoint(first)
    assert all(path.read_bytes() == data for path, data in first.items())
    assert not list(paths.ready.glob('.alo-copy-*'))


def test_audit_unbound_check_does_not_invent_source_only_state(export_window, mp3_samples):
    window, tracks, summaries = export_window
    for track in tracks:
        copy_audio(mp3_samples['original'], track.path)
        info = track.path.stat()
        track.sha256 = copy_pipeline.sha256_file(track.path)
        track.size_bytes, track.mtime_ns = info.st_size, info.st_mtime_ns
        window.repository.upsert_track(track)
    window.refresh_data()
    assert window.repository.get_file_state(tracks[0].track_id) is None
    assert window.library._file_presentation(tracks[0]).state is None
    window._check_library_clicked()
    until(lambda: window._thread is None)
    cached = window.repository.get_file_state(tracks[0].track_id)
    assert cached and cached.facts.managed_expected is None
    assert cached.evaluation.state is None
    assert window.last_reconciliation_result.files[0].evaluation.reason == 'MANAGED_EXPECTATION_UNKNOWN'
    assert window.library._file_presentation(tracks[0]).state is None
    window.refresh_data()
    assert window.library._file_presentation(tracks[0]).state is None


def test_audit_approved_adoption_keeps_desired_snapshot_unknown_in_real_check(export_window, mp3_samples):
    from audio_library_organizer.jobs.file_reconciliation import check_library
    window, tracks, summaries = export_window
    paths = window.app_settings.library
    for track, sample in zip(tracks, ('original', 'different_tail')):
        copy_audio(mp3_samples[sample], track.path)
        info = track.path.stat()
        track.sha256 = copy_pipeline.sha256_file(track.path)
        track.size_bytes, track.mtime_ns = info.st_size, info.st_mtime_ns
        window.repository.upsert_track(track)
    output = copy_audio(mp3_samples['original'], paths.ready / 'synthetic-adopted.mp3')
    inventory = legacy_adoption.inventory_legacy_outputs(window.repository, library_root=paths.root)
    proposal = next(p for p in inventory.proposals if p.track_id == tracks[0].track_id and p.can_adopt)
    legacy_adoption.adopt_legacy_output(window.repository, proposal.proposal_id,
                                        confirmed=True, library_root=paths.root)
    checked = check_library(window.repository, library_root=paths.root)
    observation = next(item for item in checked.files if item.track_id == tracks[0].track_id)
    assert observation.evaluation.state is None
    assert observation.evaluation.reason == 'OUTPUT_SNAPSHOT_UNKNOWN'
    cached = window.repository.get_file_state(tracks[0].track_id)
    assert cached.facts.managed_expected is True and cached.facts.desired is None
    assert cached.facts.applied is not None
    assert len(window.repository.list_managed_bindings()) == 1
    assert output.is_file()  # Correctly adopted data are still deliberately not declared clean.
    window.refresh_data()
    assert window.library._file_presentation(tracks[0]).state is None
