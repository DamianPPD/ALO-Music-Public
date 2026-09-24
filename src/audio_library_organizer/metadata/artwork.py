from __future__ import annotations

from io import BytesIO

from PIL import Image


def prepare_cover_image(data: bytes, *, max_size: int = 1000) -> tuple[bytes, str, tuple[int,int]]:
    with Image.open(BytesIO(data)) as img:
        img = img.convert('RGB')
        img.thumbnail((max_size,max_size), Image.Resampling.LANCZOS)
        out = BytesIO()
        img.save(out, format='JPEG', quality=90, optimize=True)
        return out.getvalue(), 'image/jpeg', img.size


class CoverArtArchiveClient:
    def __init__(self, session=None):
        import requests
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent':'AudioLibraryOrganizer/0.1'})

    def fetch_url(self, url: str, *, max_size: int = 1000) -> tuple[bytes,str] | None:
        if not url:
            return None
        try:
            r = self.session.get(url, timeout=30, allow_redirects=True)
            if getattr(r, 'status_code', 200) == 404:
                return None
            r.raise_for_status()
            data, mime, _ = prepare_cover_image(r.content, max_size=max_size)
            return data, mime
        except Exception:
            return None

    def fetch_front(self, musicbrainz_release_id: str, *, max_size: int = 1000) -> tuple[bytes,str] | None:
        if not musicbrainz_release_id:
            return None
        url = f'https://coverartarchive.org/release/{musicbrainz_release_id}/front-1200'
        try:
            r = self.session.get(url, timeout=30, allow_redirects=True)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data,mime,_ = prepare_cover_image(r.content, max_size=max_size)
            return data,mime
        except Exception:
            return None


def extract_embedded_cover(path) -> tuple[bytes, str] | None:
    """Return the first embedded front cover without modifying the file."""
    from pathlib import Path
    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4

    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix == '.mp3':
            tags = ID3(path)
            pictures = tags.getall('APIC')
            if pictures:
                pic = next((p for p in pictures if getattr(p, 'type', None) == 3), pictures[0])
                return bytes(pic.data), str(pic.mime or 'image/jpeg')
        elif suffix == '.flac':
            audio = FLAC(path)
            if audio.pictures:
                pic = next((p for p in audio.pictures if getattr(p, 'type', None) == 3), audio.pictures[0])
                return bytes(pic.data), str(pic.mime or 'image/jpeg')
        elif suffix in {'.m4a', '.mp4'}:
            audio = MP4(path)
            covers = (audio.tags or {}).get('covr', [])
            if covers:
                cover = covers[0]
                imageformat = getattr(cover, 'imageformat', None)
                mime = 'image/png' if imageformat == 14 else 'image/jpeg'
                return bytes(cover), mime
    except (ID3NoHeaderError, Exception):
        return None
    return None
