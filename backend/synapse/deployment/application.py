"""Provider-neutral local apply orchestration contracts and factual receipts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .canonical import content_fingerprint
from .fencing import (
    DeploymentFencingTokenV1,
    DeploymentIdempotencyRequestV1,
    DeploymentMutationClass,
)
from .identities import (
    ApplyReceiptReference,
    AuthorizationReference,
    CapabilityReference,
    DeploymentFingerprint,
    OccurrenceReference,
    RevisionId,
)
from .preparation import (
    LocalRevisionPreparationOutcome,
    LocalRevisionPreparationRequestV1,
    LocalRevisionPreparationResultV1,
)


class LocalApplyOutcome(StrEnum):
    APPLIED = "applied"
    PARTIALLY_APPLIED = "partially-applied"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome-unknown"


class LocalApplyFailure(StrEnum):
    PREPARED_REVISION_REQUIRED = "prepared-revision-required"
    PREPARATION_STALE = "preparation-stale"
    AUTHORIZATION_INVALID = "authorization-invalid"
    DEPLOYMENT_FENCING_INVALID = "deployment-fencing-invalid"
    IDEMPOTENCY_CONTRADICTION = "idempotency-contradiction"
    TARGET_NOT_READY = "target-not-ready"
    SANDBOX_AUTHORITY_INVALID = "sandbox-authority-invalid"
    SANDBOX_START_FAILED = "sandbox-start-failed"
    ACTIVE_STATE_FAILED = "active-state-failed"
    RECONCILIATION_REQUIRED = "reconciliation-required"


class SandboxLocalApplyOutcome(StrEnum):
    STARTED = "started"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SandboxLocalApplyCommandV1:
    preparation_reference: CapabilityReference
    workspace_reference: CapabilityReference
    command_entrypoint: CapabilityReference
    sandbox_authorization_reference: CapabilityReference
    sandbox_fencing_reference: CapabilityReference
    deployment_authorization_reference: AuthorizationReference
    deployment_fencing_reference: DeploymentFingerprint
    occurrence: OccurrenceReference


@dataclass(frozen=True, slots=True)
class SandboxLocalApplyResultV1:
    outcome: SandboxLocalApplyOutcome
    execution_reference: CapabilityReference | None
    process_started: bool
    containment_established: bool
    diagnostic_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalApplyRequestV1:
    preparation_request: LocalRevisionPreparationRequestV1
    preparation_result: LocalRevisionPreparationResultV1
    authorization_reference: AuthorizationReference
    authorization_semantic_fingerprint: DeploymentFingerprint
    deployment_fencing_token: DeploymentFencingTokenV1 | None
    idempotency: DeploymentIdempotencyRequestV1
    deployment_fencing_authority: CapabilityReference
    sandbox_authorization_reference: CapabilityReference
    sandbox_fencing_reference: CapabilityReference
    target_ready: bool
    occurrence: OccurrenceReference

    def __post_init__(self) -> None:
        if (
            self.idempotency.operation is not DeploymentMutationClass.APPLY_REQUEST
            or self.idempotency.scope.target_id
            != self.preparation_request.correspondence.target.target.target_id
            or self.idempotency.semantic_fingerprint != self.semantic_fingerprint
        ):
            raise ValueError("local apply idempotency binding is invalid")

    @property
    def semantic_fingerprint(self) -> DeploymentFingerprint:
        return local_apply_semantic_fingerprint(
            self.preparation_request,
            self.preparation_result,
            self.sandbox_authorization_reference,
            self.sandbox_fencing_reference,
        )


@dataclass(frozen=True, slots=True)
class LocalApplyReceiptV1:
    receipt_reference: ApplyReceiptReference
    release_reference: str
    attempt_reference: str
    target_reference: str
    environment_reference: str
    applied_revision: RevisionId
    prepared_revision_reference: CapabilityReference
    sandbox_execution_reference: CapabilityReference | None
    active_state_mutation_reference: CapabilityReference | None
    previous_active_revision: RevisionId | None
    occurrence: OccurrenceReference
    limitations: tuple[str, ...]
    semantic_fingerprint: DeploymentFingerprint

    @property
    def verified(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class LocalApplyResultV1:
    outcome: LocalApplyOutcome
    receipt: LocalApplyReceiptV1 | None
    failure: LocalApplyFailure | None
    reconciliation_required: bool

    @property
    def verified(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class LocalActiveStateMutationV1:
    mutation_reference: CapabilityReference
    desired_revision: RevisionId
    prepared_revision_reference: CapabilityReference
    revision_fingerprint: DeploymentFingerprint
    target_reference: str
    environment_reference: str
    slot_reference: str | None
    previous_active_revision: RevisionId | None
    semantic_fingerprint: DeploymentFingerprint


class LocalActiveStatePort(Protocol):
    def staged_receipt(self, semantic: DeploymentFingerprint) -> LocalApplyReceiptV1 | None: ...

    def stage(self, request: LocalApplyRequestV1) -> LocalActiveStateMutationV1: ...

    def promote(self, mutation: LocalActiveStateMutationV1) -> CapabilityReference: ...

    def record_receipt(self, receipt: LocalApplyReceiptV1) -> None: ...

    def incomplete(self, semantic: DeploymentFingerprint) -> bool: ...


def local_apply_semantic_fingerprint(
    preparation_request: LocalRevisionPreparationRequestV1,
    preparation_result: LocalRevisionPreparationResultV1,
    sandbox_authorization_reference: CapabilityReference,
    sandbox_fencing_reference: CapabilityReference,
) -> DeploymentFingerprint:
    return DeploymentFingerprint(
        content_fingerprint(
            (
                preparation_request.semantic_fingerprint,
                preparation_result.preparation_reference,
                preparation_result.prepared_revision_reference,
                preparation_result.revision_fingerprint,
                sandbox_authorization_reference,
                sandbox_fencing_reference,
            )
        )
    )


def preparation_corresponds(request: LocalApplyRequestV1) -> bool:
    prepared = request.preparation_result
    desired = request.preparation_request.correspondence.desired_revision
    return (
        prepared.outcome
        in {
            LocalRevisionPreparationOutcome.PREPARED,
            LocalRevisionPreparationOutcome.ALREADY_PREPARED,
        }
        and prepared.preparation_reference is not None
        and prepared.prepared_revision_reference is not None
        and prepared.revision_fingerprint == desired.revision_fingerprint
        and prepared.handoff is not None
        and not prepared.active
    )
