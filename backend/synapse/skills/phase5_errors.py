from __future__ import annotations


class SkillPublicationError(RuntimeError):
    """Base error for the application-level publication authority."""

    code = "skill_publication_error"
    safe_message = "skill publication failed"

    def __init__(self) -> None:
        super().__init__(self.safe_message)


class InvalidSkillPublicationRequest(SkillPublicationError):
    code = "invalid_skill_publication_request"
    safe_message = "skill publication request is invalid"


class SkillPublicationSnapshotMismatch(SkillPublicationError):
    code = "skill_publication_snapshot_mismatch"
    safe_message = "verified skill snapshot identity does not match"


class SkillPublicationConflict(SkillPublicationError):
    code = "skill_publication_conflict"
    safe_message = "skill publication conflicts with the catalog"


class SkillPublicationCatalogUnavailable(SkillPublicationError):
    code = "skill_publication_catalog_unavailable"
    safe_message = "skill publication catalog is unavailable"


class PublishedSkillVersionNotFound(SkillPublicationError):
    code = "published_skill_version_not_found"
    safe_message = "published skill version was not found"
