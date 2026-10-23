from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock

import pytest

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs import exporter
from audio_library_organizer.safety import copy_pipeline


def make_plan(tmp_path, statuses=('ready', 'review', 'duplicate', 'not_selected')):
    library = LibraryPaths(tmp_path / 'library')
    library.ensure_created()
    tracks = []
    for index, status in enumerate(statuses):
        source = tmp_path / f'source-{index}.mp3'
        source.write_bytes(b'synthetic audio ' + bytes([index]))
        tracks.append(TrackRecord(path=source, status=status, artist='Artist', title='Title',
                                  year='2000', genre='House', bpm=128))
    return exporter.ExportPlan.from_tracks(tracks, library), library


def test_cancel_before_first_item_has_no_outputs(tmp_path):
    plan, library = make_plan(tmp_path)
    cancelled = Event()
    cancelled.set()
    result = exporter.execute_copy_plan(plan, cancelled=cancelled.is_set)
    assert (result.planned, result.processed, result.created, result.failed, result.remaining) == (4, 0, 0, 0, 4)
    assert result.cancelled and result.status == 'cancelled'
    assert not list(library.root.rglob('*.mp3'))


@pytest.mark.parametrize('stop_phase', ['raw_verified', 'final_verified'])
def test_cancel_finishes_current_item_and_keeps_sources(tmp_path, stop_phase):
    plan, library = make_plan(tmp_path)
    before = {item.track.path: (item.track.path.read_bytes(), item.track.path.stat().st_mtime_ns) for item in plan.items}
    cancelled, events, progress = Event(), [], []

    def observe(event):
        events.append(event)
        if event.phase == stop_phase:
            cancelled.set()

    result = exporter.execute_copy_plan(plan, cancelled=cancelled.is_set, event=observe,
                                       progress=lambda *args: progress.append(args))
    assert (result.processed, result.created, result.failed, result.remaining) == (1, 1, 0, 3)
    assert result.cancelled and result.status == 'cancelled'
    assert [p for p in library.root.rglob('*.mp3')] == list(result.copied)
    assert result.verified[0].raw_copy_sha256_match
    assert result.outcomes[0].final_sha256 == copy_pipeline.sha256_file(result.copied[0])
    assert events[0].processed == 0 and events[-1].processed == 1
    assert events[-1].created == 1 and events[-1].remaining == 3
    assert next(e for e in events if e.phase == 'tags_written').created == 0
    assert progress == [(1, 4, 'source-0.mp3')]
    for path, snapshot in before.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == snapshot


def test_all_categories_are_created_and_counted_by_destination(tmp_path):
    plan, library = make_plan(tmp_path)
    result = exporter.execute_copy_plan(plan)
    assert (result.planned, result.processed, result.created, result.failed, result.skipped, result.remaining) == (4, 4, 4, 0, 0, 0)
    assert result.category_counts == {'ready': 1, 'review': 1, 'not_selected': 2}
    assert result.status == 'success' and result.elapsed_seconds >= 0
    assert {p.parent for p in result.copied} == {library.ready, library.review, library.not_selected}


@pytest.mark.parametrize('failure', ['raw', 'tag', 'final'])
def test_failed_owned_copy_is_removed_and_counted_once(tmp_path, monkeypatch, failure):
    plan, library = make_plan(tmp_path, ('ready',))
    existing = library.ready / plan.items[0].filename
    existing.write_bytes(b'previous output must survive')
    if failure == 'raw':
        monkeypatch.setattr(exporter, 'verify_exact_copy', lambda *args, **kwargs: False)
    elif failure == 'tag':
        def fail_tags(path, *args, **kwargs):
            path.write_bytes(b'partial tag write')
            raise OSError('controlled tag error')
        monkeypatch.setattr(exporter, 'write_resolved_tags', fail_tags)
    else:
        monkeypatch.setattr(exporter, 'write_resolved_tags', lambda path, *args, **kwargs: path.write_bytes(b''))
    result = exporter.execute_copy_plan(plan)
    assert (result.processed, result.created, result.failed, result.remaining) == (1, 0, 1, 0)
    assert result.status == 'problems'
    assert result.outcomes[0].status == ('tag_error' if failure == 'tag' else 'verification_error')
    assert not result.verified and not result.copied
    assert len(result.errors) + len(result.verification_errors) == 1
    assert list(library.ready.iterdir()) == [existing]
    assert existing.read_bytes() == b'previous output must survive'


def test_concurrent_copies_never_share_or_overwrite_a_destination(tmp_path, monkeypatch):
    sources = [tmp_path / 'a.wav', tmp_path / 'b.wav']
    for index, source in enumerate(sources):
        source.write_bytes(bytes([index]) * 4096)
    destination = tmp_path / 'outputs'
    barrier, lock, calls = Barrier(2), Lock(), 0
    original = copy_pipeline._unique_path

    def same_initial_candidate(directory, filename):
        nonlocal calls
        candidate = original(directory, filename)
        with lock:
            calls += 1
            wait = calls <= 2
        if wait:
            barrier.wait(timeout=5)
        return candidate

    monkeypatch.setattr(copy_pipeline, '_unique_path', same_initial_candidate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(lambda source: copy_pipeline.copy_without_overwrite(source, destination, 'same.wav'), sources))
    assert len(set(outputs)) == 2
    assert [p.read_bytes() for p in outputs] == [p.read_bytes() for p in sources]


