"""Portable contract models; NOT evidence of native Windows API behavior."""
from dataclasses import replace
from pathlib import PureWindowsPath
import importlib
import importlib.util
import pytest
from audio_adoption_fixtures import mp3_samples
from test_legacy_adoption_v0427 import library


def api():
    name='audio_library_organizer.safety.windows_file_identity'
    assert importlib.util.find_spec(name), 'Missing native Windows metadata contract'
    return importlib.import_module(name)


class ModelAPI:
    def __init__(self,m):
        self.m=m;self.opened=[];self.closed=[];self.nodes={};self.fail=None
    def open(self,path,*,mutable):
        if self.fail=='open':raise PermissionError('model denied')
        self.opened.append((path,mutable));return path
    def query(self,h):
        if self.fail=='query':raise OSError('model query failed')
        return self.nodes.get(h,self.m.NativeNode('NTFS',3,'volume-guid',17,
            (str(h).encode()+b'\0'*16)[:16],10,100,200,50,1,
            0x10 if str(h).lower() != 'c:\\safe\\song.mp3' else 0,
            0,False,str(h),str(h).lower() != 'c:\\safe\\song.mp3'))
    def close(self,h):self.closed.append(h)


def proof(m,a=None,**kwargs):
    a=a or ModelAPI(m)
    return m._capture('C:\\safe\\song.mp3',a,**kwargs)


def test_same_unchanged_object_has_same_proof_and_closes_every_handle():
    m=api();a=ModelAPI(m);p=proof(m,a)
    assert p==proof(m,a) and len(p.ancestors)==2
    assert sorted(a.closed)==sorted(h for h,_ in a.opened)
    assert [mutable for _,mutable in a.opened]==[True,True,False]*2
    assert m.same_material(p,p) and m.same_database(p,p)


def test_change_time_detects_same_size_restored_mtime_while_creation_is_unchanged():
    m=api();a=ModelAPI(m);p=proof(m,a)
    node=a.query('C:\\safe\\song.mp3')
    a.nodes['C:\\safe\\song.mp3']=replace(node,change_time=node.change_time+1)
    q=proof(m,a)
    assert (p.leaf.size,p.leaf.last_write,p.leaf.creation_time)==(q.leaf.size,q.leaf.last_write,q.leaf.creation_time)
    assert not m.same_material(p,q) and m.same_database(p,q)


@pytest.mark.parametrize('field,value',[('file_id',b'other-object-id!!'),('volume_serial',18),('volume_guid','other-volume'),('size',11),('last_write',101),('change_time',201)])
def test_changed_material_is_rejected(field,value):
    m=api();p=proof(m);q=replace(p,leaf=replace(p.leaf,**{field:value}))
    assert not m.same_material(p,q)


@pytest.mark.parametrize('field,value',[('filesystem','ReFS'),('filesystem','exFAT'),('drive_type',4),('links',2),('reparse_tag',0xA0000003),('attributes',0x400),('attributes',0x1000),('attributes',0x40000),('attributes',0x400000),('attributes',0x40),('delete_pending',True),('directory',True),('final_path','C:\\elsewhere\\song.mp3')])
def test_untrusted_leaf_never_produces_a_proof(field,value):
    m=api();a=ModelAPI(m);h='C:\\safe\\song.mp3';a.nodes[h]=replace(a.query(h),**{field:value})
    with pytest.raises((OSError,ValueError)):proof(m,a)
    assert len(a.closed)==len(a.opened)


@pytest.mark.parametrize('path',['\\\\server\\share\\song.mp3','\\\\?\\C:\\safe\\song.mp3','C:song.mp3','song.mp3','C:\\safe\\..\\song.mp3','C:\\safe\\song.mp3:stream','C:\\safe.\\song.mp3','C:\\safe\\NUL.mp3'])
def test_ambiguous_namespace_is_rejected_before_any_native_open(path):
    m=api();a=ModelAPI(m)
    with pytest.raises(ValueError):m._capture(path,a)
    assert a.opened==[]


@pytest.mark.parametrize('kind',['reparse','final-alias','other-volume','not-directory'])
def test_each_ancestor_is_checked(kind):
    m=api();a=ModelAPI(m);h='C:\\safe';node=a.query(h)
    changes={'reparse':{'attributes':0x410},'final-alias':{'final_path':'C:\\foreign'},'other-volume':{'volume_guid':'another-volume'},'not-directory':{'directory':False}}
    a.nodes[h]=replace(node,**changes[kind])
    with pytest.raises((OSError,ValueError)):proof(m,a)
    assert len(a.closed)==len(a.opened)


