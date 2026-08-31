"""Provider-neutral contracts for factual local revision preparation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import content_fingerprint
from .eligibility import ArtifactEligibilityOutcome, ArtifactEligibilityResultV1
from .fencing import (
    DeploymentFencingTokenV1,
    DeploymentIdempotencyRequestV1,
    DeploymentMutationClass,
)
from .identities import (
    AuthorizationReference,
    CapabilityReference,
    DeploymentAttemptId,
    DeploymentFingerprint,
    DeploymentTargetId,
    EnvironmentId,
    OccurrenceReference,
    PolicyReference,
    PreparationReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    SecretReference,
)
from .operational import TargetCorrespondenceRequestV1


class LocalRevisionPreparationOutcome(StrEnum):
    PREPARED = "prepared"
    ALREADY_PREPARED = "already-prepared"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome-unknown"


class LocalRevisionPreparationFailure(StrEnum):
    UNSUPPORTED_TARGET = "unsupported-target"
    ADAPTER_BINDING_UNAVAILABLE = "adapter-binding-unavailable"
    ELIGIBILITY_STALE = "eligibility-stale"
    AUTHORIZATION_INVALID = "authorization-invalid"
    FENCING_STALE_OR_UNAVAILABLE = "fencing-stale-or-unavailable"
    REVISION_MISMATCH = "revision-mismatch"
    PREPARATION_CONFLICT = "preparation-conflict"
    FILESYSTEM_PREPARATION_FAILED = "filesystem-preparation-failed"
    FINGERPRINT_VERIFICATION_FAILED = "fingerprint-verification-failed"
    SANDBOX_HANDOFF_UNAVAILABLE = "sandbox-handoff-unavailable"
    RECONCILIATION_REQUIRED = "reconciliation-required"
    NETWORK_PROFILE_UNAVAILABLE = "network-profile-unavailable"


@dataclass(frozen=True, slots=True)
class LocalRevisionPreparationAuthorizationV1:
    authorization_reference: AuthorizationReference
    requester: RequesterReference
    release_id: ReleaseId
    attempt_id: DeploymentAttemptId
    environment_id: EnvironmentId
    target_id: DeploymentTargetId
    artifact_reference: str
    artifact_fingerprint: str
    revision_id: RevisionId
    policy_reference: PolicyReference
    semantic_fingerprint: DeploymentFingerprint
    current: bool

    @property
    def authorizes(self) -> bool:
        return self.current


@dataclass(frozen=True, slots=True)
class DeploymentSandboxHandoffDraftV1:
    workspace_reference: CapabilityReference
    artifact_reference: str
    artifact_fingerprint: str
    command_entrypoint: CapabilityReference
    resource_profile: CapabilityReference
    network_profile: CapabilityReference | None
    secret_references: tuple[SecretReference, ...]
    attempt_reference: str
    release_reference: str
    authorization_reference: AuthorizationReference
    deployment_fencing_reference: DeploymentFingerprint
    sandbox_fencing_reference: CapabilityReference | None = None
    sandbox_fencing_required: bool = True

    def __post_init__(self) -> None:
        if self.sandbox_fencing_reference is not None:
            raise ValueError("Deployment preparation cannot mint Sandbox fencing")


@dataclass(frozen=True, slots=True)
class LocalRevisionPreparationRequestV1:
    correspondence: TargetCorrespondenceRequestV1
    eligibility: ArtifactEligibilityResultV1
    authorization: LocalRevisionPreparationAuthorizationV1
    fencing_token: DeploymentFencingTokenV1 | None
    idempotency: DeploymentIdempotencyRequestV1
    fencing_authority: CapabilityReference
    command_entrypoint: CapabilityReference
    resource_profile: CapabilityReference
    network_profile: CapabilityReference | None
    network_profile_available: bool
    occurrence: OccurrenceReference

    def __post_init__(self) -> None:
        if (
            self.idempotency.operation is not DeploymentMutationClass.REVISION_PREPARATION
            or self.idempotency.scope.target_id != self.correspondence.target.target.target_id
            or self.idempotency.semantic_fingerprint != self.semantic_fingerprint
        ):
            raise ValueError("preparation idempotency binding is invalid")

    @property
    def semantic_fingerprint(self) -> DeploymentFingerprint:
        return preparation_semantic_fingerprint(
            self.correspondence,
            self.command_entrypoint,
            self.resource_profile,
            self.network_profile,
        )


@dataclass(frozen=True, slots=True)
class LocalRevisionPreparationResultV1:
    outcome: LocalRevisionPreparationOutcome
    preparation_reference: PreparationReference | None
    prepared_revision_reference: CapabilityReference | None
    revision_fingerprint: DeploymentFingerprint | None
    handoff: DeploymentSandboxHandoffDraftV1 | None
    failure: LocalRevisionPreparationFailure | None
    limitations: tuple[str, ...]

    @property
    def active(self) -> bool:
        return False

    @property
    def sandbox_executed(self) -> bool:
        return False


def eligibility_is_current(
    request: LocalRevisionPreparationRequestV1,
) -> bool:
    eligibility = request.eligibility
    attempt = request.correspondence.attempt
    desired = request.correspondence.desired_revision
    return (
        eligibility.outcome is ArtifactEligibilityOutcome.ELIGIBLE
        and eligibility.release_id == attempt.release_id.value
        and eligibility.attempt_id == attempt.attempt_id.value
        and eligibility.artifact_reference == desired.artifact.artifact.value
        and eligibility.expected_fingerprint == desired.artifact.fingerprint
        and eligibility.policy_reference == desired.policy_reference
        and eligibility.semantic_fingerprint == attempt.semantic_fingerprint
    )


def authorization_is_current(request: LocalRevisionPreparationRequestV1) -> bool:
    authorization = request.authorization
    correspondence = request.correspondence
    attempt = correspondence.attempt
    desired = correspondence.desired_revision
    return (
        authorization.current
        and authorization.release_id == attempt.release_id
        and authorization.attempt_id == attempt.attempt_id
        and authorization.environment_id == correspondence.environment.environment.environment_id
        and authorization.target_id == correspondence.target.target.target_id
        and authorization.artifact_reference == desired.artifact.artifact.value
        and authorization.artifact_fingerprint == desired.artifact.fingerprint.value
        and authorization.revision_id == desired.desired_revision.revision_id
        and authorization.policy_reference == desired.policy_reference
        and authorization.semantic_fingerprint == request.semantic_fingerprint
    )


def preparation_semantic_fingerprint(
    correspondence: TargetCorrespondenceRequestV1,
    command_entrypoint: CapabilityReference,
    resource_profile: CapabilityReference,
    network_profile: CapabilityReference | None,
) -> DeploymentFingerprint:
    return DeploymentFingerprint(
        content_fingerprint(
            (
                correspondence.environment,
                correspondence.target,
                correspondence.slot,
                correspondence.desired_revision,
                correspondence.attempt,
                correspondence.requirements,
                correspondence.expected_adapter_binding,
                correspondence.expected_target_configuration,
                command_entrypoint,
                resource_profile,
                network_profile,
            )
        )
    )
