from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
import os
from pathlib import Path
import stat

from audio_library_organizer.storage.source_registry import canonical_locator

SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.opus', '.wma'}


class SourceScanStatus(StrEnum):
    SUCCESS = 'success'
    UNAVAILABLE = 'unavailable'
    ERROR = 'error'
    CANCELLED = 'cancelled'


@dataclass(frozen=True, slots=True)
class SourceScanOutcome:
    root: str
    status: SourceScanStatus
    files: int = 0
    reason: str = ''


@dataclass(frozen=True, slots=True)
class ScanInventory:
    files: tuple[Path, ...]
    outcomes: tuple[SourceScanOutcome, ...]
    file_roots: tuple[tuple[Path, tuple[int, ...]], ...]


def scan_audio_sources(source_dirs: Iterable[Path], *, cancelled=None) -> ScanInventory:
    """Enumerate roots explicitly; a partial read is never an empty success.

    Directory symlinks are not followed, avoiding cycles. File aliases and
    overlapping roots share one canonical locator in the processing queue.
    """
    found: dict[str, Path] = {}
    owners: dict[str, set[int]] = {}
    outcomes = []
    for root_index, raw_root in enumerate(source_dirs):
        root = Path(raw_root)
        local: set[str] = set()
        state = SourceScanStatus.SUCCESS
        reason = ''
        root_present = False
        try:
            root = root.expanduser().resolve()
            if cancelled and cancelled():
                state = SourceScanStatus.CANCELLED
            else:
                root_stat = root.stat()
                root_present = True
                if not stat.S_ISDIR(root_stat.st_mode):
                    raise NotADirectoryError(str(root))
                pending = [root]
                while pending and state == SourceScanStatus.SUCCESS:
                    with os.scandir(pending.pop()) as entries:
                        for entry in entries:
                            if cancelled and cancelled():
                                state = SourceScanStatus.CANCELLED
                                break
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(Path(entry.path))
                            elif Path(entry.name).suffix.lower() in SUPPORTED_EXTENSIONS:
                                # stat exposes entries disappearing during traversal.
                                if stat.S_ISREG(entry.stat().st_mode):
                                    absolute, key = canonical_locator(entry.path)
                                    local.add(key)
                                    found[key] = Path(absolute)
                                    owners.setdefault(key, set()).add(root_index)
        except FileNotFoundError as exc:
            state = SourceScanStatus.ERROR if root_present else SourceScanStatus.UNAVAILABLE
            reason = str(exc)
        except (OSError, RuntimeError, ValueError) as exc:
            state, reason = SourceScanStatus.ERROR, str(exc)
        outcomes.append(SourceScanOutcome(str(root), state, len(local), reason))
    files = tuple(sorted(found.values(), key=lambda p: str(p).casefold()))
    return ScanInventory(files, tuple(outcomes),
                         tuple((found[key], tuple(sorted(indexes))) for key, indexes in owners.items()))


def iter_audio_files(source_dirs: Iterable[Path]) -> Iterator[Path]:
    """Compatibility iterator; authoritative callers use scan_audio_sources."""
    yield from scan_audio_sources(source_dirs).files
