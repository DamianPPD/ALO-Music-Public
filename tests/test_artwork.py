from io import BytesIO
from PIL import Image

from audio_library_organizer.metadata.artwork import prepare_cover_image


def test_prepare_cover_image_limits_dimensions_and_returns_jpeg():
    src = BytesIO(); Image.new('RGB',(2200,1800)).save(src,format='PNG')
    data,mime,size = prepare_cover_image(src.getvalue(), max_size=1000)
    assert mime == 'image/jpeg'
    assert max(size) <= 1000
    img = Image.open(BytesIO(data))
    assert img.format == 'JPEG'


def test_extract_embedded_cover_reads_mp3_apic(tmp_path):
    from mutagen.id3 import ID3, APIC
    from audio_library_organizer.metadata.artwork import extract_embedded_cover

    image = BytesIO(); Image.new('RGB', (40, 40), 'white').save(image, format='JPEG')
    path = tmp_path/'cover.mp3'
    tags = ID3(); tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=image.getvalue())); tags.save(path)

    found = extract_embedded_cover(path)

    assert found is not None
    assert found[1] == 'image/jpeg'
    assert found[0].startswith(b'\xff\xd8')

class _ImageResponse:
    def __init__(self, data: bytes, status_code: int = 200):
        self.content = data
        self.status_code = status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

class _ImageSession:
    def __init__(self, data: bytes):
        self.data = data
        self.headers = {}
        self.urls = []
    def get(self, url, **kwargs):
        self.urls.append(url)
        return _ImageResponse(self.data)


def test_artwork_client_can_fetch_direct_external_cover_url():
    from audio_library_organizer.metadata.artwork import CoverArtArchiveClient
    image = BytesIO(); Image.new('RGB', (1200, 900), 'white').save(image, format='JPEG')
    session = _ImageSession(image.getvalue())
    client = CoverArtArchiveClient(session=session)

    found = client.fetch_url('https://img.example/front.jpg')

    assert found is not None
    assert found[1] == 'image/jpeg'
    assert session.urls == ['https://img.example/front.jpg']
