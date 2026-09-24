from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _is_same_or_inside(child: Path, parent: Path) -> bool:
    child = _resolved(child)
    parent = _resolved(parent)
    return child == parent or parent in child.parents


@dataclass(frozen=True, slots=True)
class LibraryPaths:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, 'root', _resolved(self.root))

    @property
    def ready(self) -> Path:
        return self.root / 'GOTOWE'

    @property
    def not_selected(self) -> Path:
        return self.root / 'NIE_WYBRANE'

    @property
    def duplicates(self) -> Path:
        # Compatibility alias: duplicate/rejected candidates now share the neutral
        # NIE_WYBRANE destination instead of implying that every file is certainly identical.
        return self.not_selected

    @property
    def review(self) -> Path:
        return self.root / 'DO_SPRAWDZENIA'

    @property
    def reports(self) -> Path:
        return self.root / 'raporty'

    @property
    def custom_folders(self) -> Path:
        return self.root / 'MOJE_FOLDERY_MP3'

    @property
    def app_data(self) -> Path:
        return self.root / '.alo'

    @property
    def database(self) -> Path:
        return self.app_data / 'library.sqlite3'

    def ensure_created(self) -> None:
        for path in (self.root, self.ready, self.not_selected, self.review, self.reports, self.custom_folders, self.app_data):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class AppSettings:
    source_dirs: tuple[Path, ...]
    library: LibraryPaths

    def __post_init__(self) -> None:
        seen: set[Path] = set()
        normalized: list[Path] = []
        for raw in self.source_dirs:
            path = _resolved(raw)
            if path not in seen:
                normalized.append(path)
                seen.add(path)
        object.__setattr__(self, 'source_dirs', tuple(normalized))
        for source in normalized:
            if _is_same_or_inside(self.library.root, source) or _is_same_or_inside(source, self.library.root):
                raise ValueError('Folder źródłowy i biblioteka nie mogą zawierać się wzajemnie.')
