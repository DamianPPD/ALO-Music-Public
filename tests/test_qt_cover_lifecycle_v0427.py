"""Cover cancellation uses real QObject, ReadTask, images and queued delivery."""
import gc
import io
import os
import shutil
import sys
from pathlib import Path
from threading import Event
from time import monotonic
from weakref import ref

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QThread, QThreadPool, Qt, SIGNAL, qInstallMessageHandler
from PySide6.QtGui import QColor
from PySide6.QtNetwork import QTcpServer, QHostAddress, QNetworkReply
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import delete, isValid

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.managed_files import ReadContext, ReadPurpose, local_read_plan, read_material
from audio_library_organizer.ui import library_page as module
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.workers import ReadTaskSignals
from audio_adoption_fixtures import mp3_samples


def pump(app, predicate, seconds=8):
    deadline = monotonic() + seconds
    while not predicate() and monotonic() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert predicate(), 'Qt operation did not finish'


@pytest.fixture
def app(monkeypatch):
    app = QApplication.instance() or QApplication([])
    errors=[]
    old_hook=sys.excepthook
    def hook(*args): errors.append(str(args[1]))
    def messages(kind,context,message):
        if any(text in message for text in ('Destroyed while','different thread','Cannot send events','already deleted')):
            errors.append(message)
    old_messages=qInstallMessageHandler(messages);sys.excepthook=hook
    original=LibraryPage._set_cover_pixmap
    def set_pixmap(page,*args):
        assert QThread.currentThread()==app.thread(),'Cover pixmap applied outside the GUI thread'
        return original(page,*args)
    monkeypatch.setattr(LibraryPage,'_set_cover_pixmap',set_pixmap)
    try:
        yield app
        assert QThreadPool.globalInstance().waitForDone(8000)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        assert not errors,errors
    finally:
        qInstallMessageHandler(old_messages);sys.excepthook=old_hook


def image(path, color):
    Image.new('RGB', (16, 16), color).save(path)
    return path


def track(tmp_path, name, *, color='#2277bb', extension='png'):
    cover = image(tmp_path / f'{name}.{extension}', color)
    return TrackRecord(path=tmp_path / f'{name}.mp3', artist='Synthetic', title=name,
                       manual_cover_path=str(cover), cover_choice='manual')


def has_color(page, color):
    if page._cover_pixmap.isNull():
        return False
    actual = page._cover_pixmap.toImage().pixelColor(3, 3)
    wanted = QColor(color)
    return all(abs(a-b) < 5 for a,b in zip(actual.getRgb()[:3], wanted.getRgb()[:3]))


def dispose(page):
    if isValid(page):
        page.close()
        delete(page)


def test_repeated_cover_requests_do_not_grow_destroyed_connections(app, tmp_path):
    page = LibraryPage()
    item = TrackRecord(path=tmp_path/'none.mp3', cover_choice='placeholder')
    retained = []  # Model cancellation tokens still owned by pending reads.
    try:
        page._load_cover(item)
        initial = page.receivers(SIGNAL('destroyed()'))
        for _ in range(100):
            retained.append(page._cover_cancel)
            page._load_cover(item)
        assert all(e.is_set() for e in retained)
        assert page.receivers(SIGNAL('destroyed()')) == initial, 'Per-request lifecycle connections accumulated'
    finally:
        dispose(page)


@pytest.mark.parametrize('extension', ['png','jpg'])
def test_manual_cover_is_decoded_on_gui_thread(app, tmp_path, extension):
    page = LibraryPage(); item = track(tmp_path, 'manual', extension=extension)
    try:
        page.set_tracks([item]); page.select_track(item)
        pump(app, lambda: has_color(page, '#2277bb'))
        assert page._cover_note == 'Okładka wybrana ręcznie.'
        assert page.thread() == app.thread()
    finally:
        dispose(page)


@pytest.mark.parametrize('destruction', ['close','delete','deleteLater','parent'])
def test_active_read_is_cancelled_by_entire_widget_lifetime(app, tmp_path, monkeypatch, destruction):
    parent = QWidget(); page = LibraryPage(parent); item = track(tmp_path, 'blocked')
    started, release = Event(), Event()
    original = module.read_artwork_bytes
    def read(path):
        started.set()
        assert release.wait(8), 'Test did not release the physical reader'
        return original(path)
    monkeypatch.setattr(module, 'read_artwork_bytes', read)
    try:
        page.set_tracks([item]); page.select_track(item)
        pump(app, started.is_set)
        cancel = page._cover_cancel
        pending = tuple(app.findChildren(ReadTaskSignals))
        assert pending, 'No real ReadTask signal object was created'
        if destruction == 'close':
            page.close()
        elif destruction == 'delete':
            delete(page)
        elif destruction == 'deleteLater':
            page.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        else:
            delete(parent)
        assert cancel.is_set(), f'{destruction} did not cancel the active cover request'
        release.set()
        pump(app, lambda: QThreadPool.globalInstance().activeThreadCount() == 0)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert all(not isValid(s) for s in pending), 'ReadTaskSignals survived completion'
    finally:
        release.set(); dispose(page)
        if isValid(parent): delete(parent)