def test_partial_io_copy_is_cleaned_up_without_touching_previous_output(tmp_path, monkeypatch):
    source = tmp_path / 'source.wav'
    source.write_bytes(b'audio payload')
    destination = tmp_path / 'output'
    destination.mkdir()
    previous = destination / 'source.wav'
    previous.write_bytes(b'old output')

    def partial_read(source_handle, target_handle, *args, **kwargs):
        target_handle.write(source_handle.read(3))
        raise OSError('controlled disk error')

    monkeypatch.setattr(copy_pipeline.shutil, '_USE_CP_SENDFILE', False)
    monkeypatch.setattr(copy_pipeline.shutil, 'copyfileobj', partial_read)
    with pytest.raises(OSError, match='controlled disk error'):
        copy_pipeline.copy_without_overwrite(source, destination)
    assert list(destination.iterdir()) == [previous]
    assert previous.read_bytes() == b'old output'
    assert source.read_bytes() == b'audio payload'


def test_cleanup_refuses_a_replaced_foreign_file(tmp_path, monkeypatch):
    plan, library = make_plan(tmp_path, ('ready',))
    held = tmp_path / 'original-owned-file'

    def replace_and_fail(path, *args, **kwargs):
        path.rename(held)
        (library.ready / plan.items[0].filename).write_bytes(b'foreign replacement')
        raise OSError('controlled replacement')

    monkeypatch.setattr(exporter, 'write_resolved_tags', replace_and_fail)
    result = exporter.execute_copy_plan(plan)
    target = library.ready / plan.items[0].filename
    assert target.read_bytes() == b'foreign replacement'
    assert result.failed == 1 and result.created == 0


def test_failure_never_unlinks_a_shared_final_destination(tmp_path, monkeypatch):
    plan, library = make_plan(tmp_path, ('ready',))
    target = library.ready / plan.items[0].filename
    held = tmp_path / 'owned-file-held'
    original_unlink = Path.unlink
    shared_unlinks = []

    def racing_unlink(path, *args, **kwargs):
        if path == target:
            shared_unlinks.append(path)
            path.rename(held)
            path.write_bytes(b'foreign replacement arriving after ownership check')
        return original_unlink(path, *args, **kwargs)

    def fail_tags(*args, **kwargs):
        raise OSError('controlled tag failure')

    monkeypatch.setattr(Path, 'unlink', racing_unlink)
    monkeypatch.setattr(exporter, 'write_resolved_tags', fail_tags)
    result = exporter.execute_copy_plan(plan)
    assert result.failed == 1 and result.created == 0
    assert shared_unlinks == [], 'Cleanup touched a shared final pathname and deleted the replacement'


def test_cleanup_failure_after_publication_does_not_lose_a_verified_output(tmp_path, monkeypatch):
    plan, library = make_plan(tmp_path, ('ready',))
    def fail_cleanup(*args, **kwargs):
        raise OSError('controlled private staging cleanup failure')
    monkeypatch.setattr(copy_pipeline.shutil, 'rmtree', fail_cleanup)
    result = exporter.execute_copy_plan(plan)
    assert result.created == 1 and result.failed == 0 and result.processed == 1
    assert result.cleanup_warnings and 'controlled private staging cleanup failure' in result.cleanup_warnings[0]
    assert result.outcomes[0].status == 'verified' and result.copied[0].is_file()
    assert copy_pipeline.sha256_file(result.copied[0]) == result.outcomes[0].final_sha256
    assert result.status == 'problems'


@pytest.mark.parametrize('filename', ['../escape.wav', 'ABSOLUTE', 'folder/file.wav', 'folder\\file.wav', 'C:escape.wav'])
def test_copy_rejects_non_component_names(tmp_path, filename):
    source = tmp_path / 'source.wav'
    source.write_bytes(b'audio')
    if filename == 'ABSOLUTE':
        filename = str(tmp_path / 'escape.wav')
    with pytest.raises(ValueError):
        copy_pipeline.copy_without_overwrite(source, tmp_path / 'output', filename)


def test_audit_contains_every_planned_item_after_stop(tmp_path):
    import csv
    from audio_library_organizer.jobs.reporting import export_verification_csv
    plan, library = make_plan(tmp_path)
    cancelled = Event()
    result = exporter.execute_copy_plan(plan, cancelled=cancelled.is_set,
        event=lambda event: cancelled.set() if event.phase == 'item_finished' else None)
    report = export_verification_csv(result, library.reports / 'audit.csv', plan=plan)
    with report.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert [row['status'] for row in rows] == ['verified', 'not_started', 'not_started', 'not_started']
    assert rows[0]['final_sha256'] == copy_pipeline.sha256_file(result.copied[0])
    assert all(row['cancelled'] == 'True' and row['remaining'] == '3' for row in rows)
    assert all(row['verified'] == 'False' and not row['destination_path'] for row in rows[1:])


