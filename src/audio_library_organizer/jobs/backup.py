from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile
import re
import os
import tempfile

from audio_library_organizer.storage.database import snapshot_database


def create_alo_backup(
    target: Path, *, database_path: Path, settings_payload: dict[str, object],
    profile_databases: dict[str, Path] | None = None,
) -> Path:
    target = Path(target)
    if not target.name.lower().endswith('.zip'):
        target = target.with_suffix(target.suffix + '.zip' if target.suffix else '.alo-backup.zip')
    target.parent.mkdir(parents=True, exist_ok=True)
    profile_files: dict[str, str] = {}
    for profile_id, db_path in (profile_databases or {}).items():
        safe_id = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(profile_id)).strip('._') or 'profile'
        if Path(db_path).is_file():
            profile_files[str(profile_id)] = f'profiles/{safe_id}.sqlite3'
    manifest = {
        'format': 'ALO_BACKUP_V1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'settings': settings_payload,
        'database_file': 'library.sqlite3',
        'profile_databases': profile_files,
    }
    # Snapshot every database before opening the archive. Failure leaves an
    # existing archive intact and no live WAL-dependent SQLite is copied.
    with tempfile.TemporaryDirectory(prefix='.alo-backup-', dir=target.parent) as workspace:
        snapshots: list[tuple[Path, str]] = []
        db = Path(database_path)
        if db.is_file():
            copy = snapshot_database(db, Path(workspace) / 'main.sqlite3')
            snapshots.append((copy, 'library.sqlite3'))
        for index, (profile_id, archive_name) in enumerate(profile_files.items()):
            copy = snapshot_database(Path((profile_databases or {})[profile_id]), Path(workspace) / f'profile-{index}.sqlite3')
            snapshots.append((copy, archive_name))
        archive = Path(workspace) / 'backup.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            for copy, archive_name in snapshots:
                zf.write(copy, archive_name)
        os.replace(archive, target)
    return target


def inspect_alo_backup(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path, 'r') as zf:
        data = json.loads(zf.read('manifest.json').decode('utf-8'))
    if data.get('format') != 'ALO_BACKUP_V1':
        raise ValueError('Nieobsługiwany format kopii ALO.')
    return data


def restore_database_from_backup(path: Path, destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'r') as zf:
        if 'library.sqlite3' not in zf.namelist():
            raise ValueError('Kopia nie zawiera bazy biblioteki.')
        data = zf.read('library.sqlite3')
    destination.write_bytes(data)
    return destination


def restore_profile_databases_from_backup(path: Path, destinations: dict[str, Path]) -> dict[str, Path]:
    """Restore profile databases present in a backup to caller-approved destinations."""
    restored: dict[str, Path] = {}
    with zipfile.ZipFile(path, 'r') as zf:
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        mapping = manifest.get('profile_databases') or {}
        if not isinstance(mapping, dict):
            return restored
        for profile_id, destination in destinations.items():
            archive_name = mapping.get(profile_id)
            if not archive_name or archive_name not in zf.namelist():
                continue
            target = Path(destination)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(archive_name))
            restored[profile_id] = target
    return restored
