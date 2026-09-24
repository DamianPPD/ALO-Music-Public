from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from audio_library_organizer.metadata.completeness import core_checks, optional_checks, core_metadata_complete, has_real_cover
from audio_library_organizer.metadata.genre import genre_items
from audio_library_organizer.jobs.file_health import file_health_reasons



def save_app_settings(store, settings) -> None:
    store.setValue('sources', json.dumps([str(p) for p in settings.source_dirs], ensure_ascii=False))
    store.setValue('library_root', str(settings.library.root))



def load_app_settings(store):
    from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
    raw_sources = store.value('sources', '')
    raw_library = str(store.value('library_root', '') or '').strip()
    if not raw_sources or not raw_library:
        return None
    try:
        if isinstance(raw_sources, str):
            sources_data = json.loads(raw_sources)
        else:
            sources_data = list(raw_sources)
        sources = tuple(Path(item) for item in sources_data if str(item).strip())
        if not sources:
            return None
        settings = AppSettings(sources, LibraryPaths(Path(raw_library)))
        settings.library.ensure_created()
        return settings
    except Exception:
        return None

def reset_folder_preferences(store) -> None:
    # Only forget the app's remembered folder choices. This intentionally
    # never removes or modifies any file/folder on disk.
    store.remove('sources')
    store.remove('library_root')


def build_library_root(parent: Path, name: str) -> Path:
    clean = name.strip()
    if not clean:
        raise ValueError('Podaj nazwę folderu biblioteki.')
    if any(ch in clean for ch in '<>:"/\\|?*'):
        raise ValueError('Nazwa folderu zawiera niedozwolone znaki.')
    return (Path(parent).expanduser() / clean).resolve()


def filter_track_rows(rows: list[dict], query: str, *, status: str | None = None) -> list[dict]:
    needle = query.casefold().strip()
    result: list[dict] = []
    for row in rows:
        if status and row.get('status') != status:
            continue
        if needle:
            haystack = ' '.join(str(row.get(key, '')) for key in ('artist','title','album','genre','status','filename')).casefold()
            if needle not in haystack:
                continue
        result.append(row)
    return result


@dataclass(frozen=True, slots=True)
class DuplicatePlaybackState:
    index: int = 0
    position_ms: int = 0

    def switch_to(self, index: int, target_duration_ms: int | None = None) -> 'DuplicatePlaybackState':
        position = self.position_ms
        if target_duration_ms is not None and target_duration_ms > 0:
            position = min(position, max(0, target_duration_ms - 500))
        return DuplicatePlaybackState(index=index, position_ms=position)



def should_autosize_table(row_count: int, threshold: int = 300) -> bool:
    return row_count <= threshold



@dataclass(frozen=True, slots=True)
class StatusPresentation:
    label: str
    background: str
    accent: str
    foreground: str = '#eef2f7'


def status_presentation(status: str) -> StatusPresentation:
    mapping = {
        'ready': StatusPresentation('GOTOWE', '#173c2d', '#43d17d'),
        'review': StatusPresentation('DO SPRAWDZENIA', '#4a3517', '#ffb84d'),
        'duplicate': StatusPresentation('DUPLIKAT', '#39244d', '#b987ff'),
        'not_selected': StatusPresentation('NIE WYBIERAM', '#2a3038', '#a8b1bd'),
        'error': StatusPresentation('BŁĄD', '#4a2022', '#ff7777'),
    }
    return mapping.get(status, StatusPresentation(status.upper() or '—', '#202732', '#7f8da1'))



