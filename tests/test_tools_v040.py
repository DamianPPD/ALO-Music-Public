from pathlib import Path
import json
import zipfile

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs.backup import create_alo_backup, inspect_alo_backup
from audio_library_organizer.jobs.playlists import write_m3u8
from audio_library_organizer.jobs.file_health import file_health_reasons


def tr(path: Path, **kw):
    defaults = dict(size_bytes=100, mtime_ns=1, artist='Artist', title='Title', duration_seconds=240, bitrate_kbps=320, has_cover=True)
    defaults.update(kw)
    return TrackRecord(path=path, **defaults)


def test_m3u8_writes_utf8_and_relative_paths_when_inside_playlist_tree(tmp_path: Path):
    folder = tmp_path / 'set'; folder.mkdir()
    a = folder / 'Zażółć.mp3'; b = folder / 'Two.mp3'
    a.write_bytes(b'a'); b.write_bytes(b'b')
    target = folder / 'set.m3u8'
    write_m3u8(target, [a, b], relative=True)
    text = target.read_text(encoding='utf-8-sig')
    assert text.startswith('#EXTM3U')
    assert 'Zażółć.mp3' in text
    assert str(folder) not in text


def test_backup_contains_manifest_and_database_without_music(tmp_path: Path):
    db = tmp_path / 'library.sqlite3'; db.write_bytes(b'SQLITE')
    music = tmp_path / 'song.mp3'; music.write_bytes(b'MUSIC')
    target = tmp_path / 'backup.alo-backup.zip'
    create_alo_backup(target, database_path=db, settings_payload={'language': 'pl', 'library_root': str(tmp_path)})
    info = inspect_alo_backup(target)
    assert info['settings']['language'] == 'pl'
    with zipfile.ZipFile(target) as zf:
        names = set(zf.namelist())
    assert 'manifest.json' in names
    assert 'library.sqlite3' in names
    assert 'song.mp3' not in names


def test_file_health_reports_real_problems_without_choosing_a_duplicate_winner(tmp_path: Path):
    missing = tr(tmp_path / 'missing.mp3')
    assert 'Plik niedostępny' in file_health_reasons(missing)

    broken = tr(tmp_path / 'broken.mp3', duration_seconds=0, codec=None, size_bytes=0)
    reasons = file_health_reasons(broken, check_filesystem=False)
    assert 'Nieprawidłowa długość audio' in reasons
    assert 'Brak informacji o kodeku' in reasons
    assert 'Pusty plik' in reasons


def test_backup_can_include_additional_library_databases(tmp_path: Path):
    main_db = tmp_path / 'main.sqlite3'; main_db.write_bytes(b'MAIN')
    house_db = tmp_path / 'house.sqlite3'; house_db.write_bytes(b'HOUSE')
    target = tmp_path / 'all.alo-backup.zip'
    create_alo_backup(
        target,
        database_path=main_db,
        settings_payload={'profiles': [{'profile_id': 'house'}]},
        profile_databases={'house': house_db},
    )
    with zipfile.ZipFile(target) as zf:
        names = set(zf.namelist())
        assert 'library.sqlite3' in names
        assert 'profiles/house.sqlite3' in names
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    assert manifest['profile_databases']['house'] == 'profiles/house.sqlite3'


def test_restore_can_restore_additional_profile_database(tmp_path: Path):
    from audio_library_organizer.jobs.backup import restore_profile_databases_from_backup
    main_db = tmp_path / 'main.sqlite3'; main_db.write_bytes(b'MAIN')
    house_db = tmp_path / 'house.sqlite3'; house_db.write_bytes(b'HOUSE')
    target = tmp_path / 'all.alo-backup.zip'
    create_alo_backup(target, database_path=main_db, settings_payload={}, profile_databases={'house': house_db})
    restored = tmp_path / 'restore' / 'house.sqlite3'
    result = restore_profile_databases_from_backup(target, {'house': restored})
    assert result['house'] == restored
    assert restored.read_bytes() == b'HOUSE'
