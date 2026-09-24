from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs.exporter import ExportPlan, execute_copy_plan


def test_execute_copy_plan_routes_without_modifying_sources(tmp_path: Path):
    src_ready = tmp_path/'r.mp3'; src_dup = tmp_path/'d.mp3'; src_review = tmp_path/'x.mp3'
    src_ready.write_bytes(b'ready'); src_dup.write_bytes(b'dup'); src_review.write_bytes(b'review')
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (src_ready,src_dup,src_review)}
    lib = LibraryPaths(tmp_path/'library'); lib.ensure_created()
    tracks = [
        TrackRecord(path=src_ready, status='ready', artist='Artist', title='Ready', year='2000', genre='House', bpm=128, proposed_filename='Artist - Ready [128bpm].mp3'),
        TrackRecord(path=src_dup, status='duplicate', proposed_filename='Artist - Dup [128bpm].mp3'),
        TrackRecord(path=src_review, status='review', proposed_filename='Unknown.mp3'),
    ]
    plan = ExportPlan.from_tracks(tracks, lib)
    result = execute_copy_plan(plan)
    assert len(result.copied) == 3
    assert (lib.ready/'Artist - Ready [128bpm].mp3').exists()
    assert (lib.duplicates/'Artist - Dup [128bpm].mp3').exists()
    assert (lib.review/'Unknown.mp3').exists()
    for p, (data, mtime) in before.items():
        assert p.read_bytes() == data
        assert p.stat().st_mtime_ns == mtime


def test_export_plan_summary_counts_statuses(tmp_path: Path):
    lib = LibraryPaths(tmp_path/'library')
    plan = ExportPlan.from_tracks([
        TrackRecord(path=tmp_path/'a.mp3', status='ready', artist='A', title='T', year='2000', genre='House', bpm=128),
        TrackRecord(path=tmp_path/'b.mp3', status='duplicate'),
        TrackRecord(path=tmp_path/'c.mp3', status='review'),
    ], lib)
    assert plan.summary == {'ready':1,'duplicate':1,'not_selected':0,'review':1,'total':3}


def test_execute_copy_plan_reports_progress(tmp_path: Path):
    lib = LibraryPaths(tmp_path/'library'); lib.ensure_created()
    files = []
    for name in ('a.mp3', 'b.mp3'):
        path = tmp_path/name; path.write_bytes(b'audio-' + name.encode()); files.append(path)
    plan = ExportPlan.from_tracks([
        TrackRecord(path=files[0], status='ready'),
        TrackRecord(path=files[1], status='review'),
    ], lib)
    calls = []

    result = execute_copy_plan(plan, progress=lambda current, total, name: calls.append((current, total, name)))

    assert len(result.copied) == 2
    assert calls == [(1, 2, 'a.mp3'), (2, 2, 'b.mp3')]


def test_execute_copy_plan_verifies_raw_copy_and_final_destination(tmp_path: Path):
    src = tmp_path/'source.mp3'
    src.write_bytes(b'original-audio-payload')
    lib = LibraryPaths(tmp_path/'library'); lib.ensure_created()
    track = TrackRecord(path=src, status='ready', proposed_filename='Artist - Track.mp3')

    result = execute_copy_plan(ExportPlan.from_tracks([track], lib))

    assert len(result.copied) == 1
    assert len(result.verified) == 1
    verification = result.verified[0]
    assert verification.source == src
    assert verification.destination.exists()
    assert verification.raw_copy_sha256_match is True
    assert verification.final_file_exists is True
    assert verification.final_size_bytes > 0
    assert result.verification_errors == ()


def test_execute_copy_plan_prefers_external_cover_url_over_source_artwork(tmp_path: Path):
    from io import BytesIO
    from PIL import Image
    from mutagen.id3 import ID3, APIC
    from audio_library_organizer.metadata.artwork import extract_embedded_cover

    old = BytesIO(); Image.new('RGB', (60, 60), 'black').save(old, format='JPEG')
    new = BytesIO(); Image.new('RGB', (90, 90), 'white').save(new, format='JPEG')
    src = tmp_path/'source.mp3'
    tags = ID3(); tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Old', data=old.getvalue())); tags.save(src)

    class FakeArtwork:
        def __init__(self): self.urls = []
        def fetch_url(self, url):
            self.urls.append(url)
            return new.getvalue(), 'image/jpeg'
        def fetch_front(self, _release_id):
            raise AssertionError('Discogs/external URL should be preferred')

    artwork = FakeArtwork()
    lib = LibraryPaths(tmp_path/'library'); lib.ensure_created()
    track = TrackRecord(
        path=src, status='ready', proposed_filename='Artist - Track [128bpm].mp3',
        artist='Artist', title='Track', bpm=128,
        cover_art_url='https://img.example/front.jpg', musicbrainz_release_id='mb-release'
    )

    result = execute_copy_plan(ExportPlan.from_tracks([track], lib), artwork_client=artwork)

    assert len(result.copied) == 1
    assert artwork.urls == ['https://img.example/front.jpg']
    cover = extract_embedded_cover(result.copied[0])
    assert cover is not None
    assert len(cover[0]) > 0


