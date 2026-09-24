from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from audio_library_organizer.domain.models import TrackRecord

_VERSION_MARKERS = (
    'mix', 'remix', 'edit', 'extended', 'radio', 'club', 'version',
    'dub', 'instrumental', 'vocal', 'original',
)
_BRACKET_SUFFIX = re.compile(r"\s*[\(\[]([^\)\]]+)[\)\]]\s*$", re.IGNORECASE)
_DASH_SUFFIX = re.compile(
    r"\s+(?:-|–|—)\s+(.+?(?:mix|remix|edit|extended|radio|club|version|dub|instrumental|vocal|original).*)$",
    re.IGNORECASE,
)


def _norm(value: str | None) -> str:
    return ' '.join((value or '').casefold().split())


def _has_marker(text: str | None) -> bool:
    value = _norm(text)
    return any(marker in value for marker in _VERSION_MARKERS)


def base_version_title(title: str | None) -> str:
    """Return a conservative base title used only for informational version families.

    Only a trailing bracket/dash segment containing a typical version marker is
    stripped.  This avoids turning arbitrary parenthetical song subtitles into a
    family relationship.
    """
    value = ' '.join((title or '').strip().split())
    while value:
        match = _BRACKET_SUFFIX.search(value)
        if not match or not _has_marker(match.group(1)):
            break
        value = value[:match.start()].rstrip()
    match = _DASH_SUFFIX.search(value)
    if match and _has_marker(match.group(1)):
        value = value[:match.start()].rstrip()
    return _norm(value)


def has_version_marker(title: str | None) -> bool:
    value = ' '.join((title or '').strip().split())
    match = _BRACKET_SUFFIX.search(value)
    if match and _has_marker(match.group(1)):
        return True
    match = _DASH_SUFFIX.search(value)
    return bool(match and _has_marker(match.group(1)))



def same_version_family(a: TrackRecord, b: TrackRecord) -> bool:
    """Whether two tracks are explicitly named versions of the same base song.

    This is intentionally conservative and informational.  Exact/same-audio
    evidence can still classify the files as duplicates elsewhere.
    """
    artist_a, artist_b = _norm(a.artist), _norm(b.artist)
    base_a, base_b = base_version_title(a.title), base_version_title(b.title)
    if not artist_a or artist_a != artist_b or not base_a or base_a != base_b:
        return False
    if _norm(a.title) == _norm(b.title):
        return False
    return has_version_marker(a.title) or has_version_marker(b.title)

def group_version_families(tracks: Iterable[TrackRecord]) -> list[list[TrackRecord]]:
    """Group related named versions without changing duplicate/status decisions.

    A family needs the same artist and conservative base title, at least two
    distinct titles, and at least one explicit version marker.  The function is
    intentionally informational: it never mutates TrackRecord.
    """
    buckets: dict[tuple[str, str], list[TrackRecord]] = defaultdict(list)
    for track in tracks:
        artist = _norm(track.artist)
        base = base_version_title(track.title)
        if artist and base:
            buckets[(artist, base)].append(track)

    families: list[list[TrackRecord]] = []
    for members in buckets.values():
        if len(members) < 2:
            continue
        distinct_titles = {_norm(t.title) for t in members if t.title}
        if len(distinct_titles) < 2:
            continue
        if not any(has_version_marker(t.title) for t in members):
            continue
        families.append(sorted(members, key=lambda t: ((t.duration_seconds or 0), str(t.path).casefold())))
    return sorted(families, key=lambda family: (_norm(family[0].artist), base_version_title(family[0].title)))
