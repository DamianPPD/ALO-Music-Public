from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResetResult:
    databases_removed: int


def _remove_database_files(database: Path) -> int:
    database = Path(database)
    removed = 0
    for candidate in (database, Path(str(database) + '-wal'), Path(str(database) + '-shm')):
        try:
            if candidate.is_file():
                candidate.unlink()
                if candidate == database:
                    removed = 1
        except OSError:
            pass
    return removed


def reset_library_index(library_root: Path) -> int:
    """Remove only ALO's SQLite index for one output library.

    Music files and the output folder structure are intentionally preserved.
    """
    database = Path(library_root).expanduser().resolve() / '.alo' / 'library.sqlite3'
    return _remove_database_files(database)


def _clear_store(store) -> None:
    clear = getattr(store, 'clear', None)
    if callable(clear):
        clear()
        return
    all_keys = getattr(store, 'allKeys', None)
    if callable(all_keys):
        for key in list(all_keys()):
            store.remove(key)
        return
    # Minimal/fake stores used by tests may expose a dict.
    data = getattr(store, 'data', None)
    if isinstance(data, dict):
        data.clear()
        return
    for key in (
        'sources', 'library_root', 'libraries/profiles', 'libraries/active',
        'ui/language', 'ui/language_selected', 'ui/theme', 'ui/normalize_names',
        'ui/name_normalization_rules',
    ):
        try:
            store.remove(key)
        except Exception:
            pass


def reset_alo_state(store, main_settings, registry) -> ResetResult:
    """Reset only ALO state; never delete source music or output folders.

    Registered SQLite indexes are removed and QSettings are cleared. The actual
    music folders (including user source files) are intentionally untouched.
    """
    databases: list[Path] = [Path(main_settings.library.database)]
    for profile in registry.profiles:
        if profile.profile_id == 'main':
            continue
        databases.append(Path(profile.library_root) / '.alo' / 'library.sqlite3')

    removed = 0
    seen: set[Path] = set()
    for database in databases:
        database = database.expanduser().resolve()
        if database in seen:
            continue
        seen.add(database)
        removed += _remove_database_files(database)

    _clear_store(store)
    sync = getattr(store, 'sync', None)
    if callable(sync):
        sync()
    return ResetResult(databases_removed=removed)
