from pathlib import Path

from audio_library_organizer.ui.i18n import translate_static_text

ROOT = Path(__file__).resolve().parents[1]
I18N = (ROOT / 'src/audio_library_organizer/ui/i18n.py').read_text(encoding='utf-8')


def test_translation_catalog_covers_library_title_tooltip_and_placeholder():
    assert translate_static_text('Biblioteki', 'en') == 'Libraries'
    assert translate_static_text('Kliknij, aby zarządzać bibliotekami', 'en') == 'Click to manage libraries'
    assert translate_static_text('np. 2009', 'en') == 'e.g. 2009'
    assert translate_static_text('Znajdź', 'en') == 'Find'
    assert translate_static_text('Zamień na', 'en') == 'Replace with'


def test_language_applier_handles_titles_tooltips_placeholders_and_table_headers():
    assert 'windowTitle' in I18N
    assert 'toolTip' in I18N
    assert 'placeholderText' in I18N
    assert 'horizontalHeaderItem' in I18N


def test_translation_handles_dynamic_multiline_library_rows():
    text = 'Biblioteka główna\nD:\\Muzyka\n● AKTYWNA'
    result = translate_static_text(text, 'en')
    assert result == 'Main Library\nD:\\Muzyka\n● ACTIVE'


def test_language_applier_translates_list_widget_items_too():
    assert 'QListWidget' in I18N
    assert 'widget.item(index)' in I18N


def test_i18n_exposes_runtime_text_helper_for_dialogs():
    assert 'def language_for(' in I18N
    assert 'def ui_text(' in I18N


def test_first_run_can_use_saved_language_too():
    main_source = (ROOT / 'src/audio_library_organizer/main.py').read_text(encoding='utf-8')
    assert 'apply_static_language(dialog, prefs.language)' in main_source
