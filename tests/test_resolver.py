from pathlib import Path
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.candidates import MetadataCandidate
from audio_library_organizer.matching.resolver import apply_candidate, decision_for_score


def test_decision_thresholds():
    assert decision_for_score(0.90) == 'certain'
    assert decision_for_score(0.75) == 'probable'
    assert decision_for_score(0.50) == 'uncertain'


def test_apply_candidate_updates_resolved_metadata_and_filename(tmp_path: Path):
    t = TrackRecord(path=tmp_path/'34.mp3', bpm=139)
    c = MetadataCandidate(source='discogs', artist='Armani & Ghost', title='Airport (Original Mix)', album='Armani & Ghost – Airport', year='2003', genre='Hard House, Jumpstyle', comment='Label: Test', release_id='144798', source_url='https://www.discogs.com/release/144798', score=0.95, reasons=('fingerprint AcoustID','długość zgodna'))
    out = apply_candidate(t,c,source_recording_id='mb1')
    assert out.status == 'ready'
    assert out.proposed_filename == 'Armani & Ghost - Airport (Original Mix) (2003) [139bpm].mp3'
    assert out.discogs_release_id == '144798'
    assert out.musicbrainz_recording_id == 'mb1'


def test_identification_uses_acoustid_score_per_recording_for_unknown_filename(tmp_path: Path):
    from audio_library_organizer.domain.candidates import AcoustIDHit, MusicBrainzRecording
    from audio_library_organizer.matching.resolver import IdentificationService

    class FakeAcoustID:
        def lookup(self, fingerprint, duration):
            return [
                AcoustIDHit('good', 0.99, 'Correct Mix', 'Right Artist'),
                AcoustIDHit('weak', 0.40, 'Wrong Mix', 'Wrong Artist'),
            ]

    records = {
        'good': MusicBrainzRecording('good', 'Right Artist', 'Correct Mix', 300.0),
        'weak': MusicBrainzRecording('weak', 'Wrong Artist', 'Wrong Mix', 300.0),
    }

    class FakeMB:
        def get_recording(self, recording_id):
            return records[recording_id]

    track = TrackRecord(path=tmp_path/'34.mp3', duration_seconds=300.0, fingerprint='FP', fingerprint_duration=300, bpm=140)
    outcome = IdentificationService(acoustid=FakeAcoustID(), musicbrainz=FakeMB()).identify(track)

    assert outcome.track.musicbrainz_recording_id == 'good'
    assert outcome.track.artist == 'Right Artist'
    assert outcome.track.title == 'Correct Mix'
    assert outcome.decision == 'certain'
    assert any('AcoustID 99%' in reason for reason in outcome.track.match_reasons)


def test_apply_candidate_respects_locked_manual_genre(tmp_path: Path):
    t = TrackRecord(path=tmp_path/'x.mp3', artist='Artist', title='Track', genre='My House', locked_fields={'genre'})
    c = MetadataCandidate(source='discogs', artist='Artist', title='Track', genre='Techno', score=0.95)

    apply_candidate(t, c)

    assert t.genre == 'My House'


def test_text_identification_tries_core_title_variant_when_filename_has_trailing_suffix(tmp_path: Path):
    from audio_library_organizer.domain.candidates import MusicBrainzRecording
    from audio_library_organizer.matching.resolver import IdentificationService

    class FakeMB:
        def __init__(self): self.queries = []
        def search_recordings(self, artist, title, limit=3):
            self.queries.append((artist, title))
            if title == 'Watch Me (Double M & D. Bone Mix)':
                return [MusicBrainzRecording('mb1', artist, title, 300.0)]
            return []

    mb = FakeMB()
    track = TrackRecord(path=tmp_path/'x.mp3', artist='Abuna E', title='Watch Me (Double M & D. Bone Mix) - EKWADOR MANIECZKI')

    rows = IdentificationService(musicbrainz=mb)._records_from_text(track)

    assert rows and rows[0][0].recording_id == 'mb1'
    assert ('Abuna E', 'Watch Me (Double M & D. Bone Mix)') in mb.queries


def test_apply_candidate_keeps_local_source_values_and_adds_online_source(tmp_path: Path):
    t = TrackRecord(
        path=tmp_path/'x.mp3', artist='Local Artist', title='Local Title',
        field_source_values={'artist': {'Tag': 'Local Artist'}, 'title': {'Tag': 'Local Title'}},
    )
    c = MetadataCandidate(source='discogs', artist='Discogs Artist', title='Discogs Title', year='2004', score=0.95)

    apply_candidate(t, c)

    assert t.field_source_values['artist'] == {'Tag': 'Local Artist', 'Discogs': 'Discogs Artist'}
    assert t.field_source_values['title']['Discogs'] == 'Discogs Title'
    assert t.field_source_values['year']['Discogs'] == '2004'
    assert t.field_sources['artist'] == 'Discogs'


def test_identification_preserves_musicbrainz_and_discogs_alternatives(tmp_path: Path):
    from audio_library_organizer.domain.candidates import MusicBrainzRecording
    from audio_library_organizer.matching.resolver import IdentificationService

    class Service(IdentificationService):
        def _records_from_fingerprint(self, track):
            return [(MusicBrainzRecording('mb1', 'MB Artist', 'MB Title', 300.0, ('rel1',), ('MB Album',), ('2002',)), 0.99)]
        def _records_from_text(self, track):
            return []
        def _discogs_candidates(self, rec):
            return [MetadataCandidate(source='discogs', artist='Discogs Artist', title='Discogs Title', album='Discogs Album', year='2003')]

    track = TrackRecord(path=tmp_path/'34.mp3', duration_seconds=300.0, bpm=128.0, fingerprint='FP', fingerprint_duration=300)
    outcome = Service().identify(track)

    assert outcome.track.field_source_values['artist']['MusicBrainz'] == 'MB Artist'
    assert outcome.track.field_source_values['title']['MusicBrainz'] == 'MB Title'
    assert outcome.track.field_source_values['artist']['Discogs'] == 'Discogs Artist'
    assert outcome.track.field_source_values['year']['Discogs'] == '2003'