@pytest.mark.parametrize('kind',['open','query'])
def test_native_errors_are_not_downgraded(kind):
    m=api();a=ModelAPI(m);a.fail=kind
    with pytest.raises(OSError):proof(m,a)
    assert len(a.closed)==len(a.opened)


def test_changed_parent_identity_rejects_material_and_database_but_parent_times_do_not():
    m=api();p=proof(m);a=p.ancestors[0]
    q=replace(p,ancestors=(replace(a,file_id=b'new-parent-id!!!'),*p.ancestors[1:]))
    assert not m.same_material(p,q) and not m.same_database(p,q)


def test_database_mutable_fields_do_not_replace_its_object_identity():
    m=api();p=proof(m);q=replace(p,leaf=replace(p.leaf,size=999,last_write=300,change_time=400))
    assert m.same_database(p,q) and not m.same_material(p,q)
    assert not m.same_database(p,replace(q,leaf=replace(q.leaf,file_id=b'new-db-object!!!')))


def test_windows_positive_gate_is_closed_and_not_an_environment_switch(monkeypatch):
    m=api();monkeypatch.setenv('ALO_WINDOWS_OUTPUT_ACCEPTANCE','1')
    assert m.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    assert not m.positive_acceptance_enabled()


def test_ctypes_structures_use_windows_abi_on_every_contract_host():
    m=api();import ctypes
    assert [ctypes.sizeof(t) for t in (m.FILE_BASIC_INFO,m.FILE_STANDARD_INFO,m.FILE_ID_INFO,m.FILE_ATTRIBUTE_TAG_INFO)]==[40,24,24,8]


def test_native_open_requests_share_accounted_read_access_not_attributes_only():
    m=api();a=m._WinAPI.__new__(m._WinAPI);calls=[]
    a.create=lambda *args:calls.append(args) or 17
    assert a.open('C:\\safe\\song.mp3',mutable=False)==17
    assert a.open('C:\\safe',mutable=True)==17
    assert calls[0][1]==calls[1][1]==0x81  # READ_DATA/LIST_DIRECTORY + READ_ATTRIBUTES
    assert calls[0][2]==1 and calls[1][2]==3  # no share-delete; no music share-write
    assert calls[0][3] is None and calls[0][4]==3


def test_missing_native_api_is_a_controlled_refusal(monkeypatch):
    m=api()
    def missing():raise AttributeError('Missing GetFileInformationByHandleEx')
    monkeypatch.setattr(m,'_WinAPI',missing)
    with pytest.raises(OSError,match='WINDOWS_NATIVE_API_UNAVAILABLE'):m.capture('C:\\safe\\song.mp3')


@pytest.mark.parametrize('kind',['material','database'])
def test_delivery_revalidates_native_proof_and_never_falls_back_to_stat(library,monkeypatch,kind):
    from uuid import uuid4
    from test_adopted_output_spec_v0427 import approve
    from audio_library_organizer.jobs import output_session as session
    from audio_library_organizer.jobs.file_reconciliation import check_library
    m=api();repo,root,track,output=library;approve(library)
    native=proof(m);captures=[];current=[native]
    def capture(path,**kwargs):captures.append((str(path),kwargs));return current[0]
    monkeypatch.setattr(m,'on_windows',lambda:True);monkeypatch.setattr(m,'capture',capture)
    monkeypatch.setattr(m,'WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED',True)  # MODEL ONLY
    op=session.OutputCheckOperation(repo.library_id,str(uuid4()),1,'policy-v1',track.track_id)
    r=op.choose(repo.list_managed_bindings())
    result=check_library(repo,library_root=root,operation_id=r.operation_id,output_request=r,current_output_request=op.current_request)
    d=session.prepare_delivery(repo,root,result.pending_output_assessment,r)
    assert d is not None and d.windows_material==(native,native) and d.windows_database==native
    assert session.material_matches(d) and session.database_safe(d)
    field='change_time' if kind=='material' else 'file_id'
    value=999 if kind=='material' else b'other-db-id-1234'
    current[0]=replace(native,leaf=replace(native.leaf,**{field:value}))
    assert not (session.material_matches(d) if kind=='material' else session.database_safe(d))
    monkeypatch.setattr(m,'WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED',False)
    current[0]=native
    assert not session.material_matches(d) and not session.database_safe(d)


