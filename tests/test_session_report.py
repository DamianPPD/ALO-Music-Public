from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.reporting import build_session_summary, export_session_html


def test_build_session_summary_counts_manual_and_review_items(tmp_path: Path):
    ready = TrackRecord(path=tmp_path/'ready.mp3', status='ready', artist='A', title='T', year='2000', genre='House', bpm=128, has_cover=True)
    edited = TrackRecord(path=tmp_path/'edited.mp3', status='ready', artist='B', title='T', year='2001', genre='Trance', bpm=132, has_cover=True)
    edited.locked_fields.add('title')
    review = TrackRecord(path=tmp_path/'review.mp3', status='review', artist='C', title='T', year=None, has_cover=False)
    duplicate = TrackRecord(path=tmp_path/'dup.mp3', status='duplicate', artist='D', title='T', year='2002', genre='House', bpm=128, has_cover=True)

    summary = build_session_summary([ready, edited, review, duplicate])

    assert summary == {
        'total': 4,
        'ready': 2,
        'duplicate': 1,
        'review': 1,
        'not_selected': 0,
        'error': 0,
        'manually_edited': 1,
    }


def test_export_session_html_escapes_metadata_and_lists_review_items(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path/'danger.mp3',
        status='review',
        artist='<script>alert(1)</script>',
        title='Mix & Edit',
        year=None,
        has_cover=False,
    )
    path = export_session_html([track], tmp_path/'raport.html')
    html = path.read_text(encoding='utf-8')

    assert 'Raport sesji ALO Music' in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<script>alert(1)</script>' not in html
    assert 'Mix &amp; Edit' in html
    assert 'DO SPRAWDZENIA — powody' in html
    assert 'Do decyzji' not in html
    assert 'Brak: Rok' in html
    assert 'Brak okładki' not in html


def test_library_health_summary_reports_genres_bpm_covers_online_and_missing(tmp_path: Path):
    from audio_library_organizer.jobs.reporting import build_library_health

    tracks = [
        TrackRecord(path=tmp_path/'a.mp3', status='ready', artist='A', title='A', year='2000', genre='Trance / Vocal', bpm=138, has_cover=True, size_bytes=100, confidence=.95, discogs_release_id='1', is_available=True),
        TrackRecord(path=tmp_path/'b.mp3', status='review', artist='B', title='B', year='2001', genre='Trance', bpm=142, has_cover=False, size_bytes=300, confidence=.4, is_available=True),
        TrackRecord(path=tmp_path/'c.mp3', status='ready', artist='C', title='C', year='2002', genre='House', bpm=128, has_cover=True, size_bytes=500, is_available=False),
    ]
    info = build_library_health(tracks)
    assert info['available'] == 2
    assert info['missing'] == 1
    assert info['genres'] == 2  # only available tracks: Trance + Vocal
    assert info['top_genre'] == 'Trance'
    assert info['suspicious'] == 0
    assert info['avg_bpm'] == 140
    assert info['cover_percent'] == 50
    assert info['online_percent'] == 50
    assert info['size_bytes'] == 400


def test_library_health_does_not_reopen_manually_approved_ready_as_suspicious(tmp_path: Path):
    from audio_library_organizer.jobs.reporting import build_library_health

    approved = TrackRecord(
        path=tmp_path/'approved.mp3',
        status='ready',
        artist='Approved Artist',
        title='Approved Title',
        year='2003',
        genre='House',
        bpm=128,
        has_cover=True,
        confidence=.71,
        match_reasons=['Duża różnica względem danych sprzed online'],
        is_available=True,
    )
    approved.locked_fields.add('__status__')

    info = build_library_health([approved])

    assert info['organized_percent'] == 100
    assert info['suspicious'] == 0