def test_completed_old_request_is_not_retained_by_destroyed_signal(app, tmp_path):
    page = LibraryPage(); first = track(tmp_path,'first'); second = track(tmp_path,'second')
    try:
        page.set_tracks([first,second]); page.select_track(first)
        old = ref(page._cover_cancel)
        page.select_track(second)
        pump(app, lambda: QThreadPool.globalInstance().activeThreadCount() == 0)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete); gc.collect()
        assert old() is None, 'Old Event is retained after the read completes'
    finally:
        dispose(page)


def test_mainwindow_close_and_application_quit_path_cancel_cover(app,tmp_path):
    page=LibraryPage(); item=TrackRecord(path=tmp_path/'none.mp3',cover_choice='placeholder')
    try:
        page._load_cover(item)
        token=page._cover_cancel; serial=page._cover_request_serial
        # MainWindow's accepted close and QApplication.aboutToQuit both use this path.
        page.cancel_context_actions(closing=True)
        assert token.is_set(), 'Accepted MainWindow close left the cover read active'
        assert page._cover_request_serial > serial, 'Queued cover result remains current during shutdown'
    finally:
        dispose(page)


def test_queued_old_manual_result_cannot_overwrite_new_track(app, tmp_path):
    page = LibraryPage(); red = track(tmp_path,'red',color='#dd2233'); blue = track(tmp_path,'blue')
    emitter = ReadTaskSignals()
    try:
        page.set_tracks([red,blue]); page.select_track(red)
        pump(app, lambda: has_color(page,'#dd2233'))
        serial = page._cover_request_serial
        plan = local_read_plan(Path(red.manual_cover_path),ReadPurpose.COVER_READ,generation=serial)
        result = read_material(plan,module.read_artwork_bytes)
        assert result.resolution.is_verified and result.value
        emitter.ready.connect(page._manual_cover_ready,Qt.ConnectionType.QueuedConnection)
        emitter.ready.emit(serial,result)
        page.select_track(blue)
        pump(app,lambda:has_color(page,'#2277bb'))
        for _ in range(5): app.processEvents()
        assert has_color(page,'#2277bb')
        assert page._current_track() is blue
    finally:
        dispose(page); delete(emitter)


def test_rapid_selection_refresh_and_cancellation_leave_latest_image(app,tmp_path):
    page = LibraryPage(); items=[track(tmp_path,str(i),color=c) for i,c in enumerate(['#dd2233','#22bb55','#2277bb'])]
    old=[]
    try:
        page.set_tracks(items)
        for i in range(60):
            page.select_track(items[i%3]); old.append(page._cover_cancel)
            page.refresh(preserve_order=True)
        page.select_track(items[-1])
        pump(app,lambda:has_color(page,'#2277bb'))
        assert all(e.is_set() for e in old)
        assert page._current_track() is items[-1]
        page.close(); assert page._cover_cancel.is_set()
        pump(app,lambda:QThreadPool.globalInstance().activeThreadCount()==0)
    finally:
        dispose(page)


def test_real_embedded_mp3_cover_and_missing_cover_placeholder(app,tmp_path,mp3_samples):
    from mutagen.id3 import ID3, APIC
    source=tmp_path/'embedded.mp3';shutil.copyfile(mp3_samples['original'],source)
    data=io.BytesIO();Image.new('RGB',(16,16),'#dd2233').save(data,format='PNG')
    tags=ID3(source);tags.delall('APIC');tags.add(APIC(mime='image/png',type=3,data=data.getvalue()));tags.save(source)
    before=source.read_bytes()
    item=TrackRecord(path=source,cover_choice='source')
    missing=TrackRecord(path=tmp_path/'missing.mp3',cover_choice='source')
    page=LibraryPage()
    try:
        page.set_tracks([item,missing]);page.select_track(item)
        pump(app,lambda:has_color(page,'#dd2233'))
        page.select_track(missing)
        pump(app,lambda:QThreadPool.globalInstance().activeThreadCount()==0)
        app.processEvents()
        assert not has_color(page,'#dd2233')
        assert 'zastępcza' in page._cover_note
        assert source.read_bytes()==before
    finally:
        dispose(page)


