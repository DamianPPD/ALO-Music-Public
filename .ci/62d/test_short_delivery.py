"""Native contract RED gate. Product and old UI assertions stay unchanged.

The test-owned guard is diagnostic instrumentation, not WindowsOutputLease.
It retains actual native handles before the real worker reads, through the
real MainWindow receiver, then closes them after the receiver acknowledges.
"""
from dataclasses import asdict
from pathlib import Path
from threading import Event, Lock, get_ident
import ctypes as C
import hashlib
import json
import os
import sqlite3
import sys
import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from audio_adoption_fixtures import mp3_samples
from test_legacy_adoption_v0427 import library
from test_output_session_ui_v0427 import adopted_window, run_check, presentation
from test_windows_output_native_v0427 import diagnostic_window
from audio_library_organizer.safety import windows_file_identity as native
from audio_library_organizer.domain.file_state import FileState

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Real Windows API required')


def output(data):
    Path(os.environ['ALO_62D_EVIDENCE'],'short-delivery.json').write_text(json.dumps(data,indent=2,
        default=lambda v:v.hex() if isinstance(v,bytes) else str(v))+'\n')


class HeldPair:
    """Only test-created paths; close all explicit handles on every test exit."""
    def __init__(self,paths,root):
        self.paths=tuple(map(Path,paths));self.root=Path(root).resolve();self.api=native._WinAPI()
        self.handles=[];self.events=[];self.active=False;self.lock=Lock();self.proofs=();self.close_attempted=False

    def note(self,event,**kw):self.events.append({'event':event,'qpc_ns':time.perf_counter_ns(),'thread':get_ident(),**kw})

    def count(self):
        k=self.api.k
        k.GetCurrentProcess.argtypes=[];k.GetCurrentProcess.restype=C.c_void_p
        k.GetProcessHandleCount.argtypes=[C.c_void_p,C.POINTER(C.c_uint32)];k.GetProcessHandleCount.restype=C.c_int32
        count=C.c_uint32()
        if not k.GetProcessHandleCount(k.GetCurrentProcess(),C.byref(count)):raise C.WinError(C.get_last_error())
        return count.value

    def acquire(self):
        self.note('acquire-start',process_handles=self.count())
        opened=set()
        try:
            for p in sorted(self.paths,key=lambda p:str(p).casefold()):
                if p.suffix.lower()!='.mp3' or self.root not in p.resolve().parents:
                    raise ValueError('Outside synthetic fixture')
                leaf=native._lexical(str(p))
                for node in (*reversed(leaf.parents),leaf):
                    name=str(node)
                    if name.casefold() in opened:continue
                    is_leaf=node==leaf
                    h=self.api.open(name,mutable=not is_leaf);self.handles.append(h);opened.add(name.casefold())
                    n=self.api.query(h)
                    if (n.filesystem!='NTFS' or n.drive_type!=3 or n.reparse_tag or n.delete_pending
                        or str(n.final_path).casefold()!=name.casefold() or n.directory==is_leaf
                        or (is_leaf and n.links!=1)):
                        raise ValueError('Unsupported diagnostic object')
                    self.note('opened',handle=h,path=name,node=asdict(n))
            # Original full namespace/capability validation while all retained
            # ancestors and leaves are held. No token or predicate is replaced.
            self.proofs=tuple(native.capture(p) for p in self.paths)
            self.active=True;self.note('acquired',owned=len(self.handles),process_handles=self.count())
            return self
        except BaseException:
            self.close();raise

    def close(self):
        with self.lock:
            if self.close_attempted:return
            if not self.handles:self.active=False;return
            self.close_attempted=True
            self.active=False;self.note('revoked',owned=len(self.handles))
            errors=[];remaining=[]
            for h in reversed(self.handles):
                try:self.api.close(h);self.note('closed',handle=h)
                except OSError as exc:errors.append(repr(exc));remaining.append(h)
            self.handles=list(reversed(remaining))
            self.note('released',owned=len(self.handles),process_handles=self.count(),errors=errors)
            if errors:raise RuntimeError('Diagnostic handle cleanup: '+repr(errors))


