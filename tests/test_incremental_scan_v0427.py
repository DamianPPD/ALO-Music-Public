"""Stage 1.3: durable work survives filesystem observations and stale scans."""
from dataclasses import asdict
import os
from pathlib import Path
import sqlite3
import struct
import wave

import pytest

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.jobs.library_service import LibraryService, ScanResult
from audio_library_organizer.metadata.manual_edits import apply_manual_field
from audio_library_organizer.metadata.tags import TagInfo
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.ui.state import track_matches_library_filters


@pytest.fixture(autouse=True)
def preserve_qt_application_style():
    # MainWindow applies the application theme. Keep isolated workflow tests
    # from changing the rendering environment of later existing UI regressions.
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    previous = app.styleSheet() if app is not None else ''
    yield
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(previous)


def wav(path, sample=0):
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000)
        stream.writeframes(struct.pack('<h', sample) * 800)


@pytest.fixture
def library(tmp_path):
    source = tmp_path / 'music'; source.mkdir()
    settings = AppSettings((source,), LibraryPaths(tmp_path / 'output'))
    repo = LibraryRepository(settings.library.database); repo.initialize()
    repo.bootstrap_sources((source,))
    return source, repo, LibraryService(settings, repo)


def imported(library):
    source, repo, service = library
    path = source / 'Artist - Title.wav'; wav(path)
    assert service.scan().scanned == 1
    return path, repo.list_tracks()[0]


def test_offline_root_scan_does_not_delete_records(library):
    path, track = imported(library)
    source, repo, service = library
    apply_manual_field([track], 'title', 'Manual')
    repo.upsert_track(track)
    before = asdict(repo.get_track(track.track_id))
    source.rename(source.with_name('offline'))
    result = service.scan()
    assert asdict(repo.get_track(track.track_id)) == before
    assert result.source_outcomes[0].status == 'unavailable'
    assert result.source_counts == ()


def test_available_empty_folder_success_without_purge(library):
    path, track = imported(library)
    source, repo, service = library
    path.unlink()
    result = service.scan()
    assert result.source_outcomes[0].status == 'success'
    assert result.source_outcomes[0].files == 0
    assert repo.get_track(track.track_id) is not None


def test_explicit_empty_scan_does_not_fall_back_to_configured_roots(library):
    path, track = imported(library)
    _, repo, service = library
    result = service.scan(source_dirs=[])
    assert result.total_seen == 0
    assert result.source_outcomes == ()
    assert len(repo.list_tracks()) == 1


def test_unchanged_scan_performs_no_updates_or_audio_reads(library, monkeypatch):
    path, track = imported(library)
    _, repo, service = library
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute("CREATE TRIGGER forbid_update BEFORE UPDATE ON tracks BEGIN SELECT RAISE(ABORT,'unexpected update'); END")
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags', lambda p: pytest.fail('unchanged read'))
    result = service.scan()
    assert result.skipped_unchanged == 1
    assert result.errors == 0
    assert repo.get_track(track.track_id).track_id == track.track_id


@pytest.mark.parametrize('status', ['ready', 'review', 'duplicate', 'not_selected'])
def test_changed_source_scan_preserves_manual_fields_and_bindings(library, monkeypatch, status):
    path, track = imported(library)
    _, repo, service = library
    for field, value in [('artist','Manual Artist'),('title','Manual Title'),('album','Manual Album'),
                          ('year','2003'),('genre','House'),('bpm',139),('filename_override','mine.wav')]:
        apply_manual_field([track], field, value)
    track.status=status; track.locked_fields.add('__status__')
    track.cover_choice='manual'; track.manual_cover_path='saved-cover.jpg'
    track.audio_recognition={'selected': {'recording':'saved'}}
    track.musicbrainz_recording_id='mb'; track.discogs_release_id='dc'
    track.pre_online_metadata={'title':'history'}
    track.match_reasons=['chosen by user']; repo.upsert_track(track)
    before=asdict(track)
    path.write_bytes(path.read_bytes()+b'changed-tag-container')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags',
                        lambda p: TagInfo(artist='New Artist',title='New Title',album='New Album',raw={'title':'New Title'}))
    result=service.scan(); saved=repo.get_track(track.track_id)
    assert result.scanned==1 and result.errors==0
    for field in ['track_id','source_id','source_relative_path','artist','title','album','year','genre','bpm',
                  'filename_override','status','locked_fields','cover_choice','manual_cover_path','audio_recognition',
                  'musicbrainz_recording_id','discogs_release_id','pre_online_metadata','match_reasons','field_sources']:
        assert getattr(saved,field)==before[field],field
    assert saved.size_bytes==path.stat().st_size
    assert saved.field_source_values['title']['Tag']=='New Title'
    assert saved.field_source_values['title']['Ręcznie']=='Manual Title'


