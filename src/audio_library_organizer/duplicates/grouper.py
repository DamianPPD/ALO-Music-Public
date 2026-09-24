from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from audio_library_organizer.domain.models import DuplicateKind, TrackRecord
from audio_library_organizer.duplicates.comparator import classify_pair
from audio_library_organizer.duplicates.families import same_version_family
from audio_library_organizer.metadata.completeness import core_metadata_complete


def group_exact_duplicates(tracks: Iterable[TrackRecord]) -> list[list[TrackRecord]]:
    buckets: dict[str, list[TrackRecord]] = defaultdict(list)
    for track in tracks:
        if track.sha256:
            buckets[track.sha256].append(track)
    groups = [sorted(group, key=lambda t: str(t.path).casefold()) for group in buckets.values() if len(group) > 1]
    return sorted(groups, key=lambda g: str(g[0].path).casefold())


def _norm(value: str | None) -> str:
    return ' '.join((value or '').casefold().replace('–', '-').split())


def _same_named_recording(a: TrackRecord, b: TrackRecord) -> bool:
    return bool(a.artist and b.artist and a.title and b.title and _norm(a.artist) == _norm(b.artist) and _norm(a.title) == _norm(b.title))


def _resolved_status_for_keep(track: TrackRecord) -> str:
    return 'ready' if core_metadata_complete(track) else 'review'


def apply_duplicate_decision(track: TrackRecord, decision: str) -> None:
    """Persist one explicit user decision made in the Duplikaty page.

    The status lock prevents later online recognition/duplicate recalculation from
    silently changing what the user chose.
    """
    decision = (decision or '').casefold().strip()
    if decision == 'keep':
        track.status = _resolved_status_for_keep(track)
        track.locked_fields.add('duplicate_primary')
        track.locked_fields.discard('separate_version')
    elif decision == 'duplicate':
        track.status = 'duplicate'
        track.locked_fields.discard('duplicate_primary')
    elif decision == 'not_selected':
        track.status = 'not_selected'
        track.locked_fields.discard('duplicate_primary')
    elif decision == 'review':
        track.status = 'review'
        track.locked_fields.discard('duplicate_primary')
    else:
        raise ValueError(f'Nieznana decyzja duplikatu: {decision}')
    track.locked_fields.add('__status__')


def _potential_duplicate_pairs(items: list[TrackRecord]) -> set[tuple[int, int]]:
    """Return only pairs that can possibly match ``group_potential_duplicates``.

    ``classify_pair`` can only return a non-NONE result for a shared SHA-256,
    fingerprint, MusicBrainz recording ID or exact normalized artist/title.
    Building candidate buckets avoids the previous O(n²) scan of every unrelated
    pair in large libraries.
    """
    buckets: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, track in enumerate(items):
        if track.sha256:
            buckets[('sha', track.sha256)].append(index)
        if track.fingerprint:
            buckets[('fp', track.fingerprint)].append(index)
        if track.musicbrainz_recording_id:
            buckets[('mb', track.musicbrainz_recording_id)].append(index)
        artist = _norm(track.artist)
        title = _norm(track.title)
        if artist and title:
            buckets[('name', artist, title)].append(index)

    pairs: set[tuple[int, int]] = set()
    for indexes in buckets.values():
        for pos, left in enumerate(indexes[:-1]):
            for right in indexes[pos + 1:]:
                pairs.add((left, right))
    return pairs


def group_potential_duplicates(tracks: Iterable[TrackRecord], *, include_resolved: bool = False) -> list[list[TrackRecord]]:
    """Group files worth human comparison, not only certain byte/audio duplicates.

    ``include_resolved`` keeps already-decided groups visible in the Duplikaty page
    so the user can review the green/gray decisions. Pending-work counters keep the
    default ``False`` behavior and therefore count only unresolved groups.

    Same artist/title with materially different duration/BPM is intentionally kept
    in this review grouping because it may be Radio/Extended/Remix rather than trash.
    """
    items = [t for t in tracks if 'separate_version' not in t.locked_fields]
    if len(items) < 2:
        return []
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j in _potential_duplicate_pairs(items):
        left = items[i]
        right = items[j]
        kind = classify_pair(left, right)
        same_external_recording = bool(
            left.musicbrainz_recording_id and right.musicbrainz_recording_id
            and left.musicbrainz_recording_id == right.musicbrainz_recording_id
        )
        # Explicitly named Radio/Extended/Club/etc. versions with materially
        # different audio are a version family, not a duplicate suggestion.
        # Exact bytes / same-audio evidence still wins over naming.
        if same_version_family(left, right) and kind not in {DuplicateKind.IDENTICAL, DuplicateKind.SAME_AUDIO}:
            continue
        if kind != DuplicateKind.NONE or same_external_recording or _same_named_recording(left, right):
            union(i, j)

    grouped: dict[int, list[TrackRecord]] = defaultdict(list)
    for i, track in enumerate(items):
        grouped[find(i)].append(track)
    groups = [
        g for g in grouped.values()
        if len(g) > 1 and (
            include_resolved or not all('__status__' in track.locked_fields for track in g)
        )
    ]
    for group in groups:
        # Human comparison is data-first: do not sort a "recommended" file to the top.
        group.sort(key=lambda t: str(t.path).casefold())
    return sorted(groups, key=lambda g: str(g[0].path).casefold())


