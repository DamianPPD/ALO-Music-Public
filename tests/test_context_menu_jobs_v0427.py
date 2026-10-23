"""Backend/unit contracts. No Qt import and no claim of Windows GUI execution."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread, get_ident
import unittest
from unittest.mock import patch

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs.managed_files import ReadContext, ReadPurpose, MaterialKind, local_read_plan
from audio_library_organizer.jobs.context_menu import (
    MenuContext, MenuWork, LatestMenuWork, execute_menu_work, frozen_value, snapshot_matches,
)


class MenuWorkTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.path = self.root / 'synthetic.mp3'
        self.path.write_bytes(b'synthetic bytes for read identity; no audio decoder in unit tests')
        self.track = TrackRecord(self.path, track_id='synthetic-UUID')
        self.context = ReadContext('library-one', str(self.root))
        self.token = MenuContext(self.context, 1, ((self.track.track_id, frozen_value(self.track)),),
                                 self.track.track_id, (), (('synthetic-UUID',),), 5)
        self.snapshot = (self.context, (self.track,), {})
        self.plan = local_read_plan(self.path, ReadPurpose.PLAYBACK, generation=3)

    def work(self, operation='action', plans=None, data=()):
        return MenuWork(self.token, operation, (self.plan,) if plans is None else plans,
                        lambda: self.snapshot, data)

    def test_real_presence_deduplicated_across_actions(self):
        calls = []; original = Path.is_file
        def observe(path): calls.append(path); return original(path)
        work = self.work('probe', tuple((key, (self.plan,)) for key in ('open', 'play', 'next', 'playlist')))
        with patch.object(Path, 'is_file', observe):
            self.assertEqual(execute_menu_work(work, Event()), tuple((k, True) for k in ('open', 'play', 'next', 'playlist')))
        self.assertEqual(calls, [self.path])

    def test_missing_unresolved_and_empty_plans_are_disabled(self):
        self.path.unlink()
        for plans in ((self.plan,), (None,), ()):
            self.assertEqual(execute_menu_work(self.work('probe', (('play', plans),)), Event()), (('play', False),))

    def test_presence_exception_is_not_permission(self):
        with patch.object(Path, 'is_file', side_effect=OSError('controlled error')):
            self.assertEqual(execute_menu_work(self.work('probe', (('play', (self.plan,)),)), Event()), (('play', False),))

    def test_slow_real_is_file_can_run_away_from_caller(self):
        entered, release = Event(), Event(); calls = []; outcome = []
        original = Path.is_file; caller = get_ident()
        def delayed(path):
            calls.append(get_ident()); entered.set()
            if not release.wait(2): raise AssertionError('Test barrier not released')
            return original(path)
        work = self.work('probe', (('play', (self.plan,)),))
        with patch.object(Path, 'is_file', delayed):
            worker = Thread(target=lambda: outcome.append(execute_menu_work(work, Event())))
            worker.start()
            try:
                self.assertTrue(entered.wait(2)); self.assertEqual(outcome, [])
                self.assertNotEqual(calls, [caller])
                # The caller can make progress before the physical check returns.
                heartbeat = list(range(100)); self.assertEqual(len(heartbeat), 100)
            finally: release.set(); worker.join(2)
        self.assertFalse(worker.is_alive()); self.assertEqual(outcome, [(('play', True),)])

    def test_cancel_before_work_performs_no_probe(self):
        cancel = Event(); cancel.set()
        with patch.object(Path, 'is_file', side_effect=AssertionError('Unexpected disk access')):
            with self.assertRaises(InterruptedError): execute_menu_work(self.work('probe'), cancel)

    def test_action_uses_real_material_validation(self):
        before = sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual(execute_menu_work(self.work(), Event()), (self.path,))
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(), before)

    def test_disappearance_after_presence_rejects_action(self):
        self.assertEqual(execute_menu_work(self.work('probe', (('play', (self.plan,)),)), Event()), (('play', True),))
        self.path.unlink()
        with self.assertRaises(ValueError): execute_menu_work(self.work(), Event())

    def test_managed_sha_is_rechecked_not_presence_authorized(self):
        plan = replace(self.plan, kind=MaterialKind.MANAGED, expected_sha256=sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(execute_menu_work(self.work(plans=(plan,)), Event()), (self.path,))
        self.path.write_bytes(b'changed synthetic bytes')
        with self.assertRaises(ValueError): execute_menu_work(self.work(plans=(plan,)), Event())

    def test_snapshot_rejects_library_record_ambiguity_and_evaluation_changes(self):
        self.assertTrue(snapshot_matches(self.token, self.snapshot))
        for snapshot in ((replace(self.context, library_id='other'), (self.track,), {}),
                         (self.context, (), {}), (self.context, (self.track, self.track), {}),
                         (self.context, (replace(self.track, title='changed'),), {}),
                         (self.context, (self.track,), {'new': 'evaluation'})):
            self.assertFalse(snapshot_matches(self.token, snapshot))
            self.snapshot = snapshot
            with self.assertRaises(ValueError): execute_menu_work(self.work(), Event())

    def test_cancel_during_repository_snapshot_stops_before_write(self):
        cancel = Event(); target = self.root / 'explicit-playlist.m3u8'
        def reader(): cancel.set(); return self.snapshot
        work = replace(self.work('playlist', data=(str(target),)), snapshot_reader=reader)
        with self.assertRaises(InterruptedError): execute_menu_work(work, cancel)
        self.assertFalse(target.exists())

    def test_cancel_during_real_playlist_resolve_stops_output_and_mkdir(self):
        cancel = Event(); target = self.root / 'not-created' / 'explicit.m3u8'
        original = Path.resolve
        def cancelled_during_resolve(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == target.parent:
                cancel.set()
            return result
        with patch.object(Path, 'resolve', cancelled_during_resolve):
            with self.assertRaises(InterruptedError):
                execute_menu_work(self.work('playlist', data=(str(target),)), cancel)
        self.assertFalse(target.exists()); self.assertFalse(target.parent.exists())

    def test_disappearance_during_real_playlist_resolve_rejects_output(self):
        target = self.root / 'playlist-dir' / 'explicit.m3u8'; original = Path.resolve
        def disappears(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == target.parent and self.path.exists():
                self.path.unlink()
            return result
        with patch.object(Path, 'resolve', disappears):
            with self.assertRaises(ValueError):
                execute_menu_work(self.work('playlist', data=(str(target),)), Event())
        self.assertFalse(target.exists())

    def test_changed_material_during_real_playlist_resolve_rejects_output(self):
        target = self.root / 'playlist-dir' / 'explicit.m3u8'; original = Path.resolve; changed = []
        def changes(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == target.parent and not changed:
                changed.append(True); self.path.write_bytes(b'replaced synthetic source')
            return result
        with patch.object(Path, 'resolve', changes):
            with self.assertRaises(ValueError):
                execute_menu_work(self.work('playlist', data=(str(target),)), Event())
        self.assertFalse(target.exists())

    def test_explicit_playlist_and_collection_plan_do_not_change_source(self):
        before = self.path.read_bytes(); target = self.root / 'explicit-playlist.m3u8'
        result, count = execute_menu_work(self.work('playlist', data=(str(target),)), Event())
        self.assertEqual((result, count), (target, 1)); self.assertIn('synthetic.mp3', target.read_text(encoding='utf-8-sig'))
        from audio_library_organizer.jobs.playlists import write_m3u8
        legacy_target=self.root/'unguarded-playlist.m3u8'
        write_m3u8(legacy_target,(self.path,),relative=True)
        self.assertEqual(target.read_bytes(),legacy_target.read_bytes())
        plan = execute_menu_work(self.work('collection', data=(LibraryPaths(self.root / 'library'), 'Explicit name')), Event())
        self.assertEqual(len(plan.items), 1); self.assertFalse(plan.items[0].destination_dir.exists())
        self.assertEqual(self.path.read_bytes(), before)

    def test_work_envelope_is_frozen(self):
        with self.assertRaises(FrozenInstanceError): self.work().operation = 'other'

    def test_real_sqlite_snapshot_and_source_are_read_only(self):
        from audio_library_organizer.storage.repository import LibraryRepository
        from audio_library_organizer.jobs.managed_files import resolve_read_path
        repo = LibraryRepository(self.root / 'synthetic.sqlite3'); repo.initialize()
        repo.bootstrap_sources([self.root]); track = TrackRecord(self.path)
        repo.upsert_track(track); track = repo.list_tracks()[0]
        def reader():
            snapshot = repo.file_check_snapshot()
            return snapshot.read_context(self.root), snapshot.tracks, {tid:c.evaluation for tid,c in snapshot.cached}
        snapshot = reader(); context = snapshot[0]
        token = replace(self.token, read_context=context, records=((track.track_id,frozen_value(track)),),target_id=track.track_id)
        plan = resolve_read_path(track,context,ReadPurpose.PLAYBACK,generation=7)
        before_db = repo.database_path.read_bytes(); before_audio = self.path.read_bytes()
        self.assertEqual(execute_menu_work(MenuWork(token,'action',(plan,),reader),Event()),(self.path,))
        self.assertEqual(repo.database_path.read_bytes(),before_db);self.assertEqual(self.path.read_bytes(),before_audio)
        repo.upsert_track(replace(track,title='Controlled concurrent SQLite edit'))
        with self.assertRaises(ValueError):execute_menu_work(MenuWork(token,'action',(plan,),reader),Event())

    def test_fresh_snapshot_is_checked_after_physical_read(self):
        from audio_library_organizer.jobs import context_menu as module
        original = module.read_material
        def changes_after_read(*args,**kwargs):
            value=original(*args,**kwargs)
            self.snapshot=(self.context,(replace(self.track,title='Concurrent change'),),{})
            return value
        with patch.object(module,'read_material',changes_after_read):
            with self.assertRaises(ValueError):execute_menu_work(self.work(),Event())


class AdmissionTests(unittest.TestCase):
    def test_many_submissions_keep_only_one_active_and_latest_pending(self):
        q = LatestMenuWork(); first = q.submit('first', None)
        for i in range(100): self.assertIsNone(q.submit(i, None))
        self.assertIs(q.active, first); self.assertTrue(first[2].is_set()); self.assertEqual(q.pending[1], 99)
        old, following = q.complete(first[0]); self.assertIs(old, first); self.assertEqual(following[1], 99)
        self.assertIsNone(q.pending); self.assertIsNone(q.complete(-1)[0])

    def test_cancelled_terminal_completion_does_not_wedge_following_work(self):
        q = LatestMenuWork(); first = q.submit('first', None); q.cancel(); q.submit('next', None)
        self.assertTrue(first[2].is_set()); self.assertEqual(q.complete(first[0])[1][1], 'next')

    def test_close_cancels_without_wait_and_forbids_new_work(self):
        q = LatestMenuWork(); first = q.submit('blocked', None); q.submit('pending', None); q.cancel(closing=True)
        self.assertTrue(first[2].is_set()); self.assertIsNone(q.pending)
        with self.assertRaises(RuntimeError): q.submit('late', None)
        self.assertIsNone(q.complete(first[0])[1])


if __name__ == '__main__': unittest.main(verbosity=2)
