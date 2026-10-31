"""Observations only. Original case023 is run separately without these hooks."""
from pathlib import Path
from collections import Counter
import ctypes as C
import hashlib,json,os,threading,weakref
import pytest
from test_output_contract_windows_v0427 import pair
from audio_adoption_fixtures import mp3_samples
from audio_library_organizer.safety import windows_file_identity as native
from audio_library_organizer.safety import windows_output_lease as leases

OWNER_TYPE=leases.WindowsOutputLease

class Row(C.Structure):
    _fields_=[('value',C.c_size_t),('flags',C.c_uint32),('object_type',C.c_uint32),
              ('type_name',C.c_wchar*128),('object_name',C.c_wchar*2048)]

class Monitor:
    def __init__(self):
        self.folder=Path(os.environ['ALO_62D_EVIDENCE']);self.events=[]
        path=self.folder.parent.parent/'n1_pss.dll'
        self.dll=C.WinDLL(str(path.resolve()),winmode=0x900)
        self.dll.n1_row_size.argtypes=[];self.dll.n1_row_size.restype=C.c_uint32
        assert self.dll.n1_row_size()==C.sizeof(Row)
        self.dll.n1_count.argtypes=[C.POINTER(C.c_uint32)];self.dll.n1_count.restype=C.c_uint32
        self.dll.n1_snapshot.argtypes=[C.POINTER(Row),C.c_uint32,C.POINTER(C.c_uint32)]
        self.dll.n1_snapshot.restype=C.c_uint32
        self.dll_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    def count(self):
        value=C.c_uint32();status=self.dll.n1_count(C.byref(value))
        if status:raise C.WinError(status)
        return value.value
    def take(self,phase,objects=(),**detail):
        before=self.count();rows=(Row*2048)();used=C.c_uint32()
        status=self.dll.n1_snapshot(rows,len(rows),C.byref(used))
        if status:raise C.WinError(status)
        after=self.count()
        live=[]
        for role,obj in objects:
            d={'role':role,'id':id(obj),'type':type(obj).__module__+'.'+type(obj).__qualname__}
            if isinstance(obj,OWNER_TYPE):
                d.update(owned_count=obj.owned_count,active=obj.active,lock=id(obj._lock),event=id(obj._done),
                    file_handles=list(obj._handles),event_is_set=obj._done.is_set())
            live.append(d)
        event={'phase':phase,'count_before_snapshot':before,'count_after_snapshot':after,
            'collector_delta':after-before,'live':live,'detail':detail,
            'handles':[{'value':x.value,'flags':x.flags,'object_type':x.object_type if x.flags&1 else None,
                        'type_name':x.type_name if x.flags&1 else None,
                        'object_name':x.object_name if x.flags&2 else None} for x in rows[:used.value]]}
        self.events.append(event);return event
    def save(self):
        (self.folder/'n1-observations.json').write_text(json.dumps({'pid':os.getpid(),
            'scope':'PSS GetCurrentProcess only; opaque values are diagnostics, not authority',
            'dll_sha256':self.dll_sha256,'monitor_id':id(self),'dll_object_id':id(self.dll),'events':self.events},indent=2)+'\n')

@pytest.fixture
def monitor():
    m=Monitor()
    m.take('diagnostic-bootstrap')
    try:yield m
    finally:
        try:m.take('after-test-function-scope')
        finally:m.save()
    assert all(x['collector_delta']==0 for x in m.events[1:]),'PSS collector changed the measured resource count'


