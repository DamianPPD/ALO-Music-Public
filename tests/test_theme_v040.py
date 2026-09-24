from audio_library_organizer.ui.theme import style_for_theme
from audio_library_organizer.ui.i18n import tr


def test_theme_resolver_supports_dark_light_and_system():
    dark = style_for_theme('dark')
    light = style_for_theme('light')
    assert '#10141a' in dark
    assert '#f4f6f8' in light
    assert style_for_theme('system', system_is_dark=True) == dark
    assert style_for_theme('system', system_is_dark=False) == light


def test_i18n_catalog_has_core_navigation_and_actions():
    assert tr('nav.library', 'pl') == 'Biblioteka'
    assert tr('nav.library', 'en') == 'Library'
    assert tr('action.identify_online', 'pl') == 'Rozpoznaj utwory online'
    assert tr('action.identify_online', 'en') == 'Identify tracks online'
    assert tr('settings.language', 'en') == 'Language'


def test_i18n_translates_new_settings_and_library_labels():
    from audio_library_organizer.ui.i18n import translate_static_text
    assert translate_static_text('Język interfejsu', 'en') == 'Interface language'
    assert translate_static_text('Normalizacja nazw', 'en') == 'Name normalization'
    assert translate_static_text('Kopia bezpieczeństwa ALO', 'en') == 'ALO backup'
    assert translate_static_text('Biblioteki…', 'en') == 'Libraries…'
