from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import warnings
from pathlib import Path


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not os.path.lexists(candidate):
        return candidate
    p = Path(filename)
    stem, suffix = p.stem, p.suffix
    index = 2
    while True:
        candidate = directory / f'{stem} ({index}){suffix}'
        if not os.path.lexists(candidate):
            return candidate
        index += 1


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_exact_copy(source: Path, destination: Path, *, source_sha256: str | None = None) -> bool:
    source = Path(source)
    destination = Path(destination)
    if not destination.is_file():
        return False
    if source.stat().st_size != destination.stat().st_size:
        return False
    expected = source_sha256 or sha256_file(source)
    return sha256_file(destination) == expected


def _publish_without_overwrite(staged: Path, target: Path) -> None:
    # Windows rename never replaces an existing destination. POSIX rename does,
    # so use an atomic new hard link on the same filesystem instead. Unsupported
    # filesystems fail closed; never fall back to overwrite-prone copy/replace.
    if os.name == 'nt':
        os.rename(staged, target)
    else:
        os.link(staged, target, follow_symlinks=False)


def copy_without_overwrite(source: Path, destination_dir: Path, filename: str | None = None, *,
                           prepare=None, on_warning=None) -> Path:
    """Prepare a private copy, then publish it atomically under a free name.

    ``prepare`` can verify/write tags before publication. Cleanup is confined
    to this operation's fresh temporary directory, never a shared final path.
    """
    source = Path(source)
    destination_dir = Path(destination_dir)
    name = filename or source.name
    if name in {'.', '..'} or any(ord(c) in (0, 47, 58, 92) for c in name):
        raise ValueError('Destination filename must be a single file name.')
    destination_dir.mkdir(parents=True, exist_ok=True)
    working = Path(tempfile.mkdtemp(prefix='.alo-copy-', dir=destination_dir))
    staged = working / name
    try:
        with source.open('rb') as source_handle, staged.open('xb') as target_handle:
            source_mode = os.fstat(source_handle.fileno()).st_mode
            if not stat.S_ISREG(source_mode):
                raise OSError('Source is not a regular file.')
            if os.name == 'posix':
                # Narrow only this open copy, before writing payload. Owner-write
                # is retained only if its actual creation policy already allowed
                # it; source restrictions still cap group/other and ACL mask.
                fresh_mode = os.fstat(target_handle.fileno()).st_mode & 0o777
                mode = fresh_mode & ((source_mode & 0o777) | stat.S_IWUSR)
                if mode != fresh_mode:
                    os.fchmod(target_handle.fileno(), mode)
            shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
        # Do not clone filesystem attributes: source read-only state can prevent
        # Mutagen writes and Windows cleanup. Windows keeps its fresh creation ACL.
        if prepare is not None:
            prepare(staged)
        while True:
            target = _unique_path(destination_dir, name)
            try:
                _publish_without_overwrite(staged, target)
                return target
            except FileExistsError:
                continue
    finally:
        try:
            shutil.rmtree(working)
        except OSError as exc:
            # Publication may already have succeeded. Never turn a verified
            # output into an uncounted failure because private cleanup failed.
            message = f'Private copy cleanup failed: {working}: {exc}'
            if on_warning is not None:
                on_warning(message)
            else:
                warnings.warn(message, RuntimeWarning, stacklevel=2)
