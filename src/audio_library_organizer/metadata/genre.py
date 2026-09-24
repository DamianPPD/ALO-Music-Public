from __future__ import annotations

import re

_SPLIT = re.compile(r"\s*(?:/|;|\||,)\s*")


def genre_items(value: str | None, *, limit: int = 3) -> list[str]:
    """Return unique genre/style labels in source order, capped for a clean UI/tag."""
    if not value:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in _SPLIT.split(str(value)):
        item = ' '.join(raw.strip().split())
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= max(1, int(limit)):
            break
    return result


def normalize_genre_list(value: str | None, *, limit: int = 3) -> str | None:
    items = genre_items(value, limit=limit)
    return ' / '.join(items) if items else None


def primary_genre(value: str | None) -> str | None:
    items = genre_items(value, limit=1)
    return items[0] if items else None
