from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Iterable


def write_m3u8(target: Path, paths: Iterable[Path], *, relative: bool = True) -> Path:
    target = Path(target)
    if target.suffix.lower() != '.m3u8':
        target = target.with_suffix('.m3u8')
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ['#EXTM3U']
    base = target.parent.resolve()
    for raw in paths:
        path = Path(raw).resolve()
        rendered = str(path)
        if relative:
            try:
                rendered = os.path.relpath(path, base)
            except ValueError:
                rendered = str(path)
        lines.append(rendered.replace('\\', '/'))
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
    return target