def test_adapter_retains_native_material_observed_before_the_content_read(library,monkeypatch):
    from test_adopted_output_spec_v0427 import approve,request
    from audio_library_organizer.jobs import adopted_output as adapter
    m=api();repo,root,track,output=library;b=approve(library);r=request(adapter,repo,track,b)
    observed=[];original=adapter.inspect_audio;native=proof(m)
    monkeypatch.setattr(m,'on_windows',lambda:True)
    monkeypatch.setattr(m,'capture',lambda p,**kw: observed.append(('native_db' if kw.get('mutable') else 'native',str(p))) or native)
    def content(*a,**kw):
        observed.append(('content',str(a[0])));return original(*a,**kw)
    monkeypatch.setattr(adapter,'inspect_audio',content)
    result=adapter.assess_adopted_mp3(repo,root,r,current_request=lambda:r)
    assert result.evaluation.is_confirmed
    assert result.guard.windows_material==(native,native)
    assert [k for k,_ in observed]==['native_db','native','native','content','native','native','native_db']


def test_adapter_refuses_native_change_across_the_content_read(library,monkeypatch):
    from test_adopted_output_spec_v0427 import approve,request
    from audio_library_organizer.jobs import adopted_output as adapter
    m=api();repo,root,track,output=library;b=approve(library);r=request(adapter,repo,track,b)
    native=proof(m);changed=replace(native,leaf=replace(native.leaf,change_time=999))
    calls=[]
    def capture(*a,**kw):
        if kw.get('mutable'):return native
        calls.append(a);return native if len(calls)<=2 else changed
    monkeypatch.setattr(m,'on_windows',lambda:True);monkeypatch.setattr(m,'capture',capture)
    result=adapter.assess_adopted_mp3(repo,root,r,current_request=lambda:r)
    assert not result.evaluation.is_confirmed
    assert result.reason=='WINDOWS_MATERIAL_CHANGED_DURING_ASSESSMENT'


@pytest.mark.parametrize('swap',[False,True])
def test_database_native_identity_covers_the_assessment_not_only_late_delivery(library,monkeypatch,swap):
    from test_adopted_output_spec_v0427 import approve,request
    from audio_library_organizer.jobs import adopted_output as adapter
    m=api();repo,root,track,output=library;b=approve(library);r=request(adapter,repo,track,b)
    native=proof(m);changed=replace(native,leaf=replace(native.leaf,file_id=b'replaced-db-1234'))
    events=[];original=repo.adopted_assessment_snapshot
    def snapshot(*a,**kw):events.append('snapshot');return original(*a,**kw)
    def capture(p,**kw):
        if kw.get('mutable'):
            old='database' in events;events.append('database');return changed if swap and old else native
        return native
    monkeypatch.setattr(repo,'adopted_assessment_snapshot',snapshot)
    monkeypatch.setattr(m,'on_windows',lambda:True);monkeypatch.setattr(m,'capture',capture)
    result=adapter.assess_adopted_mp3(repo,root,r,current_request=lambda:r)
    assert events[0]=='database'
    if swap:
        assert not result.evaluation.is_confirmed and result.reason=='WINDOWS_DATABASE_CHANGED_DURING_ASSESSMENT'
    else:assert result.guard.windows_database==native


def test_preparation_cannot_enable_windows_from_a_valid_linux_packet(library,monkeypatch):
    from uuid import uuid4
    from test_adopted_output_spec_v0427 import approve
    from audio_library_organizer.jobs import output_session as session
    from audio_library_organizer.jobs.file_reconciliation import check_library
    m=api();repo,root,track,output=library;b=approve(library)
    op=session.OutputCheckOperation(repo.library_id,str(uuid4()),1,'policy-v1',track.track_id)
    r=op.choose(repo.list_managed_bindings())
    result=check_library(repo,library_root=root,operation_id=r.operation_id,output_request=r,current_output_request=op.current_request)
    assert result.pending_output_assessment is not None
    monkeypatch.setattr(m,'on_windows',lambda:True)
    assert session.prepare_delivery(repo,root,result.pending_output_assessment,r) is None
