"""Native Windows-only validation. All data is generated under pytest tmp_path.

Positive Qt probes temporarily override ONLY the release gate in their test
fixture. The real native API, QThread, adapter, SQLite and GUI guards run as-is.
Such diagnostic PASS does not enable production; review of the actual Windows
artifacts and a separate decision are required. Never run on a private library.
"""
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import pytest
from PySide6.QtCore import Qt
from audio_adoption_fixtures import mp3_samples
from test_legacy_adoption_v0427 import library
from test_output_session_ui_v0427 import adopted_window
import test_output_session_ui_v0427 as ui
from audio_library_organizer.safety import windows_file_identity as native

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Native Windows x64/NTFS required; not a Linux simulation')


def record(kind,**data):
    target=os.environ.get('ALO_62D_EVIDENCE')
    if target:
        p=Path(target);p.mkdir(parents=True,exist_ok=True)
        with (p/'native-observations.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'kind':kind,**data},default=lambda v:v.hex() if isinstance(v,bytes) else str(v))+'\n')


def sample(tmp_path):
    p=tmp_path/'only-synthetic.bin';p.write_bytes(b'0123456789abcdef')
    return p


def test_release_gate_is_off_on_the_actual_windows_runtime(adopted_window):
    assert native.on_windows() and ctypes.sizeof(ctypes.c_void_p)==8
    assert native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    window,lib,_=adopted_window;ui.run_check(window)
    assert window.last_reconciliation_result.output_delivery is None
    assert not ui.presentation(window,lib[2]).confirmed
    record('release-gate',enabled=False)


@pytest.mark.parametrize('kind',['unchanged','same-size','restored-mtime','replace','rename-replace','hardlink','missing'])
def test_native_material_identity(tmp_path,kind):
    p=sample(tmp_path);before=native.capture(p);st=p.stat()
    if kind in ('same-size','restored-mtime'):
        p.write_bytes(b'fedcba9876543210')
        if kind=='restored-mtime':os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
    elif kind in ('replace','rename-replace'):
        replacement=tmp_path/'replacement.bin';replacement.write_bytes(b'fedcba9876543210')
        if kind=='rename-replace':p.rename(tmp_path/'original-held.bin')
        os.replace(replacement,p)
    elif kind=='hardlink':os.link(p,tmp_path/'only-synthetic-hardlink.bin')
    elif kind=='missing':p.unlink()
    if kind in ('hardlink','missing'):
        with pytest.raises((OSError,ValueError)):native.capture(p)
        record(kind,before=asdict(before),refused=True);return
    after=native.capture(p);post=p.stat()
    if kind=='unchanged':assert native.same_material(before,after)
    else:assert not native.same_material(before,after)
    if kind=='restored-mtime':
        assert (st.st_size,st.st_mtime_ns)==(post.st_size,post.st_mtime_ns)
        assert before.leaf.creation_time==after.leaf.creation_time
        assert before.leaf.change_time!=after.leaf.change_time
        # CPython3.11's ctime creation value must actually demonstrate the gap.
        if sys.version_info[:2]==(3,11):assert st.st_ctime_ns==post.st_ctime_ns
    record(kind,before=asdict(before),after=asdict(after),stat_before=list(st),stat_after=list(post),
        st_ctime_ns_before=st.st_ctime_ns,st_ctime_ns_after=post.st_ctime_ns,
        st_mtime_ns_before=st.st_mtime_ns,st_mtime_ns_after=post.st_mtime_ns)


def test_native_parent_replacement_changes_the_proof(tmp_path):
    directory=tmp_path/'parent';directory.mkdir();p=directory/'synthetic.bin';p.write_bytes(b'1234')
    before=native.capture(p);directory.rename(tmp_path/'held-parent');directory.mkdir();p.write_bytes(b'1234')
    after=native.capture(p)
    assert not native.same_material(before,after) and before.ancestors!=after.ancestors
    record('parent-replacement',before=asdict(before),after=asdict(after))


def test_native_sharing_denies_an_existing_ordinary_writer(tmp_path):
    p=sample(tmp_path)
    with p.open('r+b') as writer:
        writer.write(b'X');writer.flush()
        with pytest.raises(OSError):native.capture(p)
    assert native.capture(p)
    record('existing-writer',refused_while_open=True,accepted_after_close=True)


def test_native_open_music_handle_denies_new_writer_and_parent_handle_denies_rename(tmp_path):
    p=sample(tmp_path);api=native._WinAPI();h=api.open(str(p),mutable=False)
    try:
        with pytest.raises(OSError):
            with p.open('r+b'):pass
    finally:api.close(h)
    directory=tmp_path/'held-directory';directory.mkdir();h=api.open(str(directory),mutable=True)
    try:
        with pytest.raises(OSError):directory.rename(tmp_path/'renamed-directory')
    finally:api.close(h)
    record('share-denial',new_writer_refused=True,parent_rename_refused=True)


def test_native_junction_is_refused_without_traversal(tmp_path):
    target=tmp_path/'real-directory';target.mkdir();(target/'synthetic.bin').write_bytes(b'123')
    junction=tmp_path/'junction'
    # Windows mklink /J works without admin. Both paths are generated here;
    # no input from environment or user data is interpolated into the shell.
    for p in (junction,target):
        assert not any(c in str(p) for c in '&|<>"%^!\r\n'), 'Unsafe shell path: junction probe NOT RUN'
    cmd=Path(os.environ['SystemRoot'])/'System32'/'cmd.exe'
    result=subprocess.run([str(cmd),'/d','/c','mklink','/J',str(junction),str(target)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    try:
        with pytest.raises((OSError,ValueError)):native.capture(junction/'synthetic.bin')
        assert (target/'synthetic.bin').read_bytes()==b'123'
    finally:os.rmdir(junction)  # junction itself; never recurse into target
    record('junction',refused=True)


def test_native_symlink_is_refused_if_the_host_can_create_it(tmp_path):
    p=sample(tmp_path);link=tmp_path/'synthetic-link'
    try:link.symlink_to(p)
    except OSError as exc:
        record('symlink',status='NOT RUN',reason=str(exc))
        pytest.skip('Host does not permit symlink creation; mandatory native evidence still missing')
    try:
        with pytest.raises((OSError,ValueError)):native.capture(link)
    finally:link.unlink()


def test_unc_is_refused_before_opening_any_network_object():
    with pytest.raises(ValueError):native.capture(r'\\invalid.example\not-opened\synthetic.mp3')
    record('UNC',refused=True,network_open=False)


@pytest.fixture
def diagnostic_window(adopted_window,monkeypatch):
    assert native.on_windows() and native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    # Only diagnostic tests may exercise the proposed positive route. No API,
    # identity, evaluator, material check, context check or color is substituted.
    monkeypatch.setattr(native,'WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED',True)
    record('diagnostic-gate-override',test_only=True)
    yield adopted_window


@contextmanager
def require_native_delivery(monkeypatch):
    """Refusal tests must start with an actual eligible native worker packet."""
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    original=FileReconciliationWorker.__init__;packets=[]
    with monkeypatch.context() as local_patch:
        def init(worker,*a,**kw):
            original(worker,*a,**kw)
            worker.finished.connect(lambda result:packets.append(result.output_delivery),Qt.ConnectionType.DirectConnection)
        local_patch.setattr(FileReconciliationWorker,'__init__',init)
        yield local_patch
        assert packets and all(d is not None and len(d.windows_material)==2 and d.windows_database is not None
            and d.windows_lease is not None and not d.windows_lease.active and d.windows_lease.owned_count==0 for d in packets)


@pytest.mark.parametrize('language',['pl','en'])
def test_diagnostic_real_mp3_worker_mainwindow_column_filter_sort(diagnostic_window,language):
    ui.test_real_check_reaches_column_filter_sort_and_survives_selection_refresh(diagnostic_window,language)
    window,lib,_=diagnostic_window
    d=window.last_reconciliation_result.output_delivery
    assert d and len(d.windows_material)==2 and d.windows_database is not None
    record('real-mainwindow-positive',language=language,native_material=[asdict(x) for x in d.windows_material],
        database=asdict(d.windows_database),state='NEEDS_UPDATE')
    target=os.environ.get('ALO_62D_EVIDENCE')
    if target:window.library.grab().save(str(Path(target)/('windows-library-'+language+'.png')))


@pytest.mark.parametrize('kind',['artist','title','album','bpm','cover','binding','source','policy','generation','cancel','output-bytes'])
def test_diagnostic_real_queued_context_mutation_is_refused(diagnostic_window,monkeypatch,kind):
    with require_native_delivery(monkeypatch) as patch:
        ui.test_change_between_worker_and_gui_delivery_is_rejected(diagnostic_window,patch,kind)


@pytest.mark.parametrize('which',['source','managed'])
def test_diagnostic_same_size_restored_mtime_in_the_qt_queue_is_refused(diagnostic_window,monkeypatch,which):
    from audio_library_organizer.ui.workers import FileReconciliationWorker
    window,lib,_=diagnostic_window;repo,root,track,output=lib
    path=track.path if which=='source' else output
    original=FileReconciliationWorker.__init__;observed=[]
    def init(worker,*a,**kw):
        original(worker,*a,**kw)
        def change(result):
            assert result.output_delivery is not None
            before=native.capture(path);st=path.stat();raw=bytearray(path.read_bytes());raw[-1]^=1
            with pytest.raises(OSError):path.write_bytes(raw)
            after=native.capture(path);observed.append((before,after))
        worker.finished.connect(change,Qt.ConnectionType.DirectConnection)
    monkeypatch.setattr(FileReconciliationWorker,'__init__',init)
    ui.run_check(window)
    assert observed and native.same_material(*observed[0])
    assert window.last_reconciliation_result.output_delivery.windows_lease.accepted
    assert track.track_id in window._output_history
    assert not ui.presentation(window,track).confirmed
    record('queued-restored-mtime-write-blocked-under-lease',material=which,before=asdict(observed[0][0]),after=asdict(observed[0][1]))


@pytest.mark.parametrize('field,value',[('artist','Changed artist'),('title','Changed title'),('album','Changed album'),('bpm',131.0)])
def test_diagnostic_edit_and_recheck(diagnostic_window,field,value):
    ui.test_edit_after_acceptance_invalidates_state_before_next_check(diagnostic_window,field,value)


@pytest.mark.parametrize('case',['partial','late','foreign-library','restart-scope','watch','wal-context','busy-db'])
def test_diagnostic_existing_session_safety(diagnostic_window,monkeypatch,case):
    tests={'partial':ui.test_partial_match_never_becomes_in_library,
        'late':ui.test_late_result_cannot_replace_newer_actual_check,
        'foreign-library':ui.test_foreign_library_context_cannot_accept_existing_delivery,
        'restart-scope':ui.test_state_is_not_restored_from_cache_after_restart,
        'watch':ui.test_watch_event_invalidates_only_session_evidence,
        'wal-context':ui.test_wal_metadata_change_invalidates_accepted_state}
    if case=='partial':tests[case](diagnostic_window)
    else:
        with require_native_delivery(monkeypatch) as patch:
            if case=='busy-db':ui.test_database_locked_at_gui_acceptance_refuses_without_waiting(diagnostic_window,patch)
            else:tests[case](diagnostic_window)


def test_diagnostic_missing_watch_refuses_positive_delivery(diagnostic_window,monkeypatch):
    window,lib,_=diagnostic_window
    monkeypatch.setattr(window._output_watcher,'addPaths',lambda paths:list(paths))
    ui.run_check(window)
    ui.assert_no_output_confirmation(window,lib[2])


def test_diagnostic_ordinary_wal_cache_write_does_not_invalidate_context(diagnostic_window):
    window,lib,_=diagnostic_window;repo,_,track,_=lib
    ui.run_check(window);ui.assert_completed_observation(window,track)
    # Real cache row write via normal check; identity/context must remain same.
    from audio_library_organizer.jobs.file_reconciliation import check_library
    check_library(repo,library_root=lib[1])
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents();window._output_watch_changed(str(repo.database_path)+'-wal')
    ui.assert_completed_observation(window,track)
