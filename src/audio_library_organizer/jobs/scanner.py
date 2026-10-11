from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
import os
import ntpath
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
    file_stats: tuple[tuple[Path, os.stat_result], ...] = ()
    root_stats: tuple[os.stat_result | None, ...] = ()


class UnsafeSourcePath(OSError):
    """An alias/reparse point/mount is not an authoritative absence check."""


def scoped_stat(path: Path, root: Path, expected_root=None) -> os.stat_result:
    """Do not follow any alias in a check locator, including its ancestors.

    Device changes within the configured root and Windows reparse points need
    explicit future resolution. They are never silently scanned as owned scope.
    """
    path, root = Path(path), Path(root)
    if not path.is_absolute() or not root.is_absolute() or '..' in path.parts or '..' in root.parts:
        raise UnsafeSourcePath('LOCATOR_SCOPE_UNRESOLVED')
    path.relative_to(root)
    current = Path(root.anchor)
    root_info = None
    # The anchor is itself a possible configured root (/, C:\\, UNC share).
    # Validate it before descendants, just like any other source directory.
    components = [current]
    for part in path.parts[1:]:
        current /= part
        components.append(current)
    for current in components:
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise UnsafeSourcePath('ALIAS_OR_MOUNT_UNRESOLVED: ' + str(current))
        if current == root:
            root_info = info
            if expected_root is not None and (info.st_dev, info.st_ino) != (expected_root.st_dev, expected_root.st_ino):
                raise UnsafeSourcePath('ROOT_IDENTITY_CHANGED: ' + str(root))
        elif root_info is not None and info.st_dev != root_info.st_dev:
            raise UnsafeSourcePath('ALIAS_OR_MOUNT_UNRESOLVED: ' + str(current))
    return info


def scan_audio_sources(source_dirs: Iterable[Path], *, cancelled=None, conservative=False) -> ScanInventory:
    """Enumerate roots explicitly; a partial read is never an empty success.

    Directory symlinks are not followed, avoiding cycles. File aliases and
    overlapping roots share one canonical locator in the processing queue.
    """
    found: dict[str, Path] = {}
    owners: dict[str, set[int]] = {}
    stats: dict[str, os.stat_result] = {}
    outcomes = []
    root_stats = []
    for root_index, raw_root in enumerate(source_dirs):
        root = Path(raw_root)
        local: set[str] = set()
        state = SourceScanStatus.SUCCESS
        reason = ''
        root_present = False
        root_stat = None
        try:
            if cancelled and cancelled():
                state = SourceScanStatus.CANCELLED
            else:
                if conservative and os.name != 'nt' and (ntpath.splitdrive(str(root))[0] or str(root).startswith('\\\\')):
                    raise FileNotFoundError('FOREIGN_PLATFORM_LOCATOR: ' + str(root))
                root = root.expanduser().absolute() if conservative else root.expanduser().resolve()
                root_stat = scoped_stat(root, root) if conservative else root.stat()
                root_present = True
                if not stat.S_ISDIR(root_stat.st_mode):
                    raise NotADirectoryError(str(root))
                pending = [root]
                while pending and state == SourceScanStatus.SUCCESS:
                    directory = pending.pop()
                    if conservative:
                        scoped_stat(directory, root, root_stat)
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            if cancelled and cancelled():
                                state = SourceScanStatus.CANCELLED
                                break
                            if conservative:
                                entry_stat = scoped_stat(Path(entry.path), root, root_stat)
                            else:
                                entry_stat = None
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(Path(entry.path))
                            elif Path(entry.name).suffix.lower() in SUPPORTED_EXTENSIONS:
                                # stat exposes entries disappearing during traversal.
                                info = entry_stat if conservative else entry.stat()
                                if stat.S_ISREG(info.st_mode):
                                    absolute, key = canonical_locator(entry.path)
                                    if conservative:
                                        # Detect parent replacement while resolving the locator.
                                        scoped_stat(Path(entry.path), root, root_stat)
                                    local.add(key)
                                    found[key] = Path(absolute)
                                    stats[key] = info
                                    owners.setdefault(key, set()).add(root_index)
                    if conservative:
                        scoped_stat(directory, root, root_stat)
                if conservative:
                    scoped_stat(root, root, root_stat)
        except FileNotFoundError as exc:
            state = SourceScanStatus.ERROR if root_present else SourceScanStatus.UNAVAILABLE
            reason = str(exc)
        except (OSError, RuntimeError, ValueError) as exc:
            state, reason = SourceScanStatus.ERROR, str(exc)
        outcomes.append(SourceScanOutcome(str(root), state, len(local), reason))
        root_stats.append(root_stat)
    files = tuple(sorted(found.values(), key=lambda p: str(p).casefold()))
    return ScanInventory(files, tuple(outcomes),
                         tuple((found[key], tuple(sorted(indexes))) for key, indexes in owners.items()),
                         tuple((found[key], info) for key, info in stats.items()), tuple(root_stats))


def iter_audio_files(source_dirs: Iterable[Path]) -> Iterator[Path]:
    """Compatibility iterator; authoritative callers use scan_audio_sources."""
    yield from scan_audio_sources(source_dirs).files