def test_trace_original_eight_cycles(pair,monkeypatch,monitor):
    actual=native._WinAPI;seen=[];oldrefs=[]
    class ObservedAPI(actual):
        def __init__(self):super().__init__();self.opened=[];self.closed=[];seen.append(self)
        def open(self,*a,**kw):
            h=super().open(*a,**kw);self.opened.append(h);return h
        def close(self,h):super().close(h);self.closed.append(h)
    monkeypatch.setattr(native,'_WinAPI',ObservedAPI)
    monitor.take('before-warm',api_count=len(seen))
    warm=leases.acquire_output_lease(*map(str,pair))
    monitor.take('warm-acquired',[('warm',warm)],api_count=len(seen))
    warm.close()
    monitor.take('after-warm',[('warm',warm)],api_count=len(seen))
    for i in range(8):
        if i==0:monitor.take('before-acquire',[('warm',warm)],cycle=i,api_count=len(seen))
        else:monitor.take('before-acquire',[('warm',warm),('previous-owner',owner)],cycle=i,api_count=len(seen))
        owner=leases.acquire_output_lease(*map(str,pair));oldrefs.append(weakref.ref(owner))
        monitor.take('after-acquire',[('warm',warm),('owner',owner)],cycle=i,api_count=len(seen))
        owner.close();assert owner.owned_count==0
        monitor.take('after-close',[('warm',warm),('owner',owner)],cycle=i,api_count=len(seen),
            previous_owners_alive=sum(r() is not None for r in oldrefs),
            opened=sum(len(a.opened) for a in seen),closed=sum(len(a.closed) for a in seen))
    assert len(seen)==9 and all(a.opened and Counter(a.opened)==Counter(a.closed) for a in seen)
    monitor.take('legacy-end',[('warm',warm),('owner',owner)],api_count=len(seen))


def test_attribute_lock_event_and_owner(pair,monkeypatch,monitor):
    paths=tuple(map(str,pair));api=native._WinAPI()
    def construct():
        actual_lock=leases.Lock;actual_event=leases.Event
        def lock():
            monitor.take('before-Lock-constructor')
            obj=actual_lock();monitor.take('after-Lock-constructor',[('new-lock',obj)])
            return obj
        def event():
            monitor.take('before-Event-constructor')
            obj=actual_event();monitor.take('after-Event-constructor',[('new-event',obj)])
            return obj
        with monkeypatch.context() as context:
            context.setattr(leases,'Lock',lock);context.setattr(leases,'Event',event)
            owner=leases.WindowsOutputLease(paths,api)
        monitor.take('owner-constructed-no-files',[('owner',owner)])
        owner.close();assert owner.owned_count==0
        monitor.take('owner-closed-still-alive',[('owner',owner)])
        return weakref.ref(owner)
    monitor.take('before-owner-function-scope')
    reference=construct()
    monitor.take('after-normal-owner-function-return',owner_alive=reference() is not None)
    assert reference() is None,'Normal scope exit retained the owner'
    # Standalone Lock and Event distinguish actual runtime effects, no ABI guesses.
    def helper_scope(factory,role):
        monitor.take('before-standalone-'+role)
        obj=factory();monitor.take('standalone-'+role+'-alive',[(role,obj)])
    for factory,role in [(threading.Lock,'Lock'),(threading.Event,'Event')]:
        helper_scope(factory,role)
        monitor.take('after-normal-'+role+'-scope')


def strict_equal(before,after):
    assert before==after,'STRICT_HANDLE_COUNT_MISMATCH'


def test_deliberate_owned_event_is_detected(pair,monitor):
    k=C.WinDLL('kernel32',use_last_error=True)
    create=k.CreateEventW;create.argtypes=[C.c_void_p,C.c_int32,C.c_int32,C.c_wchar_p];create.restype=C.c_void_p
    close=k.CloseHandle;close.argtypes=[C.c_void_p];close.restype=C.c_int32
    before=monitor.take('before-deliberate-owned-event')['count_after_snapshot']
    handle=create(None,False,False,None)
    if not handle:raise C.WinError(C.get_last_error())
    try:
        observed=monitor.take('deliberate-owned-event-alive',owned_event=handle)
        assert observed['count_after_snapshot']==before+1
        found=[x for x in observed['handles'] if x['value']==handle]
        assert len(found)==1 and found[0]['type_name']=='Event'
        with pytest.raises(AssertionError,match='STRICT_HANDLE_COUNT_MISMATCH'):
            strict_equal(before,observed['count_after_snapshot'])
    finally:
        if not close(handle):raise C.WinError(C.get_last_error())
    after=monitor.take('deliberate-owned-event-closed')['count_after_snapshot']
    strict_equal(before,after)
