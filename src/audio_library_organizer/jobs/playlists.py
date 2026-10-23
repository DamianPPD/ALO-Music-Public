from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Iterable


def write_m3u8(target: Path, paths: Iterable[Path], *, relative: bool = True, guard=None, before_write=None) -> Path:
    target = Path(target)
    if target.suffix.lower() != '.m3u8':
        target = target.with_suffix('.m3u8')
    if guard is None:
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        guard()
    lines = ['#EXTM3U']
    base = target.parent.resolve()
    if guard is not None:
        guard()
    for raw in paths:
        path = Path(raw).resolve()
        if guard is not None:
            guard()
        rendered = str(path)
        if relative:
            try:
                rendered = os.path.relpath(path, base)
            except ValueError:
                rendered = str(path)
        lines.append(rendered.replace('\\', '/'))
    if guard is not None:
        guard()
        target.parent.mkdir(parents=True, exist_ok=True)
        guard()
    if before_write is not None:
        before_write()
    if guard is not None:
        guard()
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
    return target
