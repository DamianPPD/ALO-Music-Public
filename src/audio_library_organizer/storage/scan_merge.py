"""Conservative merge of scanner observations into the latest durable work."""
from __future__ import annotations

from copy import deepcopy

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.naming import propose_filename

SCAN_AUDIO_KEY = '__alo_scan_audio_v1__'
SCAN_STAT_KEY = '__alo_scan_stat_v1__'
SCAN_CONFLICT = 'scan: Zmienione lub niepotwierdzone audio pod zapisanym locatorem; zachowano dane biblioteki.'
SCANNER_SOURCES = {'Tag', 'Nazwa pliku', 'Analiza audio'}


def stat_observation(stat) -> dict[str, int]:
    return {'device': stat.st_dev, 'inode': stat.st_ino, 'ctime_ns': stat.st_ctime_ns,
            'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def audio_continuity_confirmed(current: TrackRecord, observed: TrackRecord) -> bool:
    if current.sha256 and current.sha256 == observed.sha256:
        return True
    old_audio = current.original_tags.get(SCAN_AUDIO_KEY)
    new_audio = observed.original_tags.get(SCAN_AUDIO_KEY)
    # A Chromaprint match alone never establishes record ownership. Legacy
    # records without an audio observation stay conservative when bytes change.
    return bool(old_audio and isinstance(old_audio, dict) and old_audio == new_audio)


def merge_scan_metadata(current: TrackRecord, observed: TrackRecord, baseline: TrackRecord) -> TrackRecord:
    merged = deepcopy(current)
    for field in ('size_bytes', 'mtime_ns', 'duration_seconds', 'bitrate_kbps',
                  'sample_rate_hz', 'channels', 'codec', 'sha256'):
        value = getattr(observed, field)
        if value is not None:
            setattr(merged, field, value)
    for field in ('fingerprint', 'fingerprint_duration'):
        if getattr(observed, field) is not None:
            setattr(merged, field, getattr(observed, field))
    merged.is_available = True
    for field in ('artist', 'title', 'album', 'year', 'genre', 'bpm', 'comment'):
        # Always retain the user's values and other providers' candidate JSON.
        candidates = observed.field_source_values.get(field, {})
        merged.field_source_values.setdefault(field, {}).update(deepcopy(candidates))
        selected_source = current.field_sources.get(field, '')
        value = getattr(observed, field)
        changed_during_scan = (
            getattr(current, field) != getattr(baseline, field) or
            current.field_sources.get(field) != baseline.field_sources.get(field) or
            current.field_source_values.get(field) != baseline.field_source_values.get(field) or
            (field in current.locked_fields) != (field in baseline.locked_fields)
        )
        can_replace = not changed_during_scan and field not in current.locked_fields and (
            selected_source in SCANNER_SOURCES or
            (not selected_source and getattr(current, field) in (None, ''))
        )
        if can_replace and value not in (None, ''):
            setattr(merged, field, value)
            if observed.field_sources.get(field):
                merged.field_sources[field] = observed.field_sources[field]
            if field == 'bpm':
                merged.bpm_raw, merged.bpm_confidence = observed.bpm_raw, observed.bpm_confidence
    if ('cover' not in current.locked_fields and current.cover_choice == 'auto' and not current.manual_cover_path
            and current.has_cover == baseline.has_cover):
        merged.has_cover = observed.has_cover or current.has_cover
    merged.original_tags.update(deepcopy(observed.original_tags))
    # Status, locks, online IDs, chosen cover/name, history and all remaining
    # fields start from the current transaction's record, never the scan snapshot.
    if any(getattr(merged, field) != getattr(current, field)
           for field in ('artist', 'title', 'album', 'year', 'genre', 'bpm')):
        merged.proposed_filename = propose_filename(merged)
    return merged
