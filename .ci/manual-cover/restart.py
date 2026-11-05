"""Open the persisted synthetic library in a new process and inspect column Plik."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import Event
from time import monotonic

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QThreadPool, Qt
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui import main_window
from audio_library_organizer.ui.dashboard_page import DashboardPage
from pytest_observe import database_checks

scenario = sys.argv[1]
evidence = Path(os.environ['ALO_EVIDENCE'])
before = json.loads((evidence / f'before-close-{scenario}.json').read_text(encoding='utf-8'))
assert before['pid'] != os.getpid()
count = {'full': 13, 'cancel': 3}[scenario]
paths = LibraryPaths(Path(before['library']))
main_window.DashboardPage = DashboardPage
app = QApplication([])
errors = []
sys.excepthook = lambda kind, value, tb: errors.append(str(value))
window = main_window.MainWindow(AppSettings((), paths),
                                QSettings(before['prefs'], QSettings.Format.IniFormat))
window.show()
app.processEvents()
window._check_library_clicked()
thread, worker = window._thread, window._worker
assert thread is not None and worker is not None
deadline = monotonic() + 60
idle = Event()
while window._thread is not None and monotonic() < deadline:
    app.processEvents()
    idle.wait(.005)
assert window._thread is None and window.last_reconciliation_result is not None
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
assert not isValid(thread) and not isValid(worker)
model = window.library.model
assert model.horizontalHeaderItem(10).text() == 'Plik'
cells = {model.item(i, 0).data(Qt.ItemDataRole.UserRole).track_id: model.item(i, 10).text()
         for i in range(model.rowCount())}
bindings = {row.track_id: row for row in window.repository.list_managed_bindings()}
assert len(cells) == 14 and sorted(cells) == before['track_ids']
assert bindings.keys() == before['outputs'].keys() and len(bindings) == count
assert before['missing_cover_uuid'] not in bindings
actual_paths = set(paths.root.rglob('*.mp3'))
assert len(actual_paths) == count
for track_id, binding in bindings.items():
    previous = before['outputs'][track_id]
    path = Path(binding.locator(paths.root))
    assert path in actual_paths and str(path) == previous['path']
    assert binding.binding_id == previous['binding_id']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == binding.expected_sha256 == previous['sha256']
    assert cells[track_id].startswith('W bibliotece')
assert all(cells[track_id].startswith('Tylko źródło') for track_id in cells.keys() - bindings.keys())
assert all('Niepotwierdzony' in value for value in cells.values())
checks = database_checks(window.repository.database_path)
window.close()
app.processEvents()
assert QThreadPool.globalInstance().waitForDone(5000)
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
assert not errors
summary = dict(pid=os.getpid(), previous_pid=before['pid'], state_counts=Counter(cells.values()),
               bindings=list(bindings), cells=cells, sqlite=checks, duplicate_outputs=0,
               callback_errors=errors, thread_and_worker_deleted=True, hashes_match=True)
data = json.dumps(summary, ensure_ascii=False, indent=2)
(evidence / f'after-restart-{scenario}.json').write_text(data, encoding='utf-8')
print(data)
