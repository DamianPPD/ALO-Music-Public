"""Pure owner protocol tests. Fake handles are NOT native Windows evidence."""
import importlib
import importlib.util
from dataclasses import replace
from pathlib import PureWindowsPath
from threading import Thread
import unittest
from unittest.mock import patch

from audio_library_organizer.safety import windows_file_identity as native


class ModelAPI:
    def __init__(self,fail_open=None,fail_query=None,bad=None,fail_close=None):
        self.opened=[];self.closed=[];self.fail_open=fail_open;self.fail_query=fail_query
        self.bad=bad;self.fail_close=fail_close
    def open(self,path,*,mutable):
        if self.fail_open and str(path).endswith(self.fail_open):raise OSError('model sharing refusal')
        h=len(self.opened)+1;self.opened.append((h,str(path),mutable));return h
    def query(self,h):
        if h==self.fail_query:raise OSError('model Win32 query error')
        _,path,mutable=self.opened[h-1]
        p=PureWindowsPath(path);directory=p.suffix.lower()!='.mp3'
        n=native.NativeNode('NTFS',3,'model-volume',4,bytes([h])*16,0 if directory else 16,
            5,6,7,1,0x10 if directory else 0,0,False,path,directory)
        if self.bad and not directory:n=replace(n,**self.bad)
        return n
    def close(self,h):
        if h==self.fail_close:raise OSError('model CloseHandle error')
        if h in self.closed:raise AssertionError('double close')
        self.closed.append(h)


