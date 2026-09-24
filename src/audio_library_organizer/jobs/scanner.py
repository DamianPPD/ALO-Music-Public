from __future__ import annotations

from pathlib import Path
from collections.abc import Iterable, Iterator

SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.opus', '.wma'}


def iter_audio_files(source_dirs: Iterable[Path]) -> Iterator[Path]:
    seen: set[Path] = set()
    found: list[Path] = []
    for root in source_dirs:
        root = Path(root)
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                rp = path.resolve()
                if rp not in seen:
                    found.append(rp)
                    seen.add(rp)
    yield from sorted(found, key=lambda p: str(p).casefold())
