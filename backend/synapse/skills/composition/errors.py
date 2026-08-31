from __future__ import annotations


class SkillsCompositionError(RuntimeError):
    message = "skills runtime composition operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.message)


class SkillsCompositionInvalidConfiguration(SkillsCompositionError):
    message = "skills runtime configuration is invalid"


class SkillsCompositionMigrationFailed(SkillsCompositionError):
    message = "skills runtime migration failed"


class SkillsCompositionMigrationRequired(SkillsCompositionError):
    message = "skills runtime schema migration is required"


class SkillsCompositionSchemaUnsupported(SkillsCompositionError):
    message = "skills runtime schema is unsupported"


class SkillsCompositionChecksumMismatch(SkillsCompositionError):
    message = "skills runtime migration checksum is invalid"


class SkillsCompositionDatabaseUnavailable(SkillsCompositionError):
    message = "skills runtime database is unavailable"


class SkillsCompositionIntegrityFailed(SkillsCompositionError):
    message = "skills runtime integrity verification failed"


class SkillsCompositionConstructionFailed(SkillsCompositionError):
    message = "skills runtime dependency construction failed"


class SkillsCompositionClosed(SkillsCompositionError):
    message = "skills runtime composition is closed"


class SkillsCompositionCompatibilityUnavailable(SkillsCompositionError):
    message = "skills runtime compatibility is unavailable"
