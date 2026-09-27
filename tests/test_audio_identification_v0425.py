from pathlib import Path

import pytest
import requests

from audio_library_organizer.audio.fingerprint import FingerprintResult
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.audio_identification import AudioIdentification, approve_audio_source
from audio_library_organizer.providers.acoustid import AcoustIDClient
from audio_library_organizer.providers.musicbrainz import MusicBrainzClient
from audio_library_organizer.storage.repository import LibraryRepository


PAYLOAD = {'status': 'ok', 'results': [
    {'id': 'ac1', 'score': .94, 'recordings': [{
        'id': 'mb1', 'title': 'Song (Remix)', 'artists': [{'name': 'Artist'}],
        'releasegroups': [{'title': 'Album', 'first-release-date': '2012-04-02'}],
    }]},
    {'id': 'ac2', 'score': .75, 'recordings': [{'id': 'mb2', 'title': 'Other'}]},
]}


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class Session:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return Response(self.payload)


def test_id_only_acoustid_results_are_enriched_from_recording_ids(tmp_path):
    # Synthetic ID-only payload matching the scores seen in the manual test;
    # the original HTTP response and recording IDs were not available.
    acoustid = Session({'status': 'ok', 'results': [
        {'id': 'ac-88', 'score': .88, 'recordings': [{'id': 'mb-88'}]},
        {'id': 'ac-86', 'score': .86, 'recordings': [{'id': 'mb-86'}]},
    ]})

    class RecordingSession:
        def __init__(self):
            self.headers = {}
            self.requests = []

        def get(self, url, **kwargs):
            self.requests.append((url, kwargs))
            rid = url.rsplit('/', 1)[-1]
            return Response({
                'id': rid, 'title': 'Stepping To The Beat (Dave Mcdonald Remix)',
                'artist-credit': [{'name': 'DJ Jose'}],
                'releases': [{'id': 'release-id', 'title': 'Stepping to the Beat Vinyl', 'date': '2005-03-02'}],
            })

    recordings = RecordingSession()
    job = AudioIdentification(AcoustIDClient('key', acoustid),
                              musicbrainz_client=MusicBrainzClient('test@example.org', recordings),
                              fingerprinter=lambda _: FingerprintResult('FP', 354))
    hits = job.lookup(TrackRecord(path=tmp_path / 'track.mp3'))
    assert [(h.score, h.artist, h.title, h.album, h.year, h.recording_id, h.acoustid_id) for h in hits] == [
        (.88, 'DJ Jose', 'Stepping To The Beat (Dave Mcdonald Remix)', 'Stepping to the Beat Vinyl', '2005', 'mb-88', 'ac-88'),
        (.86, 'DJ Jose', 'Stepping To The Beat (Dave Mcdonald Remix)', 'Stepping to the Beat Vinyl', '2005', 'mb-86', 'ac-86'),
    ]
    assert [url.rsplit('/', 1)[-1] for url, _ in recordings.requests] == ['mb-88', 'mb-86']
    assert all(options['params']['inc'] == 'artist-credits+releases+release-groups' for _, options in recordings.requests)


def test_unresolved_recording_is_not_presented_as_a_named_candidate(tmp_path):
    acoustid = Session({'status': 'ok', 'results': [
        {'id': 'ac-blank', 'score': .88, 'recordings': [{'id': 'mb-blank'}]},
        {'id': 'ac-good', 'score': .86, 'recordings': [{'id': 'mb-good', 'title': 'Known song', 'artists': [{'name': 'Artist'}]}]},
    ]})

    class EmptyRecording:
        def get_recording(self, recording_id):
            from audio_library_organizer.domain.candidates import MusicBrainzRecording
            return MusicBrainzRecording(recording_id, None, None, None)

    job = AudioIdentification(AcoustIDClient('key', acoustid), musicbrainz_client=EmptyRecording(),
                              fingerprinter=lambda _: FingerprintResult('FP', 354))
    hits = job.lookup(TrackRecord(path=tmp_path / 'track.mp3'))
    assert [hit.recording_id for hit in hits] == ['mb-good']


