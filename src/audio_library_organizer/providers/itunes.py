from __future__ import annotations

from audio_library_organizer.domain.candidates import MetadataCandidate
from .common import RateLimiter


def _artwork_url(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace('100x100bb', '1200x1200bb').replace('100x100', '1200x1200')


def parse_itunes_result(data: dict) -> MetadataCandidate:
    duration_ms = data.get('trackTimeMillis')
    release_date = str(data.get('releaseDate') or '')
    return MetadataCandidate(
        source='apple',
        artist=data.get('artistName'),
        title=data.get('trackName'),
        album=data.get('collectionName'),
        year=release_date[:4] if len(release_date) >= 4 else None,
        genre=data.get('primaryGenreName'),
        duration_seconds=float(duration_ms) / 1000.0 if duration_ms else None,
        source_url=data.get('trackViewUrl') or data.get('collectionViewUrl'),
        cover_art_url=_artwork_url(data.get('artworkUrl100')),
    )


class ITunesSearchClient:
    """Keyless Apple catalog lookup using the iTunes Search endpoint."""

    BASE_URL = 'https://itunes.apple.com/search'

    def __init__(self, session=None, *, country: str = 'PL'):
        import requests
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent': 'ALO-Music/0.4'})
        self.country = (country or 'PL').upper()
        self.limiter = RateLimiter(0.35)
        self._cache: dict[tuple[str, str, int], list[MetadataCandidate]] = {}

    def search_tracks(self, artist: str, title: str, limit: int = 8) -> list[MetadataCandidate]:
        key = (artist.casefold().strip(), title.casefold().strip(), int(limit))
        if key in self._cache:
            return list(self._cache[key])
        self.limiter.wait()
        term = ' '.join(x for x in (artist.strip(), title.strip()) if x)
        response = self.session.get(
            self.BASE_URL,
            params={
                'term': term,
                'entity': 'song',
                'media': 'music',
                'country': self.country,
                'limit': int(limit),
            },
            timeout=25,
        )
        response.raise_for_status()
        results = [parse_itunes_result(item) for item in (response.json().get('results') or [])]
        self._cache[key] = results
        return list(results)
