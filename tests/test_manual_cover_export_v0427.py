"""Real producer, image bytes, SQLite and Qt export boundaries."""
import csv
from dataclasses import asdict
import hashlib
import io
import os
from pathlib import Path
import sqlite3
from threading import Event
from time import monotonic

import pytest
from mutagen.id3 import ID3
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent
from shiboken6 import isValid

from audio_adoption_fixtures import copy_audio, mp3_samples
from audio_library_organizer.audio.identity import inspect_audio
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs import exporter
from audio_library_organizer.safety.copy_pipeline import sha256_file
from audio_library_organizer.storage.repository import LibraryRepository
from test_export_preflight_v0427 import preflight
from test_export_window_v0427 import export_window, no_unhandled_qt_errors


def set_cover(repo, track, path, *, color=None):
    if color is not None:
        Image.new('RGB', (12, 12), color).save(path)
    track.manual_cover_path = str(path)
    track.cover_choice = 'manual'
    repo.upsert_track(track)


def assert_embedded_color(path, expected):
    (picture,) = ID3(path).getall('APIC')
    assert picture.mime == 'image/jpeg'
    with Image.open(io.BytesIO(picture.data)) as image:
        actual = image.getpixel((0, 0))
    assert all(abs(a - b) <= 3 for a, b in zip(actual, expected))


