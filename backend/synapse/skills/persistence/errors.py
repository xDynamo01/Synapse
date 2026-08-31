from __future__ import annotations

from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreSemanticConflict,
    SkillStoreUnavailable,
)


class SkillPersistenceError(RuntimeError):
    message = "skill persistence operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.message)


class SkillPersistenceUnavailable(SkillPersistenceError, SkillStoreUnavailable):
    message = "skill persistence is unavailable"


class SkillPersistenceSchemaUnsupported(SkillPersistenceError):
    message = "skill persistence schema is unsupported"


class SkillPersistenceMigrationRequired(SkillPersistenceError):
    message = "skill persistence migration is required"


class SkillPersistenceMigrationChecksumMismatch(SkillPersistenceError):
    message = "skill persistence migration checksum does not match"


class SkillPersistenceMigrationFailed(SkillPersistenceError):
    message = "skill persistence migration failed"


class SkillPersistenceDatabaseCorrupt(SkillPersistenceError):
    message = "skill persistence database is corrupt"


class SkillPersistenceRecordDecodeFailed(SkillPersistenceError, SkillStoreUnavailable):
    message = "skill persistence record could not be decoded"


class SkillPersistenceUniquenessConflict(
    SkillPersistenceError, SkillStoreSemanticConflict
):
    message = "skill persistence uniqueness conflict"


class SkillPersistenceDivergentDuplicate(
    SkillPersistenceError, SkillStoreDivergentDuplicate
):
    message = "skill persistence duplicate is divergent"


class SkillPersistenceTransactionFailed(SkillPersistenceError, SkillStoreUnavailable):
    message = "skill persistence transaction failed"


class SkillPersistenceQueryFailed(SkillPersistenceError, SkillStoreUnavailable):
    message = "skill persistence query failed"
