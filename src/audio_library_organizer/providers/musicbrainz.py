from __future__ import annotations

from audio_library_organizer.domain.candidates import MusicBrainzRecording


def _artist_credit(data: dict) -> str | None:
    credit = data.get('artist-credit') or []
    pieces = []
    for part in credit:
        name = part.get('name') or (part.get('artist') or {}).get('name')
        if name:
            pieces.append(name)
        join = part.get('joinphrase')
        if join:
            pieces.append(join)
    text = ''.join(pieces).strip()
    return text or None


def parse_recording(data: dict) -> MusicBrainzRecording:
    releases = data.get('releases') or []
    release_ids = tuple(str(r['id']) for r in releases if r.get('id'))
    release_titles = tuple(str(r['title']) for r in releases if r.get('title'))
    years = tuple(str(r['date'])[:4] for r in releases if r.get('date'))
    length = data.get('length')
    return MusicBrainzRecording(
        recording_id=str(data.get('id') or ''),
        artist=_artist_credit(data),
        title=data.get('title'),
        duration_seconds=float(length)/1000.0 if length else None,
        release_ids=release_ids,
        release_titles=release_titles,
        years=years,
    )

class MusicBrainzClient:
    BASE_URL = 'https://musicbrainz.org/ws/2'

    def __init__(self, contact: str = 'personal-use', session=None):
        import requests
        from .common import RateLimiter
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent': f'AudioLibraryOrganizer/0.1 ({contact})'})
        self.limiter = RateLimiter(1.05)
        self._recording_cache: dict[str, MusicBrainzRecording] = {}
        self._search_cache: dict[tuple[str, str, int], list[MusicBrainzRecording]] = {}

    def get_recording(self, recording_id: str) -> MusicBrainzRecording:
        if recording_id in self._recording_cache:
            return self._recording_cache[recording_id]
        self.limiter.wait()
        r = self.session.get(
            f'{self.BASE_URL}/recording/{recording_id}',
            params={'fmt':'json','inc':'artists+releases+release-groups'}, timeout=30,
        )
        r.raise_for_status()
        result = parse_recording(r.json())
        self._recording_cache[recording_id] = result
        return result

    def search_recordings(self, artist: str, title: str, limit: int = 5) -> list[MusicBrainzRecording]:
        key = (artist.casefold().strip(), title.casefold().strip(), int(limit))
        if key in self._search_cache:
            return list(self._search_cache[key])
        self.limiter.wait()
        query = f'artist:"{artist}" AND recording:"{title}"'
        r = self.session.get(f'{self.BASE_URL}/recording', params={'fmt':'json','query':query,'limit':limit}, timeout=30)
        r.raise_for_status()
        result = [parse_recording(x) for x in (r.json().get('recordings') or [])]
        self._search_cache[key] = result
        return list(result)
