"""Real private Windows pytest + audit + FFmpeg + Qt; no product source."""
from pathlib import Path
import os,sys,traceback,json
if sys.stdin.buffer.readline()!=b'SMOKE-GO\n':raise SystemExit('Missing Job Object handshake')
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'harness')]
from contract import read_json,write_json,sha256
from private_runtime import verify_private_runtime
folder=Path(sys.argv[1]).resolve();mode=sys.argv[2];code=2;observer=None;guard=None
receipt=dict(status='STOP',scope='NATIVE_WINDOWS_OFFSCREEN_TECHNICAL_NOT_PRODUCT_GUI',mode=mode,stage='private_runtime',pid=os.getpid())
try:
    verify_private_runtime();before=os.environ['PATH']
    from PySide6 import QtCore,QtGui,QtWidgets,QtNetwork,QtMultimedia
    import PySide6,shiboken6
    after=os.environ['PATH']
    write_json(folder/'PATH.json',dict(before_Qt=before,after_Qt=after,executable=sys.executable,Qt_origin=PySide6.__file__,Qt=QtCore.qVersion()))
    from native_probe import check_native
    receipt['native_before']=check_native(os.environ['L41_RUNTIME_CATALOG'],os.environ['L41_RUNTIME_CATALOG_SHA256'])
    (folder/'data').mkdir();os.chdir(folder/'data')
    from gui_isolation import GuiIsolation,prepare_platform_diagnostics
    guard=GuiIsolation(folder,ROOT/'harness');guard.read_only_metadata={ROOT/'harness/pytest.ini'}
    sys.addaudithook(guard.audit);sys.meta_path.insert(0,guard)
    write_json(folder/'diagnostics-preparation.json',prepare_platform_diagnostics())
    if mode=='RED':from observe_baseline import Observer
    else:from observe import Observer
    observer=Observer(ROOT,folder);observer.install()
    import pytest
    from run_case import pytest_logging_options
    from types import SimpleNamespace
    phases=[];nodes=[];qt=[];handlers=[]
    ctx=SimpleNamespace(folder=folder,guard=guard,observer=observer,QtCore=QtCore,QtWidgets=QtWidgets,shiboken6=shiboken6,qt_events=qt)
    class Evidence:
        @pytest.fixture
        def smoke_env(self):return ctx
        def pytest_sessionstart(self,session):handlers.append(session.config.pluginmanager.get_plugin('logging-plugin').log_file_handler)
        def pytest_collection_finish(self,session):nodes.extend(i.nodeid for i in session.items)
        def pytest_runtest_logreport(self,report):
            phases.append(dict(nodeid=report.nodeid,phase=report.when,outcome=report.outcome,xfail=bool(getattr(report,'wasxfail',False)),longrepr=str(report.longrepr)if report.longrepr else None))
            write_json(folder/'phases.json',phases)
    receipt['stage']='pytest.initialization'
    target=str(ROOT/'harness/test_smoke.py')+('::test_SMOKE_03_ffmpeg'if mode=='RED'else'')
    code=int(pytest.main(['-c',str(ROOT/'harness/pytest.ini'),'--rootdir='+str(ROOT/'harness'),'--noconftest','-p','no:cacheprovider',
        '--basetemp='+str(folder/'data/tmp'),'-vv','--capture=tee-sys','--tb=short','-x','--junitxml='+str(folder/'results.xml'),
        *pytest_logging_options(folder,guard),target],plugins=[Evidence()]))
    write_json(folder/'collection.json',nodes);write_json(folder/'qt-lifecycle.json',qt)
    receipt.update(pytest_exit=code,cases=len(nodes),phases=len(phases),XML=1,log_closed=all(h.stream is None for h in handlers))
    if mode=='GREEN':
        from xml.etree import ElementTree as ET
        xml=list(ET.parse(folder/'results.xml').iter('testcase'))
        assert code==0 and len(nodes)==6 and len(phases)==18 and len(xml)==6
        assert all(p['outcome']=='passed'and not p['xfail']for p in phases)
        assert not any(x.find(k)is not None for x in xml for k in ('failure','error','skipped'))
        assert receipt['log_closed']and len(qt)==2 and all(x['destroyed']for x in qt)
        assert len(observer.record['violations'])==1 and observer.record['violations'][0]['event']=='subprocess.Popen'
        assert len(guard.attempts)==3 and not observer.record['errors']
        # QApplication has now loaded its real platform plugin: attest actual late-loaded DLLs too.
        receipt['native_after_QApplication']=check_native(os.environ['L41_RUNTIME_CATALOG'],os.environ['L41_RUNTIME_CATALOG_SHA256'])
        receipt['status']='PASS'
    receipt['stage']='complete'
except BaseException as error:
    receipt['error']=repr(error);(folder/'error.log').write_text(traceback.format_exc(),encoding='utf-8');code=2
finally:
    if observer is not None:observer.finish()
    if guard is not None:write_json(folder/'isolation.json',guard.evidence())
    receipt['exit_code']=code;write_json(folder/'child.json',receipt)
raise SystemExit(code)