def test_rescan_cannot_overwrite_newer_manual_edit(library, monkeypatch):
    path, track = imported(library); _,repo,service=library
    path.write_bytes(path.read_bytes()+b'tag')
    def tags(p):
        current=repo.get_track(track.track_id);apply_manual_field([current],'title','Edited during scan')
        repo.upsert_track(current)
        return TagInfo(title='Stale scanned title')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags',tags)
    service.scan()
    assert repo.get_track(track.track_id).title=='Edited During Scan'


@pytest.mark.parametrize('race', ['delete', 'move', 'rebind'])
def test_scan_cannot_resurrect_or_reassign_changed_identity(library, monkeypatch, race):
    path,track=imported(library); source,repo,service=library
    path.write_bytes(path.read_bytes()+b'tag')
    def tags(p):
        if race=='delete':
            with sqlite3.connect(repo.database_path) as conn:conn.execute('DELETE FROM tracks WHERE track_id=?',(track.track_id,))
        elif race=='move':
            current=repo.get_track(track.track_id);current.path=source/'moved.wav';repo.upsert_track(current)
        else:
            child=source/path.stem;child.mkdir();repo.register_source(child)
            repo.replace_sources(())
            with sqlite3.connect(repo.database_path) as conn:
                conn.execute('UPDATE tracks SET source_id=NULL,source_relative_path=NULL WHERE track_id=?',(track.track_id,))
        return TagInfo(title='Stale')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags',tags)
    result=service.scan()
    assert result.errors==1
    if race=='delete':assert repo.get_track(track.track_id) is None
    elif race=='move':assert repo.get_track(track.track_id).path==source/'moved.wav'
    else:assert repo.get_track(track.track_id).source_id is None


def test_other_audio_at_same_locator_retains_work_and_diagnostic(library):
    path,track=imported(library);_,repo,service=library
    apply_manual_field([track],'title','My Work');repo.upsert_track(track)
    before=asdict(track);wav(path,sample=100)
    result=service.scan();saved=repo.get_track(track.track_id)
    assert result.errors==1
    assert len(repo.list_tracks())==1
    assert saved.title==before['title'] and saved.track_id==before['track_id']
    assert saved.sha256==before['sha256'] and saved.original_tags==before['original_tags']
    assert any('scan:' in reason for reason in saved.match_reasons)


def test_cancelled_scan_preserves_saved_work(library):
    path,track=imported(library);_,repo,service=library
    before=asdict(track)
    result=service.scan(cancelled=lambda:True)
    assert result.cancelled
    assert result.source_outcomes[0].status=='cancelled'
    assert asdict(repo.get_track(track.track_id))==before


def test_permission_error_is_not_successful_empty_scan(library, monkeypatch):
    source,repo,service=library
    monkeypatch.setattr(os,'scandir',lambda p: (_ for _ in ()).throw(PermissionError('denied')))
    result=service.scan()
    assert result.source_outcomes[0].status=='error'
    assert result.source_counts==()


def test_saved_offline_track_stays_in_default_library_filter(tmp_path):
    from audio_library_organizer.domain.models import TrackRecord
    track=TrackRecord(tmp_path/'offline.mp3',is_available=False,status='ready')
    assert track_matches_library_filters(track)


@pytest.mark.parametrize('operation',['identify','export','scan_finished'])
def test_export_or_identification_cancel_cannot_purge_missing_work(tmp_path,monkeypatch,operation):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication,QMessageBox
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    from audio_library_organizer.domain.models import TrackRecord
    monkeypatch.setattr(main_window,'DashboardPage',DashboardPage)
    monkeypatch.setattr(QMessageBox,'information',lambda *a:None)
    app=QApplication.instance() or QApplication([])
    settings=AppSettings((),LibraryPaths(tmp_path/'output'))
    repo=LibraryRepository(settings.library.database);repo.initialize()
    track=TrackRecord(tmp_path/'offline.mp3',title='Saved',status='not_selected',locked_fields={'title'})
    repo.upsert_track(track)
    window=main_window.MainWindow(settings,QSettings(str(tmp_path/'prefs.ini'),QSettings.IniFormat))
    try:
        if operation=='identify':window.start_identification()
        elif operation=='export':window.export_library()
        else:window._scan_finished(ScanResult(0,0,0,0,cancelled=False))
        saved=repo.get_track(track.track_id)
        assert saved is not None
        assert saved.title=='Saved' and saved.status=='not_selected'
        assert saved.locked_fields=={'title'}
        assert any(t.track_id==track.track_id for t in window.library._tracks)
    finally:window.close()


