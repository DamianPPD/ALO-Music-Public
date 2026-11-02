"""Actual fresh-interpreter MainWindow reopening; synthetic path only."""
from pathlib import Path
import json,sys,os
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from audio_library_organizer.domain.settings import AppSettings,LibraryPaths
from audio_library_organizer.domain.preferences import AppPreferences
from audio_library_organizer.ui import main_window
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.safety import windows_file_identity as native
from test_output_session_ui_v0427 import pump,run_check,presentation

def main():
    root=Path(sys.argv[1]).resolve();track_id=sys.argv[2]
    allowed=Path(os.environ['ALO_62D_EVIDENCE']).resolve()/'synthetic'
    assert root.is_relative_to(allowed) and native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED is False
    app=QApplication([]);main_window.DashboardPage=DashboardPage
    store=QSettings(str(root/'restart-isolated.ini'),QSettings.Format.IniFormat)
    AppPreferences(language='en',theme='dark').save(store)
    window=main_window.MainWindow(AppSettings((),LibraryPaths(root)),store)
    try:
        window.show();app.processEvents();track=window.repository.get_track(track_id)
        assert not window._output_history and not window._output_session
        assert not presentation(window,track).confirmed
        assert not window.repository.get_file_state(track_id).evaluation.is_confirmed
        native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED=True
        run_check(window)
        h=window._output_history[track_id]
        assert not h.evaluation.is_confirmed and not window._output_session
        print(json.dumps({'pid':os.getpid(),'restart':'new interpreter / real MainWindow',
            'historical_P_restored':False,'initial_H_entries':0,'fresh_H_confirmed':False,
            'library_id':window.repository.library_id,'track_id':track_id,'status':'PASS'}))
    finally:
        native.WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED=False
        window.close();app.processEvents()
    return 0
if __name__=='__main__':sys.exit(main())
