"""External observational pytest plugin; no product/test-file overlays."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import threading
import time
import weakref

import pytest
import PySide6
from PySide6.QtCore import QObject, QUrl, Slot, qVersion
from PySide6.QtMultimedia import QMediaPlayer

INSTANCES = []
PATCHED_MODULES = set()


def emit(kind, **data):
    row = dict(kind=kind, pid=os.getpid(), native_thread=threading.get_native_id(),
               monotonic_ns=time.monotonic_ns(), **data)
    with Path(os.environ['ALO_MEDIA_OBSERVATIONS']).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')


def material(raw):
    if not raw:
        return None
    try:
        path = Path(raw)
        st = path.stat()
        return dict(path=str(path), absolute=path.is_absolute(), device=st.st_dev,
                    inode=st.st_ino, size=st.st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    except OSError as exc:
        return dict(path=str(raw), error=repr(exc))


def plan_data(plan):
    if plan is None:
        return None
    return {key: getattr(plan, key, None) for key in (
        'library_id', 'track_id', 'purpose', 'locator', 'kind', 'reason_code',
        'unresolved', 'generation', 'revision', 'is_verified', 'material_identity',
        'expected_sha256', 'guard_key')}


def snapshot(bar, kind, **extra):
    try:
        url = bar.player.source()
        expected = getattr(bar, '_active_read_plan', None)
        locator = getattr(expected, 'locator', None) or getattr(bar, 'current_path', None)
        actual = url.toLocalFile()
        native_equal = bool(actual and locator and Path(actual) == Path(locator))
        same_object = False
        if actual and locator:
            try:
                same_object = Path(actual).samefile(locator)
            except OSError:
                pass
        emit(kind, player=id(bar), source_string=url.toString(),
             source_encoded=bytes(url.toEncoded()).decode('ascii'),
             source_local=actual, source_is_local=url.isLocalFile(), expected_locator=locator,
             raw_equal=actual == str(locator), native_full_locator_equal=native_equal,
             same_physical_file=same_object, actual_material=material(actual),
             expected_material=material(locator), media_status=str(bar.player.mediaStatus()),
             playback_state=str(bar.player.playbackState()), error=str(bar.player.error()),
             error_string=bar.player.errorString(), current_path=bar.current_path,
             current_track=getattr(bar.current_track, 'track_id', None),
             queued_track=getattr(bar.queued_track, 'track_id', None),
             read_pending=getattr(bar, '_read_pending', None),
             pending_seek_generation=getattr(bar, '_pending_seek_generation', None),
             active_plan=plan_data(expected),
             verified_playback=plan_data(getattr(bar, '_playback_resolution', None)), **extra)
    except RuntimeError as exc:
        emit('snapshot-after-deletion', error=repr(exc))


class Spy(QObject):
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = weakref.ref(bar)

    @Slot(QUrl)
    def source(self, url):
        if (bar := self.bar()) is not None:
            snapshot(bar, 'sourceChanged', signal_value=url.toString())

    @Slot(QMediaPlayer.MediaStatus)
    def status(self, status):
        if (bar := self.bar()) is not None:
            snapshot(bar, 'mediaStatusChanged', signal_value=str(status))

    @Slot(QMediaPlayer.Error, str)
    def error(self, error, message):
        if (bar := self.bar()) is not None:
            snapshot(bar, 'errorOccurred', signal_value=str(error), signal_message=message)


def loaded_media_modules():
    if os.name != 'nt':
        return []
    from ctypes import wintypes
    process = ctypes.windll.kernel32.GetCurrentProcess()
    modules = (ctypes.c_void_p * 2048)()
    needed = wintypes.DWORD()
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
    if not psapi.EnumProcessModules(process, modules, ctypes.sizeof(modules), ctypes.byref(needed)):
        return ['EnumProcessModules failed: ' + str(ctypes.get_last_error())]
    paths = []
    for handle in modules[:needed.value // ctypes.sizeof(ctypes.c_void_p)]:
        name = ctypes.create_unicode_buffer(32768)
        if psapi.GetModuleFileNameExW(process, handle, name, len(name)):
            if any(token in name.value.lower() for token in ('media', 'ffmpeg', 'avcodec', 'avformat')):
                paths.append(name.value)
    return paths


def pytest_configure(config):
    import audio_library_organizer.ui.player as player
    import audio_library_organizer.jobs.managed_files as managed
    emit('environment', os=platform.platform(), qt=qVersion(), pyside=PySide6.__version__,
         requested_backend=os.environ.get('QT_MEDIA_BACKEND'))
    original_init = player.PlayerBar.__init__
    def observed_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        INSTANCES.append(weakref.ref(self))
        self._diagnostic_spy = Spy(self)
        self.player.sourceChanged.connect(self._diagnostic_spy.source)
        self.player.mediaStatusChanged.connect(self._diagnostic_spy.status)
        self.player.errorOccurred.connect(self._diagnostic_spy.error)
        emit('backend-modules', modules=loaded_media_modules())
    player.PlayerBar.__init__ = observed_init
    original_load = player.PlayerBar.load_track
    def observed_load(self, track, *args, **kwargs):
        emit('load_track-enter', player=id(self), track_id=track.track_id, source_locator=str(track.path))
        result = original_load(self, track, *args, **kwargs)
        snapshot(self, 'load_track-return')
        return result
    player.PlayerBar.load_track = observed_load
    for module, name in ((player, 'resolve_read_path'), (managed, 'resolve_read_path'),
                         (managed, 'recheck_read_path')):
        original = getattr(module, name)
        def observed(*args, _original=original, _name=name, **kwargs):
            result = _original(*args, **kwargs)
            emit(_name, result=plan_data(result))
            return result
        setattr(module, name, observed)


def pytest_runtest_setup(item):
    module = item.module
    if module.__name__ in PATCHED_MODULES or not hasattr(module, 'wait'):
        return
    PATCHED_MODULES.add(module.__name__)
    original = module.wait
    def observed_wait(*args, **kwargs):
        passed = False
        try:
            value = original(*args, **kwargs)
            passed = True
            return value
        finally:
            for ref in INSTANCES:
                if (bar := ref()) is not None:
                    snapshot(bar, 'bounded-wait-return', passed=passed, test=item.nodeid)
    module.wait = observed_wait


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    emit('pytest-result', nodeid=item.nodeid, phase=report.when, outcome=report.outcome)