def test_partial_directory_error_is_not_success(library, monkeypatch):
    path, track = imported(library)
    source, repo, service = library
    child = source / 'denied'; child.mkdir()
    real_scandir = os.scandir
    def scandir(path):
        if Path(path) == child:
            raise PermissionError('partial traversal')
        return real_scandir(path)
    monkeypatch.setattr(os, 'scandir', scandir)
    result = service.scan()
    assert result.source_outcomes[0].status == 'error'
    assert result.source_outcomes[0].files == 1
    assert result.source_counts == ()
    assert repo.get_track(track.track_id) is not None


def test_file_alias_processing_error_marks_owning_root(library, tmp_path, monkeypatch):
    source, repo, service = library
    target = tmp_path / 'outside.wav'; wav(target)
    (source / 'alias.wav').symlink_to(target)
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.probe_audio',
                        lambda p: (_ for _ in ()).throw(OSError('failed alias')))
    result = service.scan()
    assert result.errors == 1
    assert result.source_outcomes[0].status == 'error'
    assert result.source_counts == ()


def test_newer_unlocked_edit_survives_older_scan(library, monkeypatch):
    path, track = imported(library); _, repo, service = library
    path.write_bytes(path.read_bytes() + b'tags')
    def tags(p):
        latest = repo.get_track(track.track_id)
        apply_manual_field([latest], 'title', 'Newest unlocked edit', lock=False)
        repo.upsert_track(latest)
        return TagInfo(title='Older observation')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags', tags)
    service.scan()
    assert repo.get_track(track.track_id).title == 'Newest Unlocked Edit'


def test_one_uuid_and_deep_source_binding_survive_overlap_and_restart(library):
    from uuid import UUID
    source, repo, service = library
    child = source / 'nested'; child.mkdir()
    owner = repo.register_source(child)
    path = child / 'Artist - Title.wav'; wav(path)
    first = service.scan(source_dirs=(source, child))
    track, = repo.list_tracks()
    UUID(track.track_id)
    assert first.total_seen == 1 and first.scanned == 1
    assert track.source_id == owner.source_id and track.source_relative_path == path.name
    before = asdict(track)
    reopened = LibraryRepository(repo.database_path); reopened.initialize()
    result = LibraryService(service.settings, reopened).scan(source_dirs=(child, source))
    assert result.skipped_unchanged == 1
    assert asdict(reopened.get_track(track.track_id)) == before
    assert [s.source_id for s in reopened.list_sources()] == [s.source_id for s in repo.list_sources()]


def test_processing_error_and_cancellation_do_not_write_source_history(library, monkeypatch):
    path, track = imported(library); _, repo, service = library
    path.write_bytes(path.read_bytes() + b'tags')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags',
                        lambda p: (_ for _ in ()).throw(PermissionError('tags unavailable')))
    before = asdict(track)
    result = service.scan()
    assert result.errors == 1 and result.source_counts == ()
    assert result.source_outcomes[0].status == 'error'
    assert asdict(repo.get_track(track.track_id)) == before


def test_cancel_during_probe_discards_observation(library, monkeypatch):
    path, track = imported(library); _, repo, service = library
    path.write_bytes(path.read_bytes() + b'tags')
    state = {'cancelled': False}
    def tags(p):
        state['cancelled'] = True
        return TagInfo(title='Discard this')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags', tags)
    before = asdict(track)
    result = service.scan(cancelled=lambda: state['cancelled'])
    assert result.cancelled and result.source_counts == ()
    assert result.source_outcomes[0].status == 'cancelled'
    assert asdict(repo.get_track(track.track_id)) == before


def test_changing_file_during_probe_discards_observation(library, monkeypatch):
    path, track = imported(library); _, repo, service = library
    path.write_bytes(path.read_bytes() + b'tags')
    def tags(p):
        wav(path, sample=999)
        return TagInfo(title='Different audio')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags', tags)
    before = asdict(track)
    result = service.scan()
    assert result.errors == 1
    assert asdict(repo.get_track(track.track_id)) == before


def test_concurrent_new_insert_is_not_taken_over(library, monkeypatch):
    from audio_library_organizer.domain.models import TrackRecord
    source, repo, service = library
    path = source / 'new.wav'; wav(path)
    def tags(p):
        repo.upsert_track(TrackRecord(path, title='Concurrent owner', locked_fields={'title'}))
        return TagInfo(title='Stale import')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags', tags)
    result = service.scan()
    track, = repo.list_tracks()
    assert result.errors == 1
    assert track.title == 'Concurrent owner' and track.locked_fields == {'title'}


