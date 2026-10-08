from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from .repository import LibraryRepository
from .migrations import MigrationError


def _same_database(first: Path, second: Path) -> bool:
    first, second = LibraryPaths(first).database, LibraryPaths(second).database
    if first.resolve() == second.resolve():
        return True
    try:
        return first.samefile(second)
    except OSError:
        return False


def _optional_source_cache(cached: object) -> tuple[tuple[Path, ...], bool]:
    """Reject the whole optional cache on failure; never seed partial roots."""
    if not isinstance(cached, (list, tuple)) or not all(
        isinstance(p, str) and p.strip() and '\x00' not in p for p in cached
    ):
        return (), False
    try:
        return tuple(Path(p).expanduser().resolve() for p in cached), True
    except (OSError, RuntimeError, ValueError):
        return (), False


@dataclass(frozen=True, slots=True)
class LibraryProfile:
    profile_id: str
    name: str
    kind: str
    source_dirs: tuple[Path, ...]
    library_root: Path
    library_id: str | None = None
    # Unconsumed legacy input, separate from the SQLite-derived scan cache.
    # Keep the original JSON value until successful bootstrap/hydration.
    pending_source_cache: object = None
    source_cache_valid: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, 'source_dirs', tuple(Path(p).expanduser().resolve() for p in self.source_dirs))
        object.__setattr__(self, 'library_root', Path(self.library_root).expanduser().resolve())
        if self.kind not in {'main', 'library'}:
            raise ValueError(f'Unsupported library profile kind: {self.kind}')

    def to_dict(self) -> dict[str, object]:
        return {
            'profile_id': self.profile_id,
            'name': self.name,
            'kind': self.kind,
            'source_dirs': self.pending_source_cache if self.pending_source_cache is not None or not self.source_cache_valid else [str(p) for p in self.source_dirs],
            'library_root': str(self.library_root),
            'library_id': self.library_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> 'LibraryProfile':
        root = data.get('library_root')
        if not isinstance(root, str) or not root.strip():
            raise ValueError('Library profile requires an output root.')
        # Essential root failures must escape the optional-cache/invalid-entry
        # handlers: silently dropping this profile would lose its saved identity.
        try:
            normalized_root = Path(root).expanduser().resolve()
        except ValueError as exc:
            raise RuntimeError(f'Cannot resolve library output root: {exc}') from exc
        cached = data.get('source_dirs', [])
        sources, valid = _optional_source_cache(cached)
        return cls(
            profile_id=str(data.get('profile_id') or uuid4().hex),
            name=str(data.get('name') or 'Biblioteka'),
            kind=str(data.get('kind') or 'library'),
            source_dirs=sources,
            library_root=normalized_root,
            library_id=str(data['library_id']) if data.get('library_id') else None,
            pending_source_cache=cached,
            source_cache_valid=valid,
        )


@dataclass(frozen=True, slots=True)
class ScanHistoryEntry:
    source_dir: Path
    scanned_at: str
    file_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, 'source_dir', Path(self.source_dir).expanduser().resolve())
        object.__setattr__(self, 'file_count', max(0, int(self.file_count)))

    def to_dict(self) -> dict[str, object]:
        return {'source_dir': str(self.source_dir), 'scanned_at': self.scanned_at, 'file_count': self.file_count}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> 'ScanHistoryEntry':
        return cls(
            source_dir=Path(str(data.get('source_dir') or '.')),
            scanned_at=str(data.get('scanned_at') or ''),
            file_count=int(data.get('file_count') or 0),
        )