def wait_for_export(window):
    deadline = monotonic() + 45
    idle = Event()
    while window._thread is not None and monotonic() < deadline:
        QCoreApplication.processEvents()
        idle.wait(0.005)
    assert window._thread is None, 'Export did not tear down its worker within 45 seconds'
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize('stop_after', [None, 3])
def test_empty_output_library_isolates_missing_cover_and_persists_bindings(
        export_window, tmp_path, mp3_samples, monkeypatch, stop_after):
    window, tracks, summaries = export_window
    repo = window.repository
    paths = window.app_settings.library
    for i in range(2, 14):
        path = copy_audio(mp3_samples['original'], tracks[0].path.parent / f'track-{i:02}.mp3')
        stat = path.stat()
        track = TrackRecord(path=path, artist='Artist', title=f'Title {i:02}', year='2000',
                            genre='House', bpm=128, status='ready', locked_fields={'__status__'},
                            sha256=sha256_file(path), size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
        repo.upsert_track(track)
        tracks.append(track)
    set_cover(repo, tracks[0], tmp_path / 'red.jpg', color=(255, 0, 0))
    set_cover(repo, tracks[1], tmp_path / 'green.png', color=(0, 255, 0))
    missing = tmp_path / 'missing-manual.png'
    # The middle record is the only one with unavailable artwork.
    set_cover(repo, tracks[7], missing)
    window.refresh_data()
    assert all(not list(root.iterdir()) for root in (paths.ready, paths.review, paths.not_selected))
    before = {track.track_id: asdict(repo.get_track(track.track_id)) for track in tracks}
    originals = {track.path: (track.path.read_bytes(), track.path.stat().st_mtime_ns) for track in tracks}

    if stop_after is not None:
        original_execute = exporter.execute_copy_plan

        def execute(plan, **kwargs):
            send = kwargs['event']

            def observe(event):
                send(event)
                if event.phase == 'item_finished' and event.created == stop_after:
                    window._worker.cancel()

            return original_execute(plan, **{**kwargs, 'event': observe})

        monkeypatch.setattr(exporter, 'execute_copy_plan', execute)
    window.export_library()
    thread, worker = window._thread, window._worker
    assert thread is not None and worker is not None
    try:
        wait_for_export(window)
    finally:
        if window._thread is not None:
            window._request_export_stop()
            wait_for_export(window)
    result = window._export_result
    assert not isValid(thread) and not isValid(worker)
    assert not result.fatal_error and len(summaries) == 1
    assert result.planned == 14
    assert result.created == (13 if stop_after is None else stop_after)
    assert result.failed == 0
    assert not list(paths.root.rglob('.alo-copy-*'))
    if stop_after is None:
        assert (result.processed, result.remaining, result.skipped) == (14, 0, 1)
        omitted = next(outcome for outcome in result.outcomes if outcome.source == tracks[7].path)
        assert omitted.status == 'skipped' and omitted.destination is None
        assert 'Nie można zweryfikować ręcznej okładki' in omitted.error
        assert tracks[7].title in omitted.error and str(missing) in omitted.error
        assert 'pominięto' in omitted.error.lower()
        assert summaries[0][0].outcome == 'problems'
        assert 'okładk' in summaries[0][0].notice_text
        assert str(missing) not in summaries[0][0].notice_text
        with summaries[0][0].report.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 14 and sum(row['status'] == 'skipped' for row in rows) == 1
        assert any(str(missing) in row['error'] for row in rows)
    else:
        assert result.cancelled and result.remaining > 0 and summaries[0][0].outcome == 'cancelled'

    reopened = LibraryRepository(paths.database)
    reopened.initialize()
    bindings = {binding.track_id: binding for binding in reopened.list_managed_bindings()}
    by_source = {track.path: track for track in tracks}
    verified = {by_source[item.source].track_id: item for item in result.outcomes if item.status == 'verified'}
    assert bindings.keys() == verified.keys()
    assert tracks[7].track_id not in bindings
    from audio_library_organizer.domain.file_state import FileState
    from audio_library_organizer.jobs.file_reconciliation import check_library

    checked = check_library(reopened, library_root=paths.root)
    persisted = {entry.track_id: entry for entry in checked.files}
    for track_id in bindings:
        assert persisted[track_id].evaluation.state == FileState.IN_LIBRARY
        assert persisted[track_id].facts.managed_expected
        assert not persisted[track_id].evaluation.is_confirmed
    assert not persisted[tracks[7].track_id].facts.managed_expected
    assert set(paths.root.rglob('*.mp3')) == set(result.copied)
    for track_id, item in verified.items():
        binding = bindings[track_id]
        target = Path(binding.locator(paths.root))
        proof = inspect_audio(target)
        assert target == item.destination
        assert proof.status == 'VALID' and proof.full_sha256 == binding.expected_sha256 == item.final_sha256
        assert proof.audio_digest == binding.audio_digest == inspect_audio(item.source).audio_digest
    if stop_after is None:
        assert_embedded_color(verified[tracks[0].track_id].destination, (255, 0, 0))
        assert_embedded_color(verified[tracks[1].track_id].destination, (0, 255, 0))
        assert verified[tracks[2].track_id].destination.is_file()
    assert {track.track_id: asdict(reopened.get_track(track.track_id)) for track in tracks} == before
    assert all((path.read_bytes(), path.stat().st_mtime_ns) == value for path, value in originals.items())
    with sqlite3.connect(paths.database) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('action', ['bytes', 'replace_same_bytes', 'metadata_only', 'corrupt_image', 'late_change'])
def test_manual_cover_changes_are_checked_at_the_correct_boundary(preflight, tmp_path, action):
    _, repo, paths, worker, results, errors, _ = preflight
    track = worker.plan.items[0].track
    cover = tmp_path / 'manual.png'
    set_cover(repo, track, cover, color=(255, 0, 0))
    if action == 'corrupt_image':
        cover.write_bytes(b'not an image')
    triggered = []

    def inject(event):
        phase = 'tags_written' if action == 'late_change' else 'item_started'
        if triggered or event.phase != phase or event.source != track.path:
            return
        triggered.append(True)
        if action in ('bytes', 'late_change'):
            Image.new('RGB', (12, 12), (0, 0, 255)).save(cover)
        elif action == 'replace_same_bytes':
            replacement = cover.with_name('replacement.png')
            replacement.write_bytes(cover.read_bytes())
            replacement.replace(cover)
        elif action == 'metadata_only':
            info = cover.stat()
            os.utime(cover, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))

    worker.phase.connect(inject)
    worker.run()
    assert triggered and not errors and len(results) == 1
    result = results[0]
    if action == 'metadata_only':
        assert result.created == 2 and result.skipped == 0
        assert_embedded_color(result.outcomes[0].destination, (255, 0, 0))
    else:
        assert result.created == 1 and result.skipped == 1 and result.failed == 0
        assert result.outcomes[0].status == 'skipped' and result.outcomes[0].destination is None
        assert str(cover) in result.outcomes[0].error
        assert not any(b.track_id == track.track_id for b in repo.list_managed_bindings())
        assert len(list(paths.root.rglob('*.mp3'))) == 1