def suspicious_data_reasons(track) -> list[str]:
    reasons: list[str] = []
    bpm = getattr(track, 'bpm', None)
    if bpm is not None:
        try:
            value = float(bpm)
        except (TypeError, ValueError):
            value = None
        if value is not None and (value < 80 or value > 200):
            reasons.append('Podejrzane BPM')
    match_reasons = getattr(track, 'match_reasons', ()) or ()
    if any(('duża różnica' in str(reason).casefold()) or ('konflikt' in str(reason).casefold()) for reason in match_reasons):
        reasons.append('Sprzeczne dane online')
    # Technical health flags are meaningful only after an audio file has actually
    # been scanned. Synthetic/manual records may legitimately omit codec/size.
    path = Path(getattr(track, 'path', ''))
    has_scan_technical_data = path.is_file() and bool(
        (getattr(track, 'size_bytes', 0) or 0) > 0
        or getattr(track, 'duration_seconds', None) is not None
        or getattr(track, 'codec', None)
    )
    if has_scan_technical_data:
        reasons.extend(file_health_reasons(track, check_filesystem=False))
    return list(dict.fromkeys(reasons))

def effective_status(track) -> str:
    status = getattr(track, 'status', '') or 'review'
    if status in {'duplicate', 'not_selected', 'error'}:
        return status
    if status == 'ready' and not core_metadata_complete(track):
        return 'review'
    if status == 'ready':
        locked = getattr(track, 'locked_fields', set()) or set()
        # A deliberate user approval is authoritative once the required fields
        # are complete. Historical online warnings remain visible as context,
        # but they must not silently reopen the review state.
        if '__status__' in locked:
            return 'ready'
        confidence = getattr(track, 'confidence', None)
        if confidence is not None and float(confidence) < 0.65:
            return 'review'
        if suspicious_data_reasons(track):
            return 'review'
    if status not in {'ready', 'review'}:
        return 'review'
    return status


def review_severity(track) -> str:
    """Return visual priority for DO SPRAWDZENIA without adding a new status.

    ``critical`` is intentionally reserved for cases that are genuinely hard
    to use safely: missing artist/title, very low confidence, invalid/empty
    audio, or an explicitly severe conflict. Everything else remains the
    normal amber review state.
    """
    if effective_status(track) != 'review':
        return 'none'
    if not getattr(track, 'artist', None) or not getattr(track, 'title', None):
        return 'critical'
    confidence = getattr(track, 'confidence', None)
    if confidence is not None and float(confidence) < 0.40:
        return 'critical'
    severe_health = {'Nieprawidłowa długość audio', 'Pusty plik', 'Plik niedostępny'}
    if severe_health.intersection(file_health_reasons(track, check_filesystem=False)):
        return 'critical'
    match_reasons = [str(reason).casefold() for reason in (getattr(track, 'match_reasons', ()) or ())]
    if any('poważny konflikt' in reason or 'krytyczny konflikt' in reason for reason in match_reasons):
        return 'critical'
    return 'normal'


def library_status_presentation(track) -> StatusPresentation:
    status = effective_status(track)
    if status == 'review' and review_severity(track) == 'critical':
        return StatusPresentation('DO SPRAWDZENIA', '#4a2022', '#ff7777')
    return status_presentation(status)


def library_status_text(track) -> str:
    return library_status_presentation(track).label


def display_bpm(value) -> str:
    if value is None:
        return ''
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return ''


def export_needs_library_review(summary: dict[str, int]) -> bool:
    return int(summary.get('review', 0) or 0) > 0


def should_refresh_live_scan(current: int, total: int, every: int = 5) -> bool:
    if current <= 1 or current >= total:
        return True
    return current % max(1, every) == 0


def confidence_label(track) -> str:
    confidence = getattr(track, 'confidence', None)
    if confidence is None:
        return '—'
    percent = round(float(confidence) * 100)
    if confidence >= 0.90:
        return f'{percent}% — bardzo pewne'
    if confidence >= 0.65:
        return f'{percent}% — sprawdź wersję'
    return f'{percent}% — wymaga sprawdzenia'


