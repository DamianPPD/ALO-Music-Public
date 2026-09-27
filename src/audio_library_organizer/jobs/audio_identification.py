"""Single-track audio lookup and explicit approval of an AcoustID source."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
import requests

from audio_library_organizer.audio.fingerprint import FingerprintResult, fingerprint_audio
from audio_library_organizer.domain.candidates import AcoustIDHit
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.providers.acoustid import AcoustIDClient
from audio_library_organizer.providers.musicbrainz import MusicBrainzClient

SOURCE = 'Rozpoznanie audio'


class AudioIdentification:
    def __init__(self, client: AcoustIDClient, *, fingerprinter: Callable[[Path], FingerprintResult] | None = None,
                 musicbrainz_client: MusicBrainzClient | None = None):
        self.client = client
        self.fingerprinter = fingerprinter or fingerprint_audio
        self.musicbrainz_client = musicbrainz_client or MusicBrainzClient()

    def lookup(self, track: TrackRecord, *, progress: Callable[[str], None] | None = None) -> list[AcoustIDHit]:
        if not self.client.client_key:
            raise ValueError('Brak klucza AcoustID. Ustaw go w Integracjach i kluczach API.')
        if progress:
            progress('fingerprint')
        try:
            fingerprint = self.fingerprinter(track.path)
        except FileNotFoundError as exc:
            raise RuntimeError('Nie znaleziono fpcalc ani FFmpeg do wygenerowania fingerprintu.') from exc
        if not fingerprint.fingerprint or fingerprint.duration_seconds <= 0:
            raise ValueError('Nie udało się wygenerować poprawnego fingerprintu audio.')
        if progress:
            progress('lookup')
        # AcoustID may return a scored recording ID without artist/title. Resolve
        # those IDs before offering results to the user; keep the AcoustID score.
        candidates = []
        for hit in self.client.lookup(fingerprint.fingerprint, fingerprint.duration_seconds):
            if not all((value or '').strip() for value in (hit.artist, hit.title, hit.album, hit.year)):
                try:
                    recording = self.musicbrainz_client.get_recording(hit.recording_id)
                except (requests.RequestException, ValueError, TypeError):
                    pass
                else:
                    hit = replace(hit, artist=hit.artist or recording.artist, title=hit.title or recording.title,
                                  album=hit.album or next(iter(recording.release_titles), None),
                                  year=hit.year or next(iter(recording.years), None))
            if (hit.artist or '').strip() and (hit.title or '').strip():
                candidates.append(hit)
            if len(candidates) == 5:
                break
        # No final track fields or approved source change during a lookup.
        return candidates


def approve_audio_source(track: TrackRecord, hit: AcoustIDHit) -> None:
    """Save a candidate as a source; never write any final metadata fields."""
    values = {'artist': hit.artist, 'title': hit.title, 'album': hit.album, 'year': hit.year}
    for sources in track.field_source_values.values():
        if isinstance(sources, dict):
            sources.pop(SOURCE, None)
    for field_name, value in values.items():
        if value:
            track.field_source_values.setdefault(field_name, {})[SOURCE] = value
    track.audio_recognition = {
        'recording_id': hit.recording_id, 'acoustid_id': hit.acoustid_id,
        'score': hit.score, **values,
    }