def test_io_error_does_not_hide_later_success_or_double_count(tmp_path, monkeypatch):
    plan, library = make_plan(tmp_path)
    plan.items[0].track.path.unlink()
    result = exporter.execute_copy_plan(plan)
    assert (result.processed, result.created, result.failed, result.remaining) == (4, 3, 1, 0)
    assert result.outcomes[0].status == 'copy_error'
    assert result.category_counts == {'ready': 0, 'review': 1, 'not_selected': 2}
    assert len(result.errors) == 1 and not result.verification_errors


def test_cancel_during_last_item_is_not_reported_as_full_success(tmp_path):
    plan, library = make_plan(tmp_path, ('ready',))
    cancelled = Event()
    result = exporter.execute_copy_plan(plan, cancelled=cancelled.is_set,
        event=lambda event: cancelled.set() if event.phase == 'tags_written' else None)
    assert result.created == 1 and result.remaining == 0 and result.failed == 0
    assert result.status == 'cancelled'


def test_dangling_link_is_an_occupied_name_not_an_overwrite(tmp_path):
    source, output = tmp_path / 'source.wav', tmp_path / 'output'
    source.write_bytes(b'new copy')
    output.mkdir()
    link = output / 'source.wav'
    try:
        link.symlink_to(tmp_path / 'absent')
    except OSError:
        pytest.skip('Creating symlinks is unavailable on this platform')
    result = copy_pipeline.copy_without_overwrite(source, output)
    assert result.name == 'source (2).wav'
    assert link.is_symlink() and not (tmp_path / 'absent').exists()
    assert result.read_bytes() == source.read_bytes()


def _process_export(source, root, barrier, queue):
    try:
        track = TrackRecord(path=Path(source), status='ready', artist='Artist', title='Title',
                            year='2000', genre='House', bpm=128, proposed_filename='same.mp3')
        plan = exporter.ExportPlan.from_tracks([track], LibraryPaths(Path(root)))
        barrier.wait(timeout=6)
        result = exporter.execute_copy_plan(plan)
        queue.put((result.status, [str(path) for path in result.copied], result.outcomes[0].final_sha256))
    except BaseException as exc:
        queue.put(('error', str(exc), ''))
        raise


def test_two_process_exports_publish_distinct_verified_files(tmp_path):
    import multiprocessing
    context = multiprocessing.get_context('spawn')
    barrier, queue = context.Barrier(2), context.Queue()
    root = tmp_path / 'library'
    LibraryPaths(root).ensure_created()
    processes = []
    for index in range(2):
        source = tmp_path / f'source-{index}.mp3'
        source.write_bytes(b'synthetic payload ' + bytes([index]))
        process = context.Process(target=_process_export, args=(str(source), str(root), barrier, queue))
        process.start()
        processes.append(process)
    results = [queue.get(timeout=10) for _ in processes]
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0
    assert all(result[0] == 'success' for result in results)
    outputs = [Path(result[1][0]) for result in results]
    assert len(set(outputs)) == 2
    assert all(copy_pipeline.sha256_file(path) == result[2] for path, result in zip(outputs, results))
    assert not list(root.rglob('.alo-copy-*'))
    queue.close()


def test_real_written_metadata_and_final_digest(tmp_path):
    from mutagen.id3 import ID3
    plan, library = make_plan(tmp_path, ('ready',))
    source = plan.items[0].track.path
    original = source.read_bytes()
    result = exporter.execute_copy_plan(plan)
    tags = ID3(result.copied[0])
    # Existing ALO tag policy appends BPM to the exported title.
    assert tags['TPE1'].text == ['Artist'] and tags['TIT2'].text == ['Title [128bpm]']
    assert result.outcomes[0].raw_verified
    assert result.outcomes[0].final_sha256 == copy_pipeline.sha256_file(result.copied[0])
    assert result.outcomes[0].final_sha256 != copy_pipeline.sha256_file(source)
    assert source.read_bytes() == original


def test_publication_failure_does_not_expose_a_partial_file(tmp_path, monkeypatch):
    plan, library = make_plan(tmp_path, ('ready',))
    def unavailable(*args, **kwargs):
        raise OSError('controlled unsupported atomic publication')
    monkeypatch.setattr(copy_pipeline, '_publish_without_overwrite', unavailable)
    result = exporter.execute_copy_plan(plan)
    assert result.status == 'problems' and result.failed == 1 and result.created == 0
    assert result.outcomes[0].status == 'copy_error' and result.outcomes[0].raw_verified
    assert not list(library.root.rglob('*.mp3')) and not list(library.root.rglob('.alo-copy-*'))
