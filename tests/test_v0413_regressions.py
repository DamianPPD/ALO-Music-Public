import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from audio_library_organizer.domain.candidates import MetadataCandidate
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.identifier import IdentificationJob
from audio_library_organizer.matching.resolver import IdentificationService
from audio_library_organizer.matching.scorer import score_candidate
from audio_library_organizer.metadata.filename_hints import title_search_variants
from audio_library_organizer.ui.library_page import LibraryPage


def _qt_app():
    return QApplication.instance() or QApplication([])


def _complete_track(path: Path, *, status: str, title: str) -> TrackRecord:
    return TrackRecord(
        path=path,
        artist='Test Artist',
        title=title,
        year='2008',
        genre='House',
        bpm=128,
        has_cover=True,
        status=status,
        locked_fields={'__status__'},
    )


def test_title_search_variants_remove_website_noise_and_keep_clean_version():
    variants = title_search_variants('All I Need (Extended) Www.Djwitek.Org')

    assert variants[0] == 'All I Need (Extended) Www.Djwitek.Org'
    assert 'All I Need (Extended)' in variants
    assert 'All I Need' in variants


def test_artist_scoring_treats_feat_and_ampersand_as_same_participants():
    track = TrackRecord(
        Path('get_far.mp3'),
        artist='Get Far & Sagi Rei',
        title='All I Need (Extended)',
        duration_seconds=343,
    )
    candidate = MetadataCandidate(
        source='discogs',
        artist='Get Far* Feat. Sagi Rei',
        title='All I Need (Extended)',
        duration_seconds=343,
    )

    scored = score_candidate(track, candidate)

    assert 'wykonawca zgodny' in scored.reasons
    assert scored.score >= 0.90


class _CleanTitleDiscogs:
    def __init__(self):
        self.queries: list[tuple[str, str]] = []

    def search_release_ids(self, artist: str, track: str, limit: int = 8):
        self.queries.append((artist, track))
        return ['1610322'] if track == 'All I Need (Extended)' else []

    def get_release(self, release_id: str):
        return {
            'id': 1610322,
            'title': 'All I Need',
            'artists': [{'name': 'Get Far'}, {'name': 'Sagi Rei'}],
            'year': 2008,
            'genres': ['Electronic'],
            'styles': ['Electro'],
            'tracklist': [
                {'title': 'All I Need (Original Extended)', 'duration': '5:43'},
            ],
        }


def test_discogs_fallback_tries_clean_title_variants_for_tagged_files():
    discogs = _CleanTitleDiscogs()
    service = IdentificationService(discogs=discogs)
    track = TrackRecord(
        Path('get_far.mp3'),
        artist='Get Far & Sagi Rei',
        title='All I Need (Extended) Www.Djwitek.Org',
        duration_seconds=343,
        year='2008',
    )

    outcome = service.identify(track)

    assert ('Get Far & Sagi Rei', 'All I Need (Extended)') in discogs.queries
    assert outcome.candidate is not None
    assert outcome.track.discogs_release_id == '1610322'


class _FailingDiscogs:
    def search_release_ids(self, artist: str, track: str, limit: int = 8):
        raise RuntimeError('provider unavailable')


class _MemoryRepository:
    def __init__(self, tracks):
        self.tracks = list(tracks)

    def list_tracks(self):
        return self.tracks

    def upsert_track(self, track):
        for index, current in enumerate(self.tracks):
            if current.path == track.path:
                self.tracks[index] = track
                return
        self.tracks.append(track)


def test_identification_job_reports_provider_failure_instead_of_no_match():
    track = TrackRecord(
        Path('provider_error.mp3'),
        artist='Get Far & Sagi Rei',
        title='All I Need',
    )
    repo = _MemoryRepository([track])
    service = IdentificationService(discogs=_FailingDiscogs())

    result = IdentificationJob(repo, service, tracks=[track], force=True).run()

    assert result.errors == 1
    assert track.match_reasons
    assert 'Discogs' in track.match_reasons[0]
    assert 'Błąd' in track.match_reasons[0]
    assert 'Nie znaleziono pewnego dopasowania online' not in track.match_reasons[0]


def test_library_refresh_keeps_current_visual_order_after_status_change(tmp_path):
    _qt_app()
    ready = _complete_track(tmp_path / 'ready.mp3', status='ready', title='Ready')
    review = _complete_track(tmp_path / 'review.mp3', status='review', title='Review')
    page = LibraryPage()
    page.set_tracks([ready, review])

    page.table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
    page.model.sort(0, Qt.SortOrder.AscendingOrder)
    before = [page.model.item(row, 0).data(Qt.ItemDataRole.UserRole).path for row in range(page.model.rowCount())]

    review.status = 'not_selected'
    page.set_tracks([ready, review])
    after = [page.model.item(row, 0).data(Qt.ItemDataRole.UserRole).path for row in range(page.model.rowCount())]

    assert after == before


def test_playing_row_delegate_draws_explicit_high_contrast_highlight():
    library = Path('src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
    delegate = library.split('class LibraryRowDelegate(QStyledItemDelegate)', 1)[1].split('class LibraryPage', 1)[0]

    assert 'PLAYING_BACKGROUND = QColor(' in library
    assert 'PLAYING_ACCENT = QColor(' in library
    assert 'painter.fillRect(option.rect, PLAYING_BACKGROUND)' in delegate
    assert 'painter.setPen(QPen(PLAYING_ACCENT' in delegate
    assert 'painter.drawLine' in delegate

def test_status_change_from_metadata_editor_does_not_recenter_library():
    main_window = Path('src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
    method = main_window.split('def _set_ready_from_editor', 1)[1].split('def _edit_metadata', 1)[0]
    assert 'self.library.select_track_by_path(track.path)' not in method

