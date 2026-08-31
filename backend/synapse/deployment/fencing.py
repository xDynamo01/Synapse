"""Deployment-owned generation, fencing and idempotency contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .canonical import content_fingerprint
from .errors import DeploymentFencingUnavailable
from .identities import (
    CapabilityReference,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    DeploymentTargetId,
    OccurrenceReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    RollbackAttemptId,
    RolloutId,
    SlotId,
)

DEPLOYMENT_FENCING_AUTHORITY_VERSION = "deployment-fencing-authority-v1"
DEPLOYMENT_FENCING_TOKEN_VERSION = "deployment-fencing-token-v1"
DEPLOYMENT_IDEMPOTENCY_RECORD_VERSION = "deployment-idempotency-record-v1"
MAX_DEPLOYMENT_GENERATION = 2**64 - 1


class DeploymentFencingScopeKind(StrEnum):
    RELEASE = "release"
    TARGET = "target"
    TARGET_SLOT = "target-slot"
    ROLLOUT = "rollout"
    ROLLBACK_ATTEMPT = "rollback-attempt"


class DeploymentMutationClass(StrEnum):
    READ_ONLY_OBSERVATION = "read-only-observation"
    READ_ONLY_VERIFICATION = "read-only-verification"
    RELEASE_STATE_MUTATION = "release-state-mutation"
    ARTIFACT_SELECTION_MUTATION = "artifact-selection-mutation"
    DESIRED_REVISION_MUTATION = "desired-revision-mutation"
    REVISION_PREPARATION = "revision-preparation"
    TARGET_SLOT_MUTATION = "target-slot-mutation"
    APPLY_REQUEST = "apply-request"
    ROLLOUT_ADVANCEMENT = "rollout-advancement"
    PROMOTION = "promotion"
    ROLLBACK_REQUEST = "rollback-request"
    ROLLBACK_APPLY = "rollback-apply"
    EVIDENCE_PUBLICATION = "evidence-publication"
    RECONCILIATION_MUTATION = "reconciliation-mutation"

    @property
    def fencing_required(self) -> bool:
        return self not in {
            DeploymentMutationClass.READ_ONLY_OBSERVATION,
            DeploymentMutationClass.READ_ONLY_VERIFICATION,
        }


class DeploymentFencingValidationState(StrEnum):
    VALID = "valid"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    MISMATCHED = "mismatched"
    INVALID = "invalid"


class DeploymentIdempotencyStatus(StrEnum):
    ACCEPTED = "accepted"
    RESULT_RECORDED = "result-recorded"


class DeploymentIdempotencyDisposition(StrEnum):
    RECORDED = "recorded"
    IDEMPOTENT = "idempotent"
    FENCING_REJECTED = "fencing-rejected"


@dataclass(frozen=True, slots=True, order=True)
class DeploymentGeneration:
    value: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, int)
            or not 1 <= self.value <= MAX_DEPLOYMENT_GENERATION
        ):
            raise ValueError("deployment generation must be uint64 and positive")


@dataclass(frozen=True, slots=True)
class DeploymentFencingScopeV1:
    kind: DeploymentFencingScopeKind
    release_id: ReleaseId | None = None
    target_id: DeploymentTargetId | None = None
    slot_id: SlotId | None = None
    rollout_id: RolloutId | None = None
    rollback_attempt_id: RollbackAttemptId | None = None
    source_revision: RevisionId | None = None
    intended_revision: RevisionId | None = None

    def __post_init__(self) -> None:
        valid = {
            DeploymentFencingScopeKind.RELEASE: (
                self.release_id is not None
                and all(
                    value is None
                    for value in (
                        self.target_id,
                        self.slot_id,
                        self.rollout_id,
                        self.rollback_attempt_id,
                        self.source_revision,
                        self.intended_revision,
                    )
                )
            ),
            DeploymentFencingScopeKind.TARGET: (
                self.target_id is not None
                and all(
                    value is None
                    for value in (
                        self.release_id,
                        self.slot_id,
                        self.rollout_id,
                        self.rollback_attempt_id,
                        self.source_revision,
                        self.intended_revision,
                    )
                )
            ),
            DeploymentFencingScopeKind.TARGET_SLOT: (
                self.target_id is not None
                and self.slot_id is not None
                and all(
                    value is None
                    for value in (
                        self.release_id,
                        self.rollout_id,
                        self.rollback_attempt_id,
                        self.source_revision,
                        self.intended_revision,
                    )
                )
            ),
            DeploymentFencingScopeKind.ROLLOUT: (
                self.release_id is not None
                and self.rollout_id is not None
                and all(
                    value is None
                    for value in (
                        self.target_id,
                        self.slot_id,
                        self.rollback_attempt_id,
                        self.source_revision,
                        self.intended_revision,
                    )
                )
            ),
            DeploymentFencingScopeKind.ROLLBACK_ATTEMPT: (
                self.release_id is not None
                and self.target_id is not None
                and self.rollback_attempt_id is not None
                and self.source_revision is not None
                and self.intended_revision is not None
                and self.source_revision != self.intended_revision
                and self.slot_id is None
                and self.rollout_id is None
            ),
        }[self.kind]
        if not valid:
            raise ValueError("deployment fencing scope is invalid")

    @property
    def fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(content_fingerprint(self))


@dataclass(frozen=True, slots=True)
class DeploymentFencingTransitionRequestV1:
    scope: DeploymentFencingScopeV1
    owner: RequesterReference
    authority_identity: CapabilityReference
    expected_generation: int
    occurrence: OccurrenceReference
    semantic_binding_fingerprint: DeploymentFingerprint | None = None
    authority_version: str = DEPLOYMENT_FENCING_AUTHORITY_VERSION

    def __post_init__(self) -> None:
        if (
            self.authority_version != DEPLOYMENT_FENCING_AUTHORITY_VERSION
            or isinstance(self.expected_generation, bool)
            or not isinstance(self.expected_generation, int)
            or not 0 <= self.expected_generation < MAX_DEPLOYMENT_GENERATION
        ):
            raise ValueError("deployment fencing transition is invalid")

    @property
    def fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(content_fingerprint(self))


@dataclass(frozen=True, slots=True)
class DeploymentGenerationFactV1:
    scope: DeploymentFencingScopeV1
    generation: DeploymentGeneration
    owner: RequesterReference
    authority_identity: CapabilityReference
    authority_version: str
    occurrence: OccurrenceReference
    semantic_binding_fingerprint: DeploymentFingerprint | None
    transition_fingerprint: DeploymentFingerprint
    previous_fact_fingerprint: DeploymentFingerprint | None
    fact_fingerprint: DeploymentFingerprint

    @classmethod
    def create(
        cls,
        request: DeploymentFencingTransitionRequestV1,
        generation: int,
        previous: DeploymentFingerprint | None,
    ) -> DeploymentGenerationFactV1:
        value = DeploymentGeneration(generation)
        semantic = (
            request.scope,
            value,
            request.owner,
            request.authority_identity,
            request.authority_version,
            request.occurrence,
            request.semantic_binding_fingerprint,
            request.fingerprint,
            previous,
        )
        return cls(
            request.scope,
            value,
            request.owner,
            request.authority_identity,
            request.authority_version,
            request.occurrence,
            request.semantic_binding_fingerprint,
            request.fingerprint,
            previous,
            DeploymentFingerprint(content_fingerprint(semantic)),
        )


@dataclass(frozen=True, slots=True)
class DeploymentFencingTokenV1:
    scope: DeploymentFencingScopeV1
    generation: DeploymentGeneration
    owner: RequesterReference
    authority_identity: CapabilityReference
    authority_version: str
    occurrence: OccurrenceReference
    semantic_binding_fingerprint: DeploymentFingerprint | None
    token_fingerprint: DeploymentFingerprint
    version: str = DEPLOYMENT_FENCING_TOKEN_VERSION

    @classmethod
    def from_fact(cls, fact: DeploymentGenerationFactV1) -> DeploymentFencingTokenV1:
        semantic = (
            DEPLOYMENT_FENCING_TOKEN_VERSION,
            fact.scope,
            fact.generation,
            fact.owner,
            fact.authority_identity,
            fact.authority_version,
            fact.occurrence,
            fact.semantic_binding_fingerprint,
        )
        return cls(
            fact.scope,
            fact.generation,
            fact.owner,
            fact.authority_identity,
            fact.authority_version,
            fact.occurrence,
            fact.semantic_binding_fingerprint,
            DeploymentFingerprint(content_fingerprint(semantic)),
        )

    @property
    def authorized(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class DeploymentFencingValidationResultV1:
    state: DeploymentFencingValidationState
    presented_generation: DeploymentGeneration | None
    latest_generation: DeploymentGeneration | None
    fencing_required: bool
    diagnostics: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.fencing_required or self.state is DeploymentFencingValidationState.VALID

    @property
    def authorized(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class DeploymentIdempotencyRequestV1:
    operation: DeploymentMutationClass
    scope: DeploymentFencingScopeV1
    idempotency_key: DeploymentIdempotencyKey
    semantic_fingerprint: DeploymentFingerprint
    first_accepted_occurrence: OccurrenceReference

    def __post_init__(self) -> None:
        if not self.operation.fencing_required:
            raise ValueError("read-only operation does not require idempotency authority")


@dataclass(frozen=True, slots=True)
class DeploymentIdempotencyRecordV1:
    operation: DeploymentMutationClass
    scope: DeploymentFencingScopeV1
    idempotency_key: DeploymentIdempotencyKey
    semantic_fingerprint: DeploymentFingerprint
    fencing_generation: DeploymentGeneration
    first_accepted_occurrence: OccurrenceReference
    status: DeploymentIdempotencyStatus = DeploymentIdempotencyStatus.ACCEPTED
    result_reference: CapabilityReference | None = None
    version: str = DEPLOYMENT_IDEMPOTENCY_RECORD_VERSION


@dataclass(frozen=True, slots=True)
class DeploymentOperationAcceptanceV1:
    disposition: DeploymentIdempotencyDisposition
    fencing: DeploymentFencingValidationResultV1
    record: DeploymentIdempotencyRecordV1 | None


@dataclass(frozen=True, slots=True)
class DeploymentFencingHealthV1:
    store_available: bool
    schema_compatible: bool
    latest_generation_readable: bool
    monotonicity_integrity: bool
    token_validation_available: bool
    idempotency_store_available: bool
    contradiction_detection_available: bool
    corruption_detected: bool
    end_to_end_enforced: bool = False


class DeploymentAuthorityStore(Protocol):
    def transition(
        self, request: DeploymentFencingTransitionRequestV1
    ) -> DeploymentGenerationFactV1: ...

    def latest(self, scope: DeploymentFencingScopeV1) -> DeploymentGenerationFactV1 | None: ...

    def history(
        self, scope: DeploymentFencingScopeV1
    ) -> tuple[DeploymentGenerationFactV1, ...]: ...

    def record_idempotency(
        self,
        request: DeploymentIdempotencyRequestV1,
        generation: DeploymentGeneration,
    ) -> tuple[DeploymentIdempotencyDisposition, DeploymentIdempotencyRecordV1]: ...

    def health(self) -> DeploymentFencingHealthV1: ...


class DeploymentFencingAuthority:
    def __init__(self, store: DeploymentAuthorityStore) -> None:
        self._store = store

    def transition(self, request: DeploymentFencingTransitionRequestV1) -> DeploymentFencingTokenV1:
        return DeploymentFencingTokenV1.from_fact(self._store.transition(request))

    def validate(
        self,
        token: DeploymentFencingTokenV1 | None,
        *,
        scope: DeploymentFencingScopeV1,
        owner: RequesterReference | None,
        authority_identity: CapabilityReference,
        operation: DeploymentMutationClass,
        semantic_binding_fingerprint: DeploymentFingerprint | None = None,
    ) -> DeploymentFencingValidationResultV1:
        required = operation.fencing_required
        if not required and token is None:
            return _validation(DeploymentFencingValidationState.VALID, None, None, False)
        if token is None:
            return _validation(
                DeploymentFencingValidationState.UNAVAILABLE,
                None,
                None,
                required,
                "fencing-unavailable",
            )
        if (
            token.scope != scope
            or token.owner != owner
            or token.authority_identity != authority_identity
            or token.authority_version != DEPLOYMENT_FENCING_AUTHORITY_VERSION
            or token.semantic_binding_fingerprint != semantic_binding_fingerprint
        ):
            return _validation(
                DeploymentFencingValidationState.MISMATCHED,
                token.generation,
                None,
                required,
                "fencing-mismatched",
            )
        try:
            latest = self._store.latest(scope)
        except DeploymentFencingUnavailable:
            return _validation(
                DeploymentFencingValidationState.UNAVAILABLE,
                token.generation,
                None,
                required,
                "fencing-unavailable",
            )
        if latest is None:
            return _validation(
                DeploymentFencingValidationState.UNAVAILABLE,
                token.generation,
                None,
                required,
                "fencing-unavailable",
            )
        expected = DeploymentFencingTokenV1.from_fact(latest)
        reconstructed = DeploymentFencingTokenV1(
            token.scope,
            token.generation,
            token.owner,
            token.authority_identity,
            token.authority_version,
            token.occurrence,
            token.semantic_binding_fingerprint,
            token.token_fingerprint,
            token.version,
        )
        if (
            reconstructed.token_fingerprint
            != DeploymentFencingTokenV1.from_fact(
                DeploymentGenerationFactV1(
                    token.scope,
                    token.generation,
                    token.owner,
                    token.authority_identity,
                    token.authority_version,
                    token.occurrence,
                    token.semantic_binding_fingerprint,
                    latest.transition_fingerprint,
                    latest.previous_fact_fingerprint,
                    latest.fact_fingerprint,
                )
            ).token_fingerprint
        ):
            return _validation(
                DeploymentFencingValidationState.INVALID,
                token.generation,
                latest.generation,
                required,
                "fencing-invalid",
            )
        if token.generation.value < latest.generation.value:
            return _validation(
                DeploymentFencingValidationState.STALE,
                token.generation,
                latest.generation,
                required,
                "fencing-stale",
            )
        if token.generation.value > latest.generation.value or token != expected:
            return _validation(
                DeploymentFencingValidationState.INVALID,
                token.generation,
                latest.generation,
                required,
                "fencing-invalid",
            )
        return _validation(
            DeploymentFencingValidationState.VALID,
            token.generation,
            latest.generation,
            required,
        )

    def accept_operation(
        self,
        request: DeploymentIdempotencyRequestV1,
        token: DeploymentFencingTokenV1 | None,
        *,
        owner: RequesterReference,
        authority_identity: CapabilityReference,
    ) -> DeploymentOperationAcceptanceV1:
        fencing = self.validate(
            token,
            scope=request.scope,
            owner=owner,
            authority_identity=authority_identity,
            operation=request.operation,
            semantic_binding_fingerprint=request.semantic_fingerprint,
        )
        if not fencing.accepted or fencing.latest_generation is None:
            return DeploymentOperationAcceptanceV1(
                DeploymentIdempotencyDisposition.FENCING_REJECTED, fencing, None
            )
        disposition, record = self._store.record_idempotency(request, fencing.latest_generation)
        return DeploymentOperationAcceptanceV1(disposition, fencing, record)


def replay_generation_history(
    facts: tuple[DeploymentGenerationFactV1, ...],
) -> DeploymentGenerationFactV1 | None:
    previous: DeploymentGenerationFactV1 | None = None
    for fact in facts:
        if previous is not None and (
            fact.scope != previous.scope
            or fact.generation.value != previous.generation.value + 1
            or fact.previous_fact_fingerprint != previous.fact_fingerprint
        ):
            raise ValueError("deployment generation history is not monotonic")
        if previous is None and (
            fact.generation.value != 1 or fact.previous_fact_fingerprint is not None
        ):
            raise ValueError("deployment generation history has an invalid origin")
        previous = fact
    return previous


def _validation(
    state: DeploymentFencingValidationState,
    presented: DeploymentGeneration | None,
    latest: DeploymentGeneration | None,
    required: bool,
    diagnostic: str | None = None,
) -> DeploymentFencingValidationResultV1:
    return DeploymentFencingValidationResultV1(
        state, presented, latest, required, (diagnostic,) if diagnostic else ()
    )
