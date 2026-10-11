"""Stage 2.2: real disposable files/SQLite; managed attestations are synthetic.

Audio bytes need not decode: reconciliation must never invoke an audio probe.
The check may write observation cache only, not tracks, sources or music.
"""
from dataclasses import replace
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sqlite3
from threading import Event
import time

import pytest

from audio_library_organizer.domain.file_state import (
    ConflictReason, FileAvailability, FileFacts, FileObservation, FileState,
    OutputSnapshot, Ownership,
)
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.scanner import SourceScanStatus
from audio_library_organizer.storage.repository import LibraryRepository


def api():
    name = 'audio_library_organizer.jobs.file_reconciliation'
    assert importlib.util.find_spec(name) is not None, 'Missing Stage 2.2 reconciliation API'
    return importlib.import_module(name)


def library(tmp_path, name='A'):
    root = tmp_path / name / 'source'
    root.mkdir(parents=True)
    repo = LibraryRepository(tmp_path / name / 'library.sqlite3')
    repo.initialize()
    repo.register_source(root)
    return repo, root


def record(repo, path, *, content=b'original audio fixture', status='duplicate'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    info = path.stat()
    track = TrackRecord(
        path, size_bytes=info.st_size, mtime_ns=info.st_mtime_ns,
        sha256=hashlib.sha256(content).hexdigest(), status=status,
        artist='Ręczny artysta', title='Ręczny tytuł', album='Ręczny album',
        year='1999', genre='Dance', comment='Zachować', bpm=128,
        locked_fields={'title', '__status__'}, field_sources={'title': 'Ręcznie'},
        field_source_values={'title': {'manual': 'Ręczny tytuł'}},
        original_tags={'title': ['Original']}, filename_override='Manual.mp3',
        proposed_filename='Existing.mp3', cover_choice='manual',
        manual_cover_path='/synthetic/manual-cover.png',
        musicbrainz_recording_id='mb-recording', musicbrainz_release_id='mb-release',
        discogs_release_id='123', audio_recognition={'fingerprint': 'saved', 'score': .9},
        match_reasons=['manual decision'], pre_online_metadata={'title': 'before'},
    )
    repo.upsert_track(track)
    return track


def sql_snapshot(repo, table='tracks'):
    with sqlite3.connect(repo.database_path) as conn:
        return conn.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()


def music_snapshot(*roots):
    return {str(path): (path.read_bytes(), path.stat().st_size,
                        hashlib.sha256(path.read_bytes()).hexdigest())
            for root in roots for path in root.rglob('*')
            if path.is_file() and path.suffix == '.mp3'}


def observations(result):
    return {item.track_id: item for item in result.files}


def attest(track, at, *, managed=None, managed_expected=False, conflict=None):
    return FileFacts(
        track.track_id, at, managed_expected=managed_expected,
        managed=(FileObservation(track.track_id, str(managed), FileAvailability.UNKNOWN, at)
                 if managed is not None else None),
        ownership=Ownership.CONFIRMED if managed_expected else Ownership.UNKNOWN,
        owner_track_id=track.track_id if managed_expected else None,
        desired=OutputSnapshot('synthetic-output', 1, 'version-A') if managed_expected else None,
        applied=OutputSnapshot('synthetic-output', 1, 'version-A') if managed_expected else None,
        conflict=conflict,
    )


def test_check_reports_missing_moved_new_and_conflicting_files_without_mutation(tmp_path):
    repo, root = library(tmp_path)
    present = record(repo, root / 'present.mp3')
    missing = record(repo, root / 'missing.mp3', content=b'deleted fixture')
    missing.path.unlink()
    moved = record(repo, root / 'old.mp3', content=b'moved fixture')
    destination = root / 'nested' / 'renamed.mp3'
    destination.parent.mkdir()
    moved.path.rename(destination)
    ambiguous = record(repo, root / 'ambiguous.mp3', content=b'ambiguous fixture')
    ambiguous.path.unlink()
    for name in ('copy-one.mp3', 'copy-two.mp3'):
        (root / name).write_bytes(b'ambiguous fixture')
    (root / 'new.mp3').write_bytes(b'new independent fixture')
    before_files, before_rows = music_snapshot(root), sql_snapshot(repo)
    before_sources = sql_snapshot(repo, 'sources')

    result = api().check_library(repo, checked_at=100)
    observed = observations(result)
    assert observed[present.track_id].source.availability == FileAvailability.PRESENT
    assert observed[missing.track_id].source.availability == FileAvailability.MISSING
    assert observed[moved.track_id].source.availability == FileAvailability.MISSING
    assert any(c.locator == str(root / 'new.mp3') and c.reason == 'NEW_SOURCE_CANDIDATE'
               for c in result.new_source_candidates)
    suggestion = next(c for c in result.possible_moves if c.track_id == moved.track_id)
    assert suggestion.old_locator == str(moved.path)
    assert {c.locator for c in suggestion.candidates} == {str(destination)}
    assert suggestion.reason == 'POSSIBLE_MOVED_SOURCE'
    assert 'SHA256_MATCH' in suggestion.candidates[0].evidence
    assert suggestion.uncertainty != 'CONFIRMED_OWNERSHIP'
    assert any(c.reason == 'MULTIPLE_MOVE_CANDIDATES' and ambiguous.track_id in c.track_ids
               for c in result.unresolved)
    assert result.library_id == repo.library_id and result.operation_id
    assert result.checked_at == 100 and not result.cancelled
    assert result.completed == 4 and result.skipped == 0
    assert result.sources[0].status == SourceScanStatus.SUCCESS
    assert result.sources[0].authoritative_count == 5
    assert music_snapshot(root) == before_files
    assert sql_snapshot(repo) == before_rows
    assert sql_snapshot(repo, 'sources') == before_sources


def test_unavailable_root_is_not_an_empty_authoritative_scan(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3')
    repo.save_file_facts(replace(attest(track, 10), source=FileObservation(
        track.track_id, str(track.path), FileAvailability.PRESENT, 10, track.source_id)))
    previous = repo.get_file_state(track.track_id)
    before = sql_snapshot(repo)
    root.rename(root.with_name('disconnected'))
    result = api().check_library(repo, checked_at=20)
    assert result.sources[0].status == SourceScanStatus.UNAVAILABLE
    assert result.sources[0].authoritative_count is None
    observation = observations(result)[track.track_id]
    assert observation.source.availability == FileAvailability.OFFLINE
    assert not observation.evaluation.is_confirmed
    after = repo.get_file_state(track.track_id)
    assert after.facts.last_confirmed_state == previous.facts.last_confirmed_state
    assert after.facts.last_confirmed_at == 10
    assert sql_snapshot(repo) == before


def test_accessible_empty_root_is_success_zero_without_purge(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'gone.mp3'); track.path.unlink()
    before = sql_snapshot(repo)
    result = api().check_library(repo)
    assert result.sources[0].status == SourceScanStatus.SUCCESS
    assert result.sources[0].authoritative_count == 0
    assert observations(result)[track.track_id].source.availability == FileAvailability.MISSING
    assert sql_snapshot(repo) == before


def test_permission_error_is_not_missing(tmp_path, monkeypatch):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3')
    import audio_library_organizer.jobs.scanner as scanner
    original = scanner.os.scandir
    def denied(path):
        if Path(path) == root:
            raise PermissionError('synthetic denied root')
        return original(path)
    monkeypatch.setattr(scanner.os, 'scandir', denied)
    result = api().check_library(repo)
    assert result.sources[0].status == SourceScanStatus.ERROR
    assert result.sources[0].authoritative_count is None
    assert observations(result)[track.track_id].source.availability in (
        FileAvailability.ERROR, FileAvailability.UNKNOWN)
    assert len(repo.list_tracks()) == 1


def test_partial_inventory_does_not_confirm_absence(tmp_path, monkeypatch):
    repo, root = library(tmp_path)
    track = record(repo, root / 'nested' / 'x.mp3')
    track.path.unlink()
    import audio_library_organizer.jobs.scanner as scanner
    original = scanner.os.scandir
    def denied(path):
        if Path(path) == root / 'nested':
            raise PermissionError('synthetic partial failure')
        return original(path)
    monkeypatch.setattr(scanner.os, 'scandir', denied)
    result = api().check_library(repo)
    assert result.sources[0].status == SourceScanStatus.ERROR
    assert observations(result)[track.track_id].source.availability != FileAvailability.MISSING


def test_cancelled_check_retains_partial_report_and_commits_no_cache(tmp_path):
    repo, root = library(tmp_path)
    tracks = [record(repo, root / f'{i}.mp3') for i in range(4)]
    tracks.sort(key=lambda track: track.track_id)
    tracks[-1].path.unlink()
    cancelled = Event()
    def progress(current, total, name):
        cancelled.set()
    result = api().check_library(repo, cancelled=cancelled.is_set, progress=progress)
    assert result.cancelled and result.skipped >= 3
    assert 'CANCELLED' in result.reason_codes
    assert observations(result)[tracks[-1].track_id].source.availability == FileAvailability.UNKNOWN
    assert sql_snapshot(repo, 'file_state_cache') == []
    early = api().check_library(repo, cancelled=lambda: True)
    assert all(s.status == SourceScanStatus.CANCELLED for s in early.sources)


def test_new_candidate_never_imports_or_changes_category(tmp_path, monkeypatch):
    repo, root = library(tmp_path)
    track = record(repo, root / 'known.mp3')
    (root / 'new.mp3').write_bytes(b'new')
    def forbidden(*args, **kwargs):
        pytest.fail('check invoked a metadata/import/purge operation')
    for name in ('upsert_track', 'merge_scan_track', 'purge_missing', 'sync_availability'):
        monkeypatch.setattr(repo, name, forbidden)
    before = sql_snapshot(repo)
    result = api().check_library(repo)
    assert len(result.new_source_candidates) == 1
    assert result.new_source_candidates[0].source_id == track.source_id
    assert not hasattr(result.new_source_candidates[0], 'track_id')
    assert sql_snapshot(repo) == before


def test_filename_only_move_is_uncertain_and_never_relinked(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'old' / 'same.mp3')
    track.sha256 = ''; repo.upsert_track(track)
    track.path.unlink()
    candidate = root / 'new' / 'same.mp3'; candidate.parent.mkdir()
    candidate.write_bytes(b'completely different audio')
    before = sql_snapshot(repo)
    result = api().check_library(repo)
    move = result.possible_moves[0]
    assert move.track_id == track.track_id
    assert move.candidates[0].evidence == ('FILENAME_MATCH',)
    assert move.uncertainty == 'WEAK_EVIDENCE'
    assert sql_snapshot(repo) == before


def test_two_records_sharing_move_candidate_are_unresolved(tmp_path):
    repo, root = library(tmp_path)
    first = record(repo, root / 'a.mp3', content=b'same')
    second = record(repo, root / 'b.mp3', content=b'same')
    first.path.unlink(); second.path.unlink()
    (root / 'candidate.mp3').write_bytes(b'same')
    result = api().check_library(repo)
    assert any(c.reason == 'CANDIDATE_SHARED_BY_RECORDS' and set(c.track_ids) == {first.track_id, second.track_id}
               for c in result.unresolved)
    assert all(not item.evaluation.is_confirmed or item.evaluation.state != FileState.CONFLICT
               for item in result.files)


def test_current_synthetic_owned_managed_present_survives_source_offline(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3')
    managed_root = tmp_path / 'explicit-output'; managed_root.mkdir()
    managed = managed_root / 'owned.mp3'; managed.write_bytes(b'output')
    root.rename(root.with_name('offline'))
    result = api().check_library(repo, checked_at=100, managed_roots=(managed_root,),
        prepared_facts=(attest(track, 100, managed=managed, managed_expected=True),),
        prepared_library_id=repo.library_id)
    item = observations(result)[track.track_id]
    assert item.source.availability == FileAvailability.OFFLINE
    assert item.evaluation.state == FileState.IN_LIBRARY and item.evaluation.is_confirmed
    assert result.orphan_managed_candidates == ()


def test_current_synthetic_expected_managed_missing_has_priority(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3')
    managed_root = tmp_path / 'explicit-output'; managed_root.mkdir()
    result = api().check_library(repo, checked_at=100, managed_roots=(managed_root,),
        prepared_facts=(attest(track, 100, managed=managed_root / 'missing.mp3', managed_expected=True),),
        prepared_library_id=repo.library_id)
    item = observations(result)[track.track_id]
    assert item.source.availability == FileAvailability.PRESENT
    assert item.evaluation.state == FileState.MANAGED_FILE_MISSING and item.evaluation.is_confirmed


def test_historical_managed_cache_is_never_reconfirmed(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3')
    managed_root = tmp_path / 'output'; managed_root.mkdir()
    managed = managed_root / 'x.mp3'; managed.write_bytes(b'output')
    facts = replace(attest(track, 10, managed=managed, managed_expected=True),
                    managed=FileObservation(track.track_id, str(managed), FileAvailability.PRESENT, 10))
    repo.save_file_facts(facts)
    result = api().check_library(repo, checked_at=20, managed_roots=(managed_root,))
    item = observations(result)[track.track_id]
    assert not item.evaluation.is_confirmed
    assert item.evaluation.last_confirmed_at == 10
    assert item.facts.managed == facts.managed
    assert any('MANAGED_BINDING_UNAVAILABLE' == code for code in result.reason_codes)
    assert len(result.orphan_managed_candidates) == 1


def test_current_positive_conflict_uses_existing_evaluator_only(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3')
    result = api().check_library(repo, checked_at=10,
        prepared_facts=(attest(track, 10, conflict=ConflictReason.TARGET_COLLISION),),
        prepared_library_id=repo.library_id)
    assert observations(result)[track.track_id].evaluation.state == FileState.CONFLICT
    assert result.conflicts[0].certainty == 'CONFIRMED'


def test_libraries_and_prepared_context_are_isolated(tmp_path):
    a, ar = library(tmp_path, 'A'); b, br = library(tmp_path, 'B')
    ta = record(a, ar / 'a.mp3'); tb = record(b, br / 'b.mp3')
    before_b = sql_snapshot(b, 'file_state_cache')
    api().check_library(a, library_id=a.library_id)
    assert sql_snapshot(b, 'file_state_cache') == before_b
    assert ta.source_id != tb.source_id and a.library_id != b.library_id
    with pytest.raises(ValueError, match='library|Library'):
        api().check_library(b, library_id=a.library_id)
    with pytest.raises(ValueError, match='library|Library'):
        api().check_library(b, checked_at=10, prepared_facts=(attest(tb, 10),),
                            prepared_library_id=a.library_id)
    assert sql_snapshot(b, 'file_state_cache') == before_b


def test_older_worker_cannot_overwrite_newer_observations(tmp_path):
    repo, root = library(tmp_path)
    record(repo, root / 'x.mp3')
    api().check_library(repo, checked_at=200)
    before = sql_snapshot(repo, 'file_state_cache')
    result = api().check_library(repo, checked_at=100)
    assert 'CACHE_WRITE_REJECTED' in result.reason_codes
    assert result.cache_saved == 0
    assert sql_snapshot(repo, 'file_state_cache') == before


def test_repeat_unchanged_check_uses_no_audio_probe_or_sha(tmp_path, monkeypatch):
    repo, root = library(tmp_path)
    record(repo, root / 'x.mp3')
    m = api()
    def forbidden(*args, **kwargs):
        pytest.fail('unchanged check performed expensive audio/content work')
    monkeypatch.setattr(m, '_hash_file', forbidden)
    before = sql_snapshot(repo)
    first = m.check_library(repo, checked_at=100)
    second = m.check_library(repo, checked_at=200)
    assert first.files[0].source.availability == second.files[0].source.availability
    assert sql_snapshot(repo) == before
    assert len(sql_snapshot(repo, 'file_state_cache')) == 1


def test_overlapping_roots_deduplicate_and_keep_deepest_source_id(tmp_path):
    repo, root = library(tmp_path)
    nested = root / 'nested'; nested.mkdir()
    source = repo.register_source(nested)
    (nested / 'new.mp3').write_bytes(b'new')
    result = api().check_library(repo)
    assert len(result.sources) == 2
    assert len(result.new_source_candidates) == 1
    assert result.new_source_candidates[0].source_id == source.source_id


@pytest.mark.parametrize('kind', ['directory', 'file', 'loop'])
def test_aliases_are_not_followed_outside_scope(tmp_path, kind):
    repo, root = library(tmp_path)
    foreign = tmp_path / 'foreign'; foreign.mkdir()
    (foreign / 'private.mp3').write_bytes(b'outside source')
    target = foreign if kind == 'directory' else foreign / 'private.mp3'
    link = root / ('alias' if kind == 'directory' else 'alias.mp3')
    if kind == 'loop': target = link
    link.symlink_to(target, target_is_directory=kind == 'directory')
    result = api().check_library(repo)
    assert result.new_source_candidates == ()
    assert result.sources[0].status == SourceScanStatus.ERROR
    assert 'ALIAS_OR_MOUNT_UNRESOLVED' in result.reason_codes


def test_windows_unc_source_on_linux_is_unavailable_not_relative(tmp_path):
    if __import__('os').name == 'nt': pytest.skip('Foreign platform locator test')
    repo, root = library(tmp_path)
    repo.replace_sources((r'\\server\share\music',))
    result = api().check_library(repo)
    assert result.sources[0].status == SourceScanStatus.UNAVAILABLE
    assert result.sources[0].authoritative_count is None


def test_cache_batch_is_atomic_on_stale_track_binding(tmp_path):
    repo, root = library(tmp_path)
    tracks = [record(repo, root / f'{i}.mp3') for i in range(2)]
    m = api()
    def progress(current, total, name):
        if current == 1:
            tracks[1].path = root / 'different.mp3'; repo.upsert_track(tracks[1])
    result = m.check_library(repo, progress=progress)
    assert result.cache_saved == 0 and 'CACHE_WRITE_REJECTED' in result.reason_codes
    assert sql_snapshot(repo, 'file_state_cache') == []


def test_invalid_optional_cache_is_retained_without_blocking_other_tracks(tmp_path):
    repo, root = library(tmp_path)
    damaged = record(repo, root / 'damaged.mp3'); good = record(repo, root / 'good.mp3')
    repo.save_file_facts(attest(damaged, 1))
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute("UPDATE file_state_cache SET facts_json='invalid' WHERE track_id=?", (damaged.track_id,))
    result = api().check_library(repo)
    assert any(c.reason == 'INVALID_OPTIONAL_CACHE' and damaged.track_id in c.track_ids for c in result.unresolved)
    assert repo.get_file_state(good.track_id) is not None
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('SELECT facts_json FROM file_state_cache WHERE track_id=?', (damaged.track_id,)).fetchone()[0] == 'invalid'


def wait_for(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
    assert predicate(), 'Qt worker did not finish within bounded test timeout'


def test_explicit_check_keeps_review_and_icons_without_startup_check(current_start_window):
    from PySide6.QtWidgets import QApplication
    window = current_start_window
    assert hasattr(window, '_check_library_clicked'), 'Missing explicit check integration'
    assert window.last_reconciliation_result is None and window._thread is None
    before = sql_snapshot(window.repository)
    window._open_review()
    assert window._thread is None and window.stack.currentIndex() == 1
    # Existing review navigation highlights its icon; compare the same review
    # state before/after check, not an unrelated inactive Start button state.
    icons = [b.icon().pixmap(24, 24).toImage() for b in (window.scan_btn, window.identify_btn, window.review_btn)]
    window.review_btn.click()
    assert window._thread is not None
    wait_for(QApplication.instance(), lambda: window._thread is None)
    assert window.last_reconciliation_result is not None
    assert sql_snapshot(window.repository) == before
    assert icons == [b.icon().pixmap(24, 24).toImage() for b in (window.scan_btn, window.identify_btn, window.review_btn)]


def test_closed_or_stale_context_ignores_check_result(current_start_window):
    window = current_start_window
    m = api()
    assert hasattr(window, '_file_check_finished'), 'Missing worker context guard'
    result = m.check_library(window.repository, operation_id='old-operation')
    before = window.operation_status.text()
    window._file_check_context = ('other-library', 'new-operation', 1)
    window._file_check_finished(result)
    assert window.operation_status.text() == before and window.last_reconciliation_result is None
    window._file_check_closing = True
    window._file_check_context = (result.library_id, result.operation_id, window._file_check_generation)
    window._file_check_finished(result)
    assert window.operation_status.text() == before and window.last_reconciliation_result is None
    window._file_check_closing = False


def test_worker_cancellation_and_close_finishes_without_gui_updates(current_start_window, monkeypatch):
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication
    import audio_library_organizer.ui.workers as workers
    m = api()
    assert hasattr(workers, 'FileReconciliationWorker'), 'Missing cancellable check worker'
    window = current_start_window
    entered = Event()
    original = workers.check_library
    def blocked(repository, **kwargs):
        assert QThread.currentThread() != QApplication.instance().thread()
        entered.set()
        # Event.wait is a bounded test barrier, not a product sleep/timer.
        assert kwargs['cancelled'].__self__.wait(5)
        return original(repository, **kwargs)
    monkeypatch.setattr(workers, 'check_library', blocked)
    window.review_btn.click()
    wait_for(QApplication.instance(), entered.is_set)
    thread = window._thread
    window.close()
    wait_for(QApplication.instance(), lambda: window._thread is None)
    assert not thread.isRunning() if __import__('shiboken6').isValid(thread) else True
    assert window.last_reconciliation_result is None
    assert not window.isVisible()


def test_full_stat_change_is_checked_even_when_size_and_mtime_match(tmp_path, monkeypatch):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3', content=b'AAAA')
    m = api()
    m.check_library(repo, checked_at=10)
    replacement = root / 'replacement.tmp'; replacement.write_bytes(b'BBBB')
    replacement.replace(track.path)
    import os
    os.utime(track.path, ns=(track.mtime_ns, track.mtime_ns))
    before = sql_snapshot(repo)
    result = m.check_library(repo, checked_at=20)
    assert 'SOURCE_CONTENT_CHANGED' in observations(result)[track.track_id].reason_codes
    assert sql_snapshot(repo) == before
    def forbidden(*args, **kwargs):
        pytest.fail('unchanged technical observation needlessly recalculated SHA')
    monkeypatch.setattr(m, '_hash_file', forbidden)
    repeat = m.check_library(repo, checked_at=30)
    assert 'SOURCE_CONTENT_CHANGED' in observations(repeat)[track.track_id].reason_codes


def test_two_current_managed_owners_are_a_positive_conflict(tmp_path):
    repo, root = library(tmp_path)
    first = record(repo, root / 'one.mp3'); second = record(repo, root / 'two.mp3')
    output = tmp_path / 'output'; output.mkdir()
    shared = output / 'shared.mp3'; shared.write_bytes(b'output')
    before = sql_snapshot(repo)
    result = api().check_library(repo, checked_at=10, managed_roots=(output,),
        prepared_library_id=repo.library_id,
        prepared_facts=tuple(attest(t, 10, managed=shared, managed_expected=True) for t in (first, second)))
    assert all(item.evaluation.state == FileState.CONFLICT for item in result.files)
    assert all(item.evaluation.reason == 'MULTIPLE_OWNERS' for item in result.files)
    assert all(item.certainty == 'CONFIRMED' for item in result.conflicts)
    assert sql_snapshot(repo) == before


def test_source_registry_change_during_check_rolls_back_entire_batch(tmp_path):
    repo, root = library(tmp_path)
    record(repo, root / 'known.mp3')
    def progress(*args):
        repo.replace_sources(())
    result = api().check_library(repo, progress=progress)
    assert 'CACHE_WRITE_REJECTED' in result.reason_codes and result.cache_saved == 0
    assert sql_snapshot(repo, 'file_state_cache') == []


def test_cancel_during_batch_rolls_back_all_rows(tmp_path):
    repo, root = library(tmp_path)
    tracks = [record(repo, root / f'{i}.mp3') for i in range(2)]
    m = api()
    snapshot = repo.file_check_snapshot()
    facts = tuple(attest(t, 10) for t in tracks)
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 2
    with pytest.raises(InterruptedError):
        repo.save_file_facts_batch(facts, snapshot=snapshot, cancelled=cancel)
    assert sql_snapshot(repo, 'file_state_cache') == []


def test_managed_outside_explicit_scope_is_unknown_and_not_followed(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3')
    managed = tmp_path / 'foreign.mp3'; managed.write_bytes(b'not an authorized scope')
    result = api().check_library(repo, checked_at=10, prepared_library_id=repo.library_id,
        prepared_facts=(attest(track, 10, managed=managed, managed_expected=True),))
    item = observations(result)[track.track_id]
    assert item.facts.managed.availability == FileAvailability.UNKNOWN
    assert not item.evaluation.is_confirmed


def test_anchor_root_identity_and_device_boundary_are_checked(tmp_path):
    from types import SimpleNamespace
    from audio_library_organizer.jobs.scanner import scoped_stat, UnsafeSourcePath
    root = Path(tmp_path.anchor)
    info = root.lstat()
    changed = SimpleNamespace(st_dev=info.st_dev, st_ino=info.st_ino + 1)
    with pytest.raises(UnsafeSourcePath, match='ROOT_IDENTITY_CHANGED'):
        scoped_stat(root, root, changed)
    # Deterministic stat fault preserves a real anchor/root, without relying on
    # this host having /proc or a particular Windows volume available.
    child = root / 'synthetic-mount'
    original = Path.lstat
    from unittest.mock import patch
    def mounted(path):
        if path == child:
            return SimpleNamespace(st_dev=info.st_dev + 1, st_ino=100, st_mode=info.st_mode)
        return original(path)
    with patch.object(Path, 'lstat', mounted):
        with pytest.raises(UnsafeSourcePath, match='ALIAS_OR_MOUNT_UNRESOLVED'):
            scoped_stat(child, root, info)


def test_managed_dotdot_cannot_escape_attested_scope(tmp_path):
    repo, root = library(tmp_path)
    track = record(repo, root / 'x.mp3')
    output = tmp_path / 'output'; output.mkdir()
    foreign = tmp_path / 'outside.mp3'; foreign.write_bytes(b'outside scope')
    locator = str(output) + '/../outside.mp3'
    facts = attest(track, 10, managed=locator, managed_expected=True)
    result = api().check_library(repo, checked_at=10, managed_roots=(output,),
                                prepared_library_id=repo.library_id, prepared_facts=(facts,))
    item = observations(result)[track.track_id]
    assert item.facts.managed.availability == FileAvailability.UNKNOWN
    assert not item.evaluation.is_confirmed
    assert 'MANAGED_SCOPE_UNAVAILABLE' in item.facts.managed.reason


@pytest.mark.parametrize('middle', ['./', '//'])
def test_preserved_raw_legacy_locator_receives_cache_without_rewriting(tmp_path, middle):
    repo, root = library(tmp_path)
    track = record(repo, root / 'known.mp3')
    raw = str(root) + '/' + middle + track.path.name
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('UPDATE tracks SET path=? WHERE track_id=?', (raw, track.track_id))
    repo.initialize()
    before = sql_snapshot(repo)
    result = api().check_library(repo, checked_at=10)
    assert sql_snapshot(repo) == before
    assert result.cache_saved == 1
    assert observations(result)[track.track_id].source.locator == raw
    assert repo.get_file_state(track.track_id).facts.source.locator == raw


def test_stat_only_uncertainty_is_retained_until_identity_evidence_changes(tmp_path):
    from audio_library_organizer.storage.scan_merge import SCAN_STAT_KEY, stat_observation
    import os
    repo, root = library(tmp_path)
    track = record(repo, root / 'known.mp3', content=b'AAAA')
    track.sha256 = None
    track.original_tags[SCAN_STAT_KEY] = stat_observation(track.path.stat())
    repo.upsert_track(track)
    m = api(); m.check_library(repo, checked_at=10)
    replacement = root / 'replacement.tmp'; replacement.write_bytes(b'BBBB')
    replacement.replace(track.path)
    os.utime(track.path, ns=(track.mtime_ns, track.mtime_ns))
    before = sql_snapshot(repo)
    first = m.check_library(repo, checked_at=20)
    second = m.check_library(repo, checked_at=30)
    for result in (first, second):
        assert 'SOURCE_STAT_CHANGED' in observations(result)[track.track_id].reason_codes
        assert any(track.track_id in c.track_ids and c.reason == 'SOURCE_STAT_CHANGED' for c in result.unresolved)
    assert sql_snapshot(repo) == before


def test_foreign_windows_managed_scope_is_not_a_literal_posix_directory(tmp_path, monkeypatch):
    if __import__('os').name == 'nt': pytest.skip('Foreign platform locator test')
    repo, root = library(tmp_path)
    record(repo, root / 'known.mp3')
    monkeypatch.chdir(tmp_path)
    raw_root = r'\\server\share\output'
    literal = tmp_path / raw_root; literal.mkdir()
    (literal / 'private.mp3').write_bytes(b'not an authorized UNC output')
    result = api().check_library(repo, managed_roots=(raw_root,))
    assert result.orphan_managed_candidates == ()
    assert 'FOREIGN_PLATFORM_LOCATOR' in result.reason_codes


def test_cancel_does_not_begin_managed_io_for_skipped_records(tmp_path, monkeypatch):
    repo, root = library(tmp_path)
    tracks = [record(repo, root / f'{i}.mp3') for i in range(2)]
    output = tmp_path / 'output'; output.mkdir()
    facts = []
    for track in tracks:
        managed = output / f'{track.track_id}.mp3'; managed.write_bytes(b'output')
        facts.append(attest(track, 10, managed=managed, managed_expected=True))
    cancelled, late_queries = Event(), []
    m = api(); original = m.scoped_stat
    def observe(path, *args, **kwargs):
        if cancelled.is_set() and Path(path).is_relative_to(output):
            late_queries.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(m, 'scoped_stat', observe)
    result = m.check_library(repo, checked_at=10, managed_roots=(output,),
        prepared_facts=facts, prepared_library_id=repo.library_id,
        cancelled=cancelled.is_set, progress=lambda *args: cancelled.set())
    assert result.cancelled and result.cache_saved == 0
    assert late_queries == []
    assert not result.files[-1].evaluation.is_confirmed
    assert sql_snapshot(repo, 'file_state_cache') == []


@pytest.mark.parametrize('root_exists', [True, False])
def test_managed_missing_parent_differs_from_unavailable_output_root(tmp_path, root_exists):
    repo, root = library(tmp_path)
    track = record(repo, root / 'known.mp3')
    output = tmp_path / 'output'
    if root_exists: output.mkdir()
    result = api().check_library(repo, checked_at=10, managed_roots=(output,),
        prepared_facts=(attest(track, 10, managed=output / 'absent' / 'x.mp3', managed_expected=True),),
        prepared_library_id=repo.library_id)
    item = result.files[0]
    assert item.facts.managed.availability == (FileAvailability.MISSING if root_exists else FileAvailability.OFFLINE)
    assert item.evaluation.is_confirmed == root_exists


def test_newer_observation_of_last_track_rolls_back_prior_cache_writes(tmp_path):
    repo, root = library(tmp_path)
    tracks = sorted([record(repo, root / f'{i}.mp3') for i in range(2)], key=lambda t: t.track_id)
    def progress(current, total, name):
        if current == total:
            last = tracks[-1]
            repo.save_file_facts(replace(attest(last, 200), source=FileObservation(
                last.track_id, str(last.path), FileAvailability.PRESENT, 200, last.source_id)))
    result = api().check_library(repo, checked_at=100, progress=progress)
    assert result.cache_saved == 0 and 'CACHE_WRITE_REJECTED' in result.reason_codes
    with sqlite3.connect(repo.database_path) as conn:
        assert conn.execute('SELECT track_id,observation_at FROM file_state_cache').fetchall() == [(tracks[-1].track_id, 200)]


@pytest.mark.parametrize('change', ['retarget', 'disconnect'])
def test_raw_locator_alias_does_not_probe_historical_canonical_target(tmp_path, change):
    repo, root = library(tmp_path)
    track = record(repo, root / 'known.mp3')
    alias = tmp_path / 'legacy-alias'; alias.symlink_to(root, target_is_directory=True)
    raw = str(alias / track.path.name)
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute('UPDATE tracks SET path=? WHERE track_id=?', (raw, track.track_id))
    repo.initialize()
    alias.unlink()
    if change == 'retarget':
        foreign = tmp_path / 'foreign'; foreign.mkdir()
        alias.symlink_to(foreign, target_is_directory=True)
    assert not Path(raw).exists() and track.path.exists()
    before = sql_snapshot(repo)
    result = api().check_library(repo, checked_at=10)
    item = observations(result)[track.track_id]
    assert item.source.locator == raw
    assert item.source.availability in (FileAvailability.ERROR, FileAvailability.UNKNOWN)
    assert sql_snapshot(repo) == before
