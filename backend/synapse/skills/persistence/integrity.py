from __future__ import annotations

from datetime import UTC, datetime

from .connection import SkillSQLiteConnectionFactory
from .migrations import SkillPersistenceMigrator, SkillPersistenceSchemaVersion


class SkillPersistenceIntegrityChecker:
    """Explicit health entry point; never runs implicitly on ordinary reads."""

    def __init__(self, connections: SkillSQLiteConnectionFactory) -> None:
        self._connections = connections

    def check(self) -> SkillPersistenceSchemaVersion:
        return SkillPersistenceMigrator(
            self._connections,
            lambda: datetime.min.replace(tzinfo=UTC),
        ).verify()