def test_failed_merge_rolls_back_all_work(library):
    path, track = imported(library); _, repo, service = library
    path.write_bytes(path.read_bytes() + b'tags')
    before = asdict(track)
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute("CREATE TRIGGER reject_source_update BEFORE UPDATE OF source_id ON tracks BEGIN SELECT RAISE(ABORT,'rollback'); END")
    result = service.scan()
    assert result.errors == 1
    assert asdict(repo.get_track(track.track_id)) == before


def test_unchanged_file_is_not_hashed_and_remains_read_only(library, monkeypatch):
    from audio_library_organizer.duplicates.comparator import sha256_file
    path, track = imported(library); _, repo, service = library
    before = sha256_file(path)
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.sha256_file',
                        lambda p: pytest.fail('no whole-file hash for unchanged files'))
    assert service.scan().skipped_unchanged == 1
    assert sha256_file(path) == before


def test_unknown_legacy_audio_change_keeps_work_even_with_same_fingerprint(library, monkeypatch):
    from audio_library_organizer.storage.scan_merge import SCAN_AUDIO_KEY
    from audio_library_organizer.audio.fingerprint import FingerprintResult
    from audio_library_organizer.audio.probe import AudioInfo
    path, track = imported(library); _, repo, service = library
    track.original_tags.pop(SCAN_AUDIO_KEY, None)
    track.fingerprint = 'same'; repo.upsert_track(track)
    before = asdict(track)
    path.write_bytes(path.read_bytes() + b'tags')
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.probe_audio',
                        lambda p: AudioInfo(duration_seconds=5.0))
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.fingerprint_audio',
                        lambda p: FingerprintResult('same', 5))
    result = service.scan()
    saved = repo.get_track(track.track_id)
    assert result.errors == 1
    assert saved.sha256 == before['sha256'] and saved.title == before['title']
    assert saved.fingerprint == before['fingerprint']


def test_same_size_replacement_with_restored_mtime_is_not_unchanged(library):
    path, track = imported(library); _, repo, service = library
    old_stat = path.stat()
    wav(path, sample=555)
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    assert path.stat().st_size == track.size_bytes and path.stat().st_mtime_ns == track.mtime_ns
    result = service.scan()
    assert result.errors == 1 and result.skipped_unchanged == 0
    saved = repo.get_track(track.track_id)
    assert saved.sha256 == track.sha256 and saved.track_id == track.track_id


def test_file_replaced_before_transaction_is_not_committed(library, monkeypatch):
    path, track = imported(library); _, repo, service = library
    path.write_bytes(path.read_bytes() + b'tags')
    original_merge = repo.merge_scan_track
    def merge(observed, snapshot):
        wav(path, sample=777)
        return original_merge(observed, snapshot)
    monkeypatch.setattr(repo, 'merge_scan_track', merge)
    before = asdict(track)
    result = service.scan()
    assert result.errors == 1
    assert asdict(repo.get_track(track.track_id)) == before


def test_legacy_same_size_replacement_is_not_silent_success(library):
    from audio_library_organizer.storage.scan_merge import SCAN_AUDIO_KEY, SCAN_STAT_KEY
    path, track = imported(library); _, repo, service = library
    track.original_tags.pop(SCAN_AUDIO_KEY); track.original_tags.pop(SCAN_STAT_KEY)
    repo.upsert_track(track)
    old_stat = path.stat(); wav(path, sample=444)
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    result = service.scan()
    assert result.errors == 1 and result.source_outcomes[0].status == 'error'
    saved = repo.get_track(track.track_id)
    assert saved.sha256 == track.sha256 and saved.title == track.title
    assert any('scan:' in reason for reason in saved.match_reasons)
    assert SCAN_STAT_KEY not in saved.original_tags


@pytest.mark.parametrize('limited', [False, True])
def test_offline_duplicate_context_does_not_change_existing_category(library, tmp_path, limited):
    path, track = imported(library); source, repo, service = library
    other = tmp_path / 'other'; other.mkdir()
    (other/'copy.wav').write_bytes(path.read_bytes())
    repo.register_source(other)
    service = LibraryService(AppSettings((source, other), service.settings.library), repo)
    service.scan()
    assert repo.get_track(track.track_id).status == 'duplicate'
    other.rename(tmp_path/'offline-other')
    wav(source/'Unrelated - New.wav', sample=300)
    result = service.scan(source_dirs=(source,) if limited else None)
    assert result.scanned == 1
    assert repo.get_track(track.track_id).status == 'duplicate'


