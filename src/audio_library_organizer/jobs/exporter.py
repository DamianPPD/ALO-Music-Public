from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import Counter

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.safety.copy_pipeline import copy_without_overwrite, verify_exact_copy
from audio_library_organizer.metadata.tag_writer import write_resolved_tags
from audio_library_organizer.metadata.artwork import CoverArtArchiveClient, prepare_cover_image, extract_embedded_cover
from audio_library_organizer.metadata.naming import sanitize_windows_component
from audio_library_organizer.metadata.genre import primary_genre
from audio_library_organizer.metadata.completeness import core_metadata_complete


@dataclass(frozen=True, slots=True)
class ExportItem:
    track: TrackRecord
    destination_dir: Path
    filename: str


@dataclass(frozen=True, slots=True)
class ExportPlan:
    items: tuple[ExportItem, ...]
    summary: dict[str, int]

    @classmethod
    def from_tracks(
        cls,
        tracks: list[TrackRecord],
        library: LibraryPaths,
        *,
        folder_organization: str = 'none',
    ) -> 'ExportPlan':
        folder_organization = folder_organization if folder_organization in {'none', 'artist', 'genre'} else 'none'
        items: list[ExportItem] = []
        counts = Counter()
        for track in tracks:
            status = track.status
            if status == 'ready' and not core_metadata_complete(track):
                status = 'review'
            if status not in {'ready', 'duplicate', 'review', 'not_selected'}:
                status = 'review'
            counts[status] += 1
            if status == 'ready':
                destination = library.ready
                if folder_organization == 'artist':
                    destination = destination / sanitize_windows_component(track.artist or 'Nieznany wykonawca')
                elif folder_organization == 'genre':
                    destination = destination / sanitize_windows_component(primary_genre(track.genre) or 'Nieokreślony')
            elif status in {'duplicate', 'not_selected'}:
                destination = library.not_selected
            else:
                destination = library.review
            items.append(ExportItem(track, destination, track.proposed_filename or track.filename))
        return cls(tuple(items), {
            'ready': counts.get('ready', 0),
            'duplicate': counts.get('duplicate', 0),
            'not_selected': counts.get('not_selected', 0),
            'review': counts.get('review', 0),
            'total': len(items),
        })

    def preview_metrics(self) -> dict[str, int]:
        destination_targets = [(item.destination_dir.resolve(), item.filename) for item in self.items]
        destination_keys = [(str(directory).casefold(), filename.casefold()) for directory, filename in destination_targets]
        unique_keys = set(destination_keys)
        unique_targets: dict[tuple[str, str], tuple[Path, str]] = {}
        for target, key in zip(destination_targets, destination_keys):
            unique_targets.setdefault(key, target)
        return {
            'name_conflicts': len(destination_keys) - len(unique_keys),
            'existing_targets': sum(1 for directory, filename in unique_targets.values() if (directory / filename).exists()),
            'will_overwrite': 0,
        }

    @property
    def preview_summary(self) -> dict[str, int]:
        return {**self.summary, **self.preview_metrics()}

    def preview_lines(self, limit: int = 8) -> list[str]:
        lines: list[str] = []
        for item in self.items[:max(0, limit)]:
            lines.append(f'{item.track.filename}  →  {item.destination_dir.name}\\{item.filename}')
        return lines


@dataclass(frozen=True, slots=True)
class CopyVerification:
    source: Path
    destination: Path
    raw_copy_sha256_match: bool
    final_file_exists: bool
    final_size_bytes: int


@dataclass(frozen=True, slots=True)
class ExportResult:
    copied: tuple[Path, ...]
    errors: tuple[str, ...]
    verified: tuple[CopyVerification, ...] = ()
    verification_errors: tuple[str, ...] = ()


def _prepared_source_cover(track: TrackRecord):
    embedded = extract_embedded_cover(track.path)
    if not embedded:
        return None
    try:
        data, mime, _ = prepare_cover_image(embedded[0])
        return data, mime
    except Exception:
        return embedded


