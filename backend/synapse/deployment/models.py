"""Immutable provider-neutral Deployment Runtime V1 contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .canonical import DEPLOYMENT_CANONICAL_FORMAT_V1, content_fingerprint
from .errors import (
    InvalidDeploymentArtifactReference,
    InvalidDeploymentAttemptBinding,
    InvalidDeploymentEnvironment,
    InvalidDeploymentIntent,
    InvalidDeploymentMetadata,
    InvalidDeploymentRevision,
    InvalidDeploymentTarget,
)
from .identities import (
    AdapterBindingReference,
    ArtifactFingerprintReference,
    ArtifactReference,
    AuthorizationReference,
    CapabilityReference,
    CausationReference,
    CorrelationReference,
    CustodyReference,
    DeploymentAttemptId,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    DeploymentIntentId,
    DeploymentTargetId,
    EnvironmentId,
    ObservationReference,
    OccurrenceReference,
    PolicyReference,
    PromotionId,
    ProvenanceReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    RollbackAttemptId,
    RolloutId,
    SlotId,
)

_METADATA_PART = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,63}/[a-z0-9][a-z0-9.+-]{0,63}$")
_LOGICAL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,95}$")


class EnvironmentClassification(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"
    OTHER = "other"


class DeploymentTargetClass(StrEnum):
    APPLICATION = "application"
    SERVICE = "service"
    WORKLOAD = "workload"
    STATIC_ASSET = "static-asset"
    OTHER = "other"


class ArtifactMediaClass(StrEnum):
    APPLICATION_BUNDLE = "application-bundle"
    EXECUTABLE_BUNDLE = "executable-bundle"
    CONTAINER_IMAGE_REFERENCE = "container-image-reference"
    STATIC_ASSET_BUNDLE = "static-asset-bundle"
    OTHER = "other"


class RolloutStageClass(StrEnum):
    INITIAL = "initial"
    INTERMEDIATE = "intermediate"
    FINAL = "final"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True, order=True)
class DeploymentMetadataEntry:
    namespace: str
    key: str
    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.namespace, str)
            or not _METADATA_PART.fullmatch(self.namespace)
            or not isinstance(self.key, str)
            or not _METADATA_PART.fullmatch(self.key)
            or not isinstance(self.value, str)
            or not 1 <= len(self.value) <= 256
            or any(ord(character) < 32 for character in self.value)
        ):
            raise InvalidDeploymentMetadata("metadata must be namespaced, bounded and printable")


def _normalize_metadata(
    metadata: tuple[DeploymentMetadataEntry, ...],
) -> tuple[DeploymentMetadataEntry, ...]:
    if not isinstance(metadata, tuple) or not all(
        isinstance(item, DeploymentMetadataEntry) for item in metadata
    ):
        raise InvalidDeploymentMetadata("metadata must be an immutable entry tuple")
    normalized = tuple(sorted(metadata))
    if len(normalized) > 32:
        raise InvalidDeploymentMetadata("metadata cannot exceed 32 entries")
    if len({(item.namespace, item.key) for item in normalized}) != len(normalized):
        raise InvalidDeploymentMetadata("metadata keys must be unique per namespace")
    return normalized


@dataclass(frozen=True, slots=True)
class DeploymentEnvironmentV1:
    environment_id: EnvironmentId
    logical_name: str
    classification: EnvironmentClassification
    policy_reference: PolicyReference
    metadata: tuple[DeploymentMetadataEntry, ...] = ()
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.environment_id, EnvironmentId)
            or not isinstance(self.logical_name, str)
            or not _LOGICAL_NAME.fullmatch(self.logical_name)
            or not isinstance(self.classification, EnvironmentClassification)
            or not isinstance(self.policy_reference, PolicyReference)
        ):
            raise InvalidDeploymentEnvironment("environment logical name is invalid")
        object.__setattr__(self, "metadata", _normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class DeploymentTargetV1:
    target_id: DeploymentTargetId
    environment_id: EnvironmentId
    adapter_binding: AdapterBindingReference
    target_class: DeploymentTargetClass
    slot_id: SlotId | None = None
    capability_references: tuple[CapabilityReference, ...] = ()
    metadata: tuple[DeploymentMetadataEntry, ...] = ()
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.target_id, DeploymentTargetId)
            or not isinstance(self.environment_id, EnvironmentId)
            or not isinstance(self.adapter_binding, AdapterBindingReference)
            or not isinstance(self.target_class, DeploymentTargetClass)
            or (self.slot_id is not None and not isinstance(self.slot_id, SlotId))
            or not isinstance(self.capability_references, tuple)
            or not all(isinstance(item, CapabilityReference) for item in self.capability_references)
        ):
            raise InvalidDeploymentTarget("target binding is invalid")
        capabilities = tuple(sorted(set(self.capability_references)))
        if len(capabilities) > 32:
            raise InvalidDeploymentTarget("target capability references are unbounded")
        object.__setattr__(self, "capability_references", capabilities)
        object.__setattr__(self, "metadata", _normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True, order=True)
class DesiredRevisionV1:
    revision_id: RevisionId
    artifact_fingerprint: ArtifactFingerprintReference

    def __post_init__(self) -> None:
        if not isinstance(self.revision_id, RevisionId) or not isinstance(
            self.artifact_fingerprint, ArtifactFingerprintReference
        ):
            raise InvalidDeploymentRevision("desired revision binding is invalid")


@dataclass(frozen=True, slots=True, order=True)
class ObservedRevisionV1:
    revision_id: RevisionId
    observation: ObservationReference
    artifact_fingerprint: ArtifactFingerprintReference | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.revision_id, RevisionId)
            or not isinstance(self.observation, ObservationReference)
            or (
                self.artifact_fingerprint is not None
                and not isinstance(self.artifact_fingerprint, ArtifactFingerprintReference)
            )
        ):
            raise InvalidDeploymentRevision("observed revision requires an observation reference")


@dataclass(frozen=True, slots=True)
class DeploymentArtifactRefV1:
    artifact: ArtifactReference
    fingerprint: ArtifactFingerprintReference
    provenance: ProvenanceReference
    media_class: ArtifactMediaClass
    custody: CustodyReference | None = None
    media_type: str | None = None
    metadata: tuple[DeploymentMetadataEntry, ...] = ()
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact, ArtifactReference)
            or not isinstance(self.fingerprint, ArtifactFingerprintReference)
            or not isinstance(self.provenance, ProvenanceReference)
            or not isinstance(self.media_class, ArtifactMediaClass)
            or (self.custody is not None and not isinstance(self.custody, CustodyReference))
            or (
                self.media_type is not None
                and (
                    not isinstance(self.media_type, str)
                    or not _MEDIA_TYPE.fullmatch(self.media_type)
                )
            )
        ):
            raise InvalidDeploymentArtifactReference("artifact media type is invalid")
        object.__setattr__(self, "metadata", _normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class DeploymentIntentV1:
    intent_id: DeploymentIntentId
    artifact: DeploymentArtifactRefV1
    environment: DeploymentEnvironmentV1
    target: DeploymentTargetV1
    desired_revision: DesiredRevisionV1
    requester: RequesterReference
    policy_reference: PolicyReference
    idempotency_key: DeploymentIdempotencyKey
    correlation: CorrelationReference
    causation: CausationReference | None
    occurrence: OccurrenceReference
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        if self.target.environment_id != self.environment.environment_id:
            raise InvalidDeploymentIntent("target and environment do not correspond")
        if self.desired_revision.artifact_fingerprint != self.artifact.fingerprint:
            raise InvalidDeploymentIntent("desired revision and artifact do not correspond")

    def semantic_content(self) -> object:
        return (
            self.format_version,
            self.artifact,
            self.environment,
            self.target,
            self.desired_revision,
            self.requester,
            self.policy_reference,
        )

    @property
    def semantic_fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(content_fingerprint(self.semantic_content()))


@dataclass(frozen=True, slots=True)
class DeploymentReleaseV1:
    release_id: ReleaseId
    intent_id: DeploymentIntentId
    intent_fingerprint: DeploymentFingerprint
    artifact: DeploymentArtifactRefV1
    target_id: DeploymentTargetId
    desired_revision: DesiredRevisionV1
    policy_reference: PolicyReference
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1


@dataclass(frozen=True, slots=True)
class DeploymentAttemptV1:
    attempt_id: DeploymentAttemptId
    release_id: ReleaseId
    target_id: DeploymentTargetId
    desired_revision: DesiredRevisionV1
    artifact: DeploymentArtifactRefV1
    attempt_number: int
    policy_reference: PolicyReference
    configuration_fingerprint: DeploymentFingerprint
    occurrence: OccurrenceReference
    correlation: CorrelationReference
    causation: CausationReference | None = None
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        if (
            isinstance(self.attempt_number, bool)
            or not isinstance(self.attempt_number, int)
            or self.attempt_number < 1
        ):
            raise InvalidDeploymentAttemptBinding("attempt number must be positive")
        if self.desired_revision.artifact_fingerprint != self.artifact.fingerprint:
            raise InvalidDeploymentAttemptBinding("attempt revision and artifact mismatch")

    def semantic_content(self) -> object:
        return (
            self.format_version,
            self.release_id,
            self.target_id,
            self.desired_revision,
            self.artifact,
            self.attempt_number,
            self.policy_reference,
            self.configuration_fingerprint,
        )

    @property
    def semantic_fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(content_fingerprint(self.semantic_content()))


@dataclass(frozen=True, slots=True)
class DeploymentRolloutV1:
    rollout_id: RolloutId
    release_id: ReleaseId
    target_id: DeploymentTargetId
    stage_reference: CapabilityReference
    stage_class: RolloutStageClass
    slot_id: SlotId | None = None


@dataclass(frozen=True, slots=True)
class DeploymentPromotionV1:
    promotion_id: PromotionId
    rollout_id: RolloutId
    source_slot_id: SlotId | None
    destination_slot_id: SlotId | None
    policy_reference: PolicyReference

    def __post_init__(self) -> None:
        if self.source_slot_id is not None and self.source_slot_id == self.destination_slot_id:
            raise InvalidDeploymentTarget("promotion source and destination slots must differ")


@dataclass(frozen=True, slots=True)
class DeploymentRollbackAttemptV1:
    rollback_attempt_id: RollbackAttemptId
    release_id: ReleaseId
    target_id: DeploymentTargetId
    source_revision: RevisionId
    intended_revision: RevisionId
    authorization_reference: AuthorizationReference
    occurrence: OccurrenceReference

    def __post_init__(self) -> None:
        if self.source_revision == self.intended_revision:
            raise InvalidDeploymentRevision("rollback revisions must be distinct")