@pytest.mark.parametrize('action', ['write', 'rename_parent'])
def test_change_during_manual_cover_read_is_denied_or_rejected(preflight, tmp_path, monkeypatch, action):
    _, repo, paths, worker, results, errors, _ = preflight
    track = worker.plan.items[0].track
    cover_dir = tmp_path / 'covers'
    cover_dir.mkdir()
    cover = cover_dir / 'manual.png'
    set_cover(repo, track, cover, color=(255, 0, 0))
    if action == 'rename_parent':
        track.cover_choice = 'auto'
        repo.upsert_track(track)
    replacement = tmp_path / 'blue.png'
    Image.new('RGB', (12, 12), (0, 0, 255)).save(replacement)
    blue = replacement.read_bytes()
    attempt = []
    original_open = io.open

    class RacingRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, *args):
            data = self.stream.read(*args)
            if not attempt:
                try:
                    if action == 'rename_parent':
                        cover_dir.rename(tmp_path / 'moved-covers')
                    else:
                        with original_open(cover, 'wb') as writer:
                            writer.write(blue)
                except PermissionError:
                    attempt.append('denied')
                else:
                    attempt.append('changed')
            return data

    def observed_open(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path == cover and mode == 'rb':
            return RacingRead(stream)
        return stream

    monkeypatch.setattr(io, 'open', observed_open)
    worker.run()
    assert not errors and attempt and len(results) == 1
    result = results[0]
    if os.name == 'nt':
        assert attempt == ['denied'] and result.created == 2
        assert_embedded_color(result.outcomes[0].destination, (255, 0, 0))
    else:
        assert attempt == ['changed'] and result.created == 1 and result.skipped == 1
        assert result.outcomes[0].destination is None
        assert len(list(paths.root.rglob('*.mp3'))) == len(repo.list_managed_bindings()) == 1


def test_unplanned_record_does_not_open_its_manual_cover(preflight, tmp_path, monkeypatch):
    _, repo, _, worker, results, errors, _ = preflight
    source = worker.plan.items[0].track.path
    path = copy_audio(source, source.with_name('out-of-plan.mp3'))
    info = path.stat()
    outside = TrackRecord(path=path, sha256=sha256_file(path), size_bytes=info.st_size,
                          mtime_ns=info.st_mtime_ns)
    cover = tmp_path / 'unplanned.png'
    set_cover(repo, outside, cover, color=(255, 0, 0))
    original_open = io.open

    def observed_open(path, mode='r', *args, **kwargs):
        if path == cover and mode == 'rb':
            raise PermissionError('out-of-plan cover is not readable')
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(io, 'open', observed_open)
    worker.run()
    assert not errors and results[0].created == 2
    assert outside.track_id not in {binding.track_id for binding in repo.list_managed_bindings()}


@pytest.mark.parametrize('choice', ['source', 'auto'])
def test_non_manual_selection_preserves_available_source_cover(preflight, tmp_path, choice):
    _, repo, _, worker, results, errors, _ = preflight
    track = worker.plan.items[0].track
    copy_audio(track.path, track.path.with_name('with-cover.mp3'), cover=True).replace(track.path)
    info = track.path.stat()
    track.size_bytes, track.mtime_ns = info.st_size, info.st_mtime_ns
    track.sha256 = sha256_file(track.path)
    track.cover_choice = choice
    track.manual_cover_path = str(tmp_path / 'unused-missing.png')
    repo.upsert_track(track)
    worker.run()
    assert not errors and results[0].created == 2 and results[0].skipped == 0
    assert_embedded_color(results[0].outcomes[0].destination, (20, 40, 80))


def test_manual_cover_preflight_can_stop_before_copying(preflight, tmp_path):
    _, repo, paths, worker, results, errors, _ = preflight
    track = worker.plan.items[0].track
    set_cover(repo, track, tmp_path / 'red.png', color=(255, 0, 0))
    worker.phase.connect(lambda event: worker.cancel() if event.phase == 'preflight_covers' else None)
    worker.run()
    assert not errors and len(results) == 1 and results[0].cancelled
    assert results[0].stop_phase == 'preflight'
    assert results[0].created == results[0].processed == 0
    assert not list(paths.root.rglob('*.mp3')) and not repo.list_managed_bindings()


def test_missing_cover_english_log_and_report(preflight, tmp_path):
    _, repo, _, worker, results, errors, events = preflight
    worker.language = 'en'
    track = worker.plan.items[0].track
    path = tmp_path / 'missing.png'
    set_cover(repo, track, path)
    worker.run()
    assert not errors and results[0].created == 1 and results[0].skipped == 1
    event = next(event for event in events if event.phase == 'item_skipped')
    assert 'Cannot verify the manual cover' in event.message
    assert 'Export continues' in event.message and str(path) not in event.message
    outcome = results[0].outcomes[0]
    assert str(path) in outcome.error and 'Track skipped.' in outcome.error
    assert event.processed == 1 and event.failed == 0 and event.skipped == 1


def test_manual_cover_export_never_overwrites_a_late_occupied_name(preflight, tmp_path, mp3_samples):
    _, repo, paths, worker, results, errors, _ = preflight
    item = worker.plan.items[0]
    set_cover(repo, item.track, tmp_path / 'red.jpg', color=(255, 0, 0))
    occupied = item.destination_dir / item.filename
    existing = mp3_samples['different_tail'].read_bytes()

    def occupy(event):
        if event.phase == 'item_started' and event.source == item.track.path:
            assert not occupied.exists()
            occupied.write_bytes(existing)

    worker.phase.connect(occupy)
    worker.run()
    assert not errors and results[0].created == 2
    assert occupied.read_bytes() == existing
    outcome = results[0].outcomes[0]
    assert outcome.destination != occupied and outcome.destination.is_file()
    assert_embedded_color(outcome.destination, (255, 0, 0))
    assert all(Path(binding.locator(paths.root)) != occupied for binding in repo.list_managed_bindings())


def test_cover_changed_when_choosing_destination_cannot_publish_stale_artwork(
        preflight, tmp_path, monkeypatch):
    from audio_library_organizer.safety import copy_pipeline

    _, repo, paths, worker, results, errors, _ = preflight
    item = worker.plan.items[0]
    cover = tmp_path / 'manual.png'
    set_cover(repo, item.track, cover, color=(255, 0, 0))
    original = copy_pipeline._unique_path
    changed = []

    def choose(directory, filename):
        if filename == item.filename and not changed:
            Image.new('RGB', (12, 12), (0, 0, 255)).save(cover)
            changed.append(True)
        return original(directory, filename)

    monkeypatch.setattr(copy_pipeline, '_unique_path', choose)
    worker.run()
    assert changed and not errors
    assert results[0].created == 1 and results[0].skipped == 1
    assert results[0].outcomes[0].destination is None
    assert len(list(paths.root.rglob('*.mp3'))) == len(repo.list_managed_bindings()) == 1


def test_oversized_cover_is_omitted_before_reading_its_payload(preflight, tmp_path, monkeypatch):
    _, repo, _, worker, results, errors, _ = preflight
    track = worker.plan.items[0].track
    cover = tmp_path / 'oversized.png'
    with cover.open('wb') as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    set_cover(repo, track, cover)
    original_open = io.open

    class LimitProbe:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, *args):
            pytest.fail('Oversized artwork payload must not be read')

    def observed_open(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return LimitProbe(stream) if path == cover and mode == 'rb' else stream

    monkeypatch.setattr(io, 'open', observed_open)
    worker.run()
    assert not errors and results[0].created == 1 and results[0].skipped == 1
    assert '32 MiB' in results[0].outcomes[0].error


def test_late_cover_refusal_records_published_but_unverified_output(preflight, tmp_path):
    from audio_library_organizer.jobs.reporting import export_verification_csv

    _, repo, paths, worker, results, errors, _ = preflight
    item = worker.plan.items[0]
    cover = tmp_path / 'manual.png'
    set_cover(repo, item.track, cover, color=(255, 0, 0))

    def change(event):
        if event.phase == 'registering' and event.source == item.track.path:
            Image.new('RGB', (12, 12), (0, 0, 255)).save(cover)

    worker.phase.connect(change)
    worker.run()
    assert not errors and results[0].created == 1 and results[0].failed == 1
    outcome = results[0].outcomes[0]
    assert outcome.status == 'registration_error' and outcome.destination.is_file()
    assert inspect_audio(outcome.destination).status == 'VALID'
    assert str(cover) in outcome.error and 'bez powiązania' in outcome.error
    assert item.track.track_id not in {binding.track_id for binding in repo.list_managed_bindings()}
    report = export_verification_csv(results[0], paths.reports / 'audit.csv', plan=worker.plan)
    with report.open(encoding='utf-8-sig', newline='') as stream:
        row = next(csv.DictReader(stream))
    assert row['destination_path'] == str(outcome.destination)
    assert row['final_file_exists'] == 'True' and row['verified'] == 'False'


@pytest.mark.skipif(os.name != 'nt', reason='Requires native Windows and local NTFS')
def test_ntfs_deny_write_through_publication_and_commit(preflight, tmp_path, monkeypatch):
    from audio_library_organizer.jobs import created_output
    from audio_library_organizer.safety import copy_pipeline, windows_file_identity

    _, repo, _, worker, results, errors, _ = preflight
    item = worker.plan.items[0]
    cover = tmp_path / 'manual.png'
    set_cover(repo, item.track, cover, color=(255, 0, 0))
    assert windows_file_identity.capture(cover).leaf.filesystem == 'NTFS'
    original_bytes = cover.read_bytes()
    denied = set()

    def try_write(boundary):
        with pytest.raises(PermissionError):
            with cover.open('wb') as stream:
                stream.write(b'foreign data')
        denied.add(boundary)

    publish = copy_pipeline._publish_without_overwrite
    validate = created_output.ProducerOperation.validate_item

    def observe_publish(staged, target):
        if target.name == item.filename:
            try_write('publish')
        return publish(staged, target)

    def observe_validate(operation, current_item, conn=None):
        if conn is not None and current_item.track.track_id == item.track.track_id:
            try_write('commit')
        return validate(operation, current_item, conn)

    monkeypatch.setattr(copy_pipeline, '_publish_without_overwrite', observe_publish)
    monkeypatch.setattr(created_output.ProducerOperation, 'validate_item', observe_validate)
    worker.run()
    assert denied == {'publish', 'commit'}
    assert not errors and results[0].created == 2
    assert cover.read_bytes() == original_bytes
    assert_embedded_color(results[0].outcomes[0].destination, (255, 0, 0))
    assert len(repo.list_managed_bindings()) == 2
