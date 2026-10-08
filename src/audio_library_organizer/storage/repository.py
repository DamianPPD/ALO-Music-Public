from __future__ import annotations

import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from audio_library_organizer.domain.models import TrackRecord
from .database import connect, require_current_schema
from .migrations import migrate_library
from .scan_merge import SCAN_AUDIO_KEY, SCAN_CONFLICT, SCAN_STAT_KEY, audio_continuity_confirmed, merge_scan_metadata, stat_observation
from .source_registry import SourceRoot, canonical_locator, list_sources, match_source, write_sources


@dataclass(frozen=True, slots=True)
class AvailabilitySummary:
    total: int
    available: int
    missing: int
    purged: int = 0


@dataclass(frozen=True, slots=True)
class ScanSnapshot:
    locator: str
    track: TrackRecord | None
    source_id: str | None
    source_relative_path: str | None


class LibraryRepository:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        with closing(connect(self.database_path)) as conn:
            migrate_library(conn, self.database_path)

    @property
    def library_id(self) -> str:
        with closing(connect(self.database_path)) as conn:
            require_current_schema(conn)
            return conn.execute('SELECT library_id FROM library_metadata WHERE singleton=1').fetchone()[0]

    @property
    def sources_initialized(self) -> bool:
        with closing(connect(self.database_path)) as conn:
            require_current_schema(conn)
            return bool(conn.execute('SELECT sources_initialized FROM library_metadata WHERE singleton=1').fetchone()[0])

    def list_sources(self, *, active_only: bool = False) -> list[SourceRoot]:
        with closing(connect(self.database_path)) as conn:
            require_current_schema(conn)
            return list_sources(conn, active_only=active_only)

    def bootstrap_sources(self, roots) -> None:
        """Import legacy profile roots once; a stale cache cannot seed them again."""
        with closing(connect(self.database_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            require_current_schema(conn)
            initialized = conn.execute('SELECT sources_initialized FROM library_metadata WHERE singleton=1').fetchone()[0]
            if not initialized:
                write_sources(conn, roots, replace=True)

    def replace_sources(self, roots) -> None:
        """Change active scan roots, retaining identities and every track."""
        with closing(connect(self.database_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            require_current_schema(conn)
            write_sources(conn, roots, replace=True)

    def register_source(self, root: str | Path) -> SourceRoot:
        key = canonical_locator(root)[1]
        with closing(connect(self.database_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            require_current_schema(conn)
            write_sources(conn, (root,), replace=False)
            registered = next(source for source in list_sources(conn) if source.canonical_root_key == key)
        return registered

    @staticmethod
    def _find_locator(conn, locator):
        key = canonical_locator(locator)[1]
        matches = conn.execute('SELECT * FROM tracks WHERE path_key=? LIMIT 2', (key,)).fetchall()
        if len(matches) > 1:
            raise ValueError('Ambiguous track locator; no identity was selected.')
        return matches[0] if matches else None

    def upsert_track(self, track: TrackRecord) -> None:
        with closing(connect(self.database_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            require_current_schema(conn)
            self._write_track(conn, track)

    def _write_track(self, conn, track: TrackRecord, *, bind_source: bool = True) -> None:
        values = (
            canonical_locator(track.path)[0], track.size_bytes, track.mtime_ns,
            track.duration_seconds, track.bitrate_kbps, track.sample_rate_hz,
            track.channels, track.codec, track.artist, track.title, track.album,
            track.year, track.genre, track.bpm, track.bpm_raw, track.bpm_confidence, track.fingerprint, track.fingerprint_duration, track.comment, int(track.has_cover),
            track.sha256, track.status, track.confidence, track.proposed_filename, track.filename_override,
            json.dumps(track.original_tags, ensure_ascii=False),
            track.discogs_release_id, track.discogs_url, track.musicbrainz_recording_id,
            track.musicbrainz_release_id, track.cover_art_url, track.manual_cover_path, track.cover_choice, json.dumps(track.match_reasons, ensure_ascii=False),
            json.dumps(sorted(track.locked_fields), ensure_ascii=False),
            json.dumps(track.pre_online_metadata, ensure_ascii=False),
            json.dumps(track.field_sources, ensure_ascii=False),
            json.dumps(track.field_source_values, ensure_ascii=False),
            json.dumps(track.audio_recognition, ensure_ascii=False),
            int(track.is_available),
        )
        track_id = track.track_id
        if track_id is None:
            # Transitional callers still construct a record from a locator.
            existing = self._find_locator(conn, values[0])
            track_id = existing['track_id'] if existing else str(uuid4())
        UUID(track_id)
        conn.execute('''
            INSERT INTO tracks (
                track_id,path_key,path,size_bytes,mtime_ns,duration_seconds,bitrate_kbps,sample_rate_hz,
                channels,codec,artist,title,album,year,genre,bpm,bpm_raw,bpm_confidence,fingerprint,fingerprint_duration,comment,has_cover,
                sha256,status,confidence,proposed_filename,filename_override,original_tags_json,
                discogs_release_id,discogs_url,musicbrainz_recording_id,musicbrainz_release_id,cover_art_url,manual_cover_path,cover_choice,match_reasons_json,locked_fields_json,pre_online_metadata_json,field_sources_json,field_source_values_json,audio_recognition_json,is_available
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(track_id) DO UPDATE SET
                path=excluded.path, path_key=excluded.path_key, size_bytes=excluded.size_bytes, mtime_ns=excluded.mtime_ns,
                duration_seconds=excluded.duration_seconds, bitrate_kbps=excluded.bitrate_kbps,
                sample_rate_hz=excluded.sample_rate_hz, channels=excluded.channels,
                codec=excluded.codec, artist=excluded.artist, title=excluded.title,
                album=excluded.album, year=excluded.year, genre=excluded.genre,
                bpm=excluded.bpm, bpm_raw=excluded.bpm_raw, bpm_confidence=excluded.bpm_confidence,
                fingerprint=excluded.fingerprint, fingerprint_duration=excluded.fingerprint_duration,
                comment=excluded.comment, has_cover=excluded.has_cover,
                sha256=excluded.sha256, status=excluded.status,
                confidence=excluded.confidence, proposed_filename=excluded.proposed_filename, filename_override=excluded.filename_override,
                original_tags_json=excluded.original_tags_json,
                discogs_release_id=excluded.discogs_release_id, discogs_url=excluded.discogs_url,
                musicbrainz_recording_id=excluded.musicbrainz_recording_id, musicbrainz_release_id=excluded.musicbrainz_release_id,
                cover_art_url=excluded.cover_art_url, manual_cover_path=excluded.manual_cover_path, cover_choice=excluded.cover_choice, match_reasons_json=excluded.match_reasons_json,
                locked_fields_json=excluded.locked_fields_json,
                pre_online_metadata_json=excluded.pre_online_metadata_json,
                field_sources_json=excluded.field_sources_json,
                field_source_values_json=excluded.field_source_values_json,
                audio_recognition_json=excluded.audio_recognition_json,
                is_available=excluded.is_available
        ''', (track_id, canonical_locator(values[0])[1], *values))
        if bind_source:
            source_id, relative = match_source(values[0], list_sources(conn))
        else:
            source_id, relative = track.source_id, track.source_relative_path
        conn.execute('UPDATE tracks SET source_id=?,source_relative_path=? WHERE track_id=?',
                     (source_id, relative, track_id))
        track.track_id = track_id
        track.source_id = source_id
        track.source_relative_path = relative

    def get_track(self, track_id: str) -> TrackRecord | None:
        with closing(connect(self.database_path)) as conn:
            row = conn.execute('SELECT * FROM tracks WHERE track_id=?', (track_id,)).fetchone()
        return self._row_to_track(row) if row is not None else None

    def scan_snapshot(self, path: Path) -> ScanSnapshot:
        """Capture identity and ownership before any slow scanner work."""
        locator = canonical_locator(path)[0]
        with closing(connect(self.database_path)) as conn:
            require_current_schema(conn)
            row = self._find_locator(conn, locator)
            track = self._row_to_track(row) if row is not None else None
            binding = (track.source_id, track.source_relative_path) if track else match_source(locator, list_sources(conn))
        return ScanSnapshot(locator, track, *binding)

    def merge_scan_track(self, observed: TrackRecord, snapshot: ScanSnapshot, *, observations_only: bool = False) -> TrackRecord | None:
        """Commit one observation without resurrecting or taking over a record.

        None means ambiguous audio: only the diagnostic was saved. A stale
        identity/observation raises before any writes. Manual edits are read
        inside BEGIN IMMEDIATE and merged rather than replaced by the snapshot.
        """
        with closing(connect(self.database_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            require_current_schema(conn)
            if canonical_locator(observed.path)[0] != snapshot.locator:
                raise ValueError('Scan locator changed during processing.')
            if observed.original_tags.get(SCAN_STAT_KEY) != stat_observation(observed.path.stat()):
                raise ValueError('File changed before the scan write transaction.')
            baseline = snapshot.track
            if baseline is None:
                if self._find_locator(conn, snapshot.locator) is not None:
                    raise ValueError('A record was created at this locator during the scan.')
                if match_source(snapshot.locator, list_sources(conn)) != (snapshot.source_id, snapshot.source_relative_path):
                    raise ValueError('Scan source binding changed during processing.')
                observed.source_id, observed.source_relative_path = snapshot.source_id, snapshot.source_relative_path
                self._write_track(conn, observed, bind_source=False)
                return observed
            row = conn.execute('SELECT * FROM tracks WHERE track_id=?', (baseline.track_id,)).fetchone()
            if row is None:
                raise ValueError('Scanned record was deleted during processing.')
            current = self._row_to_track(row)
            if (str(current.path), current.source_id, current.source_relative_path) != (
                    snapshot.locator, snapshot.source_id, snapshot.source_relative_path):
                raise ValueError('Scanned record locator or source changed during processing.')
            if (current.size_bytes, current.mtime_ns, current.sha256) != (
                    baseline.size_bytes, baseline.mtime_ns, baseline.sha256):
                raise ValueError('A newer scan observation has already been saved.')
            owner = self._find_locator(conn, snapshot.locator)
            if owner is None or owner['track_id'] != baseline.track_id:
                raise ValueError('Scan locator ownership changed during processing.')
            if ((observations_only and current.sha256 != observed.sha256)
                    or not audio_continuity_confirmed(current, observed)):
                if SCAN_CONFLICT not in current.match_reasons:
                    reasons = [*current.match_reasons, SCAN_CONFLICT]
                    conn.execute('UPDATE tracks SET match_reasons_json=? WHERE track_id=?',
                                 (json.dumps(reasons, ensure_ascii=False), current.track_id))
                return None
            if observations_only:
                # One-time upgrade of a legacy scan observation. Do not read
                # tags again or rewrite metadata merely to remember stat data.
                for key in (SCAN_STAT_KEY, SCAN_AUDIO_KEY):
                    if key in observed.original_tags:
                        current.original_tags[key] = observed.original_tags[key]
                current.is_available = True
                current.match_reasons = [reason for reason in current.match_reasons if reason != SCAN_CONFLICT]
                conn.execute('UPDATE tracks SET original_tags_json=?,is_available=1,match_reasons_json=? WHERE track_id=?',
                             (json.dumps(current.original_tags, ensure_ascii=False),
                              json.dumps(current.match_reasons, ensure_ascii=False), current.track_id))
                return current
            merged = merge_scan_metadata(current, observed, baseline)
            merged.match_reasons = [reason for reason in merged.match_reasons if reason != SCAN_CONFLICT]
            self._write_track(conn, merged, bind_source=False)
            return merged

    def reconcile_scan_duplicates(self, roots, *, excluded_ids=(), incomplete_context: bool = False) -> None:
        """Re-read decisions atomically and write only changed classifications."""
        from audio_library_organizer.duplicates.grouper import mark_duplicate_statuses

        excluded = set(excluded_ids)
        with closing(connect(self.database_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            require_current_schema(conn)
            tracks = []
            for row in conn.execute('SELECT * FROM tracks'):
                track = self._row_to_track(row)
                try:
                    if not any(track.path.is_relative_to(root) for root in roots):
                        continue
                    if (track.track_id in excluded or SCAN_CONFLICT in track.match_reasons
                            or not track.is_available or not track.path.is_file()):
                        incomplete_context = True
                        continue
                    tracks.append(track)
                except (OSError, RuntimeError, ValueError):
                    incomplete_context = True
                    continue
            before = {track.track_id: (track.status, list(track.match_reasons)) for track in tracks}
            # Older not_selected decisions may predate the status lock. Respect
            # that category too; the extra marker exists only in these copies.
            for track in tracks:
                if track.status == 'not_selected':
                    track.locked_fields.add('__status__')
            mark_duplicate_statuses(tracks)
            for track in tracks:
                if incomplete_context and before[track.track_id][0] == 'duplicate':
                    track.status = 'duplicate'
                if (track.status, track.match_reasons) != before[track.track_id]:
                    conn.execute('UPDATE tracks SET status=?,match_reasons_json=? WHERE track_id=?',
                                 (track.status, json.dumps(track.match_reasons, ensure_ascii=False), track.track_id))

    def list_tracks(self, *, status: str | None = None, available_only: bool = False) -> list[TrackRecord]:
        query = 'SELECT * FROM tracks'
        clauses: list[str] = []
        args_list: list[object] = []
        if status is not None:
            clauses.append('status = ?')
            args_list.append(status)
        if available_only:
            clauses.append('is_available = 1')
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        args = tuple(args_list)
        query += ' ORDER BY path COLLATE NOCASE'
        with closing(connect(self.database_path)) as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._row_to_track(row) for row in rows]

    def sync_availability(self, *, purge_missing: bool = False) -> AvailabilitySummary:
        tracks = self.list_tracks()
        available = 0
        missing = 0
        missing_ids: list[tuple[str, str]] = []
        updates: list[tuple[int, str, str]] = []
        for track in tracks:
            exists = track.path.is_file()
            if exists:
                available += 1
            else:
                missing += 1
                missing_ids.append((track.track_id, str(track.path)))
            if exists != track.is_available:
                updates.append((int(exists), track.track_id, str(track.path)))

        purged = 0
        with closing(connect(self.database_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            require_current_schema(conn)
            if updates:
                # A filesystem observation is valid only for the locator read.
                # Another writer may have moved the same UUID in the meantime.
                conn.executemany('UPDATE tracks SET is_available=? WHERE track_id=? AND path=?', updates)
            if purge_missing and missing_ids:
                deleted = conn.executemany('DELETE FROM tracks WHERE track_id=? AND path=?', missing_ids)
                purged = deleted.rowcount
        return AvailabilitySummary(total=len(tracks), available=available, missing=missing, purged=purged)

    def purge_missing(self) -> int:
        with closing(connect(self.database_path)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            require_current_schema(conn)
            row = conn.execute('SELECT COUNT(*) AS count FROM tracks WHERE is_available = 0').fetchone()
            count = int(row['count'] if row else 0)
            conn.execute('DELETE FROM tracks WHERE is_available = 0')
        return count

    def scan_needed(self, path: Path, size_bytes: int, mtime_ns: int) -> bool:
        with closing(connect(self.database_path)) as conn:
            row = self._find_locator(conn, canonical_locator(path)[0])
        return row is None or row['size_bytes'] != size_bytes or row['mtime_ns'] != mtime_ns

    @staticmethod
    def _row_to_track(row) -> TrackRecord:
        return TrackRecord(
            path=Path(row['path']), size_bytes=row['size_bytes'], mtime_ns=row['mtime_ns'],
            duration_seconds=row['duration_seconds'], bitrate_kbps=row['bitrate_kbps'],
            sample_rate_hz=row['sample_rate_hz'], channels=row['channels'], codec=row['codec'],
            artist=row['artist'], title=row['title'], album=row['album'], year=row['year'],
            genre=row['genre'], bpm=row['bpm'], bpm_raw=row['bpm_raw'], bpm_confidence=row['bpm_confidence'],
            fingerprint=row['fingerprint'], fingerprint_duration=row['fingerprint_duration'], comment=row['comment'],
            has_cover=bool(row['has_cover']), sha256=row['sha256'], status=row['status'],
            confidence=row['confidence'], proposed_filename=row['proposed_filename'], filename_override=row['filename_override'],
            original_tags=json.loads(row['original_tags_json'] or '{}'),
            discogs_release_id=row['discogs_release_id'], discogs_url=row['discogs_url'],
            musicbrainz_recording_id=row['musicbrainz_recording_id'], musicbrainz_release_id=row['musicbrainz_release_id'],
            cover_art_url=row['cover_art_url'], manual_cover_path=row['manual_cover_path'], cover_choice=row['cover_choice'], match_reasons=json.loads(row['match_reasons_json'] or '[]'),
            locked_fields=set(json.loads(row['locked_fields_json'] or '[]')),
            pre_online_metadata=json.loads(row['pre_online_metadata_json'] or '{}'),
            field_sources=json.loads(row['field_sources_json'] or '{}'),
            field_source_values=json.loads(row['field_source_values_json'] or '{}'),
            audio_recognition=json.loads(row['audio_recognition_json'] or '{}'),
            is_available=bool(row['is_available']),
            track_id=row['track_id'],
            source_id=row['source_id'], source_relative_path=row['source_relative_path'],
        )
