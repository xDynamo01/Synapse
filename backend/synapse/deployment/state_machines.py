"""Pure factual state machines for deployment, rollout, promotion and rollback."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeVar

from .canonical import DEPLOYMENT_CANONICAL_FORMAT_V1, content_fingerprint
from .errors import (
    ContradictoryDeploymentTransition,
    DeploymentStateMismatch,
    InvalidDeploymentTransition,
    InvalidRollbackProgression,
    InvalidRolloutProgression,
    MissingDeploymentTransitionReference,
)
from .identities import (
    ApplyReceiptReference,
    ArtifactReference,
    AuthorizationReference,
    CapabilityReference,
    CausationReference,
    CorrelationReference,
    DeploymentAttemptId,
    DeploymentEventId,
    DeploymentFingerprint,
    DeploymentTargetId,
    ObservationReference,
    OccurrenceReference,
    PromotionId,
    ReleaseId,
    RevisionId,
    RollbackAttemptId,
    RollbackReceiptReference,
    RolloutId,
    SlotId,
    VerificationReference,
)


class StateTerminality(StrEnum):
    NON_TERMINAL = "non-terminal"
    TERMINAL_SUCCESS = "terminal-success"
    TERMINAL_FAILURE = "terminal-failure"
    RECONCILIATION_REQUIRED = "reconciliation-required"


class DeploymentLifecycleState(StrEnum):
    PROPOSED = "proposed"
    AUTHORIZATION_PENDING = "authorization-pending"
    AUTHORIZED = "authorized"
    PREPARED = "prepared"
    APPLYING = "applying"
    APPLIED = "applied"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    PROMOTION_PENDING = "promotion-pending"
    PROMOTED = "promoted"
    DENIED = "denied"
    PREPARATION_FAILED = "preparation-failed"
    APPLY_FAILED = "apply-failed"
    PARTIALLY_APPLIED = "partially-applied"
    APPLY_OUTCOME_UNKNOWN = "apply-outcome-unknown"
    VERIFICATION_FAILED = "verification-failed"
    VERIFICATION_UNAVAILABLE = "verification-unavailable"
    ROLLBACK_REQUIRED = "rollback-required"
    RECONCILIATION_REQUIRED = "reconciliation-required"
    MANUAL_INTERVENTION_REQUIRED = "manual-intervention-required"

    @property
    def terminality(self) -> StateTerminality:
        if self is self.PROMOTED:
            return StateTerminality.TERMINAL_SUCCESS
        if self in {
            self.DENIED,
            self.PREPARATION_FAILED,
            self.APPLY_FAILED,
            self.VERIFICATION_FAILED,
        }:
            return StateTerminality.TERMINAL_FAILURE
        if self in {
            self.PARTIALLY_APPLIED,
            self.APPLY_OUTCOME_UNKNOWN,
            self.VERIFICATION_UNAVAILABLE,
            self.ROLLBACK_REQUIRED,
            self.RECONCILIATION_REQUIRED,
            self.MANUAL_INTERVENTION_REQUIRED,
        }:
            return StateTerminality.RECONCILIATION_REQUIRED
        return StateTerminality.NON_TERMINAL


class RolloutLifecycleState(StrEnum):
    PLANNED = "planned"
    AUTHORIZED = "authorized"
    IN_PROGRESS = "in-progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    ROLLBACK_REQUIRED = "rollback-required"
    RECONCILIATION_REQUIRED = "reconciliation-required"

    @property
    def terminality(self) -> StateTerminality:
        if self is self.COMPLETED:
            return StateTerminality.TERMINAL_SUCCESS
        if self is self.FAILED:
            return StateTerminality.TERMINAL_FAILURE
        if self in {self.ROLLBACK_REQUIRED, self.RECONCILIATION_REQUIRED}:
            return StateTerminality.RECONCILIATION_REQUIRED
        return StateTerminality.NON_TERMINAL


class PromotionLifecycleState(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    APPLIED = "applied"
    DENIED = "denied"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome-unknown"
    RECONCILIATION_REQUIRED = "reconciliation-required"

    @property
    def terminality(self) -> StateTerminality:
        if self is self.APPLIED:
            return StateTerminality.TERMINAL_SUCCESS
        if self in {self.DENIED, self.FAILED}:
            return StateTerminality.TERMINAL_FAILURE
        if self in {self.OUTCOME_UNKNOWN, self.RECONCILIATION_REQUIRED}:
            return StateTerminality.RECONCILIATION_REQUIRED
        return StateTerminality.NON_TERMINAL


class RollbackLifecycleState(StrEnum):
    REQUESTED = "requested"
    AUTHORIZATION_PENDING = "authorization-pending"
    AUTHORIZED = "authorized"
    PREPARING = "preparing"
    ROLLING_BACK = "rolling-back"
    ROLLED_BACK = "rolled-back"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    DENIED = "denied"
    PREPARATION_FAILED = "preparation-failed"
    PREPARATION_OUTCOME_UNKNOWN = "preparation-outcome-unknown"
    ROLLBACK_FAILED = "rollback-failed"
    ROLLBACK_OUTCOME_UNKNOWN = "rollback-outcome-unknown"
    ROLLBACK_UNVERIFIED = "rollback-unverified"
    RECONCILIATION_REQUIRED = "reconciliation-required"
    MANUAL_INTERVENTION_REQUIRED = "manual-intervention-required"

    @property
    def terminality(self) -> StateTerminality:
        if self is self.VERIFIED:
            return StateTerminality.TERMINAL_SUCCESS
        if self in {self.DENIED, self.PREPARATION_FAILED, self.ROLLBACK_FAILED}:
            return StateTerminality.TERMINAL_FAILURE
        if self in {
            self.ROLLBACK_OUTCOME_UNKNOWN,
            self.PREPARATION_OUTCOME_UNKNOWN,
            self.ROLLBACK_UNVERIFIED,
            self.RECONCILIATION_REQUIRED,
            self.MANUAL_INTERVENTION_REQUIRED,
        }:
            return StateTerminality.RECONCILIATION_REQUIRED
        return StateTerminality.NON_TERMINAL


class TransitionFailureClass(StrEnum):
    POLICY_DENIED = "policy-denied"
    PRECONDITION_FAILED = "precondition-failed"
    EXTERNAL_FAILURE = "external-failure"
    PARTIAL_EXTERNAL_EFFECT = "partial-external-effect"
    EXTERNAL_OUTCOME_UNKNOWN = "external-outcome-unknown"
    EVIDENCE_UNAVAILABLE = "evidence-unavailable"
    VERIFICATION_MISMATCH = "verification-mismatch"
    MANUAL_INTERVENTION = "manual-intervention"


@dataclass(frozen=True, slots=True, order=True)
class RolloutStageV1:
    sequence: int
    stage_reference: CapabilityReference
    slot_id: SlotId | None = None
    abstract_percentage: int | None = None
    gate_reference: CapabilityReference | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise InvalidRolloutProgression("rollout stage sequence must be positive")
        if self.abstract_percentage is not None and (
            isinstance(self.abstract_percentage, bool)
            or not isinstance(self.abstract_percentage, int)
            or not 1 <= self.abstract_percentage <= 100
        ):
            raise InvalidRolloutProgression("rollout stage percentage must be from 1 to 100")


def _validate_optional_reference(value: object | None, expected: type[object], label: str) -> None:
    if value is not None and not isinstance(value, expected):
        raise MissingDeploymentTransitionReference(f"{label} has the wrong reference type")


@dataclass(frozen=True, slots=True)
class DeploymentTransitionEventV1:
    event_id: DeploymentEventId
    release_id: ReleaseId
    attempt_id: DeploymentAttemptId
    prior_state: DeploymentLifecycleState
    resulting_state: DeploymentLifecycleState
    correlation: CorrelationReference
    causation: CausationReference | None
    occurrence: OccurrenceReference
    authorization_reference: AuthorizationReference | None = None
    apply_receipt_reference: ApplyReceiptReference | None = None
    observation_reference: ObservationReference | None = None
    verification_reference: VerificationReference | None = None
    failure_class: TransitionFailureClass | None = None
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        _validate_optional_reference(
            self.authorization_reference, AuthorizationReference, "authorization"
        )
        _validate_optional_reference(
            self.apply_receipt_reference, ApplyReceiptReference, "apply receipt"
        )
        _validate_optional_reference(
            self.observation_reference, ObservationReference, "observation"
        )
        _validate_optional_reference(
            self.verification_reference, VerificationReference, "verification"
        )

    @property
    def fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(content_fingerprint(self))


@dataclass(frozen=True, slots=True)
class RolloutTransitionEventV1:
    event_id: DeploymentEventId
    rollout_id: RolloutId
    release_id: ReleaseId
    prior_state: RolloutLifecycleState
    resulting_state: RolloutLifecycleState
    correlation: CorrelationReference
    causation: CausationReference | None
    occurrence: OccurrenceReference
    authorization_reference: AuthorizationReference | None = None
    stage: RolloutStageV1 | None = None
    failure_class: TransitionFailureClass | None = None
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        _validate_optional_reference(
            self.authorization_reference, AuthorizationReference, "authorization"
        )

    @property
    def fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(content_fingerprint(self))


@dataclass(frozen=True, slots=True)
class PromotionTransitionEventV1:
    event_id: DeploymentEventId
    promotion_id: PromotionId
    rollout_id: RolloutId
    prior_state: PromotionLifecycleState
    resulting_state: PromotionLifecycleState
    correlation: CorrelationReference
    causation: CausationReference | None
    occurrence: OccurrenceReference
    authorization_reference: AuthorizationReference | None = None
    apply_receipt_reference: ApplyReceiptReference | None = None
    failure_class: TransitionFailureClass | None = None
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        _validate_optional_reference(
            self.authorization_reference, AuthorizationReference, "authorization"
        )
        _validate_optional_reference(
            self.apply_receipt_reference, ApplyReceiptReference, "apply receipt"
        )

    @property
    def fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(content_fingerprint(self))


@dataclass(frozen=True, slots=True)
class RollbackTransitionEventV1:
    event_id: DeploymentEventId
    rollback_attempt_id: RollbackAttemptId
    release_id: ReleaseId
    target_id: DeploymentTargetId
    source_revision: RevisionId
    intended_revision: RevisionId
    intended_artifact_reference: ArtifactReference | None
    prior_state: RollbackLifecycleState
    resulting_state: RollbackLifecycleState
    correlation: CorrelationReference
    causation: CausationReference | None
    occurrence: OccurrenceReference
    authorization_reference: AuthorizationReference | None = None
    rollback_receipt_reference: RollbackReceiptReference | None = None
    observation_reference: ObservationReference | None = None
    verification_reference: VerificationReference | None = None
    failure_class: TransitionFailureClass | None = None
    format_version: str = DEPLOYMENT_CANONICAL_FORMAT_V1

    def __post_init__(self) -> None:
        if self.source_revision == self.intended_revision:
            raise InvalidRollbackProgression("rollback revisions must be distinct")
        _validate_optional_reference(
            self.authorization_reference, AuthorizationReference, "authorization"
        )
        _validate_optional_reference(
            self.rollback_receipt_reference, RollbackReceiptReference, "rollback receipt"
        )
        _validate_optional_reference(
            self.observation_reference, ObservationReference, "observation"
        )
        _validate_optional_reference(
            self.verification_reference, VerificationReference, "verification"
        )

    @property
    def fingerprint(self) -> DeploymentFingerprint:
        return DeploymentFingerprint(content_fingerprint(self))


EventRecord = tuple[DeploymentEventId, DeploymentFingerprint]


@dataclass(frozen=True, slots=True)
class DeploymentStateProjection:
    release_id: ReleaseId
    attempt_id: DeploymentAttemptId
    state: DeploymentLifecycleState = DeploymentLifecycleState.PROPOSED
    events: tuple[EventRecord, ...] = ()

    @property
    def terminality(self) -> StateTerminality:
        return self.state.terminality

    @classmethod
    def replay(
        cls,
        release_id: ReleaseId,
        attempt_id: DeploymentAttemptId,
        events: tuple[DeploymentTransitionEventV1, ...],
    ) -> DeploymentStateProjection:
        projection = cls(release_id, attempt_id)
        for event in events:
            projection = reduce_deployment(projection, event)
        return projection


@dataclass(frozen=True, slots=True)
class RolloutStateProjection:
    rollout_id: RolloutId
    release_id: ReleaseId
    state: RolloutLifecycleState = RolloutLifecycleState.PLANNED
    current_stage: RolloutStageV1 | None = None
    events: tuple[EventRecord, ...] = ()

    @property
    def terminality(self) -> StateTerminality:
        return self.state.terminality

    @classmethod
    def replay(
        cls,
        rollout_id: RolloutId,
        release_id: ReleaseId,
        events: tuple[RolloutTransitionEventV1, ...],
    ) -> RolloutStateProjection:
        projection = cls(rollout_id, release_id)
        for event in events:
            projection = reduce_rollout(projection, event)
        return projection


@dataclass(frozen=True, slots=True)
class PromotionStateProjection:
    promotion_id: PromotionId
    rollout_id: RolloutId
    state: PromotionLifecycleState = PromotionLifecycleState.PENDING
    events: tuple[EventRecord, ...] = ()

    @property
    def terminality(self) -> StateTerminality:
        return self.state.terminality

    @classmethod
    def replay(
        cls,
        promotion_id: PromotionId,
        rollout_id: RolloutId,
        events: tuple[PromotionTransitionEventV1, ...],
    ) -> PromotionStateProjection:
        projection = cls(promotion_id, rollout_id)
        for event in events:
            projection = reduce_promotion(projection, event)
        return projection


@dataclass(frozen=True, slots=True)
class RollbackStateProjection:
    rollback_attempt_id: RollbackAttemptId
    release_id: ReleaseId
    target_id: DeploymentTargetId
    source_revision: RevisionId
    intended_revision: RevisionId
    state: RollbackLifecycleState = RollbackLifecycleState.REQUESTED
    events: tuple[EventRecord, ...] = ()

    @property
    def terminality(self) -> StateTerminality:
        return self.state.terminality

    @classmethod
    def replay(
        cls,
        rollback_attempt_id: RollbackAttemptId,
        release_id: ReleaseId,
        target_id: DeploymentTargetId,
        source_revision: RevisionId,
        intended_revision: RevisionId,
        events: tuple[RollbackTransitionEventV1, ...],
    ) -> RollbackStateProjection:
        projection = cls(
            rollback_attempt_id,
            release_id,
            target_id,
            source_revision,
            intended_revision,
        )
        for event in events:
            projection = reduce_rollback(projection, event)
        return projection


_DEPLOYMENT_ALLOWED = {
    (DeploymentLifecycleState.PROPOSED, DeploymentLifecycleState.AUTHORIZATION_PENDING),
    (DeploymentLifecycleState.AUTHORIZATION_PENDING, DeploymentLifecycleState.AUTHORIZED),
    (DeploymentLifecycleState.AUTHORIZATION_PENDING, DeploymentLifecycleState.DENIED),
    (DeploymentLifecycleState.AUTHORIZED, DeploymentLifecycleState.PREPARED),
    (DeploymentLifecycleState.AUTHORIZED, DeploymentLifecycleState.PREPARATION_FAILED),
    (DeploymentLifecycleState.PREPARED, DeploymentLifecycleState.APPLYING),
    (DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLIED),
    (DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLY_FAILED),
    (DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.PARTIALLY_APPLIED),
    (DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN),
    (DeploymentLifecycleState.APPLIED, DeploymentLifecycleState.VERIFYING),
    (DeploymentLifecycleState.VERIFYING, DeploymentLifecycleState.VERIFIED),
    (DeploymentLifecycleState.VERIFYING, DeploymentLifecycleState.VERIFICATION_FAILED),
    (DeploymentLifecycleState.VERIFYING, DeploymentLifecycleState.VERIFICATION_UNAVAILABLE),
    (DeploymentLifecycleState.VERIFIED, DeploymentLifecycleState.PROMOTION_PENDING),
    (DeploymentLifecycleState.PROMOTION_PENDING, DeploymentLifecycleState.PROMOTED),
    (DeploymentLifecycleState.PROMOTION_PENDING, DeploymentLifecycleState.ROLLBACK_REQUIRED),
    (
        DeploymentLifecycleState.RECONCILIATION_REQUIRED,
        DeploymentLifecycleState.MANUAL_INTERVENTION_REQUIRED,
    ),
}
_DEPLOYMENT_RECONCILABLE = {
    DeploymentLifecycleState.PARTIALLY_APPLIED,
    DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN,
    DeploymentLifecycleState.VERIFICATION_UNAVAILABLE,
    DeploymentLifecycleState.ROLLBACK_REQUIRED,
}

_ROLLOUT_ALLOWED = {
    (RolloutLifecycleState.PLANNED, RolloutLifecycleState.AUTHORIZED),
    (RolloutLifecycleState.PLANNED, RolloutLifecycleState.BLOCKED),
    (RolloutLifecycleState.AUTHORIZED, RolloutLifecycleState.IN_PROGRESS),
    (RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.IN_PROGRESS),
    (RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.PAUSED),
    (RolloutLifecycleState.PAUSED, RolloutLifecycleState.IN_PROGRESS),
    (RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.COMPLETED),
    (RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.BLOCKED),
    (RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.FAILED),
    (RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.ROLLBACK_REQUIRED),
    (RolloutLifecycleState.PAUSED, RolloutLifecycleState.FAILED),
    (RolloutLifecycleState.BLOCKED, RolloutLifecycleState.IN_PROGRESS),
}

_PROMOTION_ALLOWED = {
    (PromotionLifecycleState.PENDING, PromotionLifecycleState.AUTHORIZED),
    (PromotionLifecycleState.PENDING, PromotionLifecycleState.DENIED),
    (PromotionLifecycleState.AUTHORIZED, PromotionLifecycleState.APPLIED),
    (PromotionLifecycleState.AUTHORIZED, PromotionLifecycleState.FAILED),
    (PromotionLifecycleState.AUTHORIZED, PromotionLifecycleState.OUTCOME_UNKNOWN),
    (PromotionLifecycleState.OUTCOME_UNKNOWN, PromotionLifecycleState.RECONCILIATION_REQUIRED),
}

_ROLLBACK_ALLOWED = {
    (RollbackLifecycleState.REQUESTED, RollbackLifecycleState.AUTHORIZATION_PENDING),
    (RollbackLifecycleState.AUTHORIZATION_PENDING, RollbackLifecycleState.AUTHORIZED),
    (RollbackLifecycleState.AUTHORIZATION_PENDING, RollbackLifecycleState.DENIED),
    (RollbackLifecycleState.AUTHORIZED, RollbackLifecycleState.PREPARING),
    (RollbackLifecycleState.PREPARING, RollbackLifecycleState.ROLLING_BACK),
    (RollbackLifecycleState.PREPARING, RollbackLifecycleState.PREPARATION_FAILED),
    (RollbackLifecycleState.PREPARING, RollbackLifecycleState.PREPARATION_OUTCOME_UNKNOWN),
    (RollbackLifecycleState.ROLLING_BACK, RollbackLifecycleState.ROLLED_BACK),
    (RollbackLifecycleState.ROLLING_BACK, RollbackLifecycleState.ROLLBACK_FAILED),
    (RollbackLifecycleState.ROLLING_BACK, RollbackLifecycleState.ROLLBACK_OUTCOME_UNKNOWN),
    (RollbackLifecycleState.ROLLED_BACK, RollbackLifecycleState.VERIFYING),
    (RollbackLifecycleState.ROLLED_BACK, RollbackLifecycleState.ROLLBACK_UNVERIFIED),
    (RollbackLifecycleState.VERIFYING, RollbackLifecycleState.VERIFIED),
    (RollbackLifecycleState.VERIFYING, RollbackLifecycleState.ROLLBACK_UNVERIFIED),
}
_ROLLBACK_RECONCILABLE = {
    RollbackLifecycleState.PREPARATION_OUTCOME_UNKNOWN,
    RollbackLifecycleState.ROLLBACK_OUTCOME_UNKNOWN,
    RollbackLifecycleState.ROLLBACK_UNVERIFIED,
}

ProjectionT = TypeVar(
    "ProjectionT",
    DeploymentStateProjection,
    RolloutStateProjection,
    PromotionStateProjection,
    RollbackStateProjection,
)


def _idempotent_or_contradictory(
    projection: ProjectionT, event_id: DeploymentEventId, fingerprint: DeploymentFingerprint
) -> ProjectionT | None:
    for known_id, known_fingerprint in projection.events:
        if known_id == event_id:
            if known_fingerprint == fingerprint:
                return projection
            raise ContradictoryDeploymentTransition(
                "event identity is already bound to different factual content"
            )
    return None


def _next_events(
    events: tuple[EventRecord, ...], event_id: DeploymentEventId, fingerprint: DeploymentFingerprint
) -> tuple[EventRecord, ...]:
    return (*events, (event_id, fingerprint))


def _require_authorization(
    resulting_state: StrEnum, authorization: AuthorizationReference | None
) -> None:
    if resulting_state.value == "authorized" and authorization is None:
        raise MissingDeploymentTransitionReference(
            "authorized transition requires an explicit authorization acceptance reference"
        )


def _require_failure_class(
    resulting_state: StrEnum,
    failure_class: TransitionFailureClass | None,
    failure_states: set[str],
) -> None:
    if resulting_state.value in failure_states and failure_class is None:
        raise MissingDeploymentTransitionReference(
            "failure or uncertain transition requires an explicit failure classification"
        )


def reduce_deployment(
    projection: DeploymentStateProjection, event: DeploymentTransitionEventV1
) -> DeploymentStateProjection:
    duplicate = _idempotent_or_contradictory(projection, event.event_id, event.fingerprint)
    if duplicate is not None:
        return duplicate
    if event.release_id != projection.release_id or event.attempt_id != projection.attempt_id:
        raise DeploymentStateMismatch("deployment event subject mismatch")
    if event.prior_state is not projection.state:
        raise DeploymentStateMismatch("deployment prior state mismatch")
    allowed = (event.prior_state, event.resulting_state) in _DEPLOYMENT_ALLOWED or (
        event.prior_state in _DEPLOYMENT_RECONCILABLE
        and event.resulting_state is DeploymentLifecycleState.RECONCILIATION_REQUIRED
    )
    if not allowed:
        raise InvalidDeploymentTransition("illegal deployment transition")
    _require_authorization(event.resulting_state, event.authorization_reference)
    _require_failure_class(
        event.resulting_state,
        event.failure_class,
        {
            "denied",
            "preparation-failed",
            "preparation-outcome-unknown",
            "apply-failed",
            "partially-applied",
            "apply-outcome-unknown",
            "verification-failed",
            "verification-unavailable",
            "rollback-required",
            "manual-intervention-required",
        },
    )
    if (
        event.resulting_state
        in {
            DeploymentLifecycleState.APPLIED,
            DeploymentLifecycleState.PARTIALLY_APPLIED,
        }
        and event.apply_receipt_reference is None
    ):
        raise MissingDeploymentTransitionReference("apply outcome requires an apply receipt")
    if event.resulting_state is DeploymentLifecycleState.VERIFIED and (
        event.observation_reference is None or event.verification_reference is None
    ):
        raise MissingDeploymentTransitionReference(
            "verified transition requires observation and verification references"
        )
    return replace(
        projection,
        state=event.resulting_state,
        events=_next_events(projection.events, event.event_id, event.fingerprint),
    )


def reduce_rollout(
    projection: RolloutStateProjection, event: RolloutTransitionEventV1
) -> RolloutStateProjection:
    duplicate = _idempotent_or_contradictory(projection, event.event_id, event.fingerprint)
    if duplicate is not None:
        return duplicate
    if event.rollout_id != projection.rollout_id or event.release_id != projection.release_id:
        raise DeploymentStateMismatch("rollout event subject mismatch")
    if event.prior_state is not projection.state:
        raise DeploymentStateMismatch("rollout prior state mismatch")
    allowed = (event.prior_state, event.resulting_state) in _ROLLOUT_ALLOWED or (
        event.resulting_state is RolloutLifecycleState.RECONCILIATION_REQUIRED
        and event.prior_state
        in {RolloutLifecycleState.BLOCKED, RolloutLifecycleState.ROLLBACK_REQUIRED}
    )
    if not allowed:
        raise InvalidRolloutProgression("illegal rollout transition")
    _require_authorization(event.resulting_state, event.authorization_reference)
    _require_failure_class(
        event.resulting_state,
        event.failure_class,
        {"blocked", "failed", "rollback-required"},
    )
    if event.resulting_state in {
        RolloutLifecycleState.IN_PROGRESS,
        RolloutLifecycleState.COMPLETED,
    }:
        if event.stage is None:
            raise InvalidRolloutProgression("rollout progression requires an explicit stage")
        if (
            projection.current_stage is not None
            and event.resulting_state is RolloutLifecycleState.IN_PROGRESS
            and event.prior_state is not RolloutLifecycleState.PAUSED
            and event.stage.sequence <= projection.current_stage.sequence
        ):
            raise InvalidRolloutProgression("rollout stage sequence must advance")
        if (
            event.prior_state is RolloutLifecycleState.PAUSED
            and event.stage != projection.current_stage
        ):
            raise InvalidRolloutProgression("resume must retain the paused stage")
    return replace(
        projection,
        state=event.resulting_state,
        current_stage=event.stage or projection.current_stage,
        events=_next_events(projection.events, event.event_id, event.fingerprint),
    )


def reduce_promotion(
    projection: PromotionStateProjection, event: PromotionTransitionEventV1
) -> PromotionStateProjection:
    duplicate = _idempotent_or_contradictory(projection, event.event_id, event.fingerprint)
    if duplicate is not None:
        return duplicate
    if event.promotion_id != projection.promotion_id or event.rollout_id != projection.rollout_id:
        raise DeploymentStateMismatch("promotion event subject mismatch")
    if event.prior_state is not projection.state:
        raise DeploymentStateMismatch("promotion prior state mismatch")
    if (event.prior_state, event.resulting_state) not in _PROMOTION_ALLOWED:
        raise InvalidDeploymentTransition("illegal promotion transition")
    _require_authorization(event.resulting_state, event.authorization_reference)
    _require_failure_class(
        event.resulting_state,
        event.failure_class,
        {"denied", "failed", "outcome-unknown"},
    )
    if (
        event.resulting_state is PromotionLifecycleState.APPLIED
        and event.apply_receipt_reference is None
    ):
        raise MissingDeploymentTransitionReference("applied promotion requires a receipt")
    return replace(
        projection,
        state=event.resulting_state,
        events=_next_events(projection.events, event.event_id, event.fingerprint),
    )


def reduce_rollback(
    projection: RollbackStateProjection, event: RollbackTransitionEventV1
) -> RollbackStateProjection:
    duplicate = _idempotent_or_contradictory(projection, event.event_id, event.fingerprint)
    if duplicate is not None:
        return duplicate
    if (
        event.rollback_attempt_id != projection.rollback_attempt_id
        or event.release_id != projection.release_id
        or event.target_id != projection.target_id
    ):
        raise DeploymentStateMismatch("rollback event subject mismatch")
    if (
        event.source_revision != projection.source_revision
        or event.intended_revision != projection.intended_revision
    ):
        raise InvalidRollbackProgression("rollback revision binding mismatch")
    if event.prior_state is not projection.state:
        raise DeploymentStateMismatch("rollback prior state mismatch")
    allowed = (
        (event.prior_state, event.resulting_state) in _ROLLBACK_ALLOWED
        or (
            event.prior_state in _ROLLBACK_RECONCILABLE
            and event.resulting_state is RollbackLifecycleState.RECONCILIATION_REQUIRED
        )
        or (
            event.prior_state is RollbackLifecycleState.RECONCILIATION_REQUIRED
            and event.resulting_state is RollbackLifecycleState.MANUAL_INTERVENTION_REQUIRED
        )
    )
    if not allowed:
        raise InvalidRollbackProgression("illegal rollback transition")
    _require_authorization(event.resulting_state, event.authorization_reference)
    _require_failure_class(
        event.resulting_state,
        event.failure_class,
        {
            "denied",
            "preparation-failed",
            "rollback-failed",
            "rollback-outcome-unknown",
            "rollback-unverified",
            "manual-intervention-required",
        },
    )
    if event.resulting_state is RollbackLifecycleState.ROLLED_BACK and (
        event.rollback_receipt_reference is None or event.intended_artifact_reference is None
    ):
        raise MissingDeploymentTransitionReference(
            "rolled back transition requires receipt and intended artifact references"
        )
    if event.resulting_state is RollbackLifecycleState.VERIFIED and (
        event.observation_reference is None or event.verification_reference is None
    ):
        raise MissingDeploymentTransitionReference(
            "verified rollback requires observation and verification references"
        )
    return replace(
        projection,
        state=event.resulting_state,
        events=_next_events(projection.events, event.event_id, event.fingerprint),
    )
