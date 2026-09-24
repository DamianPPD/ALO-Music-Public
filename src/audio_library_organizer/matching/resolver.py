from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.candidates import MetadataCandidate, MusicBrainzRecording
from audio_library_organizer.metadata.naming import propose_filename, normalize_title_case
from audio_library_organizer.metadata.filename_hints import (
    artist_search_variants,
    is_suspicious_metadata_value,
    parse_filename_hint,
    strip_recording_time_prefix,
    title_search_variants,
)
from audio_library_organizer.matching.scorer import score_candidate
from audio_library_organizer.providers.discogs import parse_release_candidate
from audio_library_organizer.metadata.genre import normalize_genre_list
from audio_library_organizer.metadata.provenance import suspicious_identity_change


@dataclass(frozen=True, slots=True)
class IdentificationOutcome:
    track: TrackRecord
    candidate: MetadataCandidate | None
    decision: str


class ProviderLookupError(RuntimeError):
    """Raised only when no match is available and at least one provider failed."""

    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__('; '.join(self.errors))


def decision_for_score(score: float) -> str:
    if score >= 0.88:
        return 'certain'
    if score >= 0.70:
        return 'probable'
    return 'uncertain'


def _source_label(candidate: MetadataCandidate) -> str:
    return {'discogs': 'Discogs', 'musicbrainz': 'MusicBrainz', 'apple': 'Apple / iTunes'}.get(candidate.source, candidate.source.title())


def _remember_candidate_values(track: TrackRecord, candidate: MetadataCandidate) -> None:
    label = _source_label(candidate)
    values = {
        'artist': candidate.artist,
        'title': candidate.title,
        'album': candidate.album,
        'year': candidate.year,
        'genre': normalize_genre_list(candidate.genre),
        'comment': candidate.comment,
    }
    for field_name, value in values.items():
        if value:
            track.field_source_values.setdefault(field_name, {})[label] = value
    if candidate.cover_art_url:
        track.field_source_values.setdefault('__cover__', {})[label] = candidate.cover_art_url
    if candidate.source == 'discogs' and candidate.source_url:
        track.field_source_values.setdefault('discogs_url', {})['Discogs'] = candidate.source_url


def apply_candidate(track: TrackRecord, candidate: MetadataCandidate, *, source_recording_id: str | None = None) -> TrackRecord:
    suspicious = suspicious_identity_change(track, candidate.artist, candidate.title)
    updates = {
        'artist': candidate.artist, 'title': normalize_title_case(candidate.title), 'album': candidate.album,
        'year': candidate.year, 'genre': normalize_genre_list(candidate.genre), 'comment': candidate.comment,
    }
    source_label = _source_label(candidate)
    _remember_candidate_values(track, candidate)
    for field_name, value in updates.items():
        if value and field_name not in track.locked_fields:
            setattr(track, field_name, value)
            track.field_sources[field_name] = source_label
    track.confidence = candidate.score
    if candidate.source == 'discogs':
        track.discogs_release_id = candidate.release_id
        if 'discogs_url' not in track.locked_fields:
            track.discogs_url = candidate.source_url
    track.musicbrainz_recording_id = source_recording_id or track.musicbrainz_recording_id
    track.musicbrainz_release_id = candidate.musicbrainz_release_id or track.musicbrainz_release_id
    track.cover_art_url = candidate.cover_art_url or track.cover_art_url
    track.match_reasons = list(candidate.reasons)
    if suspicious:
        track.match_reasons.append('⚠ Duża różnica względem danych sprzed online — sprawdź tożsamość utworu')
    radio_prefix = strip_recording_time_prefix(track.path.stem) != track.path.stem
    duration_mismatch = bool(
        track.duration_seconds
        and candidate.duration_seconds
        and abs(track.duration_seconds - candidate.duration_seconds) > max(18.0, candidate.duration_seconds * 0.08)
    )
    if radio_prefix:
        track.match_reasons.append('Nagranie wygląda na fragment audycji / plik z prefiksem czasu')
    if duration_mismatch:
        track.match_reasons.append('Długość pliku istotnie różni się od znalezionego wydania')
    if '__status__' not in track.locked_fields:
        needs_review = suspicious or radio_prefix or duration_mismatch
        track.status = 'review' if needs_review else ('ready' if decision_for_score(candidate.score) == 'certain' else 'review')
    track.proposed_filename = propose_filename(track)
    return track


