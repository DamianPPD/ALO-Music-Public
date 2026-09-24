import json
from audio_library_organizer.domain.preferences import AppPreferences, NameNormalizationRule


class Store:
    def __init__(self): self.data = {}
    def value(self, key, default=None): return self.data.get(key, default)
    def setValue(self, key, value): self.data[key] = value


def test_preferences_defaults_and_round_trip():
    store = Store()
    prefs = AppPreferences.from_store(store)
    assert prefs.language == 'pl'
    assert prefs.theme == 'dark'
    assert prefs.normalize_names is True
    assert any(rule.replacement == 'DJ' and rule.enabled for rule in prefs.name_rules)
    assert any(rule.replacement == 'Feat.' and rule.enabled for rule in prefs.name_rules)

    changed = AppPreferences(
        language='en', theme='light', normalize_names=False,
        name_rules=(NameNormalizationRule('dj', 'DeeJay', False),),
    )
    changed.save(store)
    restored = AppPreferences.from_store(store)
    assert restored == changed


def test_preferences_reject_unknown_language_and_theme_from_store():
    store = Store(); store.data['ui/language'] = 'xx'; store.data['ui/theme'] = 'neon'
    prefs = AppPreferences.from_store(store)
    assert prefs.language == 'pl'
    assert prefs.theme == 'dark'
