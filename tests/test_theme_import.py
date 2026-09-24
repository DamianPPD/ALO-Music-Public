import importlib


def test_theme_imports_and_contains_new_player_and_workflow_rules():
    theme = importlib.import_module('audio_library_organizer.ui.theme')
    assert 'QFrame#WorkflowStep' in theme.APP_STYLE
    assert 'QPushButton#PlayButton' in theme.APP_STYLE
    assert 'QSlider#SeekSlider' in theme.APP_STYLE