def duplicate_group_count(tracks: Iterable[TrackRecord]) -> int:
    """Number of potential duplicate groups currently visible to the user."""
    return len(group_potential_duplicates(tracks))


def group_auto_duplicates(tracks: Iterable[TrackRecord]) -> list[list[TrackRecord]]:
    """Group only safe automatic duplicates: identical bytes or same fingerprint with close duration.

    A shared title is deliberately not enough. A shared fingerprint with a materially different
    duration is also kept out because it may be a radio/extended edit.
    """
    items = list(tracks)
    if len(items) < 2:
        return []

    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, track in enumerate(items):
        if 'separate_version' in track.locked_fields:
            continue
        if track.sha256:
            buckets[('sha', track.sha256)].append(index)
        if track.fingerprint:
            buckets[('fp', track.fingerprint)].append(index)
        if track.musicbrainz_recording_id:
            buckets[('mb', track.musicbrainz_recording_id)].append(index)

    for indexes in buckets.values():
        if len(indexes) < 2:
            continue
        for pos, left in enumerate(indexes[:-1]):
            for right in indexes[pos + 1:]:
                kind = classify_pair(items[left], items[right])
                if kind in (DuplicateKind.IDENTICAL, DuplicateKind.SAME_AUDIO):
                    union(left, right)

    grouped: dict[int, list[TrackRecord]] = defaultdict(list)
    for index, track in enumerate(items):
        grouped[find(index)].append(track)

    groups = [group for group in grouped.values() if len(group) > 1]
    for group in groups:
        # No automatic winner: present candidates in stable path order and let
        # the user decide which one to keep.
        group.sort(key=lambda track: str(track.path).casefold())
    return sorted(groups, key=lambda group: str(group[0].path).casefold())


def duration_delta_label(track: TrackRecord, reference: TrackRecord) -> str:
    """Return signed mm:ss duration difference for quick duplicate-version comparison."""
    if track.duration_seconds is None or reference.duration_seconds is None:
        return '—'
    delta = int(round(track.duration_seconds - reference.duration_seconds))
    sign = '+' if delta > 0 else '-' if delta < 0 else ''
    delta = abs(delta)
    return f'{sign}{delta // 60}:{delta % 60:02d}'


def mark_duplicate_statuses(tracks: Iterable[TrackRecord]) -> list[list[TrackRecord]]:
    items = list(tracks)
    # Reset only automatic duplicate classifications. Explicit user decisions are locked.
    for track in items:
        if '__status__' in track.locked_fields:
            continue
        if track.status == 'duplicate':
            track.status = _resolved_status_for_keep(track)

    groups = group_auto_duplicates(items)
    for group in groups:
        # ALO classifies the group, but never recommends/chooses a winner.
        # A previously explicit manual primary is respected; otherwise every
        # unresolved member stays DUPLIKAT until the user makes decisions.
        locked_primary = next((track for track in group if 'duplicate_primary' in track.locked_fields), None)
        for track in group:
            if '__status__' in track.locked_fields:
                continue
            if locked_primary is not None and track is locked_primary:
                track.status = _resolved_status_for_keep(track)
            else:
                track.status = 'duplicate'

    # Potential same-name / similar-audio versions should never remain silently green.
    # They stay reviewable until the user explicitly chooses GOTOWE/DUPLIKAT/NIE WYBIERAM.
    safe_members = {id(t) for group in groups for t in group}
    for group in group_potential_duplicates(items):
        if all(id(t) in safe_members for t in group):
            continue
        for track in group:
            if '__status__' in track.locked_fields or track.status in {'duplicate', 'not_selected'}:
                continue
            if track.status == 'ready':
                track.status = 'review'
            marker = 'Możliwa inna wersja / potencjalny duplikat — sprawdź w zakładce Duplikaty'
            if marker not in track.match_reasons:
                track.match_reasons.append(marker)
    return groups


def apply_manual_primary(group: Sequence[TrackRecord], selected: TrackRecord) -> None:
    if selected not in group:
        raise ValueError('Wybrany plik nie należy do tej grupy duplikatów.')
    for track in group:
        track.locked_fields.discard('duplicate_primary')
        if track is selected:
            track.status = _resolved_status_for_keep(track)
            track.locked_fields.add('duplicate_primary')
            track.locked_fields.add('__status__')
        else:
            track.status = 'duplicate'
            track.locked_fields.add('__status__')
