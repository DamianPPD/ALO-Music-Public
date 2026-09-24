from pathlib import Path
from mutagen.id3 import ID3, TIT2

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.tag_writer import write_resolved_tags, build_title_tag


def test_build_title_tag_appends_bpm_once(tmp_path: Path):
    t = TrackRecord(path=tmp_path/'x.mp3', title='Airport (Original Mix) [139bpm]', bpm=139)
    assert build_title_tag(t) == 'Airport (Original Mix) [139bpm]'


def test_write_resolved_mp3_tags_preserves_audio_file_and_writes_fields(tmp_path: Path):
    path = tmp_path/'x.mp3'
    tags = ID3(); tags.add(TIT2(encoding=3,text='Old')); tags.save(path)
    t = TrackRecord(path=path, artist='Armani & Ghost', title='Airport (Original Mix)', album='Armani & Ghost – Airport', year='2003', genre='Hard House, Jumpstyle', bpm=139, comment='Label: Overdose')
    write_resolved_tags(path, t)
    out = ID3(path)
    assert str(out['TPE1']) == 'Armani & Ghost'
    assert str(out['TIT2']) == 'Airport (Original Mix) [139bpm]'
    assert str(out['TALB']) == 'Armani & Ghost – Airport'
    assert str(out['TDRC']) == '2003'
    assert str(out['TCON']) == 'Hard House, Jumpstyle'
    assert str(out['TBPM']) == '139'
    assert 'Label: Overdose' in str(out.getall('COMM')[0])


def test_write_resolved_flac_tags_and_cover(tmp_path: Path):
    import numpy as np
    import soundfile as sf
    from io import BytesIO
    from PIL import Image
    from mutagen.flac import FLAC

    path = tmp_path/'x.flac'
    sf.write(path, np.zeros(4410, dtype=np.float32), 44100, format='FLAC')
    cover = BytesIO(); Image.new('RGB', (32, 32), 'white').save(cover, format='JPEG')
    track = TrackRecord(
        path=path, artist='Artist', title='Track (Club Mix)', album='Release',
        year='2001', genre='House', bpm=128, comment='Country: Germany'
    )

    write_resolved_tags(path, track, cover_bytes=cover.getvalue(), cover_mime='image/jpeg')

    audio = FLAC(path)
    assert audio['artist'][0] == 'Artist'
    assert audio['title'][0] == 'Track (Club Mix) [128bpm]'
    assert audio['album'][0] == 'Release'
    assert audio['genre'][0] == 'House'
    assert audio.pictures and audio.pictures[0].mime == 'image/jpeg'


def test_write_resolved_mp3_tags_preserves_existing_cover_without_replacement(tmp_path: Path):
    from io import BytesIO
    from PIL import Image
    from mutagen.id3 import APIC

    image = BytesIO(); Image.new('RGB', (24, 24), 'white').save(image, format='JPEG')
    path = tmp_path/'cover-preserve.mp3'
    tags = ID3(); tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Old cover', data=image.getvalue())); tags.save(path)
    track = TrackRecord(path=path, artist='A', title='B', bpm=128)

    write_resolved_tags(path, track)

    out = ID3(path)
    assert len(out.getall('APIC')) == 1
    assert bytes(out.getall('APIC')[0].data) == image.getvalue()


def test_write_resolved_flac_preserves_existing_cover_without_replacement(tmp_path: Path):
    import numpy as np
    import soundfile as sf
    from io import BytesIO
    from PIL import Image
    from mutagen.flac import FLAC, Picture

    path = tmp_path/'cover-preserve.flac'
    sf.write(path, np.zeros(4410, dtype=np.float32), 44100, format='FLAC')
    image = BytesIO(); Image.new('RGB', (24, 24), 'white').save(image, format='JPEG')
    audio = FLAC(path); picture = Picture(); picture.type = 3; picture.mime = 'image/jpeg'; picture.data = image.getvalue(); audio.add_picture(picture); audio.save()
    track = TrackRecord(path=path, artist='A', title='B', bpm=128)

    write_resolved_tags(path, track)

    out = FLAC(path)
    assert len(out.pictures) == 1
    assert bytes(out.pictures[0].data) == image.getvalue()


def test_write_resolved_mp3_places_discogs_link_in_url_frame_not_comment(tmp_path: Path):
    from mutagen.id3 import WXXX

    path = tmp_path/'discogs-url.mp3'
    ID3().save(path)
    track = TrackRecord(
        path=path,
        artist='Samantha Fox',
        title='Example',
        year='2000',
        comment='Label: Fox 2000 – none\nFormat: CDr, Maxi-Single, Limited Edition',
        discogs_url='https://www.discogs.com/release/20412499-Samantha-Fox-Limited-Edition',
    )

    write_resolved_tags(path, track)

    tags = ID3(path)
    comments = '\n'.join(str(frame) for frame in tags.getall('COMM'))
    assert 'discogs.com' not in comments.casefold()
    urls = tags.getall('WXXX')
    assert len(urls) == 1
    assert urls[0].desc == 'Discogs'
    assert urls[0].url == track.discogs_url
    assert str(tags['TDRC']) == '2000'


def test_write_resolved_mp3_can_remove_source_cover_for_external_cover_policy(tmp_path: Path):
    from io import BytesIO
    from PIL import Image
    from mutagen.id3 import APIC

    image = BytesIO(); Image.new('RGB', (24, 24), 'white').save(image, format='JPEG')
    path = tmp_path/'cover-remove.mp3'
    tags = ID3(); tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Source cover', data=image.getvalue())); tags.save(path)
    track = TrackRecord(path=path, artist='A', title='B', bpm=128)

    write_resolved_tags(path, track, replace_cover=True)

    out = ID3(path)
    assert out.getall('APIC') == []


def test_write_resolved_mp3_clears_track_and_disc_numbers(tmp_path: Path):
    from mutagen.id3 import TRCK, TPOS

    path = tmp_path/'numbered.mp3'
    tags = ID3()
    tags.add(TRCK(encoding=3, text='3/12'))
    tags.add(TPOS(encoding=3, text='1/2'))
    tags.save(path)
    track = TrackRecord(path=path, artist='A', title='B')

    write_resolved_tags(path, track)

    out = ID3(path)
    assert out.getall('TRCK') == []
    assert out.getall('TPOS') == []


def test_write_resolved_flac_clears_track_and_disc_numbers(tmp_path: Path):
    import numpy as np
    import soundfile as sf
    from mutagen.flac import FLAC

    path = tmp_path/'numbered.flac'
    sf.write(path, np.zeros(4410, dtype=np.float32), 44100, format='FLAC')
    audio = FLAC(path)
    audio['tracknumber'] = ['3']
    audio['tracktotal'] = ['12']
    audio['discnumber'] = ['1']
    audio['disctotal'] = ['2']
    audio.save()
    track = TrackRecord(path=path, artist='A', title='B')

    write_resolved_tags(path, track)

    out = FLAC(path)
    for key in ('tracknumber', 'tracktotal', 'discnumber', 'disctotal'):
        assert key not in out
