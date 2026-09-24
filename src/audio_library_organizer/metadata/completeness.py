from __future__ import annotations


def has_real_cover(track) -> bool:
    return bool(
        getattr(track, 'manual_cover_path', None)
        or getattr(track, 'cover_art_url', None)
        or getattr(track, 'musicbrainz_release_id', None)
        or getattr(track, 'has_cover', False)
    )


def core_checks(track) -> list[tuple[str, bool]]:
    # Artwork is always available in the result because ALO uses a packaged
    # placeholder when no real artwork exists. Lack of a real cover remains
    # separately filterable, but does not make a result unusable.
    return [
        ('Wykonawca', bool(getattr(track, 'artist', None))),
        ('Tytuł / wersja', bool(getattr(track, 'title', None))),
        ('Rok', bool(getattr(track, 'year', None))),
        ('Gatunek', bool(getattr(track, 'genre', None))),
        ('BPM', getattr(track, 'bpm', None) is not None),
        ('Okładka', True),
    ]


def optional_checks(track) -> list[tuple[str, bool]]:
    return [
        ('Album / Release', bool(getattr(track, 'album', None))),
        ('Discogs URL', bool(getattr(track, 'discogs_release_id', None) or getattr(track, 'discogs_url', None))),
        ('Komentarz', bool(getattr(track, 'comment', None))),
    ]


def core_metadata_complete(track) -> bool:
    return all(ok for _label, ok in core_checks(track))
