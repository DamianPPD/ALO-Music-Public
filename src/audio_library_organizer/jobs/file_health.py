from __future__ import annotations

from pathlib import Path


def file_health_reasons(track, *, check_filesystem: bool = True) -> list[str]:
    reasons: list[str] = []
    path = Path(getattr(track, 'path', ''))
    if not getattr(track, 'is_available', True) or (check_filesystem and not path.is_file()):
        reasons.append('Plik niedostępny')
        return reasons
    duration = getattr(track, 'duration_seconds', None)
    if duration is not None and float(duration) <= 0:
        reasons.append('Nieprawidłowa długość audio')
    if not getattr(track, 'codec', None):
        reasons.append('Brak informacji o kodeku')
    if not getattr(track, 'artist', None) or not getattr(track, 'title', None):
        reasons.append('Niekompletne podstawowe tagi')
    size = getattr(track, 'size_bytes', 0) or 0
    if size <= 0:
        reasons.append('Pusty plik')
    return reasons
