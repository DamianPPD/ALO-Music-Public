from __future__ import annotations

import csv
from html import escape
from collections import Counter
from pathlib import Path
from collections.abc import Iterable

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.state import effective_status, review_reasons, suspicious_data_reasons
from audio_library_organizer.ui.i18n import translate_static_text
from audio_library_organizer.metadata.genre import genre_items


def build_operation_summary(tracks: Iterable[TrackRecord]) -> dict[str, int]:
    tracks = list(tracks)
    counts = Counter(effective_status(t) for t in tracks)
    return {
        'total': len(tracks),
        'ready': counts.get('ready', 0),
        'duplicate': counts.get('duplicate', 0),
        'review': counts.get('review', 0),
        'not_selected': counts.get('not_selected', 0),
        'error': counts.get('error', 0),
    }



def build_library_health(tracks: Iterable[TrackRecord]) -> dict[str, object]:
    rows = list(tracks)
    available = [t for t in rows if getattr(t, 'is_available', True)]
    missing = len(rows) - len(available)
    genre_counter = Counter()
    for track in available:
        for item in genre_items(track.genre, limit=50):
            genre_counter[item] += 1
    bpm_values = [float(t.bpm) for t in available if t.bpm is not None]
    covered = sum(1 for t in available if t.has_cover or t.manual_cover_path or t.cover_art_url)
    online = sum(
        1 for t in available
        if (
            t.discogs_release_id
            or t.musicbrainz_recording_id
            or t.musicbrainz_release_id
            or any('Nie znaleziono pewnego dopasowania online' in str(reason) for reason in (t.match_reasons or []))
        )
    )
    ready = sum(1 for t in available if effective_status(t) == 'ready')
    total = len(available)
    return {
        'available': total,
        'missing': missing,
        'missing_covers': max(0, total - covered),
        'online_checked': online,
        'suspicious': sum(1 for t in available if effective_status(t) == 'review' and suspicious_data_reasons(t)),
        'genres': len(genre_counter),
        'top_genre': genre_counter.most_common(1)[0][0] if genre_counter else '—',
        'avg_bpm': round(sum(bpm_values) / len(bpm_values)) if bpm_values else 0,
        'cover_percent': round(100 * covered / total) if total else 0,
        'online_percent': round(100 * online / total) if total else 0,
        'organized_percent': round(100 * ready / total) if total else 0,
        'size_bytes': sum(int(t.size_bytes or 0) for t in available),
    }


def _session_review_reasons(track: TrackRecord) -> list[str]:
    return review_reasons(track)


def build_session_summary(tracks: Iterable[TrackRecord]) -> dict[str, int]:
    tracks = list(tracks)
    summary = build_operation_summary(tracks)
    summary['manually_edited'] = sum(1 for t in tracks if t.locked_fields)
    return summary


