from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory


@dataclass(slots=True)
class SessionStorage:
    """Ephemeral storage for one application run.

    Scan/index data lives here instead of inside the user's destination
    library.  Closing the application removes the whole directory.
    """

    _tempdir: TemporaryDirectory[str]

    @classmethod
    def create(cls) -> "SessionStorage":
        return cls(TemporaryDirectory(prefix="alo-session-"))

    @property
    def root(self) -> Path:
        return Path(self._tempdir.name)

    @property
    def database_path(self) -> Path:
        return self.root / "session.sqlite3"

    def cleanup(self) -> None:
        self._tempdir.cleanup()