def test_execute_copy_plan_preserves_source_cover_when_external_lookup_fails(tmp_path: Path):
    from io import BytesIO
    from PIL import Image
    from mutagen.id3 import ID3, APIC
    from audio_library_organizer.domain.settings import LibraryPaths
    from audio_library_organizer.jobs.exporter import ExportPlan, execute_copy_plan
    from audio_library_organizer.metadata.artwork import extract_embedded_cover

    src = tmp_path/'source.mp3'
    image = BytesIO(); Image.new('RGB', (48, 48), 'red').save(image, format='JPEG')
    tags = ID3(); tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Source cover', data=image.getvalue())); tags.save(src)
    track = TrackRecord(
        path=src, size_bytes=src.stat().st_size, status='ready', artist='A', title='T',
        has_cover=True, cover_art_url='https://example.invalid/missing.jpg',
        proposed_filename='A - T.mp3',
    )
    lib = LibraryPaths(tmp_path/'library'); lib.ensure_created()
    plan = ExportPlan.from_tracks([track], lib)

    class MissingArtwork:
        def fetch_url(self, _url): return None
        def fetch_front(self, _rid): return None

    result = execute_copy_plan(plan, artwork_client=MissingArtwork())
    assert not result.errors
    copied = result.copied[0]
    cover = extract_embedded_cover(copied)
    assert cover is not None
    assert len(cover[0]) > 0


def test_execute_copy_plan_embeds_placeholder_when_track_has_no_real_cover(tmp_path: Path):
    from mutagen.id3 import ID3
    from audio_library_organizer.metadata.artwork import extract_embedded_cover

    src = tmp_path/'no-cover.mp3'
    ID3().save(src)
    lib = LibraryPaths(tmp_path/'library'); lib.ensure_created()
    track = TrackRecord(
        path=src, status='ready', artist='Artist', title='Track', year='2000', genre='House', bpm=128,
        cover_choice='auto', proposed_filename='Artist - Track (2000) [128bpm].mp3',
    )

    class NoArtwork:
        def fetch_url(self, _url): return None
        def fetch_front(self, _rid): return None

    result = execute_copy_plan(ExportPlan.from_tracks([track], lib), artwork_client=NoArtwork())

    assert not result.errors
    assert len(result.copied) == 1
    cover = extract_embedded_cover(result.copied[0])
    assert cover is not None
    assert len(cover[0]) > 1000


def test_explicit_source_cover_choice_beats_available_external_cover(tmp_path: Path):
    from io import BytesIO
    from PIL import Image
    from mutagen.id3 import ID3, APIC
    from audio_library_organizer.metadata.artwork import extract_embedded_cover

    source_image = BytesIO(); Image.new('RGB', (50, 50), 'red').save(source_image, format='JPEG')
    external_image = BytesIO(); Image.new('RGB', (80, 80), 'blue').save(external_image, format='JPEG')
    src = tmp_path/'source-choice.mp3'
    tags = ID3(); tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Source', data=source_image.getvalue())); tags.save(src)
    lib = LibraryPaths(tmp_path/'library'); lib.ensure_created()
    track = TrackRecord(
        path=src, status='ready', artist='Artist', title='Track', year='2000', genre='House', bpm=128,
        has_cover=True, cover_art_url='https://img.example/external.jpg', cover_choice='source',
        proposed_filename='Artist - Track (2000) [128bpm].mp3',
    )

    class ExternalArtwork:
        def __init__(self): self.calls = 0
        def fetch_url(self, _url):
            self.calls += 1
            return external_image.getvalue(), 'image/jpeg'
        def fetch_front(self, _rid): return None

    artwork = ExternalArtwork()
    result = execute_copy_plan(ExportPlan.from_tracks([track], lib), artwork_client=artwork)

    assert not result.errors
    assert artwork.calls == 0
    cover = extract_embedded_cover(result.copied[0])
    assert cover is not None
