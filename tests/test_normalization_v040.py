from audio_library_organizer.domain.preferences import default_name_rules, NameNormalizationRule
from audio_library_organizer.metadata.normalization import normalize_music_text, is_valid_year_text


def test_default_music_rules_normalize_common_words_and_abbreviations():
    rules = default_name_rules()
    assert normalize_music_text('dj alpha feat beta (extended club mix)', rules) == 'DJ alpha Feat. beta (Extended Club Mix)'
    assert normalize_music_text('original remix radio edit', rules) == 'Original Remix Radio Edit'


def test_disabled_rule_is_not_applied_and_custom_rule_is_editable():
    rules = (NameNormalizationRule('dj', 'DJ', False), NameNormalizationRule('club', 'CLUB!', True))
    assert normalize_music_text('dj test club mix', rules) == 'dj test CLUB! mix'


def test_year_accepts_empty_or_exactly_four_digits_only():
    assert is_valid_year_text('')
    assert is_valid_year_text('1998')
    assert is_valid_year_text('2026')
    assert not is_valid_year_text('98')
    assert not is_valid_year_text('19985')
    assert not is_valid_year_text('20a4')
    assert not is_valid_year_text('abcd')