class LeaseProtocolTests(unittest.TestCase):
    paths=(r'C:\synthetic-source\source.mp3',r'C:\synthetic-library\GOTOWE\managed.mp3')

    def module(self):
        name='audio_library_organizer.safety.windows_output_lease'
        self.assertIsNotNone(importlib.util.find_spec(name),'WINDOWS_OUTPUT_LEASE_OWNER_MISSING')
        return importlib.import_module(name)

    def acquire(self,api=None):
        return self.module()._acquire_pair(self.paths,api or ModelAPI())

    def tearDown(self):
        # These deliberately failed closes own model integers, not OS handles.
        # Isolate their simulated process-fatal latch from other model tests;
        # never clear a quarantine belonging to the real native API.
        m=self.module()
        if hasattr(m,'_QUARANTINE_LOCK'):
            with m._QUARANTINE_LOCK:
                m._UNCERTAIN_OWNERS[:]=[o for o in m._UNCERTAIN_OWNERS if not isinstance(o._api,ModelAPI)]

    def test_pair_retains_every_handle_until_owner_finishes(self):
        api=ModelAPI();lease=self.acquire(api)
        self.assertTrue(lease.active);self.assertEqual(api.closed,[])
        self.assertEqual(len(lease.material),2);self.assertTrue(lease.active_for(self.paths,lease.material))
        lease.close();self.assertFalse(lease.active)
        self.assertEqual(api.closed,[h for h,_,_ in reversed(api.opened)])
        self.assertEqual(lease.owned_count,0)

    def test_partial_acquire_closes_first_object_and_all_ancestors(self):
        api=ModelAPI(fail_open='managed.mp3')
        with self.assertRaises(OSError):self.acquire(api)
        self.assertEqual(sorted(api.closed),sorted(h for h,_,_ in api.opened))

    def test_query_failure_closes_even_the_failing_handle(self):
        api=ModelAPI(fail_query=2)
        with self.assertRaises(OSError):self.acquire(api)
        self.assertEqual(sorted(api.closed),sorted(h for h,_,_ in api.opened))

    def test_unsupported_objects_are_not_partial_positive_proofs(self):
        for bad in ({'links':2},{'reparse_tag':1},{'delete_pending':True},{'filesystem':'FAT32'},
                    {'drive_type':4},{'attributes':0x400},{'final_path':r'C:\foreign.mp3'}):
            with self.subTest(bad=bad):
                api=ModelAPI(bad=bad)
                with self.assertRaises(ValueError):self.acquire(api)
                self.assertEqual(sorted(api.closed),sorted(h for h,_,_ in api.opened))

    def test_ack_revokes_before_owner_close_and_preserves_accepted_history(self):
        api=ModelAPI();lease=self.acquire(api)
        self.assertTrue(lease.claim(lease.material));self.assertTrue(lease.accepted)
        lease.acknowledge();self.assertFalse(lease.active);self.assertEqual(api.closed,[])
        self.assertTrue(lease.wait_for_delivery(timeout=0))
        self.assertEqual(lease.owned_count,0);self.assertTrue(lease.accepted)

    def test_ack_does_not_make_a_closed_lease_current_again(self):
        lease=self.acquire();material=lease.material
        lease.acknowledge();lease.wait_for_delivery(timeout=0);lease.acknowledge()
        self.assertFalse(lease.active_for(self.paths,material));self.assertFalse(lease.claim(material))

    def test_timeout_revokes_and_closes_without_any_receiver(self):
        lease=self.acquire()
        self.assertFalse(lease.wait_for_delivery(timeout=0))
        self.assertFalse(lease.active);self.assertEqual(lease.owned_count,0)
        self.assertFalse(lease.claim(lease.material));self.assertEqual(lease.reason,'DELIVERY_TIMEOUT')

    def test_delivery_deadline_cannot_be_missing_infinite_or_extended(self):
        for timeout in (None,float('inf'),float('nan'),-1,True,6.0):
            with self.subTest(timeout=timeout):
                lease=self.acquire();lease.acknowledge()  # Never block even on the old API.
                with self.assertRaises(ValueError):lease.wait_for_delivery(timeout)
                self.assertEqual(lease.owned_count,0)

    def test_entire_selected_operation_has_a_cooperative_budget(self):
        m=self.module()
        self.assertTrue(hasattr(m,'monotonic'),'SELECTED_PROTECTION_BUDGET_MISSING')
        with patch.object(m,'monotonic',return_value=10.) as clock:
            lease=self.acquire()
            try:
                clock.return_value=10.+m.PROTECTION_TIMEOUT_SECONDS+1
                self.assertFalse(lease.active)
                self.assertTrue(lease.cancelled())
                self.assertFalse(lease.claim(lease.material))
                self.assertEqual(lease.reason,'PROTECTION_TIMEOUT')
                self.assertFalse(lease.wait_for_delivery(timeout=0))
                self.assertEqual(lease.owned_count,0)
            finally:lease.close()

    def test_late_ack_cannot_turn_an_expired_budget_into_delivery(self):
        m=self.module()
        with patch.object(m,'monotonic',return_value=10.) as clock:
            lease=self.acquire()
            try:
                self.assertTrue(lease.claim(lease.material))
                clock.return_value=10.+m.PROTECTION_TIMEOUT_SECONDS+1
                lease.acknowledge()
                self.assertEqual(lease.reason,'PROTECTION_TIMEOUT')
                self.assertFalse(lease.wait_for_delivery(timeout=0))
            finally:lease.close()

    def test_cancel_revokes_and_wakes_without_closing_in_a_foreign_thread(self):
        api=ModelAPI();lease=self.acquire(api)
        t=Thread(target=lambda:lease.revoke('CANCELLED'));t.start();t.join()
        self.assertFalse(lease.active);self.assertEqual(api.closed,[])
        self.assertFalse(lease.wait_for_delivery(timeout=0));self.assertEqual(lease.owned_count,0)

    def test_only_acquiring_thread_may_close_native_handles(self):
        lease=self.acquire();errors=[]
        def other():
            try:lease.close()
            except RuntimeError as exc:errors.append(str(exc))
        t=Thread(target=other);t.start();t.join()
        self.assertEqual(errors,['LEASE_OWNER_THREAD_REQUIRED'])
        self.assertTrue(lease.active);lease.close()

    def test_material_or_path_mismatch_never_claims(self):
        lease=self.acquire()
        try:
            self.assertFalse(lease.active_for(self.paths[::-1],lease.material))
            self.assertFalse(lease.claim(lease.material[::-1]))
            self.assertFalse(lease.accepted)
        finally:lease.close()

    def test_duplicate_delivery_cannot_claim_twice(self):
        lease=self.acquire()
        try:
            self.assertTrue(lease.claim(lease.material));self.assertFalse(lease.claim(lease.material))
        finally:lease.close()

    def test_close_is_idempotent_and_never_retries_a_failed_close_blindly(self):
        api=ModelAPI();lease=self.acquire(api);api.fail_close=2
        with self.assertRaises(OSError):lease.close()
        self.assertFalse(lease.active);self.assertEqual(lease.owned_count,1)
        self.assertEqual(lease.failed_handles,(2,));closed=list(api.closed)
        lease.close();self.assertEqual(api.closed,closed)

    def test_partial_query_failure_keeps_failed_close_under_explicit_ownership(self):
        api=ModelAPI(fail_query=2,fail_close=1);m=self.module()
        with self.assertRaises(OSError) as raised:self.acquire(api)
        owner=getattr(raised.exception,'owner',None)
        self.assertIsNotNone(owner,'PARTIAL_CLOSE_FAILURE_LOST_ITS_OWNER')
        self.assertFalse(owner.active);self.assertEqual(owner.failed_handles,(1,))
        self.assertEqual(owner.owned_count,1);self.assertEqual(api.closed,[2])
        owner.close();self.assertEqual(api.closed,[2])

    def test_uncertain_cleanup_quarantines_future_public_acquisition(self):
        api=ModelAPI(fail_query=2,fail_close=1);m=self.module()
        with self.assertRaises(OSError):self.acquire(api)
        with self.assertRaisesRegex(OSError,'WINDOWS_LEASE_CLEANUP_UNCERTAIN_RESTART_REQUIRED'):
            m.acquire_output_lease(*self.paths)


if __name__=='__main__':unittest.main()
