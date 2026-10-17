"""Six real Windows infrastructure checks; no unpublished ALO candidate."""
import logging,os,socket,sqlite3,subprocess,sys
from pathlib import Path
from importlib import metadata
import pytest
pytest_plugins=['audio_adoption_fixtures']

def test_SMOKE_01_python(smoke_env):
    assert sys.platform=='win32'and sys.version_info[:3]==(3,11,9)and sys.flags.isolated
    import json
    pins=json.loads((Path(__file__).resolve().parents[1]/'requirements/pins.json').read_text())
    assert {k:metadata.version(k)for k in pins}==pins
    assert smoke_env.QtCore.qVersion()=='6.10.3'

def test_SMOKE_02_pytest(smoke_env,caplog):
    assert pytest.__version__=='9.1.1'
    logging.warning('SMOKE02_REAL_LOGGER');print('SMOKE02_REAL_STDOUT');print('SMOKE02_REAL_STDERR',file=sys.stderr)
    assert 'SMOKE02_REAL_LOGGER'in caplog.text
    assert (smoke_env.folder/'sandbox/logs/pytest.log').is_file()

def test_SMOKE_03_ffmpeg(smoke_env,mp3_samples):
    from mutagen.mp3 import MP3
    from contract import sha256,write_json
    evidence=[]
    for path in mp3_samples.values():
        info=MP3(path).info;assert info.length>1.5 and info.channels==2
        evidence.append(dict(path=str(path),sha256=sha256(path),size_bytes=path.stat().st_size,length=info.length))
    write_json(smoke_env.folder/'synthetic-audio.json',evidence)

def test_SMOKE_04_observer(smoke_env):
    with pytest.raises(PermissionError):subprocess.run([sys.executable,'-c','raise SystemExit(99)'])
    outside=smoke_env.folder.parent/'must-not-create.txt'
    with pytest.raises(RuntimeError):outside.write_text('denied')
    with pytest.raises(RuntimeError):sqlite3.connect(smoke_env.folder.parent/'must-not-create.sqlite3')
    with pytest.raises(RuntimeError):socket.getaddrinfo('must-not-resolve.invalid',443)
    assert not outside.exists()
    with sqlite3.connect(smoke_env.folder/'data/synthetic.sqlite3')as con:
        con.execute('CREATE TABLE proof(value TEXT)');con.execute("INSERT INTO proof VALUES ('synthetic')")
        assert con.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert con.execute('PRAGMA foreign_key_check').fetchall()==[]

def qt_lifecycle(ctx,during=None):
    app=ctx.QtWidgets.QApplication([]);destroyed=[]
    app.destroyed.connect(lambda:destroyed.append(True))
    widget=ctx.QtWidgets.QWidget();widget.setWindowTitle('Synthetic Windows CI smoke');widget.show();app.processEvents()
    assert app.platformName()=='offscreen'
    if during:during()
    widget.close();ctx.shiboken6.delete(widget)
    ctx.QtCore.QMetaObject.invokeMethod(app,'quit',ctx.QtCore.Qt.ConnectionType.QueuedConnection)
    assert app.exec()==0
    assert ctx.QtCore.QThreadPool.globalInstance().waitForDone(1000)
    ctx.shiboken6.delete(app)
    assert destroyed==[True]
    ctx.qt_events.append(dict(platform='offscreen',visible_user_desktop=False,destroyed=True))

def test_SMOKE_05_qt(smoke_env):qt_lifecycle(smoke_env)

def test_SMOKE_06_integration(smoke_env,mp3_samples):
    def during():
        wav=mp3_samples['original'].with_suffix('.wav');target=smoke_env.folder/'data/absolute-ffmpeg.mp3'
        p=subprocess.run([os.environ['I7_FFMPEG_EXE'],'-v','error','-nostdin','-i',str(wav),'-c:a','libmp3lame','-b:a','128k',str(target)],
            check=True,capture_output=True,timeout=20)
        assert p.returncode==0 and target.stat().st_size>1000
        logging.warning('SMOKE06_PYTEST_AUDIT_QT_FFMPEG_IN_ONE_PROCESS')
    qt_lifecycle(smoke_env,during)
