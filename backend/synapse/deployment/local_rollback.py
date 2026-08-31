"""Provider-neutral contracts for explicit local rollback V1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .canonical import content_fingerprint
from .eligibility import ArtifactEligibilityOutcome, ArtifactEligibilityResultV1
from .fencing import (
    DeploymentFencingTokenV1,
    DeploymentIdempotencyRequestV1,
    DeploymentMutationClass,
)
from .identities import (
    ArtifactFingerprintReference,
    ArtifactReference,
    AuthorizationReference,
    CapabilityReference,
    DeploymentFingerprint,
    OccurrenceReference,
    PolicyReference,
    RequesterReference,
    RevisionId,
    RollbackReceiptReference,
)
from .models import DeploymentRollbackAttemptV1


class LocalRollbackPreparationOutcome(StrEnum):
    PREPARED = "prepared"
    ALREADY_PREPARED = "already-prepared"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome-unknown"


class LocalRollbackOutcome(StrEnum):
    ROLLED_BACK = "rolled-back"
    PARTIALLY_ROLLED_BACK = "partially-rolled-back"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome-unknown"


class LocalRollbackFailure(StrEnum):
    TARGET_NOT_EXPLICIT = "target-not-explicit"
    ELIGIBILITY_INVALID = "eligibility-invalid"
    AUTHORIZATION_INVALID = "authorization-invalid"
    FENCING_INVALID = "fencing-invalid"
    IDEMPOTENCY_CONTRADICTION = "idempotency-contradiction"
    ARTIFACT_UNAVAILABLE = "artifact-unavailable"
    ARTIFACT_MISMATCH = "artifact-mismatch"
    PREPARATION_FAILED = "preparation-failed"
    SANDBOX_AUTHORITY_INVALID = "sandbox-authority-invalid"
    SANDBOX_START_FAILED = "sandbox-start-failed"
    ACTIVE_STATE_FAILED = "active-state-failed"
    RECONCILIATION_REQUIRED = "reconciliation-required"


@dataclass(frozen=True, slots=True)
class LocalRollbackAuthorizationV1:
    reference: AuthorizationReference
    requester: RequesterReference
    rollback_attempt_reference: str
    target_reference: str
    source_revision: RevisionId
    intended_revision: RevisionId
    semantic_fingerprint: DeploymentFingerprint
    current: bool


@dataclass(frozen=True, slots=True)
class LocalRollbackPreparationRequestV1:
    rollback: DeploymentRollbackAttemptV1
    environment_reference: str
    artifact: ArtifactReference
    artifact_fingerprint: ArtifactFingerprintReference
    revision_fingerprint: DeploymentFingerprint
    target_configuration_fingerprint: DeploymentFingerprint
    eligibility: ArtifactEligibilityResultV1
    eligibility_semantic_fingerprint: DeploymentFingerprint
    eligibility_policy_reference: PolicyReference
    authorization: LocalRollbackAuthorizationV1
    fencing_token: DeploymentFencingTokenV1 | None
    idempotency: DeploymentIdempotencyRequestV1
    fencing_authority: CapabilityReference
    command_entrypoint: CapabilityReference
    resource_profile: CapabilityReference
    occurrence: OccurrenceReference

    def __post_init__(self) -> None:
        if (
            self.idempotency.operation is not DeploymentMutationClass.ROLLBACK_REQUEST
            or self.idempotency.scope.rollback_attempt_id != self.rollback.rollback_attempt_id
            or self.idempotency.semantic_fingerprint != self.semantic_fingerprint
        ):
            raise ValueError("rollback preparation idempotency binding is invalid")

    @property
    def semantic_fingerprint(self) -> DeploymentFingerprint:
        return local_rollback_preparation_semantic_fingerprint(
            self.rollback, self.environment_reference, self.artifact,
            self.artifact_fingerprint, self.revision_fingerprint,
            self.target_configuration_fingerprint, self.eligibility_policy_reference,
            self.command_entrypoint, self.resource_profile,
        )


@dataclass(frozen=True, slots=True)
class LocalRollbackPreparationResultV1:
    outcome: LocalRollbackPreparationOutcome
    prepared_revision_reference: CapabilityReference | None
    preparation_reference: CapabilityReference | None
    revision_fingerprint: DeploymentFingerprint | None
    failure: LocalRollbackFailure | None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalRollbackApplyRequestV1:
    preparation_request: LocalRollbackPreparationRequestV1
    preparation_result: LocalRollbackPreparationResultV1
    authorization: LocalRollbackAuthorizationV1
    fencing_token: DeploymentFencingTokenV1 | None
    idempotency: DeploymentIdempotencyRequestV1
    fencing_authority: CapabilityReference
    sandbox_authorization_reference: CapabilityReference
    sandbox_fencing_reference: CapabilityReference
    occurrence: OccurrenceReference

    def __post_init__(self) -> None:
        if (
            self.idempotency.operation is not DeploymentMutationClass.ROLLBACK_APPLY
            or self.idempotency.scope != self.preparation_request.idempotency.scope
            or self.idempotency.semantic_fingerprint != self.semantic_fingerprint
        ):
            raise ValueError("rollback apply idempotency binding is invalid")

    @property
    def semantic_fingerprint(self) -> DeploymentFingerprint:
        return local_rollback_apply_semantic_fingerprint(
            self.preparation_request,
            self.preparation_result,
            self.sandbox_authorization_reference,
            self.sandbox_fencing_reference,
        )


@dataclass(frozen=True, slots=True)
class LocalRollbackMutationV1:
    mutation_reference: CapabilityReference
    source_revision: RevisionId
    intended_revision: RevisionId
    prepared_revision_reference: CapabilityReference
    revision_fingerprint: DeploymentFingerprint
    target_reference: str
    environment_reference: str
    semantic_fingerprint: DeploymentFingerprint


@dataclass(frozen=True, slots=True)
class LocalRollbackReceiptV1:
    receipt_reference: RollbackReceiptReference
    rollback_attempt_reference: str
    release_reference: str
    target_reference: str
    environment_reference: str
    source_revision: RevisionId
    intended_revision: RevisionId
    applied_revision: RevisionId
    prepared_revision_reference: CapabilityReference
    sandbox_execution_reference: CapabilityReference | None
    active_state_mutation_reference: CapabilityReference | None
    occurrence: OccurrenceReference
    limitations: tuple[str, ...]
    semantic_fingerprint: DeploymentFingerprint

    @property
    def verified(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class LocalRollbackResultV1:
    outcome: LocalRollbackOutcome
    receipt: LocalRollbackReceiptV1 | None
    failure: LocalRollbackFailure | None
    reconciliation_required: bool

    @property
    def verified(self) -> bool:
        return False


class LocalRollbackPreparationPort(Protocol):
    def prepare(self, request: LocalRollbackPreparationRequestV1) -> LocalRollbackPreparationResultV1: ...


class LocalRollbackStatePort(Protocol):
    def receipt(self, semantic: DeploymentFingerprint) -> LocalRollbackReceiptV1 | None: ...
    def incomplete(self, semantic: DeploymentFingerprint) -> bool: ...
    def stage(self, request: LocalRollbackApplyRequestV1) -> LocalRollbackMutationV1: ...
    def promote(self, mutation: LocalRollbackMutationV1) -> CapabilityReference: ...
    def record(self, receipt: LocalRollbackReceiptV1) -> None: ...


def rollback_eligibility_is_current(request: LocalRollbackPreparationRequestV1) -> bool:
    eligibility = request.eligibility
    return (
        eligibility.outcome is ArtifactEligibilityOutcome.ELIGIBLE
        and eligibility.artifact_reference == request.artifact.value
        and eligibility.expected_fingerprint == request.artifact_fingerprint
        and eligibility.observed_fingerprint == request.artifact_fingerprint
        and eligibility.custody_reference is not None
        and eligibility.provenance_evidence_reference is not None
        and eligibility.policy_reference == request.eligibility_policy_reference
        and eligibility.semantic_fingerprint == request.eligibility_semantic_fingerprint
    )


def local_rollback_apply_semantic_fingerprint(
    preparation_request: LocalRollbackPreparationRequestV1,
    preparation_result: LocalRollbackPreparationResultV1,
    sandbox_authorization_reference: CapabilityReference,
    sandbox_fencing_reference: CapabilityReference,
) -> DeploymentFingerprint:
    return DeploymentFingerprint(content_fingerprint((
        preparation_request.semantic_fingerprint,
        preparation_result.prepared_revision_reference,
        sandbox_authorization_reference,
        sandbox_fencing_reference,
    )))


def local_rollback_preparation_semantic_fingerprint(
    rollback: DeploymentRollbackAttemptV1,
    environment_reference: str,
    artifact: ArtifactReference,
    artifact_fingerprint: ArtifactFingerprintReference,
    revision_fingerprint: DeploymentFingerprint,
    target_configuration_fingerprint: DeploymentFingerprint,
    eligibility_policy_reference: PolicyReference,
    command_entrypoint: CapabilityReference,
    resource_profile: CapabilityReference,
) -> DeploymentFingerprint:
    return DeploymentFingerprint(content_fingerprint((
        rollback, environment_reference, artifact, artifact_fingerprint,
        revision_fingerprint, target_configuration_fingerprint,
        eligibility_policy_reference, command_entrypoint, resource_profile,
    )))


def rollback_authorization_is_current(
    request: LocalRollbackPreparationRequestV1 | LocalRollbackApplyRequestV1,
) -> bool:
    preparation = request if isinstance(request, LocalRollbackPreparationRequestV1) else request.preparation_request
    authorization = request.authorization
    rollback = preparation.rollback
    return (
        authorization.current
        and authorization.reference == rollback.authorization_reference
        and authorization.rollback_attempt_reference == rollback.rollback_attempt_id.value
        and authorization.target_reference == rollback.target_id.value
        and authorization.source_revision == rollback.source_revision
        and authorization.intended_revision == rollback.intended_revision
        and authorization.semantic_fingerprint
        == (preparation.semantic_fingerprint if isinstance(request, LocalRollbackPreparationRequestV1) else request.semantic_fingerprint)
    )
