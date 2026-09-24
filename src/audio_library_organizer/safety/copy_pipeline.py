from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    p = Path(filename)
    stem, suffix = p.stem, p.suffix
    index = 2
    while True:
        candidate = directory / f'{stem} ({index}){suffix}'
        if not candidate.exists():
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


def copy_without_overwrite(source: Path, destination_dir: Path, filename: str | None = None) -> Path:
    source = Path(source)
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_path(destination_dir, filename or source.name)
    # copy2 reads the source and writes only the destination; metadata on source is untouched.
    shutil.copy2(source, target)
    return target
