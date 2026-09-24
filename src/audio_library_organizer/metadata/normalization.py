from __future__ import annotations

import re
from collections.abc import Iterable

from audio_library_organizer.domain.preferences import NameNormalizationRule, default_name_rules


def _rule_pattern(find: str) -> re.Pattern[str] | None:
    token = (find or '').strip()
    if not token:
        return None
    escaped = re.escape(token.rstrip('.'))
    suffix = r'\.?' if token.casefold().rstrip('.') in {'feat', 'ft', 'vs'} else ''
    return re.compile(rf'(?<!\w){escaped}{suffix}(?!\w)', re.IGNORECASE)


def normalize_music_text(value: str | None, rules: Iterable[NameNormalizationRule] | None = None) -> str | None:
    if value is None:
        return None
    text = re.sub(r'\s+', ' ', str(value)).strip()
    if not text:
        return None
    for rule in tuple(rules or default_name_rules()):
        if not rule.enabled or not rule.find.strip():
            continue
        pattern = _rule_pattern(rule.find)
        if pattern is not None:
            text = pattern.sub(rule.replacement, text)
    text = re.sub(r'\.{2,}', '.', text)
    return text


def is_valid_year_text(value: str | None) -> bool:
    text = '' if value is None else str(value).strip()
    return text == '' or (len(text) == 4 and text.isdigit())
