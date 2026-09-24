from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(frozen=True, slots=True)
class NameNormalizationRule:
    find: str
    replacement: str
    enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        return {'find': self.find, 'replacement': self.replacement, 'enabled': self.enabled}

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> 'NameNormalizationRule':
        return cls(
            find=str(value.get('find', '') or ''),
            replacement=str(value.get('replacement', '') or ''),
            enabled=bool(value.get('enabled', True)),
        )


def default_name_rules() -> tuple[NameNormalizationRule, ...]:
    return tuple(NameNormalizationRule(find, replacement) for find, replacement in (
        ('dj', 'DJ'),
        ('club', 'Club'),
        ('mix', 'Mix'),
        ('remix', 'Remix'),
        ('extended', 'Extended'),
        ('radio', 'Radio'),
        ('edit', 'Edit'),
        ('original', 'Original'),
        ('version', 'Version'),
        ('instrumental', 'Instrumental'),
        ('vocal', 'Vocal'),
        ('dub', 'Dub'),
        ('feat', 'Feat.'),
        ('ft', 'Feat.'),
        ('vs', 'Vs.'),
    ))


@dataclass(frozen=True, slots=True)
class AppPreferences:
    language: str = 'pl'
    theme: str = 'dark'
    normalize_names: bool = True
    name_rules: tuple[NameNormalizationRule, ...] = ()

    def __post_init__(self) -> None:
        language = self.language if self.language in {'pl', 'en'} else 'pl'
        theme = 'dark'
        rules = tuple(self.name_rules) if self.name_rules else default_name_rules()
        object.__setattr__(self, 'language', language)
        object.__setattr__(self, 'theme', theme)
        object.__setattr__(self, 'name_rules', rules)

    @classmethod
    def from_store(cls, store) -> 'AppPreferences':
        language = str(store.value('ui/language', 'pl') or 'pl')
        theme = 'dark'
        raw_enabled = store.value('ui/normalize_names', True)
        if isinstance(raw_enabled, str):
            raw_enabled = raw_enabled.casefold() in {'1', 'true', 'yes', 'tak', 'on'}
        raw_rules = store.value('ui/name_normalization_rules', '')
        rules: tuple[NameNormalizationRule, ...]
        try:
            payload = json.loads(raw_rules) if isinstance(raw_rules, str) and raw_rules else raw_rules
            parsed = tuple(NameNormalizationRule.from_dict(item) for item in (payload or []) if isinstance(item, dict))
            rules = parsed or default_name_rules()
        except Exception:
            rules = default_name_rules()
        return cls(language=language, theme=theme, normalize_names=bool(raw_enabled), name_rules=rules)

    def save(self, store) -> None:
        store.setValue('ui/language', self.language)
        store.setValue('ui/theme', self.theme)
        store.setValue('ui/normalize_names', self.normalize_names)
        store.setValue('ui/name_normalization_rules', json.dumps([rule.to_dict() for rule in self.name_rules], ensure_ascii=False))


def language_selection_done(store) -> bool:
    value = store.value('ui/language_selected', False)
    if isinstance(value, str):
        return value.casefold() in {'1', 'true', 'yes', 'tak', 'on'}
    return bool(value)


def save_language_selection(store, language: str) -> str:
    language = language if language in {'pl', 'en'} else 'pl'
    current = AppPreferences.from_store(store)
    AppPreferences(
        language=language,
        theme='dark',
        normalize_names=current.normalize_names,
        name_rules=current.name_rules,
    ).save(store)
    store.setValue('ui/language_selected', True)
    return language


def restore_safe_defaults(store) -> None:
    """Restore harmless UI/workflow preferences without touching user data.

    The allow-list is deliberately explicit.  Provider credentials, library
    locations, databases, scan history and the selected language are not
    removed or rewritten by this operation.
    """
    from audio_library_organizer.metadata.naming import DEFAULT_FILENAME_TEMPLATE

    store.setValue('ui/theme', 'dark')
    store.setValue('ui/normalize_names', True)
    store.setValue(
        'ui/name_normalization_rules',
        json.dumps([rule.to_dict() for rule in default_name_rules()], ensure_ascii=False),
    )
    store.setValue('ui/filename_template', DEFAULT_FILENAME_TEMPLATE)
    store.setValue('ui/folder_organization', 'none')
    store.setValue('providers/auto_identify', False)
    store.sync()