def _norm(value: str | None) -> str:
    return ' '.join((value or '').casefold().replace('–', '-').split())


def _mb_release_for_candidate(rec: MusicBrainzRecording, candidate: MetadataCandidate) -> str | None:
    if not candidate.album:
        return None
    album = _norm(candidate.album)
    for release_id, release_title in zip(rec.release_ids, rec.release_titles):
        title = _norm(release_title)
        if title and (album == title or album.endswith(' - ' + title)):
            return release_id
    return None


def _musicbrainz_candidate(rec: MusicBrainzRecording) -> MetadataCandidate:
    release_id = rec.release_ids[0] if rec.release_ids else None
    return MetadataCandidate(
        source='musicbrainz',
        artist=rec.artist,
        title=rec.title,
        album=rec.release_titles[0] if rec.release_titles else None,
        year=rec.years[0] if rec.years else None,
        duration_seconds=rec.duration_seconds,
        musicbrainz_release_id=release_id,
        cover_art_url=f'https://coverartarchive.org/release/{release_id}/front-500' if release_id else None,
    )


def _score_with_recording_evidence(
    track: TrackRecord,
    candidate: MetadataCandidate,
    rec: MusicBrainzRecording,
    acoustid_score: float | None,
) -> MetadataCandidate:
    # Score against what the user's file actually told us. Do not manufacture
    # confidence by first copying MusicBrainz artist/title into the source.
    scored = score_candidate(track, candidate)
    score = scored.score
    reasons = list(scored.reasons)

    # Discogs/MB candidate should also genuinely describe the recording that
    # AcoustID/MusicBrainz pointed to, especially important for exact remixes.
    reference = TrackRecord(
        path=track.path,
        artist=rec.artist,
        title=rec.title,
        duration_seconds=rec.duration_seconds,
    )
    corroboration = score_candidate(reference, candidate)
    if corroboration.score >= 0.85:
        score += 0.15
        reasons.append('wersja potwierdzona MusicBrainz')
    elif corroboration.score >= 0.65:
        score += 0.08
        reasons.append('wersja zbliżona do MusicBrainz')

    if acoustid_score is not None:
        # A high-quality acoustic match is intentionally strong enough to
        # identify filenames such as 34.mp3, but duration/version evidence is
        # still needed for automatic "certain" in normal cases.
        score += max(0.0, min(1.0, acoustid_score)) * 0.60
        reasons.append(f'AcoustID {round(acoustid_score * 100)}%')

    return candidate.with_score(max(0.0, min(1.0, score)), tuple(dict.fromkeys(reasons)))


def _text_query_tracks(track: TrackRecord) -> list[TrackRecord]:
    """Return safe query identities without mutating the stored metadata.

    Timestamp-prefixed radio/set files may already exist in an older ALO
    library with the timestamp stored as artist. In that case the cleaned
    filename identity is tried first so online recognition can repair it.
    """
    variants: list[TrackRecord] = []
    has_timestamp_prefix = strip_recording_time_prefix(track.path.stem) != track.path.stem
    filename_artist, filename_title = parse_filename_hint(track.path.stem)
    title_artist, split_title = parse_filename_hint(track.title or '')

    repeated_fields = (track.artist, track.album, track.genre, track.comment)
    normalized = [' '.join((value or '').casefold().split()) for value in repeated_fields if value]
    repeated_noise = {value for value in normalized if value and normalized.count(value) >= 3}
    artist_key = ' '.join((track.artist or '').casefold().split())
    artist_unreliable = is_suspicious_metadata_value(track.artist) or artist_key in repeated_noise
    title_unreliable = is_suspicious_metadata_value(track.title)

    if artist_unreliable and title_artist and split_title:
        variants.append(replace(track, artist=title_artist, title=split_title))
    if has_timestamp_prefix and filename_artist and filename_title:
        variants.append(replace(track, artist=filename_artist, title=filename_title))
    if track.artist and track.title and not artist_unreliable and not title_unreliable:
        variants.append(track)
        if title_artist and split_title and _norm(title_artist) == _norm(track.artist):
            variants.append(replace(track, title=split_title))
    if filename_artist and filename_title:
        variants.append(replace(track, artist=filename_artist, title=filename_title))
    if not variants:
        variants.append(track)

    unique: list[TrackRecord] = []
    seen: set[tuple[str, str]] = set()
    for item in variants:
        key = ((item.artist or '').casefold().strip(), (item.title or '').casefold().strip())
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _score_text_fallback(track: TrackRecord, candidate: MetadataCandidate) -> MetadataCandidate:
    """Score against stored data plus safe filename, artist and title variants."""
    best = score_candidate(track, candidate)
    for base in _text_query_tracks(track):
        artists = artist_search_variants(base.artist or '') or [base.artist or '']
        titles = title_search_variants(base.title or '') or [base.title or '']
        for artist in artists:
            for title in titles:
                alternate = replace(base, artist=artist, title=title)
                scored = score_candidate(alternate, candidate)
                if scored.score > best.score:
                    best = scored
    return best


