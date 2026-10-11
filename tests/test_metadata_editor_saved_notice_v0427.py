"""Exercise saved-notice deadlines through real Qt events, without wall-clock waits."""
import gc
from pathlib import Path
import sys
import weakref

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QTimerEvent
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog


class _NoticeClock:
    """Control only the 2200 ms notice deadline; Qt still dispatches every callback."""

    def __init__(self, app, monkeypatch):
        self.app = app
        self.now = 0
        self.legacy = []
        self.timers = {}
        self.requested_intervals = []
        self.single_shot = QTimer.singleShot
        native_start = QTimer.start

        def single_shot(milliseconds, *args):
            if milliseconds == 2200 and len(args) == 1:
                self.requested_intervals.append(milliseconds)
                self.legacy.append((self.now + milliseconds, args[0]))
            else:
                self.single_shot(milliseconds, *args)

        def start(timer, *args):
            if args == (2200,):
                self.requested_intervals.append(2200)
                self.timers[id(timer)] = (weakref.ref(timer), self.now + 2200)
                # Keep a real active timer ID while virtual time controls its event.
                native_start(timer, 2_147_483_647)
            else:
                native_start(timer, *args)

        monkeypatch.setattr(QTimer, 'singleShot', single_shot)
        monkeypatch.setattr(QTimer, 'start', start)

    def advance(self, milliseconds, *, dispatch=True):
        self.now += milliseconds
        due = [entry for entry in self.legacy if entry[0] <= self.now]
        self.legacy = [entry for entry in self.legacy if entry[0] > self.now]
        for _, callback in due:
            self.single_shot(0, callback)
        for key, (reference, deadline) in list(self.timers.items()):
            if deadline > self.now:
                continue
            del self.timers[key]
            timer = reference()
            if timer is not None and isValid(timer) and timer.isActive():
                QCoreApplication.postEvent(timer, QTimerEvent(timer.timerId()))
        if dispatch:
            self.flush()

    def flush(self):
        dispatched = []
        self.single_shot(0, lambda: dispatched.append(True))
        self.app.processEvents()
        self.app.processEvents()
        assert dispatched == [True], 'Qt must actually dispatch the pending event queue'


@pytest.fixture
def notice_environment(monkeypatch):
    app = QApplication.instance() or QApplication([])
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *error: errors.append(error))
    clock = _NoticeClock(app, monkeypatch)
    editors = []

    def create(name='first'):
        editor = MetadataEditorDialog(TrackRecord(Path(f'/synthetic/{name}.mp3'), year='1999'))
        editors.append(weakref.ref(editor))
        editor.show()
        clock.flush()
        assert editor.saved_notice.parentWidget() is editor
        return editor

    yield create, clock, errors
    for reference in editors:
        editor = reference()
        if editor is not None and isValid(editor):
            editor.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # Drain even failing legacy cases before restoring the exception hook.
    clock.advance(10_000)
    gc.collect()


def _destroy(editor, owner):
    target = editor if owner == 'editor' else editor.saved_notice
    if owner == 'editor':
        editor._force_closing = True
        editor.close()
    target.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(target)
    assert not isValid(editor.saved_notice)


@pytest.mark.parametrize('owner', ['label', 'editor'])
@pytest.mark.parametrize('already_queued', [False, True])
def test_saved_notice_destruction_cancels_pending_qt_callback(notice_environment, owner, already_queued):
    create, clock, errors = notice_environment
    editor = create()
    assert editor._request_save()
    assert editor.saved_notice.isVisible()
    if already_queued:
        clock.advance(2200, dispatch=False)
    _destroy(editor, owner)
    if already_queued:
        clock.flush()
    else:
        clock.advance(2200)
    assert not errors


def test_saved_notice_hides_after_the_original_deadline_without_visual_changes(notice_environment):
    create, clock, errors = notice_environment
    editor = create()
    label = editor.saved_notice
    appearance = (label.text(), label.objectName(), label.styleSheet(), label.font(), label.palette())
    assert label.text() == 'Zapisano' and label.objectName() == 'SavedNotice'
    assert label.isHidden()
    assert editor._request_save()
    clock.advance(2199)
    assert label.isVisible()
    clock.advance(1)
    assert label.isHidden()
    assert clock.requested_intervals == [2200]
    assert appearance == (label.text(), label.objectName(), label.styleSheet(), label.font(), label.palette())
    assert not errors


def test_rapid_saves_restart_one_notice_deadline(notice_environment):
    create, clock, errors = notice_environment
    editor = create()
    assert editor._request_save()
    clock.advance(1000)
    assert editor._request_save()
    clock.advance(1000)
    assert editor._request_save()
    clock.advance(1200)  # Both earlier deadlines have now elapsed.
    assert editor.saved_notice.isVisible()
    clock.advance(999)
    assert editor.saved_notice.isVisible()
    clock.advance(1)
    assert editor.saved_notice.isHidden()
    clock.advance(2200)
    assert editor.saved_notice.isHidden()
    assert clock.requested_intervals == [2200, 2200, 2200]
    assert not clock.legacy and not clock.timers
    assert not errors


def test_closed_editor_does_not_affect_a_reopened_editor(notice_environment):
    create, clock, errors = notice_environment
    old = create('old')
    assert old._request_save()
    clock.advance(1000)
    _destroy(old, 'editor')
    current = create('new')
    assert current._request_save()
    clock.advance(1200)  # Old deadline, while the new notice is still current.
    assert current.isVisible() and current.saved_notice.isVisible()
    assert not errors
    clock.advance(1000)
    assert current.isVisible() and current.saved_notice.isHidden()
    assert not errors


def test_pending_notice_does_not_keep_a_destroyed_editor_alive(notice_environment):
    create, clock, errors = notice_environment
    editor = create()
    assert editor._request_save()
    reference = weakref.ref(editor)
    _destroy(editor, 'editor')
    del editor
    gc.collect()
    assert reference() is None
    clock.advance(2200)
    assert not errors
