"""Exercise real WaveformJob autoDelete in a fresh GUI process per case."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Lock, Thread, get_native_id
import traceback
import wave
import weakref

import pytest


CASES = ('success', 'managed_success', 'cancel', 'error', 'receiver_deleted',
         'held_reference', 'quit_active', 'quit_late')


def _run_case(case, output):
    from PySide6.QtCore import QObject, QMetaObject, QThread, QThreadPool, Qt, Slot
    from PySide6.QtWidgets import QApplication
    import PySide6
    import shiboken6
    from audio_library_organizer.jobs.managed_files import ReadPurpose, local_read_plan
    from audio_library_organizer.ui import waveform

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source = Path(waveform.__file__)
    os.environ['ALO_CRASH_DEBUG'] = '1'
    os.environ['ALO_CRASH_DEBUG_LOG'] = str(output / 'crash-debug.log')
    waveform.crash_debug.initialize()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    gui_tid = get_native_id()
    gui_affinity = shiboken6.getCppPointer(app.thread())[0]
    entered, release, cancel = Event(), Event(), Event()
    events, errors, ready = [], [], []
    events_lock = Lock()
    closing = case.startswith(('quit_', 'global_'))
    global_pool = case.startswith('global_')
    helper = os.environ.get('ALO_LIFETIME_NATIVE_HELPER')
    native = ctypes.CDLL(helper) if helper else None
    if native:
        native.dump_destruction.argtypes = [ctypes.c_char_p, ctypes.c_ulonglong,
                                          ctypes.c_ulonglong]

    def mark(event, **fields):
        row = dict(event=event, tid=get_native_id(), **fields)
        with events_lock:
            row['sequence'] = len(events)
            events.append(row)
            with (output / 'events.jsonl').open('a') as stream:
                stream.write(json.dumps(row) + '\n')
        return row

    class Controller(QObject):
        @Slot()
        def progress(self):
            if closing:
                return
            names = [row['event'] for row in events]
            delivery_complete = (len(ready) == 1 if case in
                ('success', 'managed_success', 'held_reference') else not ready)
            if ('signals.destroyed' in names and 'job.wrapper.finalized' in names
                    and delivery_complete):
                app.quit()

        @Slot()
        def begin_quit(self):
            mark('app.quit.request')
            app.quit()

    controller = Controller(app)

    def progress():
        if not closing:
            QMetaObject.invokeMethod(controller, 'progress', Qt.ConnectionType.QueuedConnection)

    class Receiver(QObject):
        @Slot(int, object)
        def receive(self, generation, payload):
            values = payload.value if case == 'managed_success' else payload
            verified = payload.resolution.is_verified if case == 'managed_success' else None
            row = mark('ready.delivered', generation=generation, values=list(values),
                       verified=verified)
            ready.append(row)
            controller.progress()

    receiver = Receiver(app)
    path = output / 'levels.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\x00\x20' * 960)

    original_read = waveform.read_waveform
    original_hook = sys.excepthook
    history_names = ('last_exc', 'last_traceback', 'last_value', 'last_type')
    previous_history = {name: getattr(sys, name) for name in history_names if hasattr(sys, name)}
    run_code = waveform.WaveformJob.run.__code__

    def profile(frame, event, arg):
        if frame.f_code is run_code and event == 'return':
            mark('job.run.return', thread_object=shiboken6.getCppPointer(QThread.currentThread())[0])
            sys.setprofile(None)

    def gated_read(*args, **kwargs):
        # Only synchronize the real I/O boundary. Neither run() nor signals
        # teardown is replaced, and no field/reference is cleared in the test.
        sys.setprofile(profile)
        mark('read.enter')
        entered.set()
        assert release.wait(5), 'GUI did not release the bounded I/O barrier'
        mark('read.released', cancelled=cancel.is_set())
        if case == 'error':
            raise ValueError('injected WaveformJob reader failure')
        values = original_read(*args, **kwargs)
        mark('read.return', count=len(values))
        return values

    def exception_hook(kind, error, tb):
        errors.append(dict(type=kind.__name__, message=str(error),
                           traceback=''.join(traceback.format_exception(kind, error, tb))))
        mark('job.exception', type=kind.__name__, message=str(error))
        progress()

    waveform.read_waveform = gated_read
    sys.excepthook = exception_hook
    pool = QThreadPool.globalInstance() if global_pool else QThreadPool()
    pool.setMaxThreadCount(1)
    plan = local_read_plan(path, ReadPurpose.WAVEFORM, generation=37) if case == 'managed_success' else None
    job = waveform.WaveformJob(path, 37, cancel, job_id='lifecycle-' + case, read_plan=plan)
    assert type(job) is waveform.WaveformJob and job.autoDelete()
    job_pointer = shiboken6.getCppPointer(job)[0]
    signal_pointer = shiboken6.getCppPointer(job.signals)[0]
    signal_affinity = shiboken6.getCppPointer(job.signals.thread())[0]
    mark('created', job_pointer=job_pointer, signal_pointer=signal_pointer,
         affinity=signal_affinity, auto_delete=job.autoDelete(),
         signals_owned_by_python=shiboken6.ownedByPython(job.signals))
    job_python_id = id(job)

    def native_stack(name, pointer):
        if native:
            native.dump_destruction(os.fsencode(output / (name + '-native-stack.txt')),
                                    pointer, signal_affinity)

    def signals_destroyed(*unused):
        mark('signals.destroyed', cpp_object=signal_pointer, affinity=signal_affinity)
        native_stack('signals-destroyed', signal_pointer)
        progress()

    def job_finalized(unused):
        mark('job.wrapper.finalized', cpp_object=job_pointer)
        native_stack('job-wrapper-finalized', job_pointer)
        progress()

    def signals_finalized(unused):
        mark('signals.wrapper.finalized', cpp_object=signal_pointer)

    # These callbacks retain scalar identities only, never job/signals wrappers.
    references = [weakref.ref(job, job_finalized),
                  weakref.ref(job.signals, signals_finalized)]
    job.signals.destroyed.connect(signals_destroyed, Qt.ConnectionType.DirectConnection)
    job.signals.ready.connect(receiver.receive, Qt.ConnectionType.QueuedConnection)
    job.start(pool)
    assert entered.wait(5), 'Real WaveformJob did not enter its reader'
    if case != 'held_reference':
        mark('job.gui_reference.release.enter')
        del job
        mark('job.gui_reference.release.done')

    before_loop = []
    if closing:
        def on_quit():
            mark('app.aboutToQuit', active_threads=pool.activeThreadCount())
            if case != 'global_active_success':
                cancel.set()
            if case == 'quit_active':
                release.set()
                assert pool.waitForDone(5000), 'Real runnable did not finish during quit'
                mark('pool.done.during_quit')
        app.aboutToQuit.connect(on_quit)
        QMetaObject.invokeMethod(controller, 'begin_quit', Qt.ConnectionType.QueuedConnection)
    else:
        if case == 'cancel':
            cancel.set()
        if case == 'receiver_deleted':
            shiboken6.delete(receiver)
            mark('receiver.destroyed.before_emit')
        release.set()
        assert pool.waitForDone(5000), 'Real runnable did not autoDelete within limit'
        mark('pool.done')
        if case == 'error':
            def release_interpreter_exception_history():
                # PyErr_Print stores the escaped QRunnable exception in sys.
                # Its traceback retains run.self even after C++ autoDelete.
                # Record the causal reference, then release only that history;
                # keep the serialized exception and every original assertion.
                history = getattr(sys, 'last_exc', None)
                tb = getattr(history, '__traceback__', None)
                frames = []
                while tb is not None:
                    frames.append(dict(function=tb.tb_frame.f_code.co_name,
                        retains_job=id(tb.tb_frame.f_locals.get('self')) == job_python_id))
                    tb = tb.tb_next
                mark('error.history.retention', exception_type=type(history).__name__,
                     frames=frames, wrapper_alive=references[0]() is not None,
                     cpp_valid=shiboken6.isValid(references[0]()))
                assert isinstance(history, ValueError)
                assert any(frame['retains_job'] for frame in frames)
                assert references[0]() is not None and not shiboken6.isValid(references[0]())
                for name in history_names:
                    if hasattr(sys, name):
                        delattr(sys, name)
            release_interpreter_exception_history()
            mark('error.history.released', wrapper_alive=references[0]() is not None)
            assert references[0]() is None, 'Exception-history release did not release the wrapper'
        if case == 'held_reference':
            mark('job.cpp_invalid_while_python_reference_held', valid=shiboken6.isValid(job))
            del job
            mark('job.gui_reference.release.done')
        before_loop = list(events)
        progress()

    mark('app.exec.enter')
    exec_code = app.exec()
    mark('app.exec.return', exit_code=exec_code, active_threads=pool.activeThreadCount())
    if case == 'quit_late':
        release.set()
        assert pool.waitForDone(5000), 'Runnable did not finish after GUI loop stopped'
        mark('pool.done.after_event_loop')
    waveform.read_waveform = original_read
    sys.excepthook = original_hook
    live_notifiers = len(app.findChildren(waveform.WaveformSignals))
    mark('app.live_notifiers.before_native_delete', count=live_notifiers)
    assert live_notifiers == int(case == 'quit_late' or global_pool)
    app.destroyed.connect(lambda: mark('app.destroyed'), Qt.ConnectionType.DirectConnection)
    release_thread = None
    if global_pool:
        native_delete_entered = Event()
        def release_during_native_delete():
            assert native_delete_entered.wait(5)
            mark('read.release.from_background')
            release.set()
        release_thread = Thread(target=release_during_native_delete)
        release_thread.start()
        assert pool.activeThreadCount() == 1
        mark('app.native_delete.enter', active_threads=pool.activeThreadCount())
        native_delete_entered.set()
    else:
        mark('app.native_delete.enter')
    shiboken6.delete(app)
    mark('app.native_delete.done')
    if release_thread is not None:
        release_thread.join(5)
        assert not release_thread.is_alive()
    for name, value in previous_history.items():
        setattr(sys, name, value)
    destroyed = [row for row in events if row['event'] == 'signals.destroyed']
    finalized = [row for row in events if row['event'] == 'job.wrapper.finalized']
    record = dict(case=case, python=sys.version, Qt=PySide6.__version__,
                  source_file=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  actual_WaveformJob=True, replaced_run=False, manually_released_signals=False,
                  native_autoDelete=True, gui_tid=gui_tid, gui_affinity=gui_affinity,
                  events=events, events_before_loop=before_loop, errors=errors, ready=ready,
                  job_wrapper_observed_finalized=len(finalized) == 1,
                  signals_observed_destroyed=len(destroyed) == 1,
                  signals_destroyed_in_affinity=len(destroyed) == 1 and destroyed[0]['tid'] == gui_tid)
    (output / 'observations.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: value for key, value in record.items()
                      if key not in ('events', 'events_before_loop', 'ready', 'errors')}, indent=2), flush=True)
    assert exec_code == 0
    assert len(finalized) == 1, 'Real QRunnable wrapper teardown was not observed'
    assert len(destroyed) == 1, 'WaveformSignals native destruction was not observed exactly once'
    assert signal_affinity == gui_affinity
    assert destroyed[0]['tid'] == gui_tid, 'WaveformSignals destroyed outside its QObject thread affinity'
    expected_ready = case in ('success', 'managed_success', 'held_reference')
    assert len(ready) == int(expected_ready), 'Queued ready delivery count was wrong'
    if expected_ready:
        assert ready[0]['tid'] == gui_tid and ready[0]['generation'] == 37
        assert len(ready[0]['values']) == 240 and set(ready[0]['values']) == {.25}
    if case == 'managed_success':
        assert ready[0]['verified'] is True
    assert len(errors) == int(case == 'error'), errors
    if errors:
        assert errors[0]['type'] == 'ValueError' and errors[0]['message'] == 'injected WaveformJob reader failure'
    assert all(reference() is None for reference in references), 'Python wrappers survived teardown'
    if global_pool:
        sequence = {row['event']: row['sequence'] for row in events}
        assert (sequence['app.native_delete.enter'] < sequence['job.run.return']
                < sequence['job.wrapper.finalized'] < sequence['app.destroyed']
                < sequence['signals.destroyed'] < sequence['app.native_delete.done'])


@pytest.mark.parametrize('case', CASES)
def test_real_waveform_job_destroys_signals_in_affinity(tmp_path, case):
    _assert_case(tmp_path, case)


@pytest.mark.parametrize('case', ('global_active_success', 'global_active_cancel'))
def test_application_destruction_drains_actual_global_waveform_job(tmp_path, case):
    _assert_case(tmp_path, case)


def _run_batch(output):
    """Prove completed notifiers do not accumulate in a still-live GUI."""
    from PySide6.QtCore import QObject, QMetaObject, QThreadPool, Qt, Slot
    from PySide6.QtWidgets import QApplication
    import shiboken6
    from audio_library_organizer.ui import waveform

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    gui_tid = get_native_id()
    count = 32
    delivered, destroyed, references = [], [], []
    original_read = waveform.read_waveform
    waveform.read_waveform = lambda *args, **kwargs: [.25]
    pool = QThreadPool.globalInstance()
    pool.setMaxThreadCount(4)

    class Receiver(QObject):
        @Slot(int, object)
        def receive(self, generation, values):
            delivered.append((generation, list(values), get_native_id()))
            self.progress()

        @Slot()
        def progress(self):
            if len(delivered) == count and len(destroyed) == count:
                app.quit()

    receiver = Receiver(app)
    def observed_destruction(pointer):
        destroyed.append((pointer, get_native_id()))
        QMetaObject.invokeMethod(receiver, 'progress', Qt.ConnectionType.QueuedConnection)

    for generation in range(count):
        job = waveform.WaveformJob(output / 'unused.wav', generation, Event())
        pointer = shiboken6.getCppPointer(job.signals)[0]
        references.extend((weakref.ref(job), weakref.ref(job.signals)))
        job.signals.ready.connect(receiver.receive, Qt.ConnectionType.QueuedConnection)
        job.signals.destroyed.connect(lambda *unused, pointer=pointer:
            observed_destruction(pointer), Qt.ConnectionType.DirectConnection)
        job.start(pool)
        del job
    assert app.exec() == 0
    assert pool.waitForDone(5000)
    waveform.read_waveform = original_read
    live = len(app.findChildren(waveform.WaveformSignals))
    alive_with_test_pool_reference = sum(reference() is not None for reference in references)
    def retaining_references():
        # Read-only diagnosis of a failed assertion; never collect or clear
        # frames/references to make the lifecycle assertion pass.
        import gc
        details = []
        for index, reference in enumerate(references):
            wrapper = reference()
            if wrapper is None:
                continue
            owners = []
            for owner in gc.get_referrers(wrapper):
                data = {'type': type(owner).__name__}
                if isinstance(owner, dict):
                    data['keys_pointing_to_wrapper'] = [str(key) for key, value in owner.items() if value is wrapper]
                elif isinstance(owner, (tuple, list)):
                    data['positions'] = [i for i, value in enumerate(owner) if value is wrapper]
                owners.append(data)
            details.append(dict(index=index, kind='job' if index % 2 == 0 else 'signals',
                type=type(wrapper).__name__, cpp_valid=shiboken6.isValid(wrapper), owners=owners))
        return details
    before_pool_release = retaining_references() if alive_with_test_pool_reference else []
    pool_pointer = shiboken6.getCppPointer(pool)[0]
    pool_owned_by_python = shiboken6.ownedByPython(pool)
    pool_reference = weakref.ref(pool)
    # Match PlayerBar's ephemeral globalInstance().start(job) ownership. A
    # retained test pool proxy itself retains some already-autoDeleted jobs.
    # Release only that test reference; the native global pool stays alive.
    del pool
    same_native_pool = shiboken6.getCppPointer(QThreadPool.globalInstance())[0] == pool_pointer
    alive_wrappers = sum(reference() is not None for reference in references)
    before_app_delete = retaining_references() if alive_wrappers else []
    shiboken6.delete(app)
    after_app_delete = retaining_references() if alive_wrappers else []
    (output / 'observations.json').write_text(json.dumps(dict(
        actual_WaveformJob=True, real_autoDelete=True, reader_stubbed_for_lifetime_only=True,
        jobs=count, gui_tid=gui_tid, delivered=delivered, destroyed=destroyed,
        live_notifiers_before_app_destruction=live, alive_wrappers=alive_wrappers,
        alive_with_test_pool_reference=alive_with_test_pool_reference,
        retaining_owners_before_pool_release=before_pool_release,
        same_native_global_pool_after_proxy_release=same_native_pool,
        test_pool_proxy_released=pool_reference() is None,
        pool_owned_by_python=pool_owned_by_python,
        retaining_owners_before_app_delete=before_app_delete,
        retaining_owners_after_app_delete=after_app_delete), indent=2) + '\n')
    assert len(delivered) == count and {item[0] for item in delivered} == set(range(count))
    assert all(item[1] == [.25] and item[2] == gui_tid for item in delivered)
    assert len(destroyed) == count and len({item[0] for item in destroyed}) == count
    assert all(item[1] == gui_tid for item in destroyed)
    assert live == 0 and alive_wrappers == 0
    assert not pool_owned_by_python and pool_reference() is None and same_native_pool


def test_completed_waveform_jobs_leave_no_application_owned_notifiers(tmp_path):
    _assert_case(tmp_path, 'batch')


def _assert_case(tmp_path, case):
    output = tmp_path / case
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), case, str(output)],
                            env=env, capture_output=True, text=True, timeout=15)
    (tmp_path / (case + '.stdout.log')).write_text(result.stdout)
    (tmp_path / (case + '.stderr.log')).write_text(result.stderr)
    assert result.returncode == 0, result.stdout + '\n' + result.stderr


if __name__ == '__main__':
    if sys.argv[1] == 'batch':
        _run_batch(sys.argv[2])
    else:
        _run_case(sys.argv[1], sys.argv[2])