def web_server(app, *, respond):
    server=QTcpServer();assert server.listen(QHostAddress.SpecialAddress.LocalHost,0)
    connections=[];requests=[]
    data=io.BytesIO();Image.new('RGB',(16,16),'#2277bb').save(data,format='PNG')
    body=data.getvalue()
    def connected():
        socket=server.nextPendingConnection();connections.append(socket)
        def ready():
            requests.append(bytes(socket.readAll()))
            if respond:
                socket.write(b'HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
                socket.disconnectFromHost()
        socket.readyRead.connect(ready)
    server.newConnection.connect(connected)
    return server,requests


def test_external_cover_uses_real_network_reply(app,tmp_path):
    server,requests=web_server(app,respond=True);page=LibraryPage()
    item=TrackRecord(path=tmp_path/'external.mp3',cover_choice='external',cover_art_url=f'http://127.0.0.1:{server.serverPort()}/cover.png')
    try:
        page.set_tracks([item]);page.select_track(item)
        pump(app,lambda:has_color(page,'#2277bb'))
        assert requests and 'pobrana' in page._cover_note
    finally:
        dispose(page);delete(server)


@pytest.mark.parametrize('destruction',['close','deleteLater','parent'])
def test_closing_cancels_pending_external_reply_without_new_fallback(app,tmp_path,destruction):
    server,requests=web_server(app,respond=False);parent=QWidget();page=LibraryPage(parent)
    item=TrackRecord(path=tmp_path/'external.mp3',cover_choice='external',cover_art_url=f'http://127.0.0.1:{server.serverPort()}/hold.png')
    try:
        page.set_tracks([item]);page.select_track(item)
        pump(app,lambda:bool(requests))
        replies=tuple(page._cover_network.findChildren(QNetworkReply))
        assert any(r.isRunning() for r in replies)
        cancel=page._cover_cancel
        if destruction=='close':page.close()
        elif destruction=='deleteLater':
            page.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        else:delete(parent)
        pump(app,lambda:all(not isValid(r) or not r.isRunning() for r in replies))
        assert cancel.is_set()
        assert not app.findChildren(ReadTaskSignals), 'Closing reply scheduled a fallback read'
    finally:
        dispose(page);delete(server)
        if isValid(parent):delete(parent)


def test_destroyed_page_is_not_retained_and_late_queued_signal_is_harmless(app,tmp_path):
    page=LibraryPage();item=track(tmp_path,'gone');emitter=ReadTaskSignals()
    page.set_tracks([item]);page.select_track(item)
    pump(app,lambda:has_color(page,'#2277bb'))
    serial=page._cover_request_serial
    plan=local_read_plan(Path(item.manual_cover_path),ReadPurpose.COVER_READ,generation=serial)
    result=read_material(plan,module.read_artwork_bytes)
    emitter.ready.connect(page._manual_cover_ready,Qt.ConnectionType.QueuedConnection)
    weak=ref(page);delete(page);del page;gc.collect()
    emitter.ready.emit(serial,result);app.processEvents();gc.collect()
    assert weak() is None,'A completed read or lifetime callback retained the old widget'
    delete(emitter)


@pytest.mark.parametrize('change',['context','empty'])
def test_leaving_selected_track_cancels_without_renewing_old_request(app,tmp_path,change):
    server,requests=web_server(app,respond=False);page=LibraryPage()
    item=TrackRecord(path=tmp_path/'old.mp3',cover_choice='external',cover_art_url=f'http://127.0.0.1:{server.serverPort()}/hold.png')
    try:
        page.set_read_context(ReadContext('first',str(tmp_path)))
        page.set_tracks([item]);page.select_track(item)
        pump(app,lambda:bool(requests))
        token=page._cover_cancel
        if change=='context':page.set_read_context(ReadContext('second',str(tmp_path)))
        else:page.set_tracks([])
        assert page._current_track() is None
        assert token.is_set()
        assert page._cover_cancel.is_set(),'Selection clearing started a new read for the old track'
        pump(app,lambda:all(not r.isRunning() for r in page._cover_network.findChildren(QNetworkReply)))
        assert not app.findChildren(ReadTaskSignals)
    finally:
        dispose(page);delete(server)
