from __future__ import annotations

from dataclasses import dataclass
import json


# Controlled vocabulary. File tags never extend this list.
ALO_GENRES = (
    'House', 'Deep House', 'Progressive House', 'Electro House', 'Tech House',
    'Funky House', 'Disco House', 'Jackin House', 'Bass House',
    'Trance', 'Progressive Trance', 'Vocal Trance', 'Uplifting Trance',
    'Tech Trance', 'Psytrance', 'Hard Trance',
    'Dance', 'Eurodance', 'Europop', 'Hands Up', 'Club', 'Dance Pop',
    'Techno', 'Minimal', 'Hard Techno', 'Melodic Techno',
    'Electro', 'Breakbeat', 'Breaks', 'Drum & Bass', 'Dubstep', 'Garage', 'Bassline',
    'Hardstyle', 'Hardcore', 'Happy Hardcore',
    'Disco', 'Nu Disco', 'Italo Disco', 'Funk',
    'Pop', 'Synth Pop', 'Rock', 'Alternative', 'Alternative Rock', 'Indie', 'Indie Rock',
    'Hip-Hop', 'Rap', 'R&B', 'Soul', 'Jazz', 'Blues', 'Reggae', 'Latin',
    'Ambient', 'Chillout', 'Downtempo', 'Lounge', 'Classical', 'Soundtrack', 'EDM', 'Other',
)


@dataclass(frozen=True, slots=True)
class GenreSettings:
    custom_genres: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        seen = {name.casefold() for name in ALO_GENRES}
        result = []
        values = self.custom_genres if isinstance(self.custom_genres, (list, tuple)) else ()
        for value in values:
            if not isinstance(value, str):
                continue
            name = value.strip()
            if name and name.casefold() not in seen:
                result.append(name)
                seen.add(name.casefold())
        object.__setattr__(self, 'custom_genres', tuple(result))

    @classmethod
    def from_store(cls, store) -> 'GenreSettings':
        raw = store.value('genres/custom', '[]')
        try:
            values = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            values = ()
        return cls(values if isinstance(values, (list, tuple)) else ())

    def save(self, store) -> None:
        store.setValue('genres/custom', json.dumps(self.custom_genres, ensure_ascii=False))
        store.sync()

    def suggestions(self) -> list[str]:
        return sorted((*ALO_GENRES, *self.custom_genres), key=str.casefold)
