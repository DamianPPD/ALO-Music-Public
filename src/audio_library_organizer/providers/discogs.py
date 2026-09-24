from __future__ import annotations

from difflib import SequenceMatcher

from audio_library_organizer.domain.candidates import MetadataCandidate


def _artist_name(release: dict) -> str | None:
    names = [a.get('name') for a in release.get('artists') or [] if a.get('name')]
    return ' & '.join(names) if names else None


def _duration_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parts = [int(p) for p in value.split(':')]
        if len(parts) == 2:
            return parts[0]*60 + parts[1]
        if len(parts) == 3:
            return parts[0]*3600 + parts[1]*60 + parts[2]
    except ValueError:
        return None
    return None


def _norm(value: str | None) -> str:
    return ' '.join((value or '').casefold().split())


def _best_track(release: dict, wanted_title: str | None) -> dict:
    tracks = release.get('tracklist') or []
    if not tracks:
        return {}
    if not wanted_title:
        return tracks[0]
    wanted = _norm(wanted_title)
    exact = [t for t in tracks if _norm(t.get('title')) == wanted]
    if exact:
        return exact[0]
    return max(tracks, key=lambda t: SequenceMatcher(None, wanted, _norm(t.get('title'))).ratio())


def _format_comment(release: dict) -> str:
    lines: list[str] = []
    labels = []
    for label in release.get('labels') or []:
        name = label.get('name')
        catno = label.get('catno')
        if name:
            labels.append(f'{name} – {catno}' if catno else name)
    if labels:
        lines.append('Label: ' + ', '.join(labels))
    formats = []
    for fmt in release.get('formats') or []:
        parts = [fmt.get('name')] + list(fmt.get('descriptions') or [])
        text = ', '.join(str(x) for x in parts if x)
        if text:
            formats.append(text)
    if formats:
        lines.append('Format: ' + '; '.join(formats))
    if release.get('country'):
        lines.append('Country: ' + str(release['country']))
    released = release.get('released') or release.get('released_formatted') or release.get('year')
    if released:
        lines.append('Released: ' + str(released))
    return '\n'.join(lines)


def _cover_url(release: dict) -> str | None:
    images = list(release.get('images') or [])
    if not images:
        return None
    primary = next((img for img in images if str(img.get('type') or '').casefold() == 'primary'), None)
    chosen = primary or images[0]
    return chosen.get('uri') or chosen.get('resource_url') or chosen.get('uri150')


def parse_release_candidate(release: dict, wanted_title: str | None = None) -> MetadataCandidate:
    artist = _artist_name(release)
    release_title = release.get('title')
    track = _best_track(release, wanted_title)
    styles = [str(x) for x in release.get('styles') or [] if x]
    genres = [str(x) for x in release.get('genres') or [] if x]
    genre = ', '.join(styles or genres) or None
    album = None
    if release_title:
        album = f'{artist} – {release_title}' if artist else str(release_title)
    release_id = str(release.get('id')) if release.get('id') is not None else None
    uri = release.get('uri') or (f'https://www.discogs.com/release/{release_id}' if release_id else None)
    return MetadataCandidate(
        source='discogs', artist=artist, title=track.get('title') or wanted_title or release_title,
        album=album, year=str(release.get('year')) if release.get('year') else None,
        genre=genre, comment=_format_comment(release), duration_seconds=_duration_seconds(track.get('duration')),
        release_id=release_id, source_url=uri, cover_art_url=_cover_url(release),
    )

class DiscogsClient:
    BASE_URL = 'https://api.discogs.com'

    def __init__(self, token: str, session=None):
        import requests
        from .common import RateLimiter
        self.token = token.strip()
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent':'AudioLibraryOrganizer/0.1'})
        self.limiter = RateLimiter(1.05)
        self._search_cache: dict[tuple[str, str, int], list[str]] = {}
        self._release_cache: dict[str, dict] = {}

    def search_release_ids(self, artist: str, track: str, limit: int = 8) -> list[str]:
        if not self.token:
            return []
        key = (artist.casefold().strip(), track.casefold().strip(), int(limit))
        if key in self._search_cache:
            return list(self._search_cache[key])
        self.limiter.wait()
        r = self.session.get(f'{self.BASE_URL}/database/search', params={
            'type':'release','artist':artist,'track':track,'per_page':limit,'token':self.token
        }, timeout=30)
        r.raise_for_status()
        result = [str(x['id']) for x in (r.json().get('results') or []) if x.get('id')]
        self._search_cache[key] = result
        return list(result)

    def get_release(self, release_id: str) -> dict:
        release_id = str(release_id)
        if release_id in self._release_cache:
            return dict(self._release_cache[release_id])
        self.limiter.wait()
        params = {'token':self.token} if self.token else None
        r = self.session.get(f'{self.BASE_URL}/releases/{release_id}', params=params, timeout=30)
        r.raise_for_status()
        result = r.json()
        self._release_cache[release_id] = result
        return dict(result)
