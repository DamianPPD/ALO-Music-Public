from __future__ import annotations

from audio_library_organizer.domain.candidates import AcoustIDHit


def _artist_text(recording: dict) -> str | None:
    artists = recording.get('artists') or []
    names = [a.get('name') for a in artists if a.get('name')]
    return ' & '.join(names) if names else None


def parse_acoustid_results(data: dict) -> list[AcoustIDHit]:
    hits: list[AcoustIDHit] = []
    for result in data.get('results') or []:
        score = float(result.get('score') or 0.0)
        for recording in result.get('recordings') or []:
            rid = recording.get('id')
            if rid:
                hits.append(AcoustIDHit(rid, score, recording.get('title'), _artist_text(recording)))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits

class AcoustIDClient:
    BASE_URL = 'https://api.acoustid.org/v2/lookup'

    def __init__(self, client_key: str, session=None):
        import requests
        from .common import RateLimiter
        self.client_key = client_key.strip()
        self.session = session or requests.Session()
        self.limiter = RateLimiter(0.35)
        self._lookup_cache: dict[tuple[str, int], list[AcoustIDHit]] = {}

    def lookup(self, fingerprint: str, duration_seconds: int) -> list[AcoustIDHit]:
        if not self.client_key:
            return []
        key = (fingerprint, int(duration_seconds))
        if key in self._lookup_cache:
            return list(self._lookup_cache[key])
        self.limiter.wait()
        response = self.session.post(self.BASE_URL, data={
            'client': self.client_key,
            'duration': int(duration_seconds),
            'fingerprint': fingerprint,
            'meta': 'recordings recordingids releases releasegroups',
            'format': 'json',
        }, timeout=30)
        response.raise_for_status()
        result = parse_acoustid_results(response.json())
        self._lookup_cache[key] = result
        return list(result)