class IdentificationService:
    def __init__(self, acoustid=None, musicbrainz=None, discogs=None, itunes=None):
        self.acoustid = acoustid
        self.musicbrainz = musicbrainz
        self.discogs = discogs
        self.itunes = itunes
        self._provider_errors: list[str] = []

    def _record_provider_error(self, provider: str, exc: Exception) -> None:
        message = str(exc).strip() or exc.__class__.__name__
        entry = f'{provider}: {message}'
        if entry not in self._provider_errors:
            self._provider_errors.append(entry)

    def _records_from_fingerprint(self, track: TrackRecord) -> list[tuple[MusicBrainzRecording, float]]:
        if not (self.acoustid and self.musicbrainz and track.fingerprint and track.fingerprint_duration):
            return []
        try:
            hits = self.acoustid.lookup(track.fingerprint, track.fingerprint_duration)
        except Exception as exc:
            self._record_provider_error('AcoustID', exc)
            return []

        records: list[tuple[MusicBrainzRecording, float]] = []
        seen: set[str] = set()
        for hit in hits[:5]:
            if hit.recording_id in seen:
                continue
            seen.add(hit.recording_id)
            try:
                records.append((self.musicbrainz.get_recording(hit.recording_id), hit.score))
            except Exception as exc:
                self._record_provider_error('MusicBrainz', exc)
                continue
        return records

    def _records_from_text(self, track: TrackRecord) -> list[tuple[MusicBrainzRecording, None]]:
        if not self.musicbrainz:
            return []
        seen: set[str] = set()
        results: list[tuple[MusicBrainzRecording, None]] = []
        for query_track in _text_query_tracks(track):
            if not (query_track.artist and query_track.title):
                continue
            for artist in artist_search_variants(query_track.artist):
                for title in title_search_variants(query_track.title):
                    try:
                        records = self.musicbrainz.search_recordings(artist, title, limit=3)
                    except Exception as exc:
                        self._record_provider_error('MusicBrainz', exc)
                        continue
                    for record in records:
                        if record.recording_id and record.recording_id not in seen:
                            seen.add(record.recording_id)
                            results.append((record, None))
                    if results:
                        break
                if results:
                    break
            if results:
                break
        return results

    def _discogs_candidates(self, rec: MusicBrainzRecording) -> list[MetadataCandidate]:
        if not (self.discogs and rec.artist and rec.title):
            return []
        candidates: list[MetadataCandidate] = []
        try:
            release_ids = self.discogs.search_release_ids(rec.artist, rec.title, limit=8)
        except Exception as exc:
            self._record_provider_error('Discogs', exc)
            return []
        for release_id in release_ids:
            try:
                candidate = parse_release_candidate(self.discogs.get_release(release_id), rec.title)
            except Exception as exc:
                self._record_provider_error('Discogs', exc)
                continue
            mb_release_id = _mb_release_for_candidate(rec, candidate)
            if mb_release_id:
                candidate = replace(candidate, musicbrainz_release_id=mb_release_id)
            candidates.append(candidate)
        return candidates

    def _itunes_candidates(self, track: TrackRecord) -> list[MetadataCandidate]:
        if not self.itunes:
            return []
        candidates: list[MetadataCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for query_track in _text_query_tracks(track):
            if not (query_track.artist and query_track.title):
                continue
            for artist in artist_search_variants(query_track.artist):
                for title in title_search_variants(query_track.title):
                    try:
                        rows = self.itunes.search_tracks(artist, title, limit=8)
                    except Exception as exc:
                        self._record_provider_error('Apple / iTunes', exc)
                        continue
                    for candidate in rows:
                        identity = (
                            (candidate.artist or '').casefold(),
                            (candidate.title or '').casefold(),
                            (candidate.album or '').casefold(),
                        )
                        if identity in seen:
                            continue
                        seen.add(identity)
                        candidates.append(_score_text_fallback(track, candidate))
                    if candidates:
                        break
                if candidates:
                    break
            if candidates:
                break
        return candidates

    def identify(self, track: TrackRecord) -> IdentificationOutcome:
        self._provider_errors = []
        record_rows: list[tuple[MusicBrainzRecording, float | None]] = self._records_from_fingerprint(track)
        if not record_rows:
            record_rows = self._records_from_text(track)

        best: MetadataCandidate | None = None
        best_mbid: str | None = None
        source_best: dict[str, MetadataCandidate] = {}
        for rec, acoustid_score in record_rows[:5]:
            mb_scored = _score_with_recording_evidence(track, _musicbrainz_candidate(rec), rec, acoustid_score)
            previous_mb = source_best.get('musicbrainz')
            if previous_mb is None or mb_scored.score > previous_mb.score:
                source_best['musicbrainz'] = mb_scored

            candidates = self._discogs_candidates(rec)
            if not candidates:
                candidates = [_musicbrainz_candidate(rec)]
            for candidate in candidates:
                scored = _score_with_recording_evidence(track, candidate, rec, acoustid_score)
                previous = source_best.get(scored.source)
                if previous is None or scored.score > previous.score:
                    source_best[scored.source] = scored
                if best is None or scored.score > best.score:
                    best = scored
                    best_mbid = rec.recording_id

        # Apple/iTunes is keyless and useful as corroboration / cover source.
        # It never replaces a stronger MusicBrainz/Discogs version match.
        apple_candidates = self._itunes_candidates(track)
        if apple_candidates:
            apple_best = max(apple_candidates, key=lambda candidate: candidate.score)
            source_best['apple'] = apple_best
            if best is None and apple_best.score >= 0.70:
                best = apple_best

        # Last-resort Discogs lookup for already named/tagged files when
        # MusicBrainz found nothing. Try non-destructive cleaned title variants
        # before declaring that the release does not exist.
        if best is None and self.discogs:
            for query_track in _text_query_tracks(track):
                if not (query_track.artist and query_track.title):
                    continue
                for search_artist in artist_search_variants(query_track.artist):
                    for search_title in title_search_variants(query_track.title):
                        try:
                            release_ids = self.discogs.search_release_ids(search_artist, search_title, limit=8)
                        except Exception as exc:
                            self._record_provider_error('Discogs', exc)
                            continue
                        for release_id in release_ids:
                            try:
                                candidate = parse_release_candidate(self.discogs.get_release(release_id), search_title)
                            except Exception as exc:
                                self._record_provider_error('Discogs', exc)
                                continue
                            scored = _score_text_fallback(track, candidate)
                            previous = source_best.get('discogs')
                            if previous is None or scored.score > previous.score:
                                source_best['discogs'] = scored
                            if best is None or scored.score > best.score:
                                best = scored
                        if best is not None:
                            break
                    if best is not None:
                        break
                if best is not None:
                    break

        if best is None:
            if self._provider_errors:
                raise ProviderLookupError(self._provider_errors)
            return IdentificationOutcome(track, None, 'uncertain')
        for candidate in source_best.values():
            _remember_candidate_values(track, candidate)
        apply_candidate(track, best, source_recording_id=best_mbid)
        return IdentificationOutcome(track, best, decision_for_score(best.score))
