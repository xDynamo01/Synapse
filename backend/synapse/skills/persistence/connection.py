from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .errors import SkillPersistenceUnavailable

_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10))}
)


@dataclass(frozen=True)
class SkillSQLiteConfig:
    database: Path
    busy_timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        if (
            isinstance(self.busy_timeout_ms, bool)
            or not isinstance(self.busy_timeout_ms, int)
            or self.busy_timeout_ms <= 0
        ):
            raise ValueError("skill database timeout is invalid")
        if not isinstance(self.database, Path):
            raise ValueError("skill database path is invalid")
        raw = str(self.database)
        if (
            not self.database.is_absolute()
            or raw.startswith("\\\\")
            or raw.startswith("//")
            or ".." in self.database.parts
            or any(
                part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
                for part in self.database.parts
            )
            or self.database.exists()
            and self.database.is_dir()
            or self.database.parent.exists()
            and self.database.parent.is_symlink()
        ):
            raise ValueError("skill database path is invalid")


class SkillSQLiteConnectionFactory:
    def __init__(self, config: SkillSQLiteConfig) -> None:
        self._config = config

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                str(self._config.database),
                timeout=self._config.busy_timeout_ms / 1_000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.enable_load_extension(False)
        except (OSError, sqlite3.Error) as exc:
            raise SkillPersistenceUnavailable() from exc
        try:
            yield connection
        finally:
            connection.close()
