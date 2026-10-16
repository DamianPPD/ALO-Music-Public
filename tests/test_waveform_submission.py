"""Bounded real-pool checks of exactly-once submission and start exceptions."""
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, get_native_id
import weakref
import pytest


def child(case, output):
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, Qt
    from PySide6.QtWidgets import QApplication
    import shiboken6
    from audio_library_organizer.ui import waveform
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    app = QApplication([]); gui = get_native_id()
    entered, destroyed = [], []
    waveform.read_waveform = lambda *a, **kw: entered.append(get_native_id()) or [.25]
    class Pool(QThreadPool):
        def start(self, job):
            if case == 'before_enqueue': raise ValueError('before enqueue')
            super().start(job)
            if case == 'after_enqueue': raise ValueError('after enqueue')
    pool = Pool(); job = waveform.WaveformJob(output/'unused.wav', 1, Event())
    refs = [weakref.ref(job), weakref.ref(job.signals)]
    job.signals.destroyed.connect(lambda *a: destroyed.append(get_native_id()), Qt.DirectConnection)
    if case == 'twice': job.start(pool)
    else:
        with pytest.raises(ValueError, match='enqueue'): job.start(pool)
    with pytest.raises(RuntimeError, match='only be submitted once'): job.start(pool)
    assert pool.waitForDone(5000), 'Submission exception left a worker blocked'
    native_valid = shiboken6.isValid(job)
    assert native_valid == (case == 'before_enqueue')
    del job
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    before_app = len(app.findChildren(waveform.WaveformSignals))
    # No worker owns a never-enqueued notifier; its existing GUI parent
    # releases it at app teardown. Never delete on an ambiguous start error.
    assert before_app == int(case == 'before_enqueue')
    shiboken6.delete(pool); shiboken6.delete(app)
    retained = sum(r() is not None for r in refs)
    (output/'observations.json').write_text(json.dumps(dict(case=case, native_valid_after_pool=native_valid,
        calls=len(entered), destroyed=destroyed, gui_tid=gui, retained=retained,
        live_notifiers_before_app=before_app), indent=2)+'\n')
    assert len(entered) == int(case != 'before_enqueue')
    assert all(tid != gui for tid in entered)
    assert destroyed == [gui] and retained == 0


@pytest.mark.parametrize('case', ('twice', 'before_enqueue', 'after_enqueue'))
def test_submission_is_once_and_unblocks_on_exception(tmp_path, case):
    result = subprocess.run([sys.executable, '-X', 'faulthandler', __file__, case, str(tmp_path/case)],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), capture_output=True, timeout=10)
    (tmp_path/'stdout.log').write_bytes(result.stdout); (tmp_path/'stderr.log').write_bytes(result.stderr)
    assert result.returncode == 0, result.stderr.decode()


if __name__ == '__main__': child(*sys.argv[1:])