class LibraryRegistry:
    """Persistent registry of output libraries and their explicitly added scan roots.

    QSettings owns profile selection/history. SQLite owns source identities and
    bindings; source_dirs is a compatible display/scan cache loaded from SQLite.
    """

    def __init__(
        self,
        main_settings: AppSettings,
        profiles: list[LibraryProfile] | None = None,
        *,
        active_id: str = 'main',
        scan_history: dict[str, list[ScanHistoryEntry]] | None = None,
    ):
        self.main_settings = main_settings
        self._main = LibraryProfile('main', 'Biblioteka główna', 'main', main_settings.source_dirs, main_settings.library.root)
        self._profiles: list[LibraryProfile] = [self._main]
        for profile in profiles or []:
            if profile.profile_id != 'main' and profile.kind == 'library':
                self.validate_database_location(profile.library_root)
                self._profiles.append(profile)
        self._unavailable_ids: set[str] = set()
        selected = active_id if self.find(active_id) is not None else 'main'
        hydrated = []
        for profile in self._profiles:
            try:
                hydrated.append(self._hydrate(profile, require_existing=profile.kind != 'main'))
            except (OSError, MigrationError):
                if profile.profile_id == selected or profile.kind == 'main':
                    raise
                # Preserve selection metadata; never replace an unavailable DB
                # with a new identity or bootstrap its stale source cache.
                self._unavailable_ids.add(profile.profile_id)
                pending = profile.pending_source_cache
                if pending is None and profile.source_cache_valid:
                    pending = [str(p) for p in profile.source_dirs]
                hydrated.append(replace(profile, source_dirs=(), pending_source_cache=pending))
        self._profiles = hydrated
        self._main = self._profiles[0]
        self.main_settings = AppSettings(self._main.source_dirs, main_settings.library)
        self._active_id = active_id if self.find(active_id) is not None else 'main'
        self._scan_history: dict[str, list[ScanHistoryEntry]] = {}
        valid_ids = {profile.profile_id for profile in self._profiles}
        for profile_id, entries in (scan_history or {}).items():
            if profile_id in valid_ids:
                self._scan_history[profile_id] = list(entries)[:200]

    @staticmethod
    def _repository(profile: LibraryProfile, *, require_existing: bool = False) -> LibraryRepository:
        repo = LibraryRepository(LibraryPaths(profile.library_root).database)
        if require_existing and not repo.database_path.is_file():
            raise FileNotFoundError(f'Library database is unavailable: {repo.database_path}')
        repo.initialize()
        return repo

    @classmethod
    def _hydrate(cls, profile: LibraryProfile, *, require_existing: bool = False) -> LibraryProfile:
        repo = cls._repository(profile, require_existing=require_existing)
        candidates, valid = profile.source_dirs, profile.source_cache_valid
        if profile.pending_source_cache is not None or not valid:
            candidates, valid = _optional_source_cache(profile.pending_source_cache)
        if valid:
            repo.bootstrap_sources(candidates)
        sources = tuple(Path(source.root_path) for source in repo.list_sources(active_only=True))
        if repo.sources_initialized:
            return replace(profile, source_dirs=sources, library_id=repo.library_id,
                           pending_source_cache=None, source_cache_valid=True)
        # An invalid optional cache must not certify an empty bootstrap.
        return replace(profile, source_dirs=sources, library_id=repo.library_id,
                       source_cache_valid=valid)

    def _replace_sources(self, profile: LibraryProfile, sources: tuple[Path, ...]) -> LibraryProfile:
        AppSettings(sources, LibraryPaths(profile.library_root))
        repo = self._repository(profile, require_existing=True)
        repo.replace_sources(sources)
        return replace(profile, source_dirs=tuple(Path(s.root_path) for s in repo.list_sources(active_only=True)),
                       library_id=repo.library_id, pending_source_cache=None,
                       source_cache_valid=True)

    @property
    def profiles(self) -> tuple[LibraryProfile, ...]:
        return tuple(self._profiles)

    def validate_database_location(self, root: Path, *, exclude_profile_id: str | None = None) -> None:
        for profile in self._profiles:
            if profile.profile_id != exclude_profile_id and _same_database(root, profile.library_root):
                raise ValueError('Library database is already registered in another profile.')

    def update_main_settings(self, settings: AppSettings) -> None:
        self.validate_database_location(settings.library.root, exclude_profile_id='main')
        candidate = replace(self._main, library_root=settings.library.root)
        if settings.library.root != self._main.library_root:
            updated = self._hydrate(replace(candidate, source_dirs=settings.source_dirs))
        else:
            updated = self._replace_sources(candidate, settings.source_dirs)
        self.main_settings = AppSettings(updated.source_dirs, settings.library)
        self._main = updated
        self._profiles = [self._main, *[p for p in self._profiles if p.profile_id != 'main']]

    @property
    def active(self) -> LibraryProfile:
        return self.find(self._active_id) or self._main

    def find(self, profile_id: str) -> LibraryProfile | None:
        return next((p for p in self._profiles if p.profile_id == profile_id), None)

    def add_library(
        self,
        name: str,
        source_dirs: tuple[Path, ...],
        library_root: Path | None = None,
        *,
        profile_id: str | None = None,
    ) -> LibraryProfile:
        pid = profile_id or f'lib-{uuid4().hex[:10]}'
        if self.find(pid) is not None:
            raise ValueError(f'Profile already exists: {pid}')
        # Compatibility: older callers may omit library_root; keep the private
        # workspace fallback. The v0.4.5 UI always supplies an explicit output root.
        root = Path(library_root) if library_root is not None else self.main_settings.library.app_data / 'profiles' / pid
        profile = LibraryProfile(pid, name.strip() or root.name or 'Biblioteka', 'library', tuple(source_dirs), root)
        self.validate_database_location(profile.library_root)
        # Validate any supplied sources against the output root.
        AppSettings(profile.source_dirs, LibraryPaths(profile.library_root))
        profile = self._hydrate(profile)
        self._profiles.append(profile)
        return profile

    def rename_library(self, profile_id: str, name: str) -> LibraryProfile:
        profile = self.find(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        clean_name = name.strip()
        if not clean_name:
            raise ValueError('Library name cannot be empty.')
        if profile.kind == 'main':
            updated = replace(profile, name=clean_name)
            self._main = updated
            self._profiles = [updated if item.profile_id == profile_id else item for item in self._profiles]
            return updated
        updated = replace(profile, name=clean_name)
        self._profiles = [updated if item.profile_id == profile_id else item for item in self._profiles]
        return updated

    def clear_source_dirs(self, profile_id: str) -> LibraryProfile:
        profile = self.find(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        if profile.kind == 'main':
            updated_settings = AppSettings((), self.main_settings.library)
            self.update_main_settings(updated_settings)
            return self._main
        updated = self._replace_sources(profile, ())
        self._profiles = [updated if item.profile_id == profile_id else item for item in self._profiles]
        return updated

    def add_source_dir(self, profile_id: str, source_dir: Path) -> LibraryProfile:
        profile = self.find(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        source = Path(source_dir).expanduser().resolve()
        if source in profile.source_dirs:
            return profile
        sources = profile.source_dirs + (source,)
        AppSettings(sources, LibraryPaths(profile.library_root))
        if profile.kind == 'main':
            updated = AppSettings(sources, self.main_settings.library)
            self.update_main_settings(updated)
            return self._main
        updated = self._replace_sources(profile, sources)
        self._profiles = [updated if item.profile_id == profile_id else item for item in self._profiles]
        return updated

    def settings_for(self, profile: LibraryProfile | None = None) -> AppSettings:
        profile = profile or self.active
        profile = self.find(profile.profile_id) or profile
        if profile.profile_id in self._unavailable_ids:
            profile = self._refresh_profile(profile)
        settings = AppSettings(profile.source_dirs, LibraryPaths(profile.library_root))
        settings.library.ensure_created()
        return settings

    def activate(self, profile_id: str) -> LibraryProfile:
        profile = self.find(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        profile = self._refresh_profile(profile)
        self._active_id = profile_id
        return profile

    def _refresh_profile(self, profile: LibraryProfile) -> LibraryProfile:
        self.validate_database_location(profile.library_root, exclude_profile_id=profile.profile_id)
        updated = self._hydrate(profile, require_existing=True)
        self._profiles = [updated if p.profile_id == profile.profile_id else p for p in self._profiles]
        self._unavailable_ids.discard(profile.profile_id)
        if profile.kind == 'main':
            self._main = updated
            self.main_settings = AppSettings(updated.source_dirs, LibraryPaths(updated.library_root))
        return updated

    def remove_library(self, profile_id: str) -> bool:
        if profile_id == 'main':
            return False
        before = len(self._profiles)
        self._profiles = [p for p in self._profiles if p.profile_id != profile_id]
        removed = len(self._profiles) != before
        if removed:
            self._unavailable_ids.discard(profile_id)
            self._scan_history.pop(profile_id, None)
        if removed and self._active_id == profile_id:
            self._active_id = 'main'
        return removed

    def record_scan(
        self,
        profile_id: str,
        source_dir: Path,
        file_count: int,
        *,
        scanned_at: datetime | str | None = None,
    ) -> ScanHistoryEntry:
        if self.find(profile_id) is None:
            raise KeyError(profile_id)
        if scanned_at is None:
            stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        elif isinstance(scanned_at, datetime):
            stamp = scanned_at.isoformat(timespec='seconds')
        else:
            stamp = str(scanned_at)
        entry = ScanHistoryEntry(source_dir, stamp, file_count)
        existing = self._scan_history.get(profile_id, [])
        self._scan_history[profile_id] = [entry, *existing][:200]
        return entry

    def scan_history(self, profile_id: str | None = None) -> tuple[ScanHistoryEntry, ...]:
        """Latest saved scan per source, preserving the registry's summary API."""
        pid = profile_id or self.active.profile_id
        latest: dict[str, ScanHistoryEntry] = {}
        for entry in self._scan_history.get(pid, ()):
            latest.setdefault(str(entry.source_dir).casefold(), entry)
        return tuple(latest.values())

    def scan_history_for_source(self, source_dir: Path, profile_id: str | None = None) -> tuple[ScanHistoryEntry, ...]:
        pid = profile_id or self.active.profile_id
        key = str(Path(source_dir).expanduser().resolve()).casefold()
        return tuple(entry for entry in self._scan_history.get(pid, ())
                     if str(entry.source_dir).casefold() == key)

    def remove_source_history(self, source_dir: Path, profile_id: str | None = None) -> int:
        """Remove this source's history only; scan bindings and disk files stay intact."""
        pid = profile_id or self.active.profile_id
        if self.find(pid) is None:
            raise KeyError(pid)
        key = str(Path(source_dir).expanduser().resolve()).casefold()
        entries = self._scan_history.get(pid, [])
        remaining = [entry for entry in entries if str(entry.source_dir).casefold() != key]
        self._scan_history[pid] = remaining
        return len(entries) - len(remaining)

    def clear_scan_history(self, profile_id: str | None = None) -> int:
        """Clear informational scan history for one library only.

        This never changes source music, library files, or scan bindings.
        """
        pid = profile_id or self.active.profile_id
        if self.find(pid) is None:
            raise KeyError(pid)
        removed = len(self._scan_history.get(pid, ()))
        self._scan_history.pop(pid, None)
        return removed

    def save(self, store) -> None:
        payload = [p.to_dict() for p in self._profiles if p.kind == 'library']
        store.setValue('libraries/profiles', json.dumps(payload, ensure_ascii=False))
        persisted_active = self._active_id if any(p.profile_id == self._active_id and p.kind == 'library' for p in self._profiles) else 'main'
        store.setValue('libraries/active', persisted_active)
        history_payload = {
            profile_id: [entry.to_dict() for entry in entries]
            for profile_id, entries in self._scan_history.items()
            if self.find(profile_id) is not None
        }
        store.setValue('libraries/scan_history', json.dumps(history_payload, ensure_ascii=False))

    @classmethod
    def from_store(cls, store, main_settings: AppSettings) -> 'LibraryRegistry':
        raw = store.value('libraries/profiles', '')
        profiles: list[LibraryProfile] = []
        try:
            data = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
            for item in data if isinstance(data, list) else []:
                if not isinstance(item, dict):
                    continue
                if str(item.get('kind') or 'library') != 'library':
                    continue
                try:
                    profiles.append(LibraryProfile.from_dict(item))
                except (TypeError, ValueError):
                    continue
        except (TypeError, ValueError):
            pass
        active_id = str(store.value('libraries/active', 'main') or 'main')

        history: dict[str, list[ScanHistoryEntry]] = {}
        history_raw = store.value('libraries/scan_history', '')
        try:
            history_data = json.loads(history_raw) if isinstance(history_raw, str) and history_raw else (history_raw or {})
            if isinstance(history_data, dict):
                for profile_id, entries in history_data.items():
                    if not isinstance(entries, list):
                        continue
                    history[str(profile_id)] = [ScanHistoryEntry.from_dict(item) for item in entries if isinstance(item, dict)]
        except Exception:
            history = {}
        return cls(main_settings, profiles, active_id=active_id, scan_history=history)