def export_session_html(tracks: Iterable[TrackRecord], path: Path, *, language: str = 'pl') -> Path:
    tracks = list(tracks)
    summary = build_session_summary(tracks)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    en = language == 'en'
    def label(pl: str, english: str) -> str:
        return english if en else pl
    status_names = {'ready': 'GOTOWE', 'review': 'DO SPRAWDZENIA', 'duplicate': 'DUPLIKAT', 'not_selected': 'NIE WYBIERAM'}

    review_rows: list[str] = []
    for track in tracks:
        reasons = _session_review_reasons(track)
        if not reasons:
            continue
        name = ' - '.join(part for part in (track.artist, track.title) if part) or track.filename
        visible_status = translate_static_text(status_names.get(track.status, track.status), language) if en else track.status
        review_rows.append(
            '<tr>'
            f'<td>{escape(name)}</td>'
            f'<td>{escape(visible_status)}</td>'
            f'<td>{escape(", ".join(translate_static_text(reason, language) for reason in reasons))}</td>'
            '</tr>'
        )
    table_body = ''.join(review_rows) or f'<tr><td colspan="3">{label("Brak pozycji DO SPRAWDZENIA.", "No tracks need review.")}</td></tr>'

    html_text = (
        f'<!doctype html><html lang="{label("pl", "en")}"><head><meta charset="utf-8">'
        f'<title>{label("Raport sesji ALO Music", "ALO Music session report")}</title><style>'
        'body{font-family:Segoe UI,Arial,sans-serif;background:#11161d;color:#e9eef5;margin:32px;line-height:1.45}'
        'h1{margin:0 0 8px}.muted{color:#9aa7b5}.cards{display:flex;flex-wrap:wrap;gap:10px;margin:24px 0}'
        '.card{background:#1b222c;border:1px solid #303b48;border-radius:10px;padding:12px 16px;min-width:125px}'
        '.card b{display:block;font-size:24px;color:#73d99d}table{border-collapse:collapse;width:100%;background:#171d25}'
        'th,td{border-bottom:1px solid #303b48;padding:10px 12px;text-align:left;vertical-align:top}th{color:#a9d7bb}'
        '</style></head><body>'
        f'<h1>{label("Raport sesji ALO Music", "ALO Music session report")}</h1><div class="muted">{label("Podsumowanie bieżącej sesji biblioteki.", "Summary of the current library session.")}</div>'
        '<div class="cards">'
        f'<div class="card"><b>{summary["total"]}</b>{label("Wszystkie", "All")}</div>'
        f'<div class="card"><b>{summary["ready"]}</b>{label("Gotowe", "Ready")}</div>'
        f'<div class="card"><b>{summary["duplicate"]}</b>{label("Duplikaty", "Duplicates")}</div>'
        f'<div class="card"><b>{summary["not_selected"]}</b>{label("Nie wybieram", "Not selected")}</div>'
        f'<div class="card"><b>{summary["review"]}</b>{label("Do sprawdzenia", "Needs review")}</div>'
        f'<div class="card"><b>{summary["manually_edited"]}</b>{label("Ręcznie edytowane", "Manually edited")}</div>'
        f'</div><h2>{label("DO SPRAWDZENIA — powody", "NEEDS REVIEW — reasons")}</h2>'
        f'<table><thead><tr><th>{label("Utwór", "Track")}</th><th>Status</th><th>{label("Powód", "Reason")}</th></tr></thead><tbody>'
        f'{table_body}</tbody></table></body></html>'
    )
    path.write_text(html_text, encoding='utf-8')
    return path

def export_csv(tracks: Iterable[TrackRecord], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        'source_path', 'current_filename', 'proposed_filename', 'status', 'artist',
        'title', 'album', 'year', 'genre', 'bpm', 'duration_seconds', 'bitrate_kbps',
        'sample_rate_hz', 'codec', 'size_bytes', 'sha256', 'has_cover', 'comment',
        'confidence', 'match_reasons', 'discogs_release_id', 'discogs_url',
        'musicbrainz_recording_id', 'musicbrainz_release_id', 'fingerprint_duration'
    ]
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for t in tracks:
            writer.writerow({
                'source_path': str(t.path), 'current_filename': t.filename,
                'proposed_filename': t.proposed_filename or '', 'status': t.status,
                'artist': t.artist or '', 'title': t.title or '', 'album': t.album or '',
                'year': t.year or '', 'genre': t.genre or '', 'bpm': '' if t.bpm is None else t.bpm,
                'duration_seconds': '' if t.duration_seconds is None else round(t.duration_seconds, 3),
                'bitrate_kbps': '' if t.bitrate_kbps is None else t.bitrate_kbps,
                'sample_rate_hz': '' if t.sample_rate_hz is None else t.sample_rate_hz,
                'codec': t.codec or '', 'size_bytes': t.size_bytes, 'sha256': t.sha256 or '',
                'has_cover': t.has_cover, 'comment': t.comment or '',
                'confidence': '' if t.confidence is None else round(t.confidence, 4),
                'match_reasons': ' | '.join(t.match_reasons),
                'discogs_release_id': t.discogs_release_id or '', 'discogs_url': t.discogs_url or '',
                'musicbrainz_recording_id': t.musicbrainz_recording_id or '',
                'musicbrainz_release_id': t.musicbrainz_release_id or '',
                'fingerprint_duration': '' if t.fingerprint_duration is None else t.fingerprint_duration,
            })
    return path


def export_verification_csv(result, path: Path) -> Path:
    """Write an explicit post-copy audit so users can prove where each file landed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ['source_path', 'destination_path', 'raw_copy_sha256_match', 'final_file_exists', 'final_size_bytes', 'verified']
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in getattr(result, 'verified', ()):
            writer.writerow({
                'source_path': str(item.source),
                'destination_path': str(item.destination),
                'raw_copy_sha256_match': item.raw_copy_sha256_match,
                'final_file_exists': item.final_file_exists,
                'final_size_bytes': item.final_size_bytes,
                'verified': bool(item.raw_copy_sha256_match and item.final_file_exists and item.final_size_bytes > 0),
            })
    return path
