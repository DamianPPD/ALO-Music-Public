from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import Counter
from time import perf_counter

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.safety.copy_pipeline import copy_without_overwrite, verify_exact_copy, sha256_file
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
    category: str = 'review'


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
            category = 'not_selected' if status in {'duplicate', 'not_selected'} else status
            items.append(ExportItem(track, destination, track.proposed_filename or track.filename, category))
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
class ExportOutcome:
    index: int
    source: Path
    destination: Path | None
    category: str
    status: str
    error: str = ''
    raw_verified: bool = False
    final_size_bytes: int = 0
    final_sha256: str = ''


@dataclass(frozen=True, slots=True)
class ExportEvent:
    phase: str
    total: int
    processed: int
    created: int
    failed: int
    source: Path | None = None
    destination: Path | None = None
    message: str = ''
    skipped: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.processed)


@dataclass(frozen=True, slots=True)
class ExportResult:
    copied: tuple[Path, ...]
    errors: tuple[str, ...]
    verified: tuple[CopyVerification, ...] = ()
    verification_errors: tuple[str, ...] = ()
    outcomes: tuple[ExportOutcome, ...] = ()
    planned: int = 0
    cancelled: bool = False
    elapsed_seconds: float = 0.0
    fatal_error: str = ''
    cleanup_warnings: tuple[str, ...] = ()

    @property
    def created(self) -> int:
        return len(self.verified)

    @property
    def processed(self) -> int:
        return len(self.outcomes)

    @property
    def failed(self) -> int:
        return sum(item.status not in {'verified', 'skipped'} for item in self.outcomes)

    @property
    def skipped(self) -> int:
        return sum(item.status == 'skipped' for item in self.outcomes)

    @property
    def remaining(self) -> int:
        return max(0, self.planned - self.processed)

    @property
    def category_counts(self) -> dict[str, int]:
        counts = Counter(item.category for item in self.outcomes if item.status == 'verified')
        return {category: counts[category] for category in ('ready', 'review', 'not_selected')}

    @property
    def status(self) -> str:
        if self.cancelled:
            return 'cancelled'
        if (self.fatal_error or self.cleanup_warnings or self.errors or self.verification_errors or self.failed
                or self.skipped or self.remaining or self.created != self.planned):
            return 'problems'
        return 'success'


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


def execute_copy_plan(plan: ExportPlan, *, artwork_client=None, progress=None,
                      cancelled=None, event=None) -> ExportResult:
    """Finish the current item safely; cancellation only prevents the next item."""
    started = perf_counter()
    cancelled = cancelled or (lambda: False)
    copied: list[Path] = []
    errors: list[str] = []
    verified: list[CopyVerification] = []
    verification_errors: list[str] = []
    outcomes: list[ExportOutcome] = []
    artwork = artwork_client or CoverArtArchiveClient()
    cover_cache: dict[str, tuple[bytes, str] | None] = {}
    total = len(plan.items)

    def emit(phase, source=None, destination=None, message=''):
        if event is not None:
            event(ExportEvent(phase, total, len(outcomes), len(verified),
                              sum(o.status != 'verified' for o in outcomes),
                              source, destination, message))

    emit('operation_started')
    cleanup_warnings: list[str] = []
    for index, item in enumerate(plan.items, 1):
        if cancelled():
            break
        target = None
        raw_ok, final_size, final_sha = False, 0, ''
        stage = 'copy_error'
        source = Path(item.track.path)

        def prepare(staged):
            nonlocal stage, raw_ok, final_size, final_sha
            emit('copied', source, staged)
            stage = 'verification_error'
            if not verify_exact_copy(source, staged, source_sha256=item.track.sha256):
                raise OSError('Kopia nie przeszła weryfikacji SHA-256/rozmiaru przed zapisaniem tagów.')
            raw_ok = True
            emit('raw_verified', source, staged)
            stage = 'tag_error'
            cover = resolve_cover_for_export(item.track, artwork, cover_cache)
            emit('tagging', source, staged)
            if cover:
                write_resolved_tags(staged, item.track, cover_bytes=cover[0], cover_mime=cover[1], replace_cover=True)
            else:
                write_resolved_tags(staged, item.track)
            emit('tags_written', source, staged)
            stage = 'verification_error'
            emit('final_verifying', source, staged)
            final_stat = staged.stat()
            final_size = final_stat.st_size
            if not staged.is_file() or final_size <= 0:
                raise OSError('Plik końcowy nie istnieje lub ma zerowy rozmiar.')
            # Tags intentionally change the raw SHA; keep a separate final digest.
            final_sha = sha256_file(staged)
            after_hash = staged.stat()
            fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if tuple(getattr(after_hash, f) for f in fields) != tuple(getattr(final_stat, f) for f in fields):
                raise OSError('Destination changed during final verification.')
            stage = 'copy_error'  # Publication itself can still fail.

        emit('item_started', source)
        try:
            target = copy_without_overwrite(source, item.destination_dir, item.filename,
                                           prepare=prepare, on_warning=cleanup_warnings.append)
            emit('final_verified', source, target)
            copied.append(target)
            verified.append(CopyVerification(source, target, True, True, final_size))
            outcomes.append(ExportOutcome(index, source, target, item.category, 'verified',
                                          raw_verified=True, final_size_bytes=final_size, final_sha256=final_sha))
            emit('item_finished', source, target)
        except Exception as exc:
            error = f'{source}: {exc}'
            (verification_errors if stage == 'verification_error' else errors).append(error)
            outcomes.append(ExportOutcome(index, source, target, item.category, stage, error,
                                          raw_ok, final_size, final_sha))
            emit('item_failed', source, target, error)
        finally:
            if progress is not None:
                progress(index, total, item.track.filename)
    result = ExportResult(tuple(copied), tuple(errors), tuple(verified), tuple(verification_errors),
                          tuple(outcomes), total, bool(cancelled()), perf_counter() - started,
                          cleanup_warnings=tuple(cleanup_warnings))
    emit('operation_finished')
    return result
