from audio_library_organizer.providers.itunes import ITunesSearchClient, parse_itunes_result


def test_parse_itunes_result_maps_catalog_metadata_and_high_res_artwork():
    candidate = parse_itunes_result({
        'artistName': 'Re:Locate',
        'trackName': 'Built To Last (Ferry Tayle Remix)',
        'collectionName': 'Built To Last',
        'releaseDate': '2014-06-16T07:00:00Z',
        'primaryGenreName': 'Trance',
        'trackTimeMillis': 417000,
        'trackViewUrl': 'https://music.apple.com/example',
        'artworkUrl100': 'https://example.test/100x100bb.jpg',
    })
    assert candidate.source == 'apple'
    assert candidate.artist == 'Re:Locate'
    assert candidate.year == '2014'
    assert candidate.duration_seconds == 417.0
    assert '1200x1200bb' in candidate.cover_art_url


class _Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {'results': [{
            'artistName': 'Re:Locate',
            'trackName': 'Built To Last (Ferry Tayle Remix)',
            'collectionName': 'Built To Last',
            'releaseDate': '2014-06-16T07:00:00Z',
            'primaryGenreName': 'Trance',
        }]}


class _Session:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return _Response()


def test_itunes_search_needs_no_api_key():
    session = _Session()
    client = ITunesSearchClient(session=session)
    rows = client.search_tracks('Relocate', 'Built To Last', limit=4)
    assert rows and rows[0].title == 'Built To Last (Ferry Tayle Remix)'
    assert session.calls[0][1]['entity'] == 'song'
