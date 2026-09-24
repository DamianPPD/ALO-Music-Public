from audio_library_organizer.providers.acoustid import parse_acoustid_results
from audio_library_organizer.providers.musicbrainz import parse_recording
from audio_library_organizer.providers.discogs import parse_release_candidate
from audio_library_organizer.matching.scorer import score_candidate
from audio_library_organizer.domain.models import TrackRecord


def test_parse_acoustid_results_extracts_recording_ids_and_score():
    data = {'status':'ok','results':[{'score':0.98,'recordings':[{'id':'mb1','title':'Airport','artists':[{'name':'Armani & Ghost'}]}]}]}
    hits = parse_acoustid_results(data)
    assert hits[0].recording_id == 'mb1'
    assert hits[0].score == 0.98
    assert hits[0].artist == 'Armani & Ghost'


def test_parse_musicbrainz_recording_prefers_release_information():
    data = {
        'id':'mb1','title':'Airport (Original Mix)','length':349000,
        'artist-credit':[{'name':'Armani & Ghost'}],
        'releases':[{'id':'rel1','title':'Airport','date':'2003-01-01','release-group':{'id':'rg1'}}]
    }
    rec = parse_recording(data)
    assert rec.artist == 'Armani & Ghost'
    assert rec.title == 'Airport (Original Mix)'
    assert rec.release_ids == ('rel1',)
    assert rec.duration_seconds == 349.0


def test_parse_discogs_release_builds_exact_track_candidate():
    release = {
        'id':144798, 'title':'Airport', 'year':2003, 'country':'Germany', 'released':'2003',
        'artists':[{'name':'Armani & Ghost'}],
        'genres':['Electronic'], 'styles':['Hard House','Jumpstyle'],
        'labels':[{'name':'Overdose','catno':'DOSE 123'}],
        'formats':[{'name':'Vinyl','descriptions':['12"']}],
        'images':[{'type':'secondary','uri':'https://img.example/back.jpg'}, {'type':'primary','uri':'https://img.example/front.jpg'}],
        'uri':'https://www.discogs.com/release/144798',
        'tracklist':[{'position':'A','title':'Airport (Original Mix)','duration':'5:50'}]
    }
    c = parse_release_candidate(release, 'Airport (Original Mix)')
    assert c.release_id == '144798'
    assert c.artist == 'Armani & Ghost'
    assert c.title == 'Airport (Original Mix)'
    assert c.album == 'Armani & Ghost – Airport'
    assert c.genre == 'Hard House, Jumpstyle'
    assert 'Label: Overdose – DOSE 123' in c.comment
    assert c.duration_seconds == 350
    assert c.cover_art_url == 'https://img.example/front.jpg'


def test_score_candidate_rewards_exact_version_duration_and_album(tmp_path):
    track = TrackRecord(path=tmp_path/'x.mp3', artist='Armani & Ghost', title='Airport (Original Mix)', album='Armani & Ghost – Airport', duration_seconds=350)
    release = {
        'id':144798, 'title':'Airport', 'year':2003, 'artists':[{'name':'Armani & Ghost'}],
        'genres':['Electronic'], 'styles':['Hard House'], 'labels':[], 'formats':[],
        'uri':'https://www.discogs.com/release/144798',
        'tracklist':[{'title':'Airport (Original Mix)','duration':'5:50'}]
    }
    c = parse_release_candidate(release, track.title)
    scored = score_candidate(track, c)
    assert scored.score >= 0.85
    assert 'dokładny tytuł/wersja' in scored.reasons
    assert 'długość zgodna' in scored.reasons


class _FakeResponse:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): return None
    def json(self): return self.payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload; self.calls = 0; self.headers = {}
    def get(self, *args, **kwargs): self.calls += 1; return _FakeResponse(self.payload)
    def post(self, *args, **kwargs): self.calls += 1; return _FakeResponse(self.payload)


def test_musicbrainz_get_recording_uses_memory_cache():
    from audio_library_organizer.providers.musicbrainz import MusicBrainzClient
    session = _FakeSession({'id':'mb1','title':'Track','artist-credit':[{'name':'Artist'}],'releases':[]})
    client = MusicBrainzClient(session=session)
    client.get_recording('mb1'); client.get_recording('mb1')
    assert session.calls == 1


def test_discogs_release_and_search_use_memory_cache():
    from audio_library_organizer.providers.discogs import DiscogsClient
    session = _FakeSession({'results':[{'id':1}]})
    client = DiscogsClient('token', session=session)
    client.search_release_ids('Artist','Track'); client.search_release_ids('Artist','Track')
    assert session.calls == 1


def test_acoustid_lookup_uses_memory_cache():
    from audio_library_organizer.providers.acoustid import AcoustIDClient
    session = _FakeSession({'results':[]})
    client = AcoustIDClient('key', session=session)
    client.lookup('fp', 123); client.lookup('fp', 123)
    assert session.calls == 1
