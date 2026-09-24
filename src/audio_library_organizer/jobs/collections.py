from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs.exporter import ExportItem, ExportPlan
from audio_library_organizer.metadata.naming import sanitize_windows_component
from audio_library_organizer.jobs.scanner import SUPPORTED_EXTENSIONS


@dataclass(frozen=True, slots=True)
class CollectionInfo:
    name: str
    path: Path
    file_count: int
    size_bytes: int


def collection_path(library: LibraryPaths, name: str) -> Path:
    clean = sanitize_windows_component(name.strip())
    if not clean:
        raise ValueError('Podaj nazwę folderu.')
    return library.custom_folders / clean


def build_collection_plan(library: LibraryPaths, name: str, tracks: list[TrackRecord]) -> ExportPlan:
    destination = collection_path(library, name)
    items = tuple(
        ExportItem(track, destination, track.proposed_filename or track.filename)
        for track in tracks
        if getattr(track, 'is_available', True) and Path(track.path).is_file()
    )
    return ExportPlan(items, {
        'ready': len(items), 'duplicate': 0, 'not_selected': 0, 'review': 0, 'total': len(items),
    })


def list_collections(library: LibraryPaths) -> list[CollectionInfo]:
    library.custom_folders.mkdir(parents=True, exist_ok=True)
    result: list[CollectionInfo] = []
    for folder in sorted((p for p in library.custom_folders.iterdir() if p.is_dir()), key=lambda p: p.name.casefold()):
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
        result.append(CollectionInfo(
            name=folder.name,
            path=folder,
            file_count=len(files),
            size_bytes=sum(p.stat().st_size for p in files),
        ))
    return result


def remove_collection_file(collection_root: Path, file_path: Path) -> bool:
    root = Path(collection_root).resolve()
    target = Path(file_path).resolve()
    if root not in target.parents or not target.is_file():
        return False
    target.unlink()
    return True
