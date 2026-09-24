from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths


@dataclass(frozen=True, slots=True)
class LibraryProfile:
    profile_id: str
    name: str
    kind: str
    source_dirs: tuple[Path, ...]
    library_root: Path

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
            'source_dirs': [str(p) for p in self.source_dirs],
            'library_root': str(self.library_root),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> 'LibraryProfile':
        return cls(
            profile_id=str(data.get('profile_id') or uuid4().hex),
            name=str(data.get('name') or 'Biblioteka'),
            kind=str(data.get('kind') or 'library'),
            source_dirs=tuple(Path(str(p)) for p in (data.get('source_dirs') or [])),
            library_root=Path(str(data.get('library_root') or '.')),
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

    ``library_root`` is always the ALO output/destination folder. ``source_dirs``
    are scan roots registered for that library and are never presented as the
    library location. Scan history is persisted separately and is informational;
    it never triggers automatic scanning by itself.
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
                self._profiles.append(profile)
        self._active_id = active_id if self.find(active_id) is not None else 'main'
        self._scan_history: dict[str, list[ScanHistoryEntry]] = {}
        valid_ids = {profile.profile_id for profile in self._profiles}
        for profile_id, entries in (scan_history or {}).items():
            if profile_id in valid_ids:
                self._scan_history[profile_id] = list(entries)[:200]

    @property
    def profiles(self) -> tuple[LibraryProfile, ...]:
        return tuple(self._profiles)

    def update_main_settings(self, settings: AppSettings) -> None:
        self.main_settings = settings
        self._main = LibraryProfile('main', 'Biblioteka główna', 'main', settings.source_dirs, settings.library.root)
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
        # Validate any supplied sources against the output root.
        AppSettings(profile.source_dirs, LibraryPaths(profile.library_root))
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
            updated = LibraryProfile(profile.profile_id, clean_name, profile.kind, profile.source_dirs, profile.library_root)
            self._main = updated
            self._profiles = [updated if item.profile_id == profile_id else item for item in self._profiles]
            return updated
        updated = LibraryProfile(profile.profile_id, clean_name, profile.kind, profile.source_dirs, profile.library_root)
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
        updated = LibraryProfile(profile.profile_id, profile.name, profile.kind, (), profile.library_root)
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
        updated = LibraryProfile(profile.profile_id, profile.name, profile.kind, sources, profile.library_root)
        self._profiles = [updated if item.profile_id == profile_id else item for item in self._profiles]
        return updated

    def settings_for(self, profile: LibraryProfile | None = None) -> AppSettings:
        profile = profile or self.active
        settings = AppSettings(profile.source_dirs, LibraryPaths(profile.library_root))
        settings.library.ensure_created()
        return settings

    def activate(self, profile_id: str) -> LibraryProfile:
        profile = self.find(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        self._active_id = profile_id
        return profile

    def remove_library(self, profile_id: str) -> bool:
        if profile_id == 'main':
            return False
        before = len(self._profiles)
        self._profiles = [p for p in self._profiles if p.profile_id != profile_id]
        removed = len(self._profiles) != before
        if removed:
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
        key = str(entry.source_dir).casefold()
        existing = [item for item in self._scan_history.get(profile_id, []) if str(item.source_dir).casefold() != key]
        self._scan_history[profile_id] = [entry, *existing][:200]
        return entry

    def scan_history(self, profile_id: str | None = None) -> tuple[ScanHistoryEntry, ...]:
        pid = profile_id or self.active.profile_id
        return tuple(self._scan_history.get(pid, ()))

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
            for item in data:
                if not isinstance(item, dict):
                    continue
                if str(item.get('kind') or 'library') != 'library':
                    continue
                profiles.append(LibraryProfile.from_dict(item))
        except Exception:
            profiles = []
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