def test_musicbrainz_failure_keeps_usable_acoustid_metadata(tmp_path):
    acoustid = Session({'status': 'ok', 'results': [
        {'id': 'ac-good', 'score': .86, 'recordings': [{'id': 'mb-good', 'title': 'Known song',
                                                    'artists': [{'name': 'Artist'}]}]},
        {'id': 'ac-blank', 'score': .75, 'recordings': [{'id': 'mb-blank'}]},
    ]})

    class OfflineRecordings:
        def get_recording(self, recording_id):
            raise requests.Timeout('MusicBrainz offline')

    job = AudioIdentification(AcoustIDClient('key', acoustid), musicbrainz_client=OfflineRecordings(),
                              fingerprinter=lambda _: FingerprintResult('FP', 354))
    hits = job.lookup(TrackRecord(path=tmp_path / 'track.mp3'))
    assert [(hit.recording_id, hit.artist, hit.title) for hit in hits] == [('mb-good', 'Artist', 'Known song')]


def test_fingerprint_is_local_and_acoustid_returns_ranked_candidates(tmp_path):
    from audio_library_organizer.domain.candidates import MusicBrainzRecording

    class RecordingStub:
        def get_recording(self, recording_id):
            return MusicBrainzRecording(recording_id, 'Other artist', 'Other', None)

    session = Session(PAYLOAD)
    client = AcoustIDClient('key', session=session)
    track = TrackRecord(path=tmp_path / 'song.mp3', artist='Original')
    states = []
    identify = AudioIdentification(client, fingerprinter=lambda path: FingerprintResult('FP', 230),
                                   musicbrainz_client=RecordingStub())
    hits = identify.lookup(track, progress=states.append)
    assert states == ['fingerprint', 'lookup']
    assert [hit.recording_id for hit in hits] == ['mb1', 'mb2']
    assert hits[0].album == 'Album' and hits[0].year == '2012'
    assert hits[0].acoustid_id == 'ac1'
    assert track.artist == 'Original' and track.fingerprint is None
    assert session.requests[0][1]['data']['fingerprint'] == 'FP'
    assert 'file' not in session.requests[0][1]


def test_no_key_no_results_and_invalid_response(tmp_path):
    track = TrackRecord(path=tmp_path / 'song.mp3')
    with pytest.raises(ValueError, match='AcoustID'):
        AudioIdentification(AcoustIDClient('')).lookup(track)
    identify = AudioIdentification(AcoustIDClient('key', Session({'status': 'ok', 'results': []})), fingerprinter=lambda _: FingerprintResult('FP', 230))
    assert identify.lookup(track) == []
    for data in ({'status': 'error', 'error': {'message': 'bad key'}}, {'results': 'bad'}, ['bad'],
                 {'status': 'ok', 'results': [{'score': 'nan', 'recordings': [{'id': 'mb1'}]}]},
                 {'status': 'ok', 'results': [{'score': 'inf', 'recordings': [{'id': 'mb1'}]}]}):
        with pytest.raises(ValueError):
            AcoustIDClient('key', Session(data)).lookup('FP', 230)


def test_network_timeout_is_reported_and_previous_approval_survives(tmp_path):
    class Offline(Session):
        def post(self, *args, **kwargs):
            raise requests.Timeout('offline')

    track = TrackRecord(path=tmp_path / 'song.mp3', artist='Untouched')
    approve_audio_source(track, AcoustIDClient('key', Session(PAYLOAD)).lookup('FP', 230)[0])
    original = dict(track.audio_recognition)
    with pytest.raises(requests.Timeout):
        AudioIdentification(AcoustIDClient('key', Offline(None)), fingerprinter=lambda _: FingerprintResult('FP', 230)).lookup(track)
    assert track.audio_recognition == original and track.artist == 'Untouched'


def test_approval_replacement_and_repository_round_trip(tmp_path):
    repo = LibraryRepository(tmp_path / 'library.db')
    repo.initialize()
    track = TrackRecord(path=tmp_path / 'song.mp3', artist='Old', title='Old title',
                        field_sources={'artist': 'Tag'}, field_source_values={'artist': {'Tag': 'Old'}})
    candidates = AcoustIDClient('key', Session(PAYLOAD)).lookup('FP', 230)
    approve_audio_source(track, candidates[0])
    repo.upsert_track(track)
    reloaded = repo.list_tracks()[0]
    assert (reloaded.artist, reloaded.title) == ('Old', 'Old title')
    assert reloaded.field_sources['artist'] == 'Tag'
    assert reloaded.field_source_values['artist']['Rozpoznanie audio'] == 'Artist'
    assert reloaded.field_source_values['album']['Rozpoznanie audio'] == 'Album'
    assert reloaded.audio_recognition['score'] == .94
    approve_audio_source(reloaded, candidates[1])
    assert 'Rozpoznanie audio' not in reloaded.field_source_values['artist']
    assert reloaded.field_source_values['title']['Rozpoznanie audio'] == 'Other'
    assert reloaded.artist == 'Old'
