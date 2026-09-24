from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_four_numbered_steps_are_grouped_before_auxiliary_add_files_action():
    assert 'WorkflowToolbarGroup' in MAIN
    assert 'WorkflowToolbarSeparator' in MAIN
    workflow_line = next(line for line in MAIN.splitlines() if 'workflow.addWidget(self.scan_btn)' in line)
    assert workflow_line.index('self.scan_btn') < workflow_line.index('self.identify_btn') < workflow_line.index('self.review_btn') < workflow_line.index('self.export_btn')
    assert MAIN.index("action.addWidget(workflow_group)") < MAIN.index("action.addWidget(workflow_separator)") < MAIN.index("action.addWidget(self.new_files_btn)")


def test_workflow_actions_have_distinct_icons_and_clear_export_name():
    assert "QPushButton('1. Skanuj foldery')" in MAIN
    assert "QPushButton('2. Rozpoznaj utwory online')" in MAIN
    assert "QPushButton('3. Sprawdź w Bibliotece')" in MAIN
    assert "QPushButton('4. Utwórz pliki wynikowe')" in MAIN
    assert "(self.scan_btn, 'scan')" in MAIN
    assert "(self.identify_btn, 'search')" in MAIN
    assert "(self.review_btn, 'review')" in MAIN
    assert "(self.export_btn, 'export')" in MAIN
    assert 'Utwórz pliki wynikowe' in MAIN
    assert 'QFrame#WorkflowToolbarSeparator' in THEME
