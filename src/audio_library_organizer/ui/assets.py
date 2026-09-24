from __future__ import annotations

from pathlib import Path
import sys


def asset_path(name: str) -> Path:
    """Resolve bundled UI assets in editable installs and PyInstaller builds."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    candidate = base / 'assets' / name
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parents[1] / 'assets' / name
