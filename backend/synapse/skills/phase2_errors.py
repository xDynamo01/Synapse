from __future__ import annotations


class SkillPhase2DomainError(ValueError):
    """Base error for immutable Skills Phase 2 domain values."""

    code = "skill_phase2_domain_error"


class InvalidSkillId(SkillPhase2DomainError):
    code = "invalid_skill_id"


class InvalidSkillVersion(SkillPhase2DomainError):
    code = "invalid_skill_version"


class InvalidSkillVersionConstraint(SkillPhase2DomainError):
    code = "invalid_skill_version_constraint"


class UnsupportedSkillManifestFormat(SkillPhase2DomainError):
    code = "unsupported_skill_manifest_format"


class InvalidSkillFingerprint(SkillPhase2DomainError):
    code = "invalid_skill_fingerprint"


class InvalidSkillReference(SkillPhase2DomainError):
    code = "invalid_skill_reference"


class InvalidSkillContentReference(SkillPhase2DomainError):
    code = "invalid_skill_content_reference"


class InvalidSkillDependencyDeclaration(SkillPhase2DomainError):
    code = "invalid_skill_dependency_declaration"


class InvalidSkillCompatibilityDeclaration(SkillPhase2DomainError):
    code = "invalid_skill_compatibility_declaration"


class InvalidSkillSecurityDeclaration(SkillPhase2DomainError):
    code = "invalid_skill_security_declaration"


class InvalidPublishedSkillManifest(SkillPhase2DomainError):
    code = "invalid_published_skill_manifest"


class NonCanonicalSkillManifest(SkillPhase2DomainError):
    code = "non_canonical_skill_manifest"


class ImmutableSkillIdentityMismatch(SkillPhase2DomainError):
    code = "immutable_skill_identity_mismatch"