def test_legacy_exact_bytes_seed_observation_once_without_metadata_update(library, monkeypatch):
    from audio_library_organizer.storage.scan_merge import SCAN_AUDIO_KEY, SCAN_STAT_KEY
    from audio_library_organizer.duplicates.comparator import sha256_file
    path, track = imported(library); _, repo, service = library
    track.original_tags.pop(SCAN_AUDIO_KEY); track.original_tags.pop(SCAN_STAT_KEY)
    repo.upsert_track(track)
    with sqlite3.connect(repo.database_path) as conn:
        conn.execute("CREATE TRIGGER forbid_metadata_update BEFORE UPDATE OF title,artist,status,source_id ON tracks BEGIN SELECT RAISE(ABORT,'metadata rewrite'); END")
    reads = []
    def hash_once(p):
        reads.append(p)
        return sha256_file(p)
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.sha256_file', hash_once)
    monkeypatch.setattr('audio_library_organizer.jobs.library_service.read_tags', lambda p: pytest.fail('legacy tag reread'))
    assert service.scan().skipped_unchanged == 1
    assert service.scan().skipped_unchanged == 1
    saved = repo.get_track(track.track_id)
    assert reads == [path]
    assert SCAN_STAT_KEY in saved.original_tags and SCAN_AUDIO_KEY in saved.original_tags
    assert saved.title == track.title and saved.source_id == track.source_id


def test_real_unreadable_audio_is_processing_error_not_success(library):
    source, repo, service = library
    (source/'broken.wav').write_bytes(b'not a valid WAV or audio stream')
    result = service.scan()
    assert result.errors == 1 and result.scanned == 0
    assert result.source_outcomes[0].status == 'error'
    assert result.source_counts == () and repo.list_tracks() == []


def test_export_preview_rejection_retains_missing_work(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui import main_window
    from audio_library_organizer.ui.dashboard_page import DashboardPage
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.duplicates.comparator import sha256_file
    monkeypatch.setattr(main_window, 'DashboardPage', DashboardPage)
    app = QApplication.instance() or QApplication([])
    settings = AppSettings((), LibraryPaths(tmp_path/'library'))
    repo = LibraryRepository(settings.library.database); repo.initialize()
    missing = TrackRecord(tmp_path/'offline.wav', title='My saved work', status='not_selected', locked_fields={'title'})
    repo.upsert_track(missing)
    path = tmp_path/'available.wav'; wav(path)
    repo.upsert_track(TrackRecord(path, artist='Artist', title='Title', year='2001', genre='House', bpm=128,
                                  has_cover=True, status='ready', locked_fields={'__status__'}))
    before = sha256_file(path)
    previews = []
    monkeypatch.setattr(main_window, 'confirm_bulk_copy', lambda *a, **kw: previews.append(a) or False)
    window = main_window.MainWindow(settings, QSettings(str(tmp_path/'prefs.ini'), QSettings.IniFormat))
    try:
        window.export_library()
        assert len(previews) == 1 and window._thread is None
        saved = repo.get_track(missing.track_id)
        assert saved.title == missing.title and saved.status == missing.status and saved.locked_fields == {'title'}
        assert sha256_file(path) == before
        assert not list(settings.library.ready.rglob('*.wav'))
    finally:
        window.close()


def test_identification_worker_cancel_preserves_missing_work(library, tmp_path):
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.domain.models import TrackRecord
    from audio_library_organizer.jobs.identifier import IdentificationJob
    from audio_library_organizer.ui.workers import IdentificationWorker
    path, track = imported(library); _, repo, service = library
    missing = TrackRecord(tmp_path/'offline.wav', title='Saved offline', status='not_selected', locked_fields={'title'})
    repo.upsert_track(missing)
    before = asdict(missing)
    app = QApplication.instance() or QApplication([])
    class Identifier:
        def identify(self, track):
            pytest.fail('cancelled worker must not make a provider request')
    # UI's operation preflight retains the missing row; the real job and worker
    # then receive only available tracks and an actual cancellation event.
    repo.sync_availability()
    worker = IdentificationWorker(IdentificationJob(repo, Identifier(), tracks=repo.list_tracks(available_only=True)))
    worker.cancel()
    result = worker.job.run()
    assert result.cancelled and result.processed == 0
    saved = repo.get_track(missing.track_id)
    assert saved.track_id == before['track_id'] and saved.title == before['title']
    assert saved.status == before['status'] and saved.locked_fields == before['locked_fields']
