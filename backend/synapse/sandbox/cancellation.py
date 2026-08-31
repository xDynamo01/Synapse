"""Pure cancellation, explicit deadline and deterministic escalation semantics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .errors import InvalidCancellation
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxAttemptId,
    SandboxCancellationDecisionId,
    SandboxCancellationResultId,
    SandboxDeadlineSetId,
    SandboxPolicyVersion,
    SandboxTerminationProofId,
    SandboxTimeoutPolicyId,
    derive_identity,
)
from .runtime_supervision import (
    SandboxExecutionAttempt,
    SandboxTerminationProof,
    SandboxTerminationVerificationOutcome,
)

CANCELLATION_FORMAT = "sandbox-cancellation-v1"
_CODE = re.compile(r"[a-z][a-z0-9_.-]{0,95}")


def _aware(value: datetime, code: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidCancellation(code)


def _codes(values: tuple[str, ...], code: str) -> None:
    if values != tuple(sorted(set(values))) or any(
        _CODE.fullmatch(value) is None for value in values
    ):
        raise InvalidCancellation(code)


class SandboxDeadlineKind(StrEnum):
    STARTUP = "startup"
    IDLE = "idle"
    WALL_CLOCK = "wall_clock"
    TERMINATION_GRACE = "termination_grace"
    CLEANUP = "cleanup"


class SandboxCancellationClassification(StrEnum):
    REQUESTED = "requested"
    STARTUP_TIMEOUT = "startup_timeout"
    IDLE_TIMEOUT = "idle_timeout"
    WALL_CLOCK_TIMEOUT = "wall_clock_timeout"
    TERMINATION_GRACE_TIMEOUT = "termination_grace_timeout"
    CLEANUP_TIMEOUT = "cleanup_timeout"


class SandboxCancellationState(StrEnum):
    REQUESTED = "requested"
    ACKNOWLEDGED = "acknowledged"
    TERMINATION_REQUESTED = "termination_requested"
    TERMINATION_INITIATED = "termination_initiated"
    TERMINATION_VERIFIED = "termination_verified"
    TERMINATION_UNVERIFIED = "termination_unverified"
    COMPLETED = "completed"
    MANUAL_INTERVENTION = "manual_intervention"


class SandboxTerminationEscalationStage(StrEnum):
    COOPERATIVE_CANCELLATION = "cooperative_cancellation"
    GRACEFUL_TERMINATION = "graceful_termination"
    FORCED_TERMINATION = "forced_termination"
    MANUAL_INTERVENTION = "manual_intervention"


class SandboxCancellationEventKind(StrEnum):
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLATION_ACKNOWLEDGED = "cancellation_acknowledged"
    TERMINATION_REQUESTED = "termination_requested"
    TERMINATION_INITIATED = "termination_initiated"
    ESCALATED = "escalated"
    TERMINATION_VERIFIED = "termination_verified"
    TERMINATION_UNVERIFIED = "termination_unverified"
    CANCELLATION_COMPLETED = "cancellation_completed"


class SandboxDescendantsStatus(StrEnum):
    CLEAR = "clear"
    ACTIVE = "active"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SandboxTimeoutPolicy:
    policy_id: SandboxTimeoutPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    version: SandboxPolicyVersion
    required_deadlines: tuple[SandboxDeadlineKind, ...]
    escalation_order: tuple[SandboxTerminationEscalationStage, ...]
    acknowledgement_required: bool
    forced_termination_allowed: bool
    cleanup_required_when_unverified: bool

    def semantic_content(self) -> tuple[object, ...]:
        return (
            CANCELLATION_FORMAT,
            self.version,
            self.required_deadlines,
            self.escalation_order,
            self.acknowledgement_required,
            self.forced_termination_allowed,
            self.cleanup_required_when_unverified,
        )

    def __post_init__(self) -> None:
        if self.required_deadlines != tuple(
            sorted(set(self.required_deadlines), key=lambda item: item.value)
        ):
            raise InvalidCancellation("policy.deadlines_not_canonical")
        canonical_order = (
            SandboxTerminationEscalationStage.COOPERATIVE_CANCELLATION,
            SandboxTerminationEscalationStage.GRACEFUL_TERMINATION,
            SandboxTerminationEscalationStage.FORCED_TERMINATION,
            SandboxTerminationEscalationStage.MANUAL_INTERVENTION,
        )
        selected = tuple(item for item in canonical_order if item in self.escalation_order)
        if self.escalation_order != selected or not self.escalation_order:
            raise InvalidCancellation("policy.escalation_not_canonical")
        if (
            SandboxTerminationEscalationStage.FORCED_TERMINATION in self.escalation_order
            and not self.forced_termination_allowed
        ):
            raise InvalidCancellation("policy.forced_termination_conflict")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.policy_fingerprint:
            raise InvalidCancellation("policy.fingerprint_mismatch")
        if derive_identity(SandboxTimeoutPolicyId, expected) != self.policy_id:
            raise InvalidCancellation("policy.identity_mismatch")

    @classmethod
    def create(
        cls,
        *,
        version: SandboxPolicyVersion,
        required_deadlines: tuple[SandboxDeadlineKind, ...],
        escalation_order: tuple[SandboxTerminationEscalationStage, ...],
        acknowledgement_required: bool = True,
        forced_termination_allowed: bool = False,
        cleanup_required_when_unverified: bool = True,
    ) -> SandboxTimeoutPolicy:
        deadlines = tuple(sorted(set(required_deadlines), key=lambda item: item.value))
        semantic = (
            CANCELLATION_FORMAT,
            version,
            deadlines,
            escalation_order,
            acknowledgement_required,
            forced_termination_allowed,
            cleanup_required_when_unverified,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic)
        identity = derive_identity(SandboxTimeoutPolicyId, fingerprint)
        return cls(
            SandboxTimeoutPolicyId(identity.value),
            fingerprint,
            version,
            deadlines,
            escalation_order,
            acknowledgement_required,
            forced_termination_allowed,
            cleanup_required_when_unverified,
        )


@dataclass(frozen=True, slots=True)
class SandboxDeadline:
    kind: SandboxDeadlineKind
    expires_at: datetime

    def __post_init__(self) -> None:
        _aware(self.expires_at, "deadline.timestamp_invalid")


@dataclass(frozen=True, slots=True)
class SandboxDeadlineSet:
    deadline_set_id: SandboxDeadlineSetId
    deadline_set_fingerprint: SandboxArtifactFingerprint
    attempt_id: SandboxAttemptId
    attempt_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxTimeoutPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    deadlines: tuple[SandboxDeadline, ...]
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            CANCELLATION_FORMAT,
            self.attempt_id,
            self.attempt_fingerprint,
            self.policy_id,
            self.policy_fingerprint,
            self.deadlines,
        )

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "deadline_set.occurred_at_invalid")
        if self.deadlines != tuple(sorted(self.deadlines, key=lambda item: item.kind.value)) or len(
            {item.kind for item in self.deadlines}
        ) != len(self.deadlines):
            raise InvalidCancellation("deadline_set.not_canonical")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.deadline_set_fingerprint:
            raise InvalidCancellation("deadline_set.fingerprint_mismatch")
        if derive_identity(SandboxDeadlineSetId, expected) != self.deadline_set_id:
            raise InvalidCancellation("deadline_set.identity_mismatch")

    @classmethod
    def create(
        cls,
        attempt: SandboxExecutionAttempt,
        policy: SandboxTimeoutPolicy,
        deadlines: tuple[SandboxDeadline, ...],
        *,
        occurred_at: datetime,
    ) -> SandboxDeadlineSet:
        ordered = tuple(sorted(deadlines, key=lambda item: item.kind.value))
        kinds = {item.kind for item in ordered}
        if not set(policy.required_deadlines).issubset(kinds):
            raise InvalidCancellation("deadline_set.required_deadline_absent")
        semantic = (
            CANCELLATION_FORMAT,
            attempt.attempt_id,
            attempt.attempt_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            ordered,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic)
        identity = derive_identity(SandboxDeadlineSetId, fingerprint)
        return cls(
            SandboxDeadlineSetId(identity.value),
            fingerprint,
            attempt.attempt_id,
            attempt.attempt_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            ordered,
            occurred_at,
        )


@dataclass(frozen=True, slots=True)
class SandboxDeadlineEvaluation:
    evaluated_at: datetime
    expired: tuple[SandboxDeadlineKind, ...]
    pending: tuple[SandboxDeadlineKind, ...]

    def __post_init__(self) -> None:
        _aware(self.evaluated_at, "deadline_evaluation.timestamp_invalid")
        for values in (self.expired, self.pending):
            if values != tuple(sorted(set(values), key=lambda item: item.value)):
                raise InvalidCancellation("deadline_evaluation.not_canonical")
        if set(self.expired) & set(self.pending):
            raise InvalidCancellation("deadline_evaluation.overlap")


@dataclass(frozen=True, slots=True)
class SandboxCancellationRequest:
    attempt_id: SandboxAttemptId
    attempt_fingerprint: SandboxArtifactFingerprint
    actor_ref: OpaqueReference
    purpose: str
    reason_code: str
    policy_id: SandboxTimeoutPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    deadline_set_id: SandboxDeadlineSetId
    deadline_set_fingerprint: SandboxArtifactFingerprint
    occurred_at: datetime

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "request.occurred_at_invalid")
        _codes((self.reason_code,), "request.reason_invalid")
        if (
            not self.purpose
            or len(self.purpose) > 128
            or any(marker in self.purpose.lower() for marker in ("secret=", "token=", "password="))
        ):
            raise InvalidCancellation("request.purpose_invalid")

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.attempt_id,
            self.attempt_fingerprint,
            self.actor_ref,
            self.purpose,
            self.reason_code,
            self.policy_id,
            self.policy_fingerprint,
            self.deadline_set_id,
            self.deadline_set_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class SandboxTerminationEscalation:
    stages: tuple[SandboxTerminationEscalationStage, ...]
    applied_stage: SandboxTerminationEscalationStage

    def __post_init__(self) -> None:
        if not self.stages or self.applied_stage not in self.stages:
            raise InvalidCancellation("escalation.stage_invalid")
        canonical = (
            SandboxTerminationEscalationStage.COOPERATIVE_CANCELLATION,
            SandboxTerminationEscalationStage.GRACEFUL_TERMINATION,
            SandboxTerminationEscalationStage.FORCED_TERMINATION,
            SandboxTerminationEscalationStage.MANUAL_INTERVENTION,
        )
        if self.stages != tuple(item for item in canonical if item in self.stages):
            raise InvalidCancellation("escalation.stages_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxCancellationDecision:
    decision_id: SandboxCancellationDecisionId
    decision_fingerprint: SandboxArtifactFingerprint
    attempt_id: SandboxAttemptId
    attempt_fingerprint: SandboxArtifactFingerprint
    classification: SandboxCancellationClassification
    state: SandboxCancellationState
    escalation: SandboxTerminationEscalation
    policy_id: SandboxTimeoutPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    deadline_set_fingerprint: SandboxArtifactFingerprint
    cause_fingerprint: SandboxArtifactFingerprint
    diagnostics: tuple[str, ...]
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            CANCELLATION_FORMAT,
            self.attempt_id,
            self.attempt_fingerprint,
            self.classification,
            self.state,
            self.escalation,
            self.policy_id,
            self.policy_fingerprint,
            self.deadline_set_fingerprint,
            self.cause_fingerprint,
            self.diagnostics,
        )

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "decision.occurred_at_invalid")
        _codes(self.diagnostics, "decision.diagnostics_not_canonical")
        if self.state is not SandboxCancellationState.REQUESTED:
            raise InvalidCancellation("decision.initial_state_invalid")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.decision_fingerprint:
            raise InvalidCancellation("decision.fingerprint_mismatch")
        if derive_identity(SandboxCancellationDecisionId, expected) != self.decision_id:
            raise InvalidCancellation("decision.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxCancellationEvent:
    sequence: int
    kind: SandboxCancellationEventKind
    decision_id: SandboxCancellationDecisionId
    escalation_stage: SandboxTerminationEscalationStage | None = None
    termination_proof: SandboxTerminationProof | None = None
    diagnostics: tuple[str, ...] = ()
    occurred_at: datetime | None = None

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.sequence,
            self.kind,
            self.decision_id,
            self.escalation_stage,
            (
                self.termination_proof.proof_id,
                self.termination_proof.proof_fingerprint,
            )
            if self.termination_proof is not None
            else None,
            self.diagnostics,
        )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence <= 0
        ):
            raise InvalidCancellation("event.sequence_invalid")
        if self.occurred_at is not None:
            _aware(self.occurred_at, "event.occurred_at_invalid")
        _codes(self.diagnostics, "event.diagnostics_not_canonical")
        if (
            self.kind
            in {
                SandboxCancellationEventKind.TERMINATION_VERIFIED,
                SandboxCancellationEventKind.TERMINATION_UNVERIFIED,
            }
            and self.termination_proof is None
        ):
            raise InvalidCancellation("event.proof_required")
        if (
            self.kind
            in {
                SandboxCancellationEventKind.TERMINATION_INITIATED,
                SandboxCancellationEventKind.ESCALATED,
            }
            and self.escalation_stage is None
        ):
            raise InvalidCancellation("event.escalation_required")


@dataclass(frozen=True, slots=True)
class SandboxCancellationResult:
    result_id: SandboxCancellationResultId
    result_fingerprint: SandboxArtifactFingerprint
    decision_id: SandboxCancellationDecisionId
    decision_fingerprint: SandboxArtifactFingerprint
    attempt_id: SandboxAttemptId
    attempt_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxTimeoutPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    deadline_set_fingerprint: SandboxArtifactFingerprint
    classification: SandboxCancellationClassification
    final_state: SandboxCancellationState
    escalation: SandboxTerminationEscalation
    termination_proof_ref: SandboxTerminationProofId | None
    descendants_status: SandboxDescendantsStatus
    cleanup_required: bool
    diagnostics: tuple[str, ...]
    event_fingerprint: SandboxArtifactFingerprint
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            CANCELLATION_FORMAT,
            self.decision_id,
            self.decision_fingerprint,
            self.attempt_id,
            self.attempt_fingerprint,
            self.policy_id,
            self.policy_fingerprint,
            self.deadline_set_fingerprint,
            self.classification,
            self.final_state,
            self.escalation,
            self.termination_proof_ref,
            self.descendants_status,
            self.cleanup_required,
            self.diagnostics,
            self.event_fingerprint,
        )

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "result.occurred_at_invalid")
        _codes(self.diagnostics, "result.diagnostics_not_canonical")
        if self.final_state is SandboxCancellationState.COMPLETED and (
            self.termination_proof_ref is None
            or self.descendants_status is not SandboxDescendantsStatus.CLEAR
        ):
            raise InvalidCancellation("result.completed_without_termination")
        if self.final_state is SandboxCancellationState.TERMINATION_UNVERIFIED and (
            not self.cleanup_required
            and self.escalation.applied_stage
            is not SandboxTerminationEscalationStage.MANUAL_INTERVENTION
        ):
            raise InvalidCancellation("result.unverified_without_recovery")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.result_fingerprint:
            raise InvalidCancellation("result.fingerprint_mismatch")
        if derive_identity(SandboxCancellationResultId, expected) != self.result_id:
            raise InvalidCancellation("result.identity_mismatch")


class SandboxDeadlineService:
    @staticmethod
    def evaluate(
        deadlines: SandboxDeadlineSet, *, evaluated_at: datetime
    ) -> SandboxDeadlineEvaluation:
        _aware(evaluated_at, "deadline_evaluation.timestamp_invalid")
        expired = tuple(
            sorted(
                (item.kind for item in deadlines.deadlines if evaluated_at >= item.expires_at),
                key=lambda item: item.value,
            )
        )
        pending = tuple(
            sorted(
                (item.kind for item in deadlines.deadlines if evaluated_at < item.expires_at),
                key=lambda item: item.value,
            )
        )
        return SandboxDeadlineEvaluation(evaluated_at, expired, pending)


class SandboxCancellationDecisionService:
    @staticmethod
    def decide(
        attempt: SandboxExecutionAttempt,
        policy: SandboxTimeoutPolicy,
        deadlines: SandboxDeadlineSet,
        request: SandboxCancellationRequest | None,
        evaluation: SandboxDeadlineEvaluation,
        *,
        occurred_at: datetime,
    ) -> SandboxCancellationDecision:
        if (
            deadlines.attempt_id != attempt.attempt_id
            or deadlines.attempt_fingerprint != attempt.attempt_fingerprint
        ):
            raise InvalidCancellation("binding.deadline_attempt_mismatch")
        if (
            deadlines.policy_id != policy.policy_id
            or deadlines.policy_fingerprint != policy.policy_fingerprint
        ):
            raise InvalidCancellation("binding.deadline_policy_mismatch")
        if request is not None and request.semantic_content()[:2] != (
            attempt.attempt_id,
            attempt.attempt_fingerprint,
        ):
            raise InvalidCancellation("binding.request_attempt_mismatch")
        if request is not None and (
            request.policy_id != policy.policy_id
            or request.policy_fingerprint != policy.policy_fingerprint
            or request.deadline_set_id != deadlines.deadline_set_id
            or request.deadline_set_fingerprint != deadlines.deadline_set_fingerprint
        ):
            raise InvalidCancellation("binding.request_policy_mismatch")
        if evaluation != SandboxDeadlineService.evaluate(
            deadlines,
            evaluated_at=evaluation.evaluated_at,
        ):
            raise InvalidCancellation("binding.deadline_evaluation_mismatch")
        if request is None and not evaluation.expired:
            raise InvalidCancellation("decision.no_cancellation_cause")
        priority = (
            (SandboxDeadlineKind.CLEANUP, SandboxCancellationClassification.CLEANUP_TIMEOUT),
            (
                SandboxDeadlineKind.TERMINATION_GRACE,
                SandboxCancellationClassification.TERMINATION_GRACE_TIMEOUT,
            ),
            (SandboxDeadlineKind.WALL_CLOCK, SandboxCancellationClassification.WALL_CLOCK_TIMEOUT),
            (SandboxDeadlineKind.IDLE, SandboxCancellationClassification.IDLE_TIMEOUT),
            (SandboxDeadlineKind.STARTUP, SandboxCancellationClassification.STARTUP_TIMEOUT),
        )
        classification = SandboxCancellationClassification.REQUESTED
        if request is None:
            classification = next(value for kind, value in priority if kind in evaluation.expired)
        escalation = SandboxTerminationEscalation(
            policy.escalation_order,
            policy.escalation_order[0],
        )
        diagnostics = (
            (f"deadline.{classification.value}",)
            if request is None
            else ("cancellation.requested",)
        )
        cause_fingerprint = SandboxArtifactFingerprint.from_content(
            request.semantic_content()
            if request is not None
            else (deadlines.deadline_set_fingerprint, classification)
        )
        semantic = (
            CANCELLATION_FORMAT,
            attempt.attempt_id,
            attempt.attempt_fingerprint,
            classification,
            SandboxCancellationState.REQUESTED,
            escalation,
            policy.policy_id,
            policy.policy_fingerprint,
            deadlines.deadline_set_fingerprint,
            cause_fingerprint,
            diagnostics,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic)
        identity = derive_identity(SandboxCancellationDecisionId, fingerprint)
        return SandboxCancellationDecision(
            SandboxCancellationDecisionId(identity.value),
            fingerprint,
            attempt.attempt_id,
            attempt.attempt_fingerprint,
            classification,
            SandboxCancellationState.REQUESTED,
            escalation,
            policy.policy_id,
            policy.policy_fingerprint,
            deadlines.deadline_set_fingerprint,
            cause_fingerprint,
            diagnostics,
            occurred_at,
        )


class SandboxTerminationEscalationService:
    @staticmethod
    def advance(
        policy: SandboxTimeoutPolicy,
        current: SandboxTerminationEscalation,
    ) -> SandboxTerminationEscalation:
        if current.stages != policy.escalation_order:
            raise InvalidCancellation("escalation.policy_mismatch")
        index = current.stages.index(current.applied_stage)
        if index + 1 >= len(current.stages):
            raise InvalidCancellation("escalation.exhausted")
        next_stage = current.stages[index + 1]
        if (
            next_stage is SandboxTerminationEscalationStage.FORCED_TERMINATION
            and not policy.forced_termination_allowed
        ):
            raise InvalidCancellation("escalation.forced_not_allowed")
        return SandboxTerminationEscalation(current.stages, next_stage)


class SandboxCancellationService:
    @classmethod
    def reduce(
        cls,
        decision: SandboxCancellationDecision,
        policy: SandboxTimeoutPolicy,
        events: tuple[SandboxCancellationEvent, ...],
        *,
        occurred_at: datetime,
    ) -> SandboxCancellationResult:
        if (
            decision.policy_id != policy.policy_id
            or decision.policy_fingerprint != policy.policy_fingerprint
        ):
            raise InvalidCancellation("binding.decision_policy_mismatch")
        if tuple(item.sequence for item in events) != tuple(range(1, len(events) + 1)):
            raise InvalidCancellation("events.sequence_invalid")
        if any(item.decision_id != decision.decision_id for item in events):
            raise InvalidCancellation("events.decision_mismatch")
        if not events or events[0].kind is not SandboxCancellationEventKind.CANCELLATION_REQUESTED:
            raise InvalidCancellation("events.request_required")
        seen: set[
            tuple[
                SandboxCancellationEventKind,
                SandboxTerminationEscalationStage | None,
            ]
        ] = set()
        state = SandboxCancellationState.REQUESTED
        escalation = decision.escalation
        proof: SandboxTerminationProof | None = None
        diagnostics = set(decision.diagnostics)
        for event in events:
            event_key = (event.kind, event.escalation_stage)
            if event_key in seen:
                raise InvalidCancellation(
                    ("events.duplicate", f"events.{event.kind.value}_duplicate")
                )
            seen.add(event_key)
            if (
                event.termination_proof is not None
                and event.termination_proof.attempt_id != decision.attempt_id
            ):
                raise InvalidCancellation("events.proof_attempt_mismatch")
            state, escalation, proof = cls._transition(state, escalation, proof, policy, event)
            diagnostics.update(event.diagnostics)
        if state not in {
            SandboxCancellationState.COMPLETED,
            SandboxCancellationState.TERMINATION_UNVERIFIED,
            SandboxCancellationState.MANUAL_INTERVENTION,
        }:
            raise InvalidCancellation("events.result_incomplete")
        descendants = SandboxDescendantsStatus.UNKNOWN
        proof_ref = None
        if proof is not None:
            proof_ref = proof.proof_id
            descendants = (
                SandboxDescendantsStatus.CLEAR
                if proof.no_active_descendants
                else SandboxDescendantsStatus.ACTIVE
            )
        if (
            state is SandboxCancellationState.COMPLETED
            and descendants is not SandboxDescendantsStatus.CLEAR
        ):
            raise InvalidCancellation("events.active_descendants")
        cleanup = (
            state is not SandboxCancellationState.COMPLETED
            and policy.cleanup_required_when_unverified
        )
        event_fp = SandboxArtifactFingerprint.from_content(
            tuple(item.semantic_content() for item in events)
        )
        ordered_diagnostics = tuple(sorted(diagnostics))
        _codes(ordered_diagnostics, "result.diagnostics_not_canonical")
        semantic = (
            CANCELLATION_FORMAT,
            decision.decision_id,
            decision.decision_fingerprint,
            decision.attempt_id,
            decision.attempt_fingerprint,
            decision.policy_id,
            decision.policy_fingerprint,
            decision.deadline_set_fingerprint,
            decision.classification,
            state,
            escalation,
            proof_ref,
            descendants,
            cleanup,
            ordered_diagnostics,
            event_fp,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic)
        identity = derive_identity(SandboxCancellationResultId, fingerprint)
        return SandboxCancellationResult(
            SandboxCancellationResultId(identity.value),
            fingerprint,
            decision.decision_id,
            decision.decision_fingerprint,
            decision.attempt_id,
            decision.attempt_fingerprint,
            decision.policy_id,
            decision.policy_fingerprint,
            decision.deadline_set_fingerprint,
            decision.classification,
            state,
            escalation,
            proof_ref,
            descendants,
            cleanup,
            ordered_diagnostics,
            event_fp,
            occurred_at,
        )

    @staticmethod
    def _transition(
        state: SandboxCancellationState,
        escalation: SandboxTerminationEscalation,
        proof: SandboxTerminationProof | None,
        policy: SandboxTimeoutPolicy,
        event: SandboxCancellationEvent,
    ) -> tuple[
        SandboxCancellationState, SandboxTerminationEscalation, SandboxTerminationProof | None
    ]:
        kind = event.kind
        if (
            state is SandboxCancellationState.REQUESTED
            and kind is SandboxCancellationEventKind.CANCELLATION_REQUESTED
        ):
            return state, escalation, proof
        if (
            state is SandboxCancellationState.REQUESTED
            and kind is SandboxCancellationEventKind.CANCELLATION_ACKNOWLEDGED
        ):
            return SandboxCancellationState.ACKNOWLEDGED, escalation, proof
        if (
            state is SandboxCancellationState.REQUESTED
            and not policy.acknowledgement_required
            and kind is SandboxCancellationEventKind.TERMINATION_REQUESTED
        ) or (
            state is SandboxCancellationState.ACKNOWLEDGED
            and kind is SandboxCancellationEventKind.TERMINATION_REQUESTED
        ):
            return SandboxCancellationState.TERMINATION_REQUESTED, escalation, proof
        if (
            state is SandboxCancellationState.TERMINATION_REQUESTED
            and kind is SandboxCancellationEventKind.TERMINATION_INITIATED
        ):
            if event.escalation_stage != escalation.applied_stage:
                raise InvalidCancellation("events.escalation_stage_mismatch")
            return SandboxCancellationState.TERMINATION_INITIATED, escalation, proof
        if (
            state is SandboxCancellationState.TERMINATION_INITIATED
            and kind is SandboxCancellationEventKind.ESCALATED
        ):
            advanced = SandboxTerminationEscalationService.advance(policy, escalation)
            if event.escalation_stage != advanced.applied_stage:
                raise InvalidCancellation("events.escalation_stage_mismatch")
            if advanced.applied_stage is SandboxTerminationEscalationStage.MANUAL_INTERVENTION:
                return SandboxCancellationState.MANUAL_INTERVENTION, advanced, proof
            return state, advanced, proof
        if (
            state is SandboxCancellationState.TERMINATION_INITIATED
            and kind is SandboxCancellationEventKind.TERMINATION_VERIFIED
        ):
            assert event.termination_proof is not None
            if (
                event.termination_proof.outcome
                is not SandboxTerminationVerificationOutcome.VERIFIED
            ):
                raise InvalidCancellation("events.proof_unverified")
            return (
                SandboxCancellationState.TERMINATION_VERIFIED,
                escalation,
                event.termination_proof,
            )
        if (
            state is SandboxCancellationState.TERMINATION_INITIATED
            and kind is SandboxCancellationEventKind.TERMINATION_UNVERIFIED
        ):
            return (
                SandboxCancellationState.TERMINATION_UNVERIFIED,
                escalation,
                event.termination_proof,
            )
        if (
            state is SandboxCancellationState.TERMINATION_VERIFIED
            and kind is SandboxCancellationEventKind.CANCELLATION_COMPLETED
        ):
            return SandboxCancellationState.COMPLETED, escalation, proof
        raise InvalidCancellation(("events.out_of_order", f"events.{kind.value}_invalid"))
