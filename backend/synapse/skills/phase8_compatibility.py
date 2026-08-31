from __future__ import annotations

import hashlib

from synapse.skills.phase2_models import (
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillSecurityDeclaration,
    SkillSemanticReference,
)
from synapse.skills.phase2_serialization import canonical_json_bytes
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase8_matching import matches_constraint
from synapse.skills.phase8_models import (
    CompatibilityRequirementValue,
    SkillCompatibilityDimension,
    SkillCompatibilityObservation,
    SkillCompatibilityObservationStatus,
    SkillCompatibilityRequirementFact,
    SkillCompatibilityRequirementId,
    SkillCompatibilityStatus,
)


def compatibility_requirements(
    subject: PublishedSkillVersionRecord,
    candidate: PublishedSkillVersionRecord,
) -> tuple[SkillCompatibilityRequirementFact, ...]:
    facts: dict[
        SkillCompatibilityRequirementId, SkillCompatibilityRequirementFact
    ] = {}
    for record in (subject, candidate):
        manifest = record.manifest
        compatibility = manifest.compatibility
        values: list[
            tuple[SkillCompatibilityDimension, CompatibilityRequirementValue]
        ] = []
        values.extend(
            (SkillCompatibilityDimension.OPERATING_PROFILE, value)
            for value in compatibility.operating_profiles
        )
        values.extend(
            (SkillCompatibilityDimension.PLATFORM, value)
            for value in compatibility.platforms
        )
        if compatibility.python_constraint is not None:
            values.append(
                (
                    SkillCompatibilityDimension.PYTHON_RUNTIME,
                    compatibility.python_constraint,
                )
            )
        values.extend(
            (SkillCompatibilityDimension.EXTERNAL_RUNTIME, value)
            for value in compatibility.external_runtimes
        )
        values.extend(
            (SkillCompatibilityDimension.PROVIDER, value)
            for value in compatibility.providers
        )
        values.extend(
            (SkillCompatibilityDimension.SCHEMA, value)
            for value in compatibility.schemas
        )
        security = manifest.security
        defaults = SkillSecurityDeclaration()
        if security.classification_ceiling is not defaults.classification_ceiling:
            values.append(
                (
                    SkillCompatibilityDimension.SECURITY_CLASSIFICATION,
                    security.classification_ceiling,
                )
            )
        if security.network_requirement is not defaults.network_requirement:
            values.append(
                (
                    SkillCompatibilityDimension.SECURITY_NETWORK,
                    security.network_requirement,
                )
            )
        if (
            security.external_processing_requirement
            is not defaults.external_processing_requirement
        ):
            values.append(
                (
                    SkillCompatibilityDimension.SECURITY_EXTERNAL_PROCESSING,
                    security.external_processing_requirement,
                )
            )
        if security.filesystem_requirement is not defaults.filesystem_requirement:
            values.append(
                (
                    SkillCompatibilityDimension.SECURITY_FILESYSTEM,
                    security.filesystem_requirement,
                )
            )
        if security.egress_requirement is not defaults.egress_requirement:
            values.append(
                (
                    SkillCompatibilityDimension.SECURITY_EGRESS,
                    security.egress_requirement,
                )
            )
        if security.sandbox_profile_requirement is not None:
            values.append(
                (
                    SkillCompatibilityDimension.SECURITY_SANDBOX_PROFILE,
                    security.sandbox_profile_requirement,
                )
            )
        values.extend(
            (SkillCompatibilityDimension.SECURITY_SECRET_REFERENCE, value)
            for value in security.secret_reference_requirements
        )
        for dimension, value in values:
            requirement_id = compatibility_requirement_id(
                record.identity, dimension, value
            )
            facts[requirement_id] = SkillCompatibilityRequirementFact(
                requirement_id, record.identity, dimension, value
            )
    return tuple(facts[key] for key in sorted(facts, key=str))


def compatibility_requirement_id(
    owner: PublishedSkillVersionId,
    dimension: SkillCompatibilityDimension,
    value: CompatibilityRequirementValue,
) -> SkillCompatibilityRequirementId:
    digest = hashlib.sha256(
        canonical_json_bytes((owner.to_canonical_text(), dimension.value, value))
    ).hexdigest()
    return SkillCompatibilityRequirementId(
        f"compatibility-requirement:{digest}"
    )


def compatibility_status(
    subject: PublishedSkillVersionRecord,
    candidate: PublishedSkillVersionRecord,
    requirements: tuple[SkillCompatibilityRequirementFact, ...],
    observations: tuple[SkillCompatibilityObservation, ...],
    profile_ref: SkillSemanticReference,
    used_observations: set[SkillSemanticReference],
) -> tuple[
    SkillCompatibilityStatus,
    tuple[SkillSemanticReference, ...],
    bool,
]:
    declared_incompatible = declares_conflict(
        subject.manifest, candidate.identity
    ) or declares_conflict(candidate.manifest, subject.identity)
    requirement_ids = {
        requirement.requirement_id for requirement in requirements
    }
    applicable = tuple(
        observation
        for observation in observations
        if observation.dependency == candidate.identity
        and observation.analysis_profile_ref == profile_ref
        and observation.requirement_id in requirement_ids
    )
    for observation in applicable:
        used_observations.add(observation.observation_ref)
    by_requirement: dict[
        SkillCompatibilityRequirementId,
        set[SkillCompatibilityObservationStatus],
    ] = {}
    for observation in applicable:
        by_requirement.setdefault(observation.requirement_id, set()).add(
            observation.status
        )
    conflicting = any(len(statuses) > 1 for statuses in by_requirement.values())
    any_positive = any(
        SkillCompatibilityObservationStatus.COMPATIBLE in statuses
        for statuses in by_requirement.values()
    )
    any_negative = any(
        SkillCompatibilityObservationStatus.INCOMPATIBLE in statuses
        for statuses in by_requirement.values()
    )
    refs = tuple(sorted((item.observation_ref for item in applicable), key=str))
    if conflicting or (declared_incompatible and any_positive):
        return SkillCompatibilityStatus.CONFLICTING_INFORMATION, refs, False
    if any_negative:
        return SkillCompatibilityStatus.OBSERVED_INCOMPATIBLE, refs, False
    if declared_incompatible:
        return SkillCompatibilityStatus.DECLARED_INCOMPATIBLE, refs, False
    if requirements and all(
        SkillCompatibilityObservationStatus.COMPATIBLE
        in by_requirement.get(requirement.requirement_id, set())
        for requirement in requirements
    ):
        return SkillCompatibilityStatus.OBSERVED_COMPATIBLE, refs, False
    if requirements:
        return SkillCompatibilityStatus.UNKNOWN, refs, True
    return SkillCompatibilityStatus.DECLARED_COMPATIBLE, refs, False


def declares_conflict(
    manifest: PublishedSkillManifest,
    other: PublishedSkillVersionId,
) -> bool:
    return any(
        declaration.skill_id == other.skill_id
        and (
            declaration.version_constraint is None
            or matches_constraint(declaration.version_constraint, other.version)
        )
        for declaration in manifest.conflicts
    )
