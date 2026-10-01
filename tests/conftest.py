"""Release Qt windows between tests while retaining the shared QApplication."""

import gc
import sys

import pytest


@pytest.fixture(autouse=True)
def release_test_windows():
    yield
    widgets = sys.modules.get('PySide6.QtWidgets')
    if widgets is None or widgets.QApplication.instance() is None:
        return
    from PySide6.QtCore import QCoreApplication, QEvent

    # close() only hides Qt windows. Their Python signal cycles keep them alive,
    # so later application stylesheet changes revisit every previous editor.
    # Delete roots directly: teardown must never open an unsaved-changes dialog.
    deleted = False
    for window in widgets.QApplication.topLevelWidgets():
        if window.parentWidget() is None:
            window.hide()
            window.deleteLater()
            deleted = True
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    if deleted:
        gc.collect()
