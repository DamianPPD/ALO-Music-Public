from __future__ import annotations

from collections.abc import Iterable

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.naming import propose_filename, normalize_title_case
from audio_library_organizer.metadata.genre import normalize_genre_list
from audio_library_organizer.metadata.completeness import core_metadata_complete

_ALLOWED_FIELDS = {'artist', 'title', 'album', 'year', 'genre', 'comment', 'bpm', 'discogs_url', 'filename_override'}


def apply_manual_field(tracks: Iterable[TrackRecord], field_name: str, value, *, lock: bool = True, source: str = 'Ręcznie') -> None:
    if field_name not in _ALLOWED_FIELDS:
        raise ValueError(f'Nie można ręcznie zmieniać pola: {field_name}')
    if field_name == 'genre':
        value = normalize_genre_list(value)
    elif field_name == 'title':
        value = normalize_title_case(value)
    for track in tracks:
        setattr(track, field_name, value)
        if lock:
            track.locked_fields.add(field_name)
            if hasattr(track, 'field_sources'):
                track.field_sources[field_name] = source or 'Ręcznie'
            if hasattr(track, 'field_source_values') and value not in (None, ''):
                track.field_source_values.setdefault(field_name, {})[source or 'Ręcznie'] = value
        else:
            track.locked_fields.discard(field_name)
        if field_name in {'artist', 'title', 'album', 'year', 'genre', 'bpm', 'filename_override'}:
            track.proposed_filename = propose_filename(track)
        if track.status not in {'duplicate', 'not_selected', 'error'}:
            track.status = 'ready' if core_metadata_complete(track) else 'review'


def approve_as_ready(track: TrackRecord) -> None:
    track.status = 'ready' if core_metadata_complete(track) else 'review'
    track.locked_fields.add('__status__')
    marker = 'Ręcznie zatwierdzone przez użytkownika'
    if marker not in track.match_reasons:
        track.match_reasons.append(marker)
    track.proposed_filename = propose_filename(track)



def promote_duplicate_as_version(track: TrackRecord, *, approve: bool = False) -> None:
    """Detach one candidate from duplicate handling and keep it as its own musical version.

    This never changes the status of any other file in the group. The user can
    edit title/version metadata first and then approve this track independently.
    """
    track.locked_fields.discard('duplicate_primary')
    track.locked_fields.add('separate_version')
    track.status = 'review'
    marker = 'Zachowane ręcznie jako osobna wersja z grupy duplikatów'
    if marker not in track.match_reasons:
        track.match_reasons.append(marker)
    track.proposed_filename = propose_filename(track)
    if approve:
        approve_as_ready(track)

def apply_duplicate_group_edits(group, selected: TrackRecord, values: dict[str, object], *, manual_cover_path: str | None = None, approve: bool = False) -> None:
    """Edit metadata once for one same-audio duplicate group.

    The chosen primary remains the only non-duplicate copy. All shared metadata
    is applied to every encoding/copy so later manual comparison stays coherent.
    """
    from audio_library_organizer.duplicates.grouper import apply_manual_primary

    items = list(group)
    apply_manual_primary(items, selected)
    for field_name, value in values.items():
        if field_name == 'filename_override':
            continue
        apply_manual_field(items, field_name, value, lock=True)
    if values.get('filename_override'):
        apply_manual_field([selected], 'filename_override', values['filename_override'], lock=True)
    if manual_cover_path is not None:
        for track in items:
            track.manual_cover_path = manual_cover_path
            track.has_cover = bool(manual_cover_path)
            track.locked_fields.add('cover')
    if approve:
        approve_as_ready(selected)
        for track in items:
            if track is not selected:
                track.status = 'duplicate'
