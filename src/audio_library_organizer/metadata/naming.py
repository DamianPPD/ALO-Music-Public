from __future__ import annotations

import re
from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.normalization import normalize_music_text

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_BPM_SUFFIX = re.compile(r'\s*\[\s*\d+(?:\.\d+)?\s*bpm\s*\]\s*$', re.IGNORECASE)
_TITLE_VERSION = re.compile(r'^(?P<title>.*?)(?:\s*\((?P<version>[^()]*)\))$')
_PLACEHOLDER = re.compile(r'\{([A-Za-z][A-Za-z0-9_]*)\}')
_OPTIONAL_GROUP = re.compile(r'(\([^()]*\{[^{}]+\}[^()]*\)|\[[^\[\]]*\{[^{}]+\}[^\[\]]*\])')
_RESERVED = {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}

DEFAULT_FILENAME_TEMPLATE = '{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]'

FILENAME_FIELD_ORDER = ('Artist', 'Title', 'Version', 'Year', 'BPM', 'Genre', 'Album')

_TITLE_ACRONYMS = {
    'DJ', 'MC', 'VIP', 'UK', 'USA', 'US', 'EU', 'EP', 'LP', 'BPM',
    'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
}


def normalize_title_case(value: str | None) -> str | None:
    """Normalize track titles to a predictable word-capitalized form.

    Artist names are intentionally excluded from this rule. Common music
    acronyms and roman numerals stay uppercase while ordinary words become
    ``First Letter Upper + rest lower``. Punctuation and separators are kept.
    """
    if value is None:
        return None
    text = re.sub(r'\s+', ' ', str(value)).strip()
    if not text:
        return None

    def fix_token(match: re.Match[str]) -> str:
        token = match.group(0)
        upper = token.upper()
        if upper in _TITLE_ACRONYMS:
            return upper
        return token[:1].upper() + token[1:].lower()

    normalized = re.sub(r"[A-Za-zÀ-ÖØ-öø-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż]+)?", fix_token, text)
    return normalize_music_text(normalized)



def filename_fields_from_template(template: str) -> set[str]:
    """Return supported filename placeholders present in *template*."""
    names = set(_PLACEHOLDER.findall(template or ''))
    return {name for name in FILENAME_FIELD_ORDER if name in names}


def template_from_filename_fields(fields) -> str:
    """Build the canonical ALO filename layout from checkbox field selection."""
    enabled = set(fields or ()) | {'Artist', 'Title'}
    parts = ['{Artist} - {Title}']
    if 'Version' in enabled:
        parts.append('({Version})')
    if 'Year' in enabled:
        parts.append('({Year})')
    if 'BPM' in enabled:
        parts.append('[{BPM}bpm]')
    if 'Genre' in enabled:
        parts.append('[{Genre}]')
    if 'Album' in enabled:
        parts.append('[{Album}]')
    return ' '.join(parts)

def sanitize_windows_component(value: str) -> str:
    value = _INVALID.sub('-', value)
    value = re.sub(r'\s+', ' ', value).strip().rstrip('. ')
    if value.upper() in _RESERVED:
        value = f'_{value}'
    return value or 'Bez nazwy'


def split_title_version(title: str | None) -> tuple[str, str]:
    clean = _BPM_SUFFIX.sub('', (title or '').strip())
    match = _TITLE_VERSION.match(clean)
    if not match:
        return clean, ''
    base = (match.group('title') or '').strip()
    version = (match.group('version') or '').strip()
    return base or clean, version


def _template_values(track: TrackRecord) -> dict[str, str]:
    base_title, version = split_title_version(track.title)
    if not base_title and not track.artist:
        base_title = track.path.stem
    bpm = '' if track.bpm is None else str(int(round(track.bpm)))
    return {
        'Artist': (track.artist or '').strip(),
        'Title': base_title,
        'TitleFull': _BPM_SUFFIX.sub('', (track.title or base_title or '').strip()),
        'Version': version,
        'Year': (track.year or '').strip(),
        'BPM': bpm,
        'Genre': (track.genre or '').strip(),
        'Album': (track.album or '').strip(),
    }


def render_filename_template(track: TrackRecord, template: str = DEFAULT_FILENAME_TEMPLATE) -> str:
    values = _template_values(track)
    text = (template or DEFAULT_FILENAME_TEMPLATE).strip()

    def render_group(match: re.Match[str]) -> str:
        group = match.group(0)
        names = _PLACEHOLDER.findall(group)
        if any(not values.get(name, '') for name in names):
            return ''
        return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), ''), group)

    # Parentheses/brackets containing placeholders are optional units. If the
    # relevant value is missing, the whole unit disappears instead of leaving
    # artifacts like "()" or "[bpm]".
    previous = None
    while previous != text:
        previous = text
        text = _OPTIONAL_GROUP.sub(render_group, text)

    text = _PLACEHOLDER.sub(lambda m: values.get(m.group(1), ''), text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'(?:\s+-\s*){2,}', ' - ', text)
    text = re.sub(r'\s+-\s*$', '', text)
    text = re.sub(r'^\s*-\s*', '', text)
    return text.strip(' -') or (track.path.stem or 'Bez nazwy')


def propose_filename(track: TrackRecord, *, template: str = DEFAULT_FILENAME_TEMPLATE) -> str:
    ext = track.path.suffix.lower() or '.audio'
    if track.filename_override:
        override = Path(track.filename_override.strip()).stem if Path(track.filename_override.strip()).suffix else track.filename_override.strip()
        base = sanitize_windows_component(override)
    else:
        base = sanitize_windows_component(render_filename_template(track, template))
    return f'{base}{ext}'
