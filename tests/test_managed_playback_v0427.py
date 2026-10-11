"""Stage 2.3 read contracts. Managed ownership is explicit synthetic evidence.

No test turns a cache/name/hash match into a production binding. Physical FLAC
fixtures exercise the real reader and Qt decoder; offline provider guard is used.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
from io import BytesIO
from pathlib import Path
from threading import Event, get_ident
from time import monotonic
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image
import numpy as np
import soundfile as sf
from mutagen.flac import FLAC, Picture
from PySide6.QtCore import Qt, QThreadPool, QCoreApplication, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.file_state import (
    ConflictReason, FileAvailability, FileFacts, FileObservation, FileState, Ownership,
)
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.identifier import IdentificationJob
from audio_library_organizer.matching.resolver import IdentificationOutcome
from audio_library_organizer.metadata.change_history import ChangeHistory
from audio_library_organizer.storage.repository import LibraryRepository
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
from audio_library_organizer.ui.player import CompactPlayerBar, PlayerBar


def api():
    name = 'audio_library_organizer.jobs.managed_files'
    assert importlib.util.find_spec(name) is not None, 'Central read resolver is not implemented'
    return importlib.import_module(name)


@pytest.fixture
def app():
    app = QApplication.instance() or QApplication([])
    yield app
    assert QThreadPool.globalInstance().waitForDone(5000), 'Read workers did not stop'
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def wait(app, predicate, seconds=5):
    deadline = monotonic() + seconds
    while not predicate() and monotonic() < deadline:
        app.processEvents()
    assert predicate(), 'Bounded Qt read did not finish'


def audio(path, color='#dc5588'):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.sin(np.arange(1600) * .12) * .25, 8000)
    out = BytesIO(); Image.new('RGB', (24, 18), color).save(out, 'PNG')
    pic = Picture(); pic.type = 3; pic.mime = 'image/png'; pic.data = out.getvalue()
    f = FLAC(path); f.add_picture(pic); f.save()
    return path


def library(tmp_path):
    source = audio(tmp_path / 'source' / 'song.flac')
    root = tmp_path / 'library'; root.mkdir()
    repo = LibraryRepository(root / '.alo' / 'library.sqlite3'); repo.initialize()
    repo.register_source(source.parent)
    track = TrackRecord(path=source, artist='Manual Artist', title='Manual Song', year='2001',
                        genre='House', bpm=128, album='Manual Album', status='duplicate',
                        locked_fields={'artist', 'title', '__status__'},
                        field_sources={'artist': 'Ręcznie'}, original_tags={'old_source': str(source)},
                        cover_choice='source', size_bytes=source.stat().st_size,
                        mtime_ns=source.stat().st_mtime_ns)
    repo.upsert_track(track)
    managed = root / 'GOTOWE_MP3' / 'managed.flac'; managed.parent.mkdir()
    managed.write_bytes(source.read_bytes())
    return repo, track, managed, root


def context(repo, track, managed, root, *, current=True, ownership=Ownership.CONFIRMED,
            availability=FileAvailability.PRESENT, conflict=None, binding=True, revision='owned-v1'):
    m = api()
    facts = FileFacts(track.track_id, 20,
        source=FileObservation(track.track_id, str(track.path), FileAvailability.OFFLINE, 20,
                               source_id=track.source_id, is_current=current),
        managed=FileObservation(track.track_id, str(managed), availability, 20, is_current=current),
        managed_expected=True, ownership=ownership, owner_track_id=track.track_id,
        conflict=conflict, is_current=current)
    bindings = ()
    if binding:
        bindings = (m.ManagedReadBinding(repo.library_id, track.track_id, str(managed),
                       hashlib.sha256(managed.read_bytes()).hexdigest(), revision),)
    return m.ReadContext(repo.library_id, str(root), tuple(repo.list_sources()), (facts,), bindings)


def close(editor):
    editor._force_closing = True; editor.close()


def test_rename_keeps_selection_queue_and_editor_identity(tmp_path, app):
    # Old implementation loses both selection and undo on the same UUID at a new locator.
    track = TrackRecord(path=tmp_path / 'old.flac', track_id=str(uuid4()), artist='Old')
    other = TrackRecord(path=tmp_path / 'other.flac', track_id=str(uuid4()), artist='Other')
    page = LibraryPage(); bar = PlayerBar(); history = ChangeHistory()
    editor = MetadataEditorDialog(track, player_bar=bar, navigation_index=0, navigation_total=2)
    try:
        page.set_tracks([track, other]); page.select_track(track)
        page.model.item(page.table.currentIndex().row(), 0).setCheckState(Qt.CheckState.Checked)
        history.record([track], 'Manual change'); track.artist = 'New'
        bar.queue_next(track)
        renamed = replace(track, path=tmp_path / 'new.flac')
        page.set_tracks([renamed, other])
        assert page._current_track() is renamed, 'Selected UUID was lost after locator change'
        assert page._checked_tracks() == [renamed], 'Checked UUID was lost during refresh'
        assert history.history_for(renamed) == ['Manual change']
        history.undo_last([renamed]); assert renamed.artist == 'Old'
        assert renamed.path == tmp_path / 'new.flac'
        assert bar.queued_track.track_id == renamed.track_id
        bar.reconcile_tracks([renamed, other])
        assert bar.queued_track is renamed
        assert editor.track.track_id == renamed.track_id
        assert editor.next_file_button.isEnabled() and not editor.previous_file_button.isEnabled()
        editor.next_file_button.click()
        assert editor.navigation_delta == 1
    finally:
        close(editor); page.close(); bar.close()


def test_undo_uses_uuid_and_does_not_restore_locator_or_source_binding(tmp_path):
    track = TrackRecord(path=tmp_path / 'old.mp3', track_id=str(uuid4()), artist='Before',
                        source_id=str(uuid4()), source_relative_path='old.mp3')
    history = ChangeHistory(); history.record([track], 'Edit')
    old_source = track.source_id
    track.path = tmp_path / 'new.mp3'; track.source_relative_path = 'new.mp3'; track.artist = 'After'
    track.original_tags['fresh_observation'] = 77
    history.undo_last([track])
    assert track.artist == 'Before', 'Undo was addressed to the old path instead of UUID'
    assert track.path == tmp_path / 'new.mp3'
    assert track.source_id == old_source and track.source_relative_path == 'new.mp3'
    assert track.original_tags == {'fresh_observation': 77}


def test_online_stale_result_does_not_overwrite_manual_or_physical_state(tmp_path):
    repo = LibraryRepository(tmp_path / 'db.sqlite3'); repo.initialize()
    track = TrackRecord(path=tmp_path / 'old.mp3', title='Before', artist='A'); repo.upsert_track(track)

    class DelayedIdentifier:
        def identify(self, old):
            fresh = repo.get_track(old.track_id)
            fresh.title = 'Saved while online'; fresh.locked_fields.add('title')
            fresh.path = tmp_path / 'new.mp3'; fresh.original_tags['fresh_scan'] = 42
            repo.upsert_track(fresh)
            old.title = 'Outdated online'
            return IdentificationOutcome(old, None, 'uncertain')

    IdentificationJob(repo, DelayedIdentifier(), tracks=[track]).run()
    loaded = repo.get_track(track.track_id)
    assert loaded.title == 'Saved while online', 'Stale online job overwrote the newer manual save'
    assert loaded.path == tmp_path / 'new.mp3'
    assert loaded.original_tags == {'fresh_scan': 42}
    assert 'title' in loaded.locked_fields


def test_compact_player_uses_uuid_even_when_material_locator_changes(tmp_path, app):
    track = TrackRecord(path=tmp_path / 'old.mp3', track_id=str(uuid4()))
    bar = PlayerBar(); compact = CompactPlayerBar(bar, track)
    try:
        bar.current_track = replace(track, path=tmp_path / 'new.mp3')
        bar.current_path = bar.current_track.path
        assert compact._is_edited_track_loaded(), 'Compact player identifies the record only by path'
    finally:
        compact.close(); bar.close()


def test_managed_only_restart_can_play_edit_and_read_cover(tmp_path, app):
    repo, track, managed, root = library(tmp_path)
    before = managed.read_bytes(); library_id = repo.library_id; source_id = track.source_id
    repo.save_file_facts(context(repo, track, managed, root).facts[0])
    track.path.unlink(); repo.sync_availability()
    reopened = LibraryRepository(repo.database_path); reopened.initialize()
    track = reopened.get_track(track.track_id)
    cached = reopened.get_file_state(track.track_id)
    assert not cached.facts.is_current and not cached.facts.managed.is_current
    # Ownership proof is supplied independently of that historical SQLite cache.
    ctx = context(reopened, track, managed, root, current=False)
    bar = PlayerBar(); bar.set_read_context(ctx)
    editor = MetadataEditorDialog(track, player_bar=bar, read_context=ctx)
    try:
        bar.load_track(track, autoplay=False)
        wait(app, lambda: bar.player.source().toLocalFile() == str(managed))
        wait(app, lambda: editor._cover_candidate_states.get('source') == 'ready')
        assert bar.current_track.track_id == track.track_id
        assert bar.current_path == managed and track.path != managed
        assert editor._cover_candidate_pixmaps['source'].toImage().pixelColor(5, 5) == QColor('#dc5588')
        editor.artist.setText('Saved offline')
        from audio_library_organizer.metadata.change_history import metadata_revision
        fresh = reopened.get_track(track.track_id)
        reopened.save_metadata(track.track_id, {'artist': editor.values()['artist']},
                               expected_revision=metadata_revision(fresh), library_id=library_id)
        final = reopened.get_track(track.track_id)
        assert final.artist == 'Saved offline' and final.title == 'Manual Song'
        assert final.source_id == source_id and final.status == 'duplicate'
        assert final.locked_fields == {'artist', 'title', '__status__'}
        assert final.field_sources == {'artist': 'Ręcznie'}
        assert final.original_tags['old_source'] == str(track.path)
        assert reopened.library_id == library_id and len(reopened.list_tracks()) == 1
        assert managed.read_bytes() == before
    finally:
        close(editor); bar.close()


@pytest.mark.parametrize('purpose', ['PLAYBACK', 'WAVEFORM', 'COVER_READ', 'AUDIO_IDENTIFICATION',
                                    'AUDIO_PROPERTIES', 'METADATA_EDITOR_READ'])
def test_owned_managed_read_purposes_recheck_without_mutation(tmp_path, purpose):
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root); before = managed.read_bytes(); original = deepcopy(track)
    plan = m.resolve_read_path(track, ctx, m.ReadPurpose[purpose], generation=3)
    assert plan.locator == str(managed) and plan.kind == m.MaterialKind.MANAGED
    assert plan.requires_recheck and not plan.is_verified
    result = m.read_material(plan, lambda path: path.read_bytes())
    assert result.resolution.is_verified and not result.resolution.unresolved
    assert result.value == before and result.resolution.generation == 3
    assert not result.resolution.safe_for_file_mutation
    assert track == original and managed.read_bytes() == before


@pytest.mark.parametrize('state', [FileAvailability.UNKNOWN, FileAvailability.OFFLINE, FileAvailability.ERROR])
def test_unknown_offline_error_do_not_delete_record(tmp_path, state):
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root, availability=state)
    before = deepcopy(track)
    plan = m.resolve_read_path(track, ctx, m.ReadPurpose.PLAYBACK)
    assert plan.requires_recheck and not plan.is_verified
    assert track == before and len(repo.list_tracks()) == 1


def test_history_cache_alone_cannot_supply_managed_ownership(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root, current=False, binding=False)
    track.path.unlink()
    plan = m.resolve_read_path(track, ctx, m.ReadPurpose.PLAYBACK)
    assert plan.kind != m.MaterialKind.MANAGED and not plan.is_verified


@pytest.mark.parametrize('kind', ['unknown_owner', 'conflict', 'missing', 'hash_only'])
def test_invalid_managed_uses_explicit_source_fallback_without_changing_file_state(tmp_path, kind):
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root,
                  ownership=Ownership.UNKNOWN if kind == 'unknown_owner' else Ownership.CONFIRMED,
                  conflict=ConflictReason.MULTIPLE_OWNERS if kind == 'conflict' else None,
                  availability=FileAvailability.MISSING if kind == 'missing' else FileAvailability.PRESENT,
                  binding=kind != 'hash_only')
    facts = replace(ctx.facts[0], source=replace(ctx.facts[0].source, availability=FileAvailability.PRESENT))
    ctx = replace(ctx, facts=(facts,)); before = deepcopy(facts)
    plan = m.resolve_read_path(track, ctx, m.ReadPurpose.PLAYBACK)
    assert plan.kind == m.MaterialKind.SOURCE and plan.locator == str(track.path)
    assert m.recheck_read_path(plan).is_verified
    assert ctx.facts[0] == before and ctx.facts[0].managed_expected is True
    assert track.track_id == facts.track_id


def test_source_only_works_with_registered_source_and_no_managed_binding(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = m.ReadContext(repo.library_id, str(root), tuple(repo.list_sources()))
    plan = m.resolve_read_path(track, ctx, m.ReadPurpose.PLAYBACK)
    assert plan.kind == m.MaterialKind.SOURCE
    assert m.recheck_read_path(plan).is_verified
    foreign = replace(track, source_id=str(uuid4()))
    assert m.resolve_read_path(foreign, ctx, m.ReadPurpose.PLAYBACK).locator is None


def test_replaced_managed_same_path_and_same_stat_is_not_accepted(tmp_path):
    import os
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root); plan = m.resolve_read_path(track, ctx, m.ReadPurpose.COVER_READ)
    stat = managed.stat(); data = bytearray(managed.read_bytes()); data[-1] ^= 1
    managed.write_bytes(data); os.utime(managed, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    checked = m.recheck_read_path(plan)
    assert checked.unresolved and not checked.is_verified
    assert checked.reason_code == 'MANAGED_IDENTITY_CHANGED'


def test_managed_symlink_escape_is_rejected(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root)
    outside = tmp_path / 'outside.flac'; outside.write_bytes(managed.read_bytes())
    managed.unlink(); managed.symlink_to(outside)
    plan = m.resolve_read_path(track, ctx, m.ReadPurpose.COVER_READ)
    assert not m.recheck_read_path(plan).is_verified


def test_source_sha_or_fingerprint_never_adopts_an_unknown_managed(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api()
    track.sha256 = hashlib.sha256(managed.read_bytes()).hexdigest(); track.fingerprint = 'SAME'
    ctx = context(repo, track, managed, root, binding=False)
    assert m.resolve_read_path(track, ctx, m.ReadPurpose.PLAYBACK).kind != m.MaterialKind.MANAGED


def test_read_context_and_history_are_isolated_by_library_uuid(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root)
    foreign = replace(ctx, library_id=str(uuid4()))
    assert m.resolve_read_path(track, foreign, m.ReadPurpose.PLAYBACK).locator is None
    history = ChangeHistory(library_id=ctx.library_id); history.record([track], 'Edit')
    track.artist = 'New'
    assert history.undo_last([track], library_id=foreign.library_id) is None
    assert track.artist == 'New'
    history.undo_last([track], library_id=ctx.library_id); assert track.artist == 'Manual Artist'


def test_stale_cover_or_waveform_generation_is_ignored(tmp_path, app):
    repo, track, managed, root = library(tmp_path); m = api(); ctx = context(repo, track, managed, root)
    bar = PlayerBar(); bar.set_read_context(ctx); bar.load_track(track, autoplay=False)
    wait(app, lambda: bar.player.source().toLocalFile() == str(managed))
    editor = MetadataEditorDialog(track, player_bar=bar, read_context=ctx)
    old_generation = bar._waveform_generation; old_cover = bar._cover_request_serial
    second = audio(root / 'GOTOWE_MP3' / 'second.flac', '#2277bb')
    changed = context(repo, track, second, root, revision='owned-v2')
    bar.set_read_context(changed); bar.load_track(track, autoplay=False)
    wait(app, lambda: bar.player.source().toLocalFile() == str(second))
    bar._waveform_ready(old_generation, [1.0])
    assert bar.seek.peaks != [1.0] and bar._cover_request_serial > old_cover
    assert not editor.accepts_read_result(m.resolve_read_path(track, ctx, m.ReadPurpose.COVER_READ))
    close(editor)
    assert not editor.accepts_read_result(m.resolve_read_path(track, changed, m.ReadPurpose.COVER_READ))
    bar.set_read_context(replace(changed, library_id=str(uuid4())))
    assert bar.current_track is None and bar.queued_track is None
    bar._waveform_ready(bar._waveform_generation - 1, [1.0]); assert bar.seek.peaks != [1.0]
    bar.close()


def test_table_render_and_sort_do_not_probe_audio_paths(tmp_path, app, monkeypatch):
    repo, track, managed, root = library(tmp_path); m = api(); ctx = context(repo, track, managed, root)
    page = LibraryPage(); page.set_read_context(ctx); gui_thread = get_ident()
    original_stat, original_resolve = Path.stat, Path.resolve
    def stat(path, *args, **kwargs):
        assert get_ident() != gui_thread or path not in (track.path, managed), 'GUI probed an audio path'
        return original_stat(path, *args, **kwargs)
    def resolve(path, *args, **kwargs):
        assert get_ident() != gui_thread or path not in (track.path, managed), 'GUI resolved an audio path'
        return original_resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat); monkeypatch.setattr(Path, 'resolve', resolve)
    try:
        page.set_tracks([track]); page.select_track(track); page.refresh()
        page.table.sortByColumn(2, Qt.SortOrder.AscendingOrder); page.table.viewport().repaint()
    finally:
        page.close()


def test_read_cancellation_prevents_reader_and_no_new_public_file_state(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api(); called = []
    plan = m.resolve_read_path(track, context(repo, track, managed, root), m.ReadPurpose.COVER_READ)
    result = m.read_material(plan, lambda p: called.append(p), cancelled=lambda: True)
    assert called == [] and result.resolution.unresolved and result.resolution.reason_code == 'CANCELLED'
    assert len(FileState) == 6


def test_metadata_compare_and_set_rejects_stale_revision_and_other_library(tmp_path):
    repo, track, managed, root = library(tmp_path)
    assert hasattr(repo, 'save_metadata'), 'Field-only conditional metadata write is missing'
    from audio_library_organizer.metadata.change_history import metadata_revision
    baseline = metadata_revision(track)
    repo.save_metadata(track.track_id, {'title': 'New'}, expected_revision=baseline, library_id=repo.library_id)
    with pytest.raises(ValueError):
        repo.save_metadata(track.track_id, {'title': 'Old'}, expected_revision=baseline, library_id=repo.library_id)
    fresh = repo.get_track(track.track_id)
    with pytest.raises(ValueError):
        repo.save_metadata(track.track_id, {'title': 'Other'}, expected_revision=metadata_revision(fresh), library_id=str(uuid4()))
    with pytest.raises(ValueError):
        repo.save_metadata(track.track_id, {'path': str(managed)}, expected_revision=metadata_revision(fresh), library_id=repo.library_id)
    assert repo.get_track(track.track_id).path == track.path


def test_saved_notice_owned_timer_and_variant_d_geometry_remain(tmp_path, app):
    bar = PlayerBar(); editor = MetadataEditorDialog(TrackRecord(path=tmp_path / 'a.mp3'), player_bar=bar)
    try:
        assert editor._saved_notice_timer.parent() is editor.saved_notice
        assert editor._saved_notice_timer.isSingleShot()
        assert bar.minimumHeight() == 114 and editor.compact_player.height() == 74
        assert type(bar.surface) is type(editor.compact_player.surface)
    finally:
        close(editor); bar.close()


def test_audio_identification_reads_the_resolved_managed_fixture(tmp_path):
    import inspect
    from audio_library_organizer.audio.fingerprint import FingerprintResult
    from audio_library_organizer.jobs.audio_identification import AudioIdentification
    repo, track, managed, root = library(tmp_path); ctx = context(repo, track, managed, root)
    assert 'read_context' in inspect.signature(AudioIdentification.__init__).parameters, 'Audio job bypasses the read resolver'
    read_paths = []
    class OfflineClient:
        client_key = 'fixture-key'
        def lookup(self, fingerprint, duration):
            assert fingerprint == 'prepared-fixture-fingerprint' and duration == 5
            return []
    def fingerprinter(path):
        read_paths.append(path)
        assert path.read_bytes() == managed.read_bytes()
        return FingerprintResult('prepared-fixture-fingerprint', 5)
    job = AudioIdentification(OfflineClient(), fingerprinter=fingerprinter, read_context=ctx)
    assert job.lookup(track) == []
    assert read_paths == [managed]
    assert track.path != managed and job.read_resolution.is_verified


def test_editor_save_does_not_restore_stale_source_locator(tmp_path, app):
    from PySide6.QtCore import QSettings
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui.main_window import MainWindow
    window = MainWindow(AppSettings((), LibraryPaths(tmp_path / 'library')),
        QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    track = TrackRecord(path=tmp_path / 'old.mp3', artist='Before', title='Song')
    window.repository.upsert_track(track)
    editor = MetadataEditorDialog(track, window, player_bar=window.player)
    try:
        fresh = window.repository.get_track(track.track_id)
        fresh.path = tmp_path / 'new.mp3'; fresh.original_tags['new_source_evidence'] = 19
        window.repository.upsert_track(fresh)
        editor.artist.setText('Saved manually')
        window._save_metadata_from_editor(track, editor)
        loaded = window.repository.get_track(track.track_id)
        assert loaded.path == fresh.path, 'Editor saved an old whole TrackRecord over newer source state'
        assert loaded.original_tags['new_source_evidence'] == 19 and loaded.artist == 'Saved manually'
    finally:
        close(editor); window.close()


def test_conflicting_explicit_managed_owners_cannot_read_the_same_locator(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root)
    other_owner = replace(ctx.managed_bindings[0], track_id=str(uuid4()))
    ctx = replace(ctx, managed_bindings=(*ctx.managed_bindings, other_owner))
    plan = m.resolve_read_path(track, ctx, m.ReadPurpose.PLAYBACK)
    assert plan.locator is None, 'Two explicit owners of one output must not select managed'
    assert plan.unresolved and not plan.safe_for_file_mutation


def test_foreign_library_managed_owner_is_not_ignored_at_the_same_locator(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api(); ctx = context(repo, track, managed, root)
    foreign_owner = replace(ctx.managed_bindings[0], library_id=str(uuid4()))
    ctx = replace(ctx, managed_bindings=(*ctx.managed_bindings, foreign_owner))
    plan = m.resolve_read_path(track, ctx, m.ReadPurpose.PLAYBACK)
    assert plan.locator is None, 'Known output ownership in a foreign library was ignored'


def test_audio_approval_does_not_overwrite_newer_database_metadata(tmp_path, app):
    from PySide6.QtCore import QSettings
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui.main_window import MainWindow
    from audio_library_organizer.domain.candidates import AcoustIDHit
    from audio_library_organizer.jobs.audio_identification import approve_audio_source
    window = MainWindow(AppSettings((), LibraryPaths(tmp_path / 'library')),
        QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    track = TrackRecord(path=tmp_path / 'song.mp3', artist='Before')
    window.repository.upsert_track(track)
    previous = deepcopy(track)
    try:
        fresh = window.repository.get_track(track.track_id)
        fresh.artist = 'New manual save'
        fresh.field_source_values = {'artist': {'Ręcznie': 'New manual save'}}
        fresh.locked_fields.add('artist')
        window.repository.upsert_track(fresh)
        approve_audio_source(track, AcoustIDHit('recording', .9, 'Old title', 'Old artist'))
        window._save_audio_source(track, previous)
        loaded = window.repository.get_track(track.track_id)
        assert loaded.field_source_values == fresh.field_source_values, 'Stale audio approval replaced newer provenance'
        assert loaded.artist == fresh.artist and loaded.locked_fields == fresh.locked_fields
        assert not loaded.audio_recognition
    finally:
        window.close()


def test_async_source_cover_keeps_existing_gallery_capacity(tmp_path, app, monkeypatch):
    repo, track, managed, root = library(tmp_path)
    track.field_source_values['__cover__'] = {f'Provider {n}': f'https://example.invalid/{n}.png' for n in range(5)}
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    legacy = MetadataEditorDialog(track)
    editor = MetadataEditorDialog(track, read_context=context(repo, track, managed, root))
    try:
        wait(app, lambda: editor._cover_candidate_states['source'] == 'ready')
        assert len(editor._cover_candidate_urls) == len(legacy._cover_candidate_urls) == 4
        assert editor.cover_proposals_grid.count() == legacy.cover_proposals_grid.count()
    finally:
        close(editor); close(legacy)


def test_bulk_online_callback_is_ignored_after_library_switch(tmp_path, app, monkeypatch):
    from PySide6.QtCore import QSettings
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui.main_window import MainWindow
    window = MainWindow(AppSettings((), LibraryPaths(tmp_path / 'library')),
        QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    source = audio(tmp_path / 'source' / 'song.flac')
    window.repository.register_source(source.parent)
    track = TrackRecord(path=source, artist='Before', title='Song')
    window.repository.upsert_track(track)
    started, released = Event(), Event(); callbacks = []
    class DelayedIdentifier:
        def identify(self, record):
            started.set()
            assert released.wait(5)
            return IdentificationOutcome(record, None, 'uncertain')
    monkeypatch.setattr(window, '_build_identifier', lambda: DelayedIdentifier())
    monkeypatch.setattr(window, '_identify_finished', lambda result: callbacks.append(window.repository.library_id))
    try:
        window.start_identification(); wait(app, started.is_set)
        foreign = LibraryRepository(tmp_path / 'other' / 'db.sqlite3'); foreign.initialize()
        window.repository = foreign
        released.set(); wait(app, lambda: window._thread is None)
        assert callbacks == [], 'Old library result was dispatched to the active profile'
        assert foreign.list_tracks() == []
    finally:
        released.set(); wait(app, lambda: window._thread is None); window.close()


def test_main_window_defers_close_until_identification_worker_stops(tmp_path, app, monkeypatch):
    from PySide6.QtCore import QSettings
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui.main_window import MainWindow
    window = MainWindow(AppSettings((), LibraryPaths(tmp_path / 'library')),
        QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    source = audio(tmp_path / 'source' / 'song.flac')
    window.repository.register_source(source.parent)
    window.repository.upsert_track(TrackRecord(path=source, artist='Before', title='Song'))
    started, released = Event(), Event()
    class DelayedIdentifier:
        def identify(self, record):
            started.set()
            assert released.wait(5)
            return IdentificationOutcome(record, None, 'uncertain')
    monkeypatch.setattr(window, '_build_identifier', lambda: DelayedIdentifier())
    try:
        window.show(); window.start_identification(); wait(app, started.is_set)
        assert not window.close(), 'QThread owner closed before its worker stopped'
        assert window._worker._cancelled.is_set()
        released.set(); wait(app, lambda: window._thread is None)
        assert not window.isVisible()
    finally:
        released.set(); wait(app, lambda: window._thread is None); window.close()


@pytest.mark.parametrize('alias_kind', ['symlink', 'hardlink'])
def test_managed_alias_cannot_hide_a_different_explicit_owner(tmp_path, alias_kind):
    import os
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = context(repo, track, managed, root)
    alias = managed.with_name('alias.flac')
    if alias_kind == 'symlink':
        alias.symlink_to(managed)
    else:
        os.link(managed, alias)
    other_owner = replace(ctx.managed_bindings[0], track_id=str(uuid4()), locator=str(alias))
    ctx = replace(ctx, managed_bindings=(*ctx.managed_bindings, other_owner))
    result = m.read_material(m.resolve_read_path(track, ctx, m.ReadPurpose.PLAYBACK), lambda path: path.read_bytes())
    assert result.resolution.unresolved and result.value is None, 'An alias hid conflicting managed ownership'


def test_late_cover_worker_cannot_replace_new_material_or_closed_editor(tmp_path, app):
    from audio_library_organizer.metadata.artwork import extract_embedded_cover
    from audio_library_organizer.ui.workers import ReadTask
    repo, track, managed, root = library(tmp_path); m = api(); ctx = context(repo, track, managed, root)
    bar = PlayerBar(); bar.set_read_context(ctx)
    editor = MetadataEditorDialog(track, player_bar=bar, read_context=ctx)
    started, released, delivered = Event(), Event(), Event()
    try:
        wait(app, lambda: editor._cover_candidate_states['source'] == 'ready')
        old_plan = editor._gallery_read_plan
        def delayed_cover(path):
            value = extract_embedded_cover(path)
            started.set(); assert released.wait(5)
            return value
        task = ReadTask(old_plan, delayed_cover, Event())
        task.signals.ready.connect(editor._source_cover_read_ready, Qt.ConnectionType.QueuedConnection)
        task.signals.ready.connect(lambda *args: delivered.set(), Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task); wait(app, started.is_set)
        second = audio(root / 'GOTOWE_MP3' / 'blue.flac', '#2277bb')
        bar.set_read_context(context(repo, track, second, root, revision='owned-v2'))
        editor._load_cover_gallery()
        wait(app, lambda: editor._cover_candidate_states['source'] == 'ready')
        close(editor); released.set(); wait(app, delivered.is_set)
        assert editor._cover_candidate_pixmaps['source'].toImage().pixelColor(5, 5) == QColor('#2277bb')
        assert not editor.accepts_read_result(old_plan)
    finally:
        released.set(); close(editor); bar.close()


def test_source_only_playback_and_queue_use_refreshed_uuid(tmp_path, app, monkeypatch):
    from PySide6.QtMultimedia import QMediaPlayer
    repo, track, managed, root = library(tmp_path); m = api()
    ctx = m.ReadContext(repo.library_id, str(root), tuple(repo.list_sources()))
    next_path = audio(track.path.with_name('next.flac'))
    queued = TrackRecord(path=next_path, artist='Next', title='Next')
    repo.upsert_track(queued)
    renamed = replace(queued, path=audio(next_path.with_name('renamed.flac')), source_relative_path='renamed.flac')
    before = {p: p.read_bytes() for p in (track.path, next_path, renamed.path)}
    bar = PlayerBar(); bar.set_read_context(ctx)
    try:
        bar.load_track(track, autoplay=False)
        wait(app, lambda: bar.player.source().toLocalFile() == str(track.path))
        bar.queue_next(queued); bar.reconcile_tracks([track, renamed])
        assert bar.queued_track is renamed
        monkeypatch.setattr(bar.player, 'mediaStatus', lambda: QMediaPlayer.MediaStatus.EndOfMedia)
        bar._media_status(QMediaPlayer.MediaStatus.EndOfMedia)
        wait(app, lambda: bar.player.source().toLocalFile() == str(renamed.path))
        assert bar.current_track.track_id == queued.track_id
        assert bar.current_track.source_id == queued.source_id and bar.queued_track is None
        assert before == {p: p.read_bytes() for p in before}
    finally:
        bar.close()


def test_play_pause_during_read_preflight_does_not_play_an_empty_or_stale_source(tmp_path, app, monkeypatch):
    import audio_library_organizer.ui.player as player_module
    repo, track, managed, root = library(tmp_path); m = api()
    original_task = player_module.ReadTask
    started, released = Event(), Event(); plays = []
    def task(plan, reader, cancel):
        if plan.purpose == m.ReadPurpose.PLAYBACK:
            def delayed(path):
                started.set(); assert released.wait(5)
                return None
            reader = delayed
        return original_task(plan, reader, cancel)
    monkeypatch.setattr(player_module, 'ReadTask', task)
    bar = PlayerBar(); bar.set_read_context(context(repo, track, managed, root))
    monkeypatch.setattr(bar.player, 'play', lambda: plays.append(bar.player.source().toLocalFile()))
    try:
        bar.load_track(track, autoplay=True); wait(app, started.is_set)
        bar.toggle()  # Pause the pending autoplay request before it resolves.
        released.set(); wait(app, lambda: bar.player.source().toLocalFile() == str(managed))
        assert plays == [], 'Pause during preflight played an empty source or resurrected autoplay'
    finally:
        released.set(); bar.close()


def test_late_seek_autoplay_cannot_start_new_material(tmp_path, app, monkeypatch):
    first = audio(tmp_path / 'first.flac'); second = audio(tmp_path / 'second.flac')
    bar = PlayerBar(); plays = []
    monkeypatch.setattr(bar.player, 'play', lambda: plays.append(bar.player.source().toLocalFile()))
    monkeypatch.setattr(bar.player, 'position', lambda: 1000)
    monkeypatch.setattr(bar.player, 'duration', lambda: 5000)
    try:
        bar.load(first, position_ms=1000, autoplay=True)
        bar._pending_source_ready = True
        bar._pending_seek.target_for_duration(5000, generation=bar._waveform_generation)
        bar._position(1000)  # Existing deferred autoplay is now queued.
        bar.load(second, autoplay=False)
        app.processEvents()
        assert plays == [], 'Deferred autoplay from the old source started a new material'
    finally:
        bar.close()


def test_old_editor_ready_signal_cannot_modify_another_library(tmp_path, app, monkeypatch):
    from PySide6.QtCore import QSettings
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui.main_window import MainWindow
    window = MainWindow(AppSettings((), LibraryPaths(tmp_path / 'library')),
        QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    track = TrackRecord(path=tmp_path / 'song.mp3', artist='Before', status='review')
    window.repository.upsert_track(track); window.refresh_data()
    foreign = LibraryRepository(tmp_path / 'other' / '.alo' / 'library.sqlite3'); foreign.initialize()
    foreign.upsert_track(deepcopy(track))
    before_locks = foreign.get_track(track.track_id).locked_fields.copy()
    def use_editor(editor):
        window.repository = foreign
        window.change_history = ChangeHistory(library_id=foreign.library_id)
        editor.ready_requested.emit(editor, True)
        assert foreign.get_track(track.track_id).locked_fields == before_locks, 'Old editor changed a foreign library with the same UUID'
        editor._force_closing = True
        return 0
    monkeypatch.setattr(MetadataEditorDialog, 'exec', use_editor)
    try:
        window._open_metadata_editor(track)
    finally:
        window.close()


def test_duplicate_selection_does_not_cross_library_context(tmp_path, app):
    from audio_library_organizer.ui.duplicates_page import DuplicatesPage
    a = TrackRecord(path=tmp_path / 'a.mp3', track_id=str(uuid4()), sha256='same', artist='A', title='B')
    b = TrackRecord(path=tmp_path / 'b.mp3', track_id=str(uuid4()), sha256='same', artist='A', title='B')
    bar = PlayerBar(); page = DuplicatesPage(bar)
    try:
        page.library_id = str(uuid4()); page.set_tracks([a, b]); page.files.selectRow(1)
        assert page._selected()[0].track_id == b.track_id
        page.library_id = str(uuid4())
        page.set_tracks([replace(a, path=tmp_path / 'foreign_a.mp3'), replace(b, path=tmp_path / 'foreign_b.mp3')])
        assert page.files.currentRow() == 0, 'Selection was restored using a UUID from the previous library'
    finally:
        page.close(); bar.close()


def test_source_scan_revision_rejects_old_waveform_at_the_same_locator(tmp_path, app):
    repo, track, managed, root = library(tmp_path); m = api()
    bar = PlayerBar(); bar.set_read_context(m.ReadContext(repo.library_id, str(root), tuple(repo.list_sources())))
    try:
        bar.load_track(track, autoplay=False)
        wait(app, lambda: bar.player.source().toLocalFile() == str(track.path))
        old_plan = bar.read_plan(track, m.ReadPurpose.WAVEFORM)
        old_generation = bar._waveform_generation
        fresh = replace(track, mtime_ns=track.mtime_ns + 1, sha256='f' * 64)
        bar.reconcile_tracks([fresh])
        assert not bar.accepts_read_result(old_plan), 'Same source locator accepted the previous scan revision'
        bar._waveform_ready(old_generation, [1.0])
        assert bar.seek.peaks != [1.0]
    finally:
        bar.close()


def test_editor_source_guard_uses_refreshed_database_material_stamp(tmp_path, app):
    from PySide6.QtCore import QSettings
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    from audio_library_organizer.ui.main_window import MainWindow
    repo, track, managed, root = library(tmp_path)
    window = MainWindow(AppSettings((), LibraryPaths(root)),
        QSettings(str(tmp_path / 'prefs.ini'), QSettings.Format.IniFormat))
    editor = MetadataEditorDialog(window.repository.get_track(track.track_id), window, player_bar=window.player)
    try:
        old_plan = editor._gallery_read_plan
        fresh = window.repository.get_track(track.track_id)
        fresh.mtime_ns += 1; fresh.sha256 = 'f' * 64
        window.repository.upsert_track(fresh); window.refresh_data()
        assert not editor.accepts_read_result(old_plan), 'Inactive editor kept the old source material revision'
    finally:
        close(editor); window.close()


@pytest.mark.parametrize('state', ['pending', 'closed', 'old_status'])
def test_review_stale_native_end_does_not_consume_queue_or_repeat(tmp_path, app, monkeypatch, state):
    from PySide6.QtMultimedia import QMediaPlayer
    track = TrackRecord(path=tmp_path / 'current.flac', track_id=str(uuid4()))
    queued = TrackRecord(path=tmp_path / 'next.flac', track_id=str(uuid4()))
    bar = PlayerBar(); calls = []
    bar.current_track = track; bar.current_path = track.path; bar.queue_next(queued)
    bar._read_pending = state == 'pending'
    if state == 'closed':
        bar.close()
    monkeypatch.setattr(bar, 'load_track', lambda *a, **k: calls.append('queue'))
    monkeypatch.setattr(bar.player, 'play', lambda: calls.append('repeat'))
    try:
        bar.player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)
        assert bar.queued_track is queued and not calls, 'Stale native end consumed the new queue'
        bar.repeat.setChecked(True)
        bar.player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)
        assert not calls, 'Stale native end restarted a different material'
    finally:
        bar.close()


def test_review_duplicate_propagation_preserves_manual_provenance(tmp_path):
    repo = LibraryRepository(tmp_path / 'db.sqlite3'); repo.initialize()
    primary = TrackRecord(path=tmp_path / 'a.mp3', sha256='same', status='review',
        artist='Online', title='Primary', field_sources={'artist': 'MusicBrainz', 'title': 'MusicBrainz'},
        field_source_values={'artist': {'MusicBrainz': 'Online'}, 'title': {'MusicBrainz': 'Primary'}})
    manual_values = {'Ręcznie': 'Manual', 'Tag': 'Original artist'}
    duplicate = TrackRecord(path=tmp_path / 'b.mp3', sha256='same', status='duplicate',
        artist='Manual', title='Before', locked_fields={'artist', '__status__'},
        field_sources={'artist': 'Ręcznie'}, field_source_values={'artist': manual_values.copy()})
    repo.upsert_track(primary); repo.upsert_track(duplicate)
    class Identifier:
        def identify(self, track): return IdentificationOutcome(track, None, 'uncertain')
    IdentificationJob(repo, Identifier(), tracks=[primary, duplicate]).run()
    fresh = repo.get_track(duplicate.track_id)
    assert fresh.artist == 'Manual' and fresh.field_sources['artist'] == 'Ręcznie'
    assert fresh.field_source_values['artist'] == manual_values
    assert fresh.title == 'Primary' and fresh.field_sources['title'] == 'MusicBrainz'
    assert fresh.track_id == duplicate.track_id and fresh.path == duplicate.path
    assert fresh.status == 'duplicate' and fresh.sha256 == 'same'


def test_review_online_cas_rejects_previous_audio_at_the_same_locator(tmp_path):
    repo = LibraryRepository(tmp_path / 'db.sqlite3'); repo.initialize()
    track = TrackRecord(path=tmp_path / 'same.mp3', title='Before', size_bytes=10,
                        mtime_ns=10, sha256='a' * 64, fingerprint='OLD_AUDIO')
    repo.upsert_track(track)
    class ReplacedAudio:
        def identify(self, old):
            scanned = repo.get_track(old.track_id)
            scanned.size_bytes = 20; scanned.mtime_ns = 20
            scanned.sha256 = 'b' * 64; scanned.fingerprint = 'NEW_AUDIO'
            repo.upsert_track(scanned)
            old.title = 'Stale old audio result'
            return IdentificationOutcome(old, None, 'uncertain')
    result = IdentificationJob(repo, ReplacedAudio(), tracks=[track]).run()
    fresh = repo.get_track(track.track_id)
    assert fresh.title == 'Before', 'Same-locator material replacement accepted an old online result'
    assert fresh.sha256 == 'b' * 64 and fresh.fingerprint == 'NEW_AUDIO'
    assert fresh.path == track.path and fresh.track_id == track.track_id
    assert result.skipped_stale == 1


def test_review_async_embedded_cover_keeps_explicit_source_choice(tmp_path, app, monkeypatch):
    repo, track, managed, root = library(tmp_path)
    track.field_source_values['__cover__'] = {'Existing provider': 'https://example.invalid/cover.png'}
    monkeypatch.setattr(MetadataEditorDialog, '_load_candidate_cover', lambda *args: None)
    editor = MetadataEditorDialog(track, read_context=context(repo, track, managed, root))
    before = managed.read_bytes()
    try:
        assert editor.cover_choice == 'source', 'Pending source cover silently selected external'
        wait(app, lambda: editor._cover_candidate_states.get('source') == 'ready')
        assert editor.cover_choice == editor._selected_cover_key == 'source'
        assert editor.cover_save_state()['cover_choice'] == 'source'
        assert managed.read_bytes() == before
    finally:
        close(editor)


def test_review_renamed_source_is_readable_despite_historical_cache(tmp_path):
    repo, track, managed, root = library(tmp_path); m = api()
    repo.save_file_facts(context(repo, track, managed, root).facts[0])
    new_path = audio(track.path.with_name('renamed.flac'))
    repo.upsert_track(replace(track, path=new_path, source_relative_path='renamed.flac'))
    snapshot = repo.file_check_snapshot(); fresh = repo.get_track(track.track_id)
    ctx = m.ReadContext(snapshot.library_id, str(root), snapshot.sources,
        tuple(cached.facts for _, cached in snapshot.cached),
        source_materials=tuple(m.SourceReadMaterial.from_track(t) for t in snapshot.tracks))
    assert repo.get_file_state(track.track_id).evaluation.reason == 'TRACK_BINDING_CHANGED'
    plan = m.resolve_read_path(fresh, ctx, m.ReadPurpose.COVER_READ)
    assert plan.locator == str(new_path) and plan.kind == m.MaterialKind.SOURCE
    from audio_library_organizer.metadata.artwork import extract_embedded_cover
    result = m.read_material(plan, extract_embedded_cover)
    assert result.resolution.is_verified and result.value
    assert fresh.track_id == track.track_id and fresh.source_id == track.source_id


def test_review_playback_fallback_uses_waveform_of_the_actual_source(tmp_path, app, monkeypatch):
    import audio_library_organizer.ui.waveform as waveform_module
    repo, track, managed, root = library(tmp_path); m = api()
    track.cover_choice = 'placeholder'
    ctx = context(repo, track, managed, root)
    ctx = replace(ctx, facts=(replace(ctx.facts[0], source=replace(ctx.facts[0].source,
        availability=FileAvailability.PRESENT)),))
    jobs = []
    class Pool:
        def start(self, job): jobs.append(job)
    bar = PlayerBar(); bar.set_read_context(ctx)
    pool = QThreadPool.globalInstance()
    monkeypatch.setattr(QThreadPool, 'globalInstance', lambda: Pool())
    monkeypatch.setattr(waveform_module, 'read_waveform',
                        lambda path, **kwargs: [.9] if path == managed else [.1])
    try:
        bar.load_track(track, autoplay=False)
        with ThreadPoolExecutor(max_workers=1) as worker:
            completed = set()
            for job in list(jobs):
                if isinstance(job, waveform_module.WaveformJob):
                    worker.submit(job.run).result(timeout=5); completed.add(id(job))
            app.processEvents()
            managed.unlink()  # Fixture operation only: disappears before playback preflight.
            playback = next(job for job in jobs if getattr(job, 'plan', None) is not None
                            and job.plan.purpose == m.ReadPurpose.PLAYBACK)
            worker.submit(playback.run).result(timeout=5); completed.add(id(playback))
            app.processEvents()
            for job in list(jobs):
                if id(job) not in completed:
                    worker.submit(job.run).result(timeout=5)
            app.processEvents()
        assert bar.current_path == track.path and bar.current_track.track_id == track.track_id
        assert bar.seek.peaks == [.1], 'Managed waveform was shown after playback fell back to source'
    finally:
        monkeypatch.setattr(QThreadPool, 'globalInstance', lambda: pool)
        bar.close()


def test_review_standalone_player_keeps_an_absolute_local_url(tmp_path, app, monkeypatch):
    path = audio(tmp_path / 'standalone.flac')
    monkeypatch.chdir(tmp_path)
    bar = PlayerBar()
    try:
        bar.load(Path('standalone.flac'), autoplay=False)
        assert bar.player.source().toLocalFile() == str(path)
    finally:
        bar.close()
