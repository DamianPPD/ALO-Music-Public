"""Bounded native Server spike. No product edits, UI automation or gate switch.

Uses the established ci.py prepare/provenance, pytest and original assertions.
Raw Win32 probes run independently of expected assertion RED; infrastructure,
integrity, crash or timeout errors stop further child execution.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import ctypes
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('established_ci', HERE/'ci.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
OUT = ci.EVIDENCE/'same-size-fix'
OUT.mkdir(exist_ok=True)
PREFIX = 'tests/test_windows_output_native_v0427.py::'
CASES = [PREFIX+'test_native_material_identity[same-size]']*3 + [
    PREFIX+'test_native_material_identity[restored-mtime]',
    PREFIX+'test_diagnostic_same_size_restored_mtime_in_the_qt_queue_is_refused[source]',
    PREFIX+'test_diagnostic_same_size_restored_mtime_in_the_qt_queue_is_refused[managed]']


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=lambda v:v.hex() if isinstance(v, bytes) else str(v))+'\n', encoding='utf-8')


def windows_required():
    if sys.platform != 'win32' or struct.calcsize('P') != 8 or sys.version_info[:3] != (3,11,9):
        raise RuntimeError('Native Windows x64 CPython3.11.9 required; no Linux/Wine substitute')


def load_product():
    sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
    from audio_library_organizer.safety import windows_file_identity as native
    assert native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    return native


class Phases:
    def __init__(self, folder): self.folder = folder; self.exceptions = {}
    def pytest_runtest_makereport(self, item, call):
        exc=call.excinfo
        self.exceptions[call.when] = (None, False) if exc is None else (
            exc.type.__module__+'.'+exc.type.__qualname__, exc.type is AssertionError)
    def pytest_runtest_logreport(self, report):
        exc,is_assertion=self.exceptions.get(report.when,(None,False))
        with (self.folder/'phases.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome,
                               'duration':report.duration,'wasxfail':getattr(report,'wasxfail',None),
                               'exception_type':exc,'assertion_error':is_assertion})+'\n')


def pytest_child(case, folder):
    windows_required()
    assert case in CASES
    assert folder.resolve().parent == OUT.resolve()
    load_product()
    import pytest
    # Observe call.excinfo before pytest's default firstresult implementation;
    # returning None does not replace its actual TestReport or assertions.
    Phases.pytest_runtest_makereport=pytest.hookimpl(tryfirst=True)(Phases.pytest_runtest_makereport)
    return pytest.main([case,'-v','--junitxml='+str(folder/'result.xml'),
        '--basetemp='+str(folder/'synthetic'),'-o','cache_dir='+str(folder/'cache')],plugins=[Phases(folder)])


def native_probe():
    windows_required();native=load_product()
    work=OUT/'probe-synthetic';work.mkdir(exist_ok=False)
    rows=[];old=b'0123456789abcdef';new=b'fedcba9876543210'
    api=native._WinAPI()
    k=api.k
    flush=k.FlushFileBuffers;flush.argtypes=[ctypes.c_void_p];flush.restype=ctypes.c_int32
    def proof(p): return native.capture(str(p))
    def save(kind,index,p,before,after,actual,**extra):
        row={'kind':kind,'iteration':index,'before':asdict(before),'after':asdict(after),
             'bytes_expected_before_hex':old.hex(),'bytes_expected_after_hex':new.hex(),
             'bytes_after_actual_hex':actual.hex(),'sha_after_actual':hashlib.sha256(actual).hexdigest(),
             'same_material':native.same_material(before,after),'actual_changed':actual==new,**extra}
        rows.append(row)
        # Serialize only after the second observation; no extra logging/hash I/O
        # is inserted between the two token captures of the minimal scenario.
        write(OUT/'native-probes.json',{'scope':'real native API, synthetic NTFS files',
             'product_gate':'OFF','product_modified':False,'samples':rows})
    for kind,count in [('same-size',8),('restored-mtime',8),('new-handle',4),('flush-close',4),('replace',4)]:
        for i in range(count):
            p=work/(kind+'-'+str(i)+'.bin');p.write_bytes(old)
            initial=p.read_bytes();assert initial==old
            before=proof(p);st=p.stat() if kind=='restored-mtime' else None
            if kind=='replace':
                q=work/('replacement-'+str(i)+'.bin');q.write_bytes(new);os.replace(q,p)
            elif kind in ('new-handle','flush-close'):
                with p.open('r+b',buffering=0) as f:
                    assert f.write(new)==16
                    if kind=='flush-close':
                        import msvcrt
                        if not flush(msvcrt.get_osfhandle(f.fileno())): raise ctypes.WinError(ctypes.get_last_error())
            else:
                assert p.write_bytes(new)==16
                if st is not None:os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
            after=proof(p);actual=p.read_bytes()
            assert actual==new and p.stat().st_size==16
            save(kind,i,p,before,after,actual,bytes_before_actual_hex=initial.hex(),
                 sha_before_actual=hashlib.sha256(initial).hexdigest(),writer_closed_before_after_capture=True)
    p=work/'rapid.bin';p.write_bytes(old);before=proof(p)
    previous=old
    for i in range(32):
        content=new if i%2==0 else old
        assert p.write_bytes(content)==16
        after=proof(p);actual=p.read_bytes();assert actual==content
        save('rapid',i,p,before,after,actual,actual_changed=actual!=previous,
             bytes_expected_before_hex=previous.hex(),bytes_before_actual_hex=previous.hex(),
             sha_before_actual=hashlib.sha256(previous).hexdigest(),
             bytes_expected_after_hex=content.hex(),writer_closed_before_after_capture=True)
        before=after;previous=actual
    import msvcrt
    for i in range(4):
        p=work/('same-handle-'+str(i)+'.bin');p.write_bytes(old)
        with p.open('r+b',buffering=0) as f:
            h=msvcrt.get_osfhandle(f.fileno());before=api.query(h)
            assert f.write(new)==16
            after=api.query(h);f.seek(0);actual=f.read();assert actual==new
            refused=False
            try:proof(p)
            except OSError:refused=True
            assert refused,'Public capture must refuse while the ordinary writer is open'
        public_after=proof(p)
        rows.append({'kind':'same-writer-handle-raw-query','iteration':i,
            'before':asdict(before),'after':asdict(after),'actual_changed':True,
            'bytes_after_actual_hex':actual.hex(),'sha_after_actual':hashlib.sha256(actual).hexdigest(),
            'same_raw_node':before==after,'writer_open_during_query':True,
            'public_capture_refused_writer':refused,'public_after_close':asdict(public_after)})
    class FILETIME(ctypes.Structure): _fields_=[('value',ctypes.c_uint64)]
    coarse=k.GetSystemTimeAsFileTime;coarse.argtypes=[ctypes.POINTER(FILETIME)];coarse.restype=None
    precise=k.GetSystemTimePreciseAsFileTime;precise.argtypes=[ctypes.POINTER(FILETIME)];precise.restype=None
    clocks=[]
    for _ in range(2048):
        a=FILETIME();b=FILETIME();coarse(ctypes.byref(a));precise(ctypes.byref(b))
        clocks.append([time.perf_counter_ns(),a.value,b.value])
    trace=[]
    class TraceAPI(native._WinAPI):
        def open(self,path,*,mutable):
            trace.append({'event':'open-attempt','path':path,'mutable':mutable,'qpc_ns':time.perf_counter_ns()})
            h=super().open(path,mutable=mutable)
            trace.append({'event':'open-return','handle':h,'qpc_ns':time.perf_counter_ns()});return h
        def query(self,h):
            n=super().query(h);trace.append({'event':'query-return','handle':h,'node':asdict(n),'qpc_ns':time.perf_counter_ns()});return n
        def close(self,h):
            super().close(h);trace.append({'event':'closed','handle':h,'qpc_ns':time.perf_counter_ns()})
    p=work/'traced.bin';p.write_bytes(old)
    before=native._capture(str(p),TraceAPI())
    trace.append({'event':'write-attempt','qpc_ns':time.perf_counter_ns()})
    assert p.write_bytes(new)==16
    trace.append({'event':'write-returned-and-closed','qpc_ns':time.perf_counter_ns()})
    after=native._capture(str(p),TraceAPI());assert p.read_bytes()==new
    write(OUT/'native-probes.json',{'scope':'real Windows Server API, synthetic data only',
        'gate':'OFF','samples':rows,'clocks_qpc_coarse_precise':clocks,
        'trace':trace,'traced_before':asdict(before),'traced_after':asdict(after),
        'traced_same_material':native.same_material(before,after),
        'notes':['Raw writer-handle query is not a trusted public capture.',
                 'Clock observation and trace alter timing; not proof of causation.',
                 'No sleep or production fix; each minimal pair logs only after capture.']})
    assert native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    return 0


def classify(folder,code):
    if code not in (0,1): return 'STOP_PROCESS'
    path=folder/'result.xml'
    if not path.exists(): return 'STOP_NO_XML'
    cases=list(ET.parse(path).iter('testcase'))
    if len(cases)!=1:return 'STOP_XML_COUNT'
    c=cases[0]
    if c.find('error') is not None:return 'ERROR'
    if c.find('skipped') is not None:return 'SKIP'
    try:
        phases=[json.loads(line) for line in (folder/'phases.jsonl').read_text().splitlines()]
    except (OSError,ValueError):return 'STOP_PHASES'
    if ([p.get('when') for p in phases]!=['setup','call','teardown']
            or phases[0].get('outcome')!='passed' or phases[2].get('outcome')!='passed'
            or any(p.get('wasxfail') is not None for p in phases)):
        return 'STOP_PHASES'
    call=phases[1]
    if c.find('failure') is not None:
        if code!=1:return 'STOP_EXIT_XML_MISMATCH'
        if call.get('outcome')!='failed':return 'STOP_PHASES'
        return 'FAIL' if call.get('assertion_error') is True and call.get('exception_type')=='builtins.AssertionError' else 'ERROR'
    if any(p.get('outcome')!='passed' or p.get('exception_type') is not None for p in phases):return 'STOP_PHASES'
    return 'PASS' if code==0 else 'STOP_EXIT_XML_MISMATCH'


def child_environment(python,binpath):
    env=ci.safe_environment(python,binpath)
    # Only the verified private evidence root crosses the environment boundary;
    # Actions tokens/secrets remain excluded by the original allowlist.
    env['RUNNER_TEMP']=str(ci.EVIDENCE.parent)
    return env


def run():
    windows_required();ci.verify_sources()
    data=json.loads((ci.EVIDENCE/'prepared.json').read_text())
    env=child_environment(Path(data['python']),Path(data['bin']))
    status={'scope':'Native Windows Server2022; not Desktop','gate':'OFF',
            'product_modified':False,'candidate_tree':ci.TREE,'cases':[],
            'native_probe':'NOT RUN','source_before':True,'source_after':False}
    write(OUT/'run.json',status)
    try:
        for i,case in enumerate(CASES,1):
            folder=OUT/(f'{i:02d}-original');folder.mkdir(exist_ok=False)
            profile=folder/'profile';profile.mkdir()
            childenv=dict(env,ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),
                          APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile))
            cmd=[data['python'],'-I','-B',str(Path(__file__).resolve()),'pytest-child',case,str(folder)]
            with (folder/'stdout.log').open('wb') as out,(folder/'stderr.log').open('wb') as err:
                result=subprocess.run(cmd,cwd=ROOT,env=childenv,stdout=out,stderr=err,timeout=120)
            (folder/'exit.txt').write_text(str(result.returncode))
            outcome=classify(folder,result.returncode)
            status['cases'].append({'index':i,'case':case,'exit':result.returncode,'status':outcome})
            ci.verify_sources();write(OUT/'run.json',status)
            if outcome not in ('PASS','FAIL'):raise RuntimeError('Unexpected original case outcome: '+outcome)
        with (OUT/'probe.stdout.log').open('wb') as out,(OUT/'probe.stderr.log').open('wb') as err:
            result=subprocess.run([data['python'],'-I','-B',str(Path(__file__).resolve()),'native-probe'],
                cwd=ROOT,env=env,stdout=out,stderr=err,timeout=90)
        (OUT/'probe.exit.txt').write_text(str(result.returncode))
        status['native_probe']='COMPLETE' if result.returncode==0 else 'ERROR'
        if result.returncode:raise RuntimeError('Native probe incomplete')
        status['status']='DIAGNOSTIC_COMPLETE_REVIEW_REQUIRED'
    except BaseException as exc:
        status['status']='STOP';status['error']=type(exc).__name__+': '+str(exc)
        (OUT/'exception.log').write_text(traceback.format_exc())
        raise
    finally:
        ci.verify_sources();status['source_after']=True
        write(OUT/'run.json',status)
    # Diagnostic completeness does not mean original assertions passed.
    return 0 if all(c['status']=='PASS' for c in status['cases']) else 1


def finish():
    integrity='NOT RUN'
    try:
        if (ci.EVIDENCE/'prepared.json').exists():ci.verify_sources();integrity='PASS'
    except Exception as exc:
        integrity='FAIL';write(ci.EVIDENCE/'finish-integrity-error.json',{'error':str(exc)})
    write(ci.EVIDENCE/'FIX-SUMMARY.json',{'source_integrity':integrity,'product_gate':'OFF',
        'native_run':json.loads((OUT/'run.json').read_text()) if (OUT/'run.json').exists() else {'status':'NOT RUN'}})
    files=[p for p in ci.EVIDENCE.rglob('*') if p.is_file()
        and not any(part in ('probe-synthetic','synthetic','cache','profile') for part in p.relative_to(ci.EVIDENCE).parts)
        and p.suffix in ('.json','.jsonl','.log','.txt','.xml','.png')
        and p.name!='FIX-MANIFEST.json']
    manifest=[{'path':p.relative_to(ci.EVIDENCE).as_posix(),'bytes':p.stat().st_size,
               'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    write(ci.EVIDENCE/'FIX-MANIFEST.json',manifest)
    output=ci.EVIDENCE/'ALO-62D-SAME-SIZE-evidence.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(ci.EVIDENCE).as_posix())
        z.write(ci.EVIDENCE/'FIX-MANIFEST.json','FIX-MANIFEST.json')
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        for f in manifest:assert hashlib.sha256(z.read(f['path'])).hexdigest()==f['sha256']
    Path(str(output)+'.sha256.txt').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n')
    return 2 if integrity=='FAIL' else 0


if __name__=='__main__':
    try:
        action=sys.argv[1]
        if action=='pytest-child':code=pytest_child(sys.argv[2],Path(sys.argv[3]))
        else:code={'run':run,'native-probe':native_probe,'finish':finish}[action]()
    except BaseException:
        (OUT/'controller-exception.log').write_text(traceback.format_exc());raise
    sys.exit(code)