@pytest.mark.parametrize('language',['pl','en'])
def test_closed_receipt_refresh(diagnostic_window,tmp_path,monkeypatch,language):
    scenario(diagnostic_window,tmp_path,monkeypatch,language,None)


@pytest.mark.parametrize('changed',['source','managed'])
def test_closed_receipt_after_mutation(diagnostic_window,tmp_path,monkeypatch,changed):
    scenario(diagnostic_window,tmp_path,monkeypatch,'pl',changed)


def scenario(fixture,tmp_path,monkeypatch,language,changed):
    from dataclasses import replace
    from audio_library_organizer.ui import workers
    from audio_library_organizer.ui.i18n import apply_static_language
    window,lib,binding=fixture;repo,root,track,managed=lib
    window.preferences=replace(window.preferences,language=language);apply_static_language(window.library,language)
    window.library.select_track(repo.get_track(track.track_id))
    guard=HeldPair((track.path,managed),tmp_path);ack=Event()
    state={'scope':'test-owned native guard, unchanged product','language':language,'changed':changed,
        'actor_errors':[],'complete':False,'trace':guard.events,'gui_thread':get_ident()}
    actual_check=workers.check_library;actual_accept=window._accept_output_delivery
    actual_init=workers.FileReconciliationWorker.__init__;worker=[]

    def init(instance,*args,**kwargs):
        actual_init(instance,*args,**kwargs);worker.append(instance)

    def finished(result):
        try:
            state['worker_thread']=get_ident()
            state['delivery_present']=result.output_delivery is not None
            state['same_guard_material']=(result.output_delivery is not None and result.output_delivery.windows_material==guard.proofs)
            state['ack_received']=ack.wait(5)  # observed GUI ack, bounded diagnostic wait
            if not state['ack_received']:state['actor_errors'].append('GUI ack deadline exceeded')
        except BaseException as exc:state['actor_errors'].append(repr(exc))
        finally:
            try:guard.close()
            except BaseException as exc:state['actor_errors'].append(repr(exc))

    def failed(*args):
        state['actor_errors'].append('Worker failed: '+repr(args))
        try:guard.close()
        except BaseException as exc:state['actor_errors'].append(repr(exc))

    def check(*args,**kwargs):
        guard.acquire()
        # MainWindow's queued receiver is already registered. This direct
        # callback is last, so delivery can reach GUI before its bounded wait.
        worker[-1].finished.connect(finished,Qt.ConnectionType.DirectConnection)
        worker[-1].failed.connect(failed,Qt.ConnectionType.DirectConnection)
        try:return actual_check(*args,**kwargs)
        except BaseException:guard.close();raise

    def accept(result):
        try:
            state['guard_at_gui_entry']=guard.active;guard.note('gui-accept-entry')
            actual_accept(result)
            state['accepted_confirmed']=presentation(window,track).confirmed
            state['accepted_needs_update']=presentation(window,track).state==FileState.NEEDS_UPDATE
            state['accepted_delivery_is_actual']=window._output_session.get(track.track_id) is result.output_delivery
            delivery=result.output_delivery
            request=window._output_operation.current_request() if window._output_operation is not None else None
            state['accepted_request_is_actual']=delivery is not None and delivery.pending.request is request
            state['accepted_request']=asdict(request) if request is not None else None
            state['accepted_operation_id']=result.operation_id
            state['guard_at_gui_exit']=guard.active;guard.note('gui-accept-exit')
        except BaseException as exc:
            state['actor_errors'].append('Receiver: '+repr(exc));raise
        finally:
            guard.note('gui-ack');ack.set()

    monkeypatch.setattr(workers.FileReconciliationWorker,'__init__',init)
    monkeypatch.setattr(workers,'check_library',check)
    monkeypatch.setattr(window,'_accept_output_delivery',accept)
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in guard.paths}
    try:
        run_check(window)
        state['closed_before_refresh']=not guard.active and not guard.handles
        state['thread_finished']=window._thread is None
        state['generation']=window._file_check_generation
        state['protected_native_material']=[asdict(p) for p in guard.proofs]
        if changed:
            p=track.path if changed=='source' else managed
            stamp=p.stat();data=bytearray(p.read_bytes());data[-16]^=0x5a
            with p.open('r+b',buffering=0) as f:
                assert f.write(data)==len(data),'Synthetic mutation short write'
            os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            state['mutated_path']=str(p);state['mutated_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
            state['actual_bytes_changed']=state['mutated_sha256']!=before[str(p)]
            state['size_unchanged']=p.stat().st_size==stamp.st_size
            state['mtime_restored']=p.stat().st_mtime_ns==stamp.st_mtime_ns
            fresh=tuple(native.capture(p) for p in guard.paths)
            state['post_mutation_native_material']=[asdict(p) for p in fresh]
            state['native_material_equal_after_mutation']=fresh==guard.proofs
        else:
            state['actual_bytes_unchanged']=before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in guard.paths}
        window.refresh_data()  # Exact synchronous refresh; no pump, no wait, no new hash in GUI product.
        state['refresh_returned_qpc_ns']=time.perf_counter_ns()
        state['confirmed_after_refresh']=presentation(window,track).confirmed
        state['state_after_refresh']=presentation(window,track).state
        state['session_entries_after_refresh']=len(window._output_session)
        retained=window._output_session.get(track.track_id)
        state['retained_actual_delivery']=retained is window.last_reconciliation_result.output_delivery
        state['retained_operation_id']=retained.pending.request.operation_id if retained is not None else None
        request=window._output_operation.current_request() if window._output_operation is not None else None
        state['retained_actual_request']=retained is not None and retained.pending.request is request
        state['owned_handles_end']=len(guard.handles)
        state['binding_unchanged']=repo.list_managed_bindings()==(binding,)
        connection=sqlite3.connect(Path(repo.database_path).resolve().as_uri()+'?mode=ro',uri=True)
        try:state['sqlite_integrity']=connection.execute('PRAGMA integrity_check').fetchone()[0]
        finally:connection.close()
        state['complete']=True;output(state)
        assert not state['actor_errors'],'Actor error: '+repr(state['actor_errors'])
        assert state['delivery_present'] and state['same_guard_material'],'Missing actual protected delivery'
        assert state['guard_at_gui_entry'] and state['guard_at_gui_exit'] and state['accepted_confirmed'],'No actual acceptance under protection'
        assert state['accepted_needs_update'] and state['accepted_delivery_is_actual'] and state['accepted_request_is_actual'],'Actual packet/request was not accepted as NEEDS_UPDATE'
        assert state['closed_before_refresh'] and state['thread_finished'] and state['owned_handles_end']==0,'Guard not fully released'
        assert state['worker_thread']!=state['gui_thread'] and state['ack_received'],'Wrong thread/ack'
        assert state['binding_unchanged'],'Binding changed'
        assert state['sqlite_integrity']=='ok','SQLite integrity failure'
        if changed:assert state['actual_bytes_changed'] and state['size_unchanged'] and state['mtime_restored'],'Missing actual same-size/restored-mtime mutation'
        else:assert state['actual_bytes_unchanged'],'Unexpected mutation'
        if state['confirmed_after_refresh']:
            assert state['state_after_refresh']==FileState.NEEDS_UPDATE and state['retained_actual_delivery'] and state['retained_actual_request'] and state['retained_operation_id']==state['accepted_operation_id'],'Confirmation not tied to the accepted packet/request'
        assert not state['confirmed_after_refresh'],'CLOSED_RECEIPT_REUSED_AS_CURRENT'
    finally:
        ack.set();guard.close();output(state)
