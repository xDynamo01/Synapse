"""Provider-neutral operational descriptors for Deployment targets and revisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .canonical import content_fingerprint
from .errors import (
    InvalidDeploymentAttemptBinding,
    InvalidDeploymentEnvironment,
    InvalidDeploymentRevision,
    InvalidDeploymentTarget,
)
from .identities import (
    AdapterBindingReference,
    CapabilityReference,
    DeploymentAttemptId,
    DeploymentFingerprint,
    DeploymentTargetId,
    ObservationReference,
    PolicyReference,
    ReleaseId,
    SecretReference,
    SlotId,
)
from .models import (
    DeploymentArtifactRefV1,
    DeploymentAttemptV1,
    DeploymentEnvironmentV1,
    DeploymentTargetV1,
    DesiredRevisionV1,
    ObservedRevisionV1,
)

_LOGICAL_ROLE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_HOST_DRIVE = re.compile(r"^[A-Za-z]:[/\\]")
_FORBIDDEN_CONFIG_KEYS = {
    "credential",
    "endpoint",
    "host-path",
    "port",
    "provider-payload",
    "secret-value",
}


class EnvironmentOperationalClass(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION_LIKE = "production-like"
    PRODUCTION = "production"
    CUSTOM = "custom"


class DeploymentTier(StrEnum):
    EPHEMERAL = "ephemeral"
    NON_CRITICAL = "non-critical"
    CRITICAL = "critical"
    CUSTOM = "custom"


class DeploymentTargetKind(StrEnum):
    LOCAL_SERVICE = "local-service"
    APPLICATION = "application"
    PROCESS_SERVICE = "process-service"
    CONTAINER_TARGET = "container-target"
    REMOTE_SERVICE = "remote-service"
    CUSTOM = "custom"


class SlotCapability(StrEnum):
    UNSUPPORTED = "unsupported"
    SINGLE_SLOT = "single-slot"
    MULTI_SLOT = "multi-slot"


class SlotActivity(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class TargetCapabilityKind(StrEnum):
    PREPARE = "prepare"
    APPLY = "apply"
    OBSERVE = "observe"
    VERIFY = "verify"
    ROLLBACK = "rollback"
    SLOTS = "slots"
    STAGED_ROLLOUT = "staged-rollout"
    LOCAL_EXECUTION = "local-execution"
    EXTERNAL_EGRESS = "external-egress"


class CapabilityAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class RevisionCorrespondence(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class TargetCompatibility(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class TargetCapabilityRequirementsV1:
    release_id: ReleaseId
    attempt_id: DeploymentAttemptId
    policy_reference: PolicyReference
    required_capabilities: tuple[TargetCapabilityKind, ...]

    def __post_init__(self) -> None:
        normalized = tuple(sorted(set(self.required_capabilities)))
        if not normalized or len(normalized) > 16:
            raise InvalidDeploymentAttemptBinding("target capability requirements are invalid")
        object.__setattr__(self, "required_capabilities", normalized)


@dataclass(frozen=True, slots=True, order=True)
class TargetCapabilityFactV1:
    capability: TargetCapabilityKind
    declared: bool
    required: bool
    availability: CapabilityAvailability
    evidence_reference: CapabilityReference | None = None

    def __post_init__(self) -> None:
        if not self.declared and self.availability is CapabilityAvailability.AVAILABLE:
            raise InvalidDeploymentTarget("available target capability must be declared")


@dataclass(frozen=True, slots=True)
class DeploymentEnvironmentOperationalV1:
    environment: DeploymentEnvironmentV1
    operational_class: EnvironmentOperationalClass
    tier: DeploymentTier
    required_capabilities: tuple[TargetCapabilityKind, ...] = ()

    def __post_init__(self) -> None:
        _reject_concrete_metadata(self.environment.metadata, InvalidDeploymentEnvironment)
        normalized = tuple(sorted(set(self.required_capabilities)))
        if len(normalized) > 16:
            raise InvalidDeploymentEnvironment("environment capability requirements are unbounded")
        object.__setattr__(self, "required_capabilities", normalized)


@dataclass(frozen=True, slots=True)
class DeploymentTargetOperationalV1:
    target: DeploymentTargetV1
    kind: DeploymentTargetKind
    slot_capability: SlotCapability
    capability_facts: tuple[TargetCapabilityFactV1, ...]
    configuration_references: tuple[CapabilityReference, ...]
    verification_capability_reference: CapabilityReference | None = None
    rollback_capability_reference: CapabilityReference | None = None
    secret_requirements: tuple[SecretReference, ...] = ()
    requires_external_egress: bool = False

    def __post_init__(self) -> None:
        _reject_concrete_metadata(self.target.metadata, InvalidDeploymentTarget)
        capabilities = tuple(sorted(self.capability_facts))
        if len({item.capability for item in capabilities}) != len(capabilities):
            raise InvalidDeploymentTarget("target capability facts must be unique")
        references = tuple(sorted(set(self.configuration_references)))
        secrets = tuple(sorted(set(self.secret_requirements)))
        if len(capabilities) > 16 or len(references) > 32 or len(secrets) > 16:
            raise InvalidDeploymentTarget("target operational configuration is unbounded")
        if self.slot_capability is SlotCapability.UNSUPPORTED and self.target.slot_id is not None:
            raise InvalidDeploymentTarget("slot-unsupported target cannot bind a slot")
        object.__setattr__(self, "capability_facts", capabilities)
        object.__setattr__(self, "configuration_references", references)
        object.__setattr__(self, "secret_requirements", secrets)

    @property
    def configuration_fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(
            content_fingerprint(
                (
                    self.target.target_id,
                    self.target.environment_id,
                    self.target.adapter_binding,
                    self.target.target_class,
                    self.target.slot_id,
                    self.target.capability_references,
                    self.target.metadata,
                    self.kind,
                    self.slot_capability,
                    self.capability_facts,
                    self.configuration_references,
                    self.verification_capability_reference,
                    self.rollback_capability_reference,
                    self.secret_requirements,
                    self.requires_external_egress,
                )
            )
        )

    @property
    def adapter_available(self) -> bool:
        return False

    @property
    def egress_authorized(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class DeploymentSlotV1:
    slot_id: SlotId
    target_id: DeploymentTargetId
    logical_role: str
    activity: SlotActivity = SlotActivity.UNKNOWN
    observed_revision: ObservedRevisionV1 | None = None
    observation_reference: ObservationReference | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.target_id, DeploymentTargetId)
            or not _LOGICAL_ROLE.fullmatch(self.logical_role)
            or (self.observed_revision is None) != (self.observation_reference is None)
            or (
                self.observed_revision is not None
                and self.observed_revision.observation != self.observation_reference
            )
        ):
            raise InvalidDeploymentTarget("slot observation binding is invalid")


@dataclass(frozen=True, slots=True)
class DesiredOperationalRevisionV1:
    desired_revision: DesiredRevisionV1
    artifact: DeploymentArtifactRefV1
    target_configuration_fingerprint: DeploymentFingerprint
    deployment_configuration_references: tuple[CapabilityReference, ...]
    policy_reference: PolicyReference
    policy_version: str

    def __post_init__(self) -> None:
        if (
            self.desired_revision.artifact_fingerprint != self.artifact.fingerprint
            or not self.policy_version
        ):
            raise InvalidDeploymentRevision("desired operational revision binding is invalid")
        references = tuple(sorted(set(self.deployment_configuration_references)))
        if len(references) > 32:
            raise InvalidDeploymentRevision("revision configuration is unbounded")
        object.__setattr__(self, "deployment_configuration_references", references)

    @property
    def revision_fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(
            content_fingerprint(
                (
                    self.artifact.artifact,
                    self.artifact.fingerprint,
                    self.target_configuration_fingerprint,
                    self.deployment_configuration_references,
                    self.policy_reference,
                    self.policy_version,
                )
            )
        )


@dataclass(frozen=True, slots=True)
class ObservedOperationalRevisionV1:
    observed_revision: ObservedRevisionV1
    target_configuration_fingerprint: DeploymentFingerprint | None = None
    slot_id: SlotId | None = None

    @property
    def verified(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class TargetCorrespondenceRequestV1:
    environment: DeploymentEnvironmentOperationalV1
    target: DeploymentTargetOperationalV1
    slot: DeploymentSlotV1 | None
    desired_revision: DesiredOperationalRevisionV1
    attempt: DeploymentAttemptV1
    requirements: TargetCapabilityRequirementsV1
    expected_adapter_binding: AdapterBindingReference
    expected_target_configuration: DeploymentFingerprint


def classify_revision_correspondence(
    desired: DesiredOperationalRevisionV1,
    observed: ObservedOperationalRevisionV1 | None,
) -> RevisionCorrespondence:
    if observed is None:
        return RevisionCorrespondence.UNAVAILABLE
    if observed.observed_revision.artifact_fingerprint is None:
        return RevisionCorrespondence.INDETERMINATE
    if (
        observed.observed_revision.revision_id == desired.desired_revision.revision_id
        and observed.observed_revision.artifact_fingerprint == desired.artifact.fingerprint
        and (
            observed.target_configuration_fingerprint is None
            or observed.target_configuration_fingerprint == desired.target_configuration_fingerprint
        )
    ):
        return RevisionCorrespondence.MATCH
    return RevisionCorrespondence.MISMATCH


def classify_target_compatibility(
    target: DeploymentTargetOperationalV1,
    required: tuple[TargetCapabilityKind, ...],
) -> TargetCompatibility:
    facts = {item.capability: item for item in target.capability_facts}
    if any(item not in facts or not facts[item].declared for item in required):
        return TargetCompatibility.INCOMPATIBLE
    if any(facts[item].availability is CapabilityAvailability.UNAVAILABLE for item in required):
        return TargetCompatibility.INCOMPATIBLE
    if any(facts[item].availability is CapabilityAvailability.UNKNOWN for item in required):
        return TargetCompatibility.INDETERMINATE
    return TargetCompatibility.COMPATIBLE


def validate_target_correspondence(request: TargetCorrespondenceRequestV1) -> None:
    target = request.target
    if target.target.environment_id != request.environment.environment.environment_id:
        raise InvalidDeploymentTarget("target environment correspondence mismatch")
    if request.slot is not None and request.slot.target_id != target.target.target_id:
        raise InvalidDeploymentTarget("slot target correspondence mismatch")
    if (
        request.desired_revision.artifact != request.attempt.artifact
        or request.desired_revision.desired_revision != request.attempt.desired_revision
        or request.attempt.target_id != target.target.target_id
        or target.target.adapter_binding != request.expected_adapter_binding
        or target.configuration_fingerprint != request.expected_target_configuration
        or request.attempt.configuration_fingerprint
        != request.desired_revision.target_configuration_fingerprint
        or request.requirements.release_id != request.attempt.release_id
        or request.requirements.attempt_id != request.attempt.attempt_id
        or request.requirements.policy_reference != request.attempt.policy_reference
    ):
        raise InvalidDeploymentAttemptBinding("target operational correspondence mismatch")
    if (
        classify_target_compatibility(target, request.requirements.required_capabilities)
        is TargetCompatibility.INCOMPATIBLE
    ):
        raise InvalidDeploymentTarget("target lacks a required declared capability")


def _reject_concrete_metadata(metadata: tuple[object, ...], error: type[ValueError]) -> None:
    for item in metadata:
        key = getattr(item, "key", "")
        value = getattr(item, "value", "")
        if (
            key in _FORBIDDEN_CONFIG_KEYS
            or "://" in value
            or "\\" in value
            or _HOST_DRIVE.match(value)
        ):
            raise error("operational metadata cannot contain concrete provider or host data")
