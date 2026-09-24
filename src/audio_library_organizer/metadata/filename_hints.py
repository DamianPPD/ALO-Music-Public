from __future__ import annotations

import re

_BPM_SUFFIX = re.compile(r'\s*\[\s*(\d+(?:\.\d+)?)\s*bpm\s*\]\s*$', re.IGNORECASE)
_TIME_PREFIX = re.compile(r'^\s*\d{1,2}[-:.]\d{2}[-:.]\d{2}\s*-\s*')
_RMX_TOKEN = re.compile(r'(?i)\brmx\b')
_WEBSITE_TOKEN = re.compile(
    r'(?i)(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9.-]*\.[a-z]{2,12}(?:/[^\s]*)?'
)
_DOTTED_ARTIST_TOKEN = re.compile(r'(?i)[a-z]{2,}\.[a-z]\.[a-z]{2,}')
_TRAILING_VERSION = re.compile(r'\s*[\(\[][^\(\)\[\]]+[\)\]]\s*$')
_EMPTY_BRACKETS = re.compile(r'\s*(?:\(\s*\)|\[\s*\])\s*')
_WATERMARK_TOKEN = re.compile(
    r'(?i)\b(?:download(?:ed)?\s+from|ripped\s+by|uploaded\s+by|'
    r'free\s+(?:mp3|music|download)|promo(?:tional)?\s+(?:use\s+)?only|'
    r'visit\s+(?:us|our\s+(?:site|page)))\b'
)


def is_suspicious_metadata_value(value: str | None) -> bool:
    """Return whether a tag looks like a website/download watermark."""
    text = ' '.join((value or '').split()).strip()
    if not text:
        return False
    if _WATERMARK_TOKEN.search(text):
        return True
    return any(_website_token_is_noise(match.group(0)) for match in _WEBSITE_TOKEN.finditer(text))


def _website_token_is_noise(token: str) -> bool:
    """Distinguish web addresses from dotted stage names such as will.i.am."""
    normalized = token.casefold()
    if normalized.startswith(('http://', 'https://', 'www.')) or '/' in normalized:
        return True
    return _DOTTED_ARTIST_TOKEN.fullmatch(token) is None


def parse_filename_bpm(stem: str) -> float | None:
    match = _BPM_SUFFIX.search(stem)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if 35.0 <= value <= 300.0 else None


def strip_recording_time_prefix(value: str) -> str:
    """Remove radio/set timestamp prefixes such as 12-07-56 -."""
    return _TIME_PREFIX.sub('', value or '', count=1).strip()


def normalize_version_tokens(value: str) -> str:
    """Normalize harmless search/name abbreviations without changing identity."""
    return _RMX_TOKEN.sub('Remix', value or '').strip()


def parse_filename_hint(stem: str) -> tuple[str | None, str | None]:
    text = _BPM_SUFFIX.sub('', stem).strip()
    text = strip_recording_time_prefix(text)
    if ' - ' not in text:
        return None, None
    artist, title = text.split(' - ', 1)
    artist = artist.strip()
    title = normalize_version_tokens(title.strip())
    if not artist or not title:
        return None, None
    return artist, title


def _append_variant(variants: list[str], value: str) -> None:
    value = ' '.join(value.split()).strip(' -_.,')
    if value and value not in variants:
        variants.append(value)


def _without_website_noise(value: str) -> str:
    cleaned = _WEBSITE_TOKEN.sub(
        lambda match: '' if _website_token_is_noise(match.group(0)) else match.group(0),
        value,
    )
    cleaned = _EMPTY_BRACKETS.sub(' ', cleaned)
    return ' '.join(cleaned.split()).strip(' -_.,')


def artist_search_variants(artist: str) -> list[str]:
    """Return non-destructive artist aliases used only for provider queries."""
    artist = (artist or '').strip()
    if not artist:
        return []
    variants = [artist]
    compact = artist.casefold().replace(' ', '')
    if compact == 'relocate':
        _append_variant(variants, 'Re:Locate')
    elif compact == 're:locate':
        _append_variant(variants, 'Relocate')
    return variants


def title_search_variants(title: str) -> list[str]:
    title = title.strip()
    if not title:
        return []
    variants = [title]

    normalized = normalize_version_tokens(title)
    _append_variant(variants, normalized)

    # Search fallbacks are deliberately non-destructive: the original title is
    # always first and remains the value shown/saved by ALO. Extra variants only
    # make provider queries tolerant of release-site watermarks and suffixes.
    clean = _without_website_noise(normalized)
    _append_variant(variants, clean)

    for value in (title, normalized, clean):
        if ' - ' in value:
            _append_variant(variants, value.rsplit(' - ', 1)[0])

    # A final base-title query helps providers that index a mix/version under the
    # release track rather than the exact local suffix, e.g. "(Extended)".
    if clean:
        base = _TRAILING_VERSION.sub('', clean)
        _append_variant(variants, base)

    return variants