def _prepared_placeholder_cover():
    from audio_library_organizer.ui.assets import asset_path
    path = asset_path('no_cover.png')
    if not path.is_file():
        return None
    try:
        data, mime, _ = prepare_cover_image(path.read_bytes())
        return data, mime
    except Exception:
        return None


def _external_cover(track: TrackRecord, artwork, cover_cache: dict[str, tuple[bytes, str] | None]):
    if track.cover_art_url:
        key = f'url:{track.cover_art_url}'
        if key not in cover_cache:
            cover_cache[key] = artwork.fetch_url(track.cover_art_url)
        if cover_cache[key]:
            return cover_cache[key]
    if track.musicbrainz_release_id:
        key = f'mb:{track.musicbrainz_release_id}'
        if key not in cover_cache:
            cover_cache[key] = artwork.fetch_front(track.musicbrainz_release_id)
        if cover_cache[key]:
            return cover_cache[key]
    return None


def _manual_cover(track: TrackRecord):
    if not track.manual_cover_path:
        return None
    manual = Path(track.manual_cover_path)
    if not manual.is_file():
        return None
    try:
        data, mime, _ = prepare_cover_image(manual.read_bytes())
        return data, mime
    except Exception:
        return None


def resolve_cover_for_export(track: TrackRecord, artwork, cover_cache: dict[str, tuple[bytes, str] | None]):
    """Always return the best available cover, honoring an explicit user choice."""
    choice = (track.cover_choice or 'auto').casefold()
    manual = lambda: _manual_cover(track)
    external = lambda: _external_cover(track, artwork, cover_cache)
    source = lambda: _prepared_source_cover(track)
    placeholder = _prepared_placeholder_cover

    orders = {
        'manual': (manual, external, source, placeholder),
        'external': (external, source, manual, placeholder),
        'source': (source, external, manual, placeholder),
        'placeholder': (placeholder,),
        'auto': (manual, external, source, placeholder),
    }
    for provider in orders.get(choice, orders['auto']):
        cover = provider()
        if cover:
            return cover
    return None


def execute_copy_plan(plan: ExportPlan, *, artwork_client=None, progress=None) -> ExportResult:
    copied: list[Path] = []
    errors: list[str] = []
    verified: list[CopyVerification] = []
    verification_errors: list[str] = []
    artwork = artwork_client or CoverArtArchiveClient()
    cover_cache: dict[str, tuple[bytes,str] | None] = {}
    total = len(plan.items)
    for index, item in enumerate(plan.items, 1):
        target: Path | None = None
        try:
            target = copy_without_overwrite(item.track.path, item.destination_dir, item.filename)
            raw_ok = verify_exact_copy(item.track.path, target, source_sha256=item.track.sha256)
            if not raw_ok:
                raise OSError('Kopia nie przeszła weryfikacji SHA-256/rozmiaru przed zapisaniem tagów.')

            cover = resolve_cover_for_export(item.track, artwork, cover_cache)
            if cover:
                write_resolved_tags(target, item.track, cover_bytes=cover[0], cover_mime=cover[1], replace_cover=True)
            else:
                # Last-resort safety for unsupported formats. The source copy is still preserved.
                write_resolved_tags(target, item.track)

            final_exists = target.is_file()
            final_size = target.stat().st_size if final_exists else 0
            if not final_exists or final_size <= 0:
                verification_errors.append(f'{target}: plik końcowy nie istnieje lub ma zerowy rozmiar.')
                continue
            copied.append(target)
            verified.append(CopyVerification(
                source=Path(item.track.path),
                destination=target,
                raw_copy_sha256_match=True,
                final_file_exists=True,
                final_size_bytes=final_size,
            ))
        except Exception as exc:
            errors.append(f'{item.track.path}: {exc}')
            if target is not None and target.exists() and not verify_exact_copy(item.track.path, target, source_sha256=item.track.sha256):
                verification_errors.append(f'{target}: kopia niezgodna ze źródłem.')
        finally:
            if progress is not None:
                progress(index, total, item.track.filename)
    return ExportResult(tuple(copied), tuple(errors), tuple(verified), tuple(verification_errors))