def review_reasons(track) -> list[str]:
    """Explain why a track is currently in DO SPRAWDZENIA.

    Reasons are intentionally empty for every other status, including a
    manually approved GOTOWE track. This keeps one clear attention workflow.
    """
    if effective_status(track) != 'review':
        return []
    reasons: list[str] = ['Status DO SPRAWDZENIA']
    missing_core = [label for label, ok in core_checks(track) if not ok]
    for label in missing_core:
        reasons.append(f'Brak: {label}')
    confidence = getattr(track, 'confidence', None)
    if confidence is not None and confidence < 0.65:
        reasons.append('Niska pewność rozpoznania')
    reasons.extend(suspicious_data_reasons(track))
    return list(dict.fromkeys(reasons))


def review_queue(tracks) -> list:
    return sorted(
        (track for track in tracks if effective_status(track) == 'review'),
        key=lambda track: (0 if review_severity(track) == 'critical' else 1, str(getattr(track, 'path', '')).casefold()),
    )


def track_matches_quick_filter(track, key: str) -> bool:
    key = (key or 'all').casefold()
    status = effective_status(track)
    if key == 'all':
        return True
    if key == 'no_cover':
        return not has_real_cover(track)
    if key == 'no_year':
        return not bool(getattr(track, 'year', None))
    if key == 'duplicate':
        return status == 'duplicate'
    if key == 'ready':
        return status == 'ready'
    if key == 'review':
        return status == 'review'
    if key == 'not_selected':
        return status == 'not_selected'
    if key == 'manual':
        return bool(getattr(track, 'locked_fields', set()) or set())
    return True



def track_matches_library_filters(track, *, genres_text: str = '', bpm_min=None, bpm_max=None) -> bool:
    if not getattr(track, 'is_available', True):
        return False
    requested = {item.casefold() for item in genre_items(genres_text, limit=50)}
    actual = {item.casefold() for item in genre_items(getattr(track, 'genre', None), limit=50)}
    if requested and not requested.issubset(actual):
        return False
    bpm = getattr(track, 'bpm', None)
    try:
        low = None if bpm_min in (None, '') else float(bpm_min)
    except (TypeError, ValueError):
        low = None
    try:
        high = None if bpm_max in (None, '') else float(bpm_max)
    except (TypeError, ValueError):
        high = None
    if low is not None or high is not None:
        if bpm is None:
            return False
        try:
            value = float(bpm)
        except (TypeError, ValueError):
            return False
        if low is not None and value < low:
            return False
        if high is not None and value > high:
            return False
    return True

def identification_summary(track) -> dict[str, str]:
    sources: list[str] = []
    if getattr(track, 'discogs_release_id', None):
        sources.append(f'Discogs Release {track.discogs_release_id}')
    if getattr(track, 'musicbrainz_recording_id', None):
        sources.append(f'MusicBrainz {track.musicbrainz_recording_id}')
    confidence = getattr(track, 'confidence', None)
    match_reasons = list(getattr(track, 'match_reasons', []) or [])
    if match_reasons:
        reasons = ' · '.join(match_reasons)
    elif confidence is None and not sources:
        reasons = 'Rozpoznawanie online nie zostało jeszcze uruchomione dla tego pliku.'
    else:
        reasons = 'Brak dodatkowych szczegółów dopasowania.'
    return {
        'confidence': confidence_label(track),
        'sources': ' · '.join(sources) if sources else 'Dane lokalne / nierozpoznane online',
        'reasons': reasons,
    }


def metadata_completeness(track) -> dict[str, object]:
    core = core_checks(track)
    optional = optional_checks(track)
    confirmed_core = [label for label, ok in core if ok]
    missing_core = [label for label, ok in core if not ok]
    confirmed_optional = [label for label, ok in optional if ok]
    missing_optional = [label for label, ok in optional if not ok]
    return {
        'confirmed': confirmed_core,
        'missing': missing_core,
        'confirmed_core': confirmed_core,
        'missing_core': missing_core,
        'confirmed_optional': confirmed_optional,
        'missing_optional': missing_optional,
        'ready_for_manual_approval': not missing_core,
    }
