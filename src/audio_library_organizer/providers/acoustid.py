from __future__ import annotations

from audio_library_organizer.domain.candidates import AcoustIDHit


def _artist_text(recording: dict) -> str | None:
    artists = recording.get('artists') or []
    names = [a.get('name') for a in artists if isinstance(a, dict) and a.get('name')]
    return ' & '.join(names) if names else None


def parse_acoustid_results(data: dict) -> list[AcoustIDHit]:
    if not isinstance(data, dict) or data.get('status', 'ok') != 'ok' or not isinstance(data.get('results'), list):
        raise ValueError('Nieprawidłowa odpowiedź AcoustID.')
    hits: list[AcoustIDHit] = []
    for result in data['results']:
        if not isinstance(result, dict) or not isinstance(result.get('recordings', []), list):
            raise ValueError('Nieprawidłowa odpowiedź AcoustID.')
        try:
            score = float(result.get('score') or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError('Nieprawidłowa odpowiedź AcoustID.') from exc
        for recording in result.get('recordings') or []:
            if not isinstance(recording, dict):
                raise ValueError('Nieprawidłowa odpowiedź AcoustID.')
            rid = recording.get('id')
            if rid:
                groups = recording.get('releasegroups') or recording.get('release-groups') or recording.get('releases') or []
                release = next((r for r in groups if isinstance(r, dict)), {}) if isinstance(groups, list) else {}
                date = release.get('first-release-date') or release.get('date') or ''
                year = date[:4] if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit() else None
                hits.append(AcoustIDHit(rid, score, recording.get('title'), _artist_text(recording),
                                          release.get('title'), year, result.get('id')))
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
