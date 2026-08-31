"""Deterministic event reduction and abstract runtime supervision ports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from .capability_grants import SandboxCapabilityGrantSet
from .errors import InvalidRuntimeSupervision
from .execution_plan import SandboxExecutionPlan
from .filesystem_boundary import SandboxFilesystemSpecification
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxAttemptId,
    SandboxIsolationProfileId,
    SandboxMaterializationId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxSupervisionResultId,
    SandboxTerminationProofId,
    derive_identity,
)
from .materialization import (
    SandboxMaterializationPlan,
    SandboxMaterializationRecord,
    SandboxMaterializationVerificationOutcome,
)
from .network_boundary import SandboxNetworkSpecification
from .process_boundary import SandboxProcessEnforcement, SandboxProcessSpecification
from .resource_limits import (
    SandboxResourceDimension,
    SandboxResourceScope,
    SandboxResourceSpecification,
    SandboxResourceUnit,
)
from .secrets_boundary import SandboxSecretLeaseSpecification
from .states import SandboxCleanupState

SUPERVISION_FORMAT = "sandbox-runtime-supervision-v1"
_CODE = re.compile(r"[a-z][a-z0-9_.-]{0,95}")


def _aware(value: datetime, code: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidRuntimeSupervision(code)


def _codes(values: tuple[str, ...], code: str) -> None:
    if values != tuple(sorted(set(values))) or any(
        _CODE.fullmatch(value) is None for value in values
    ):
        raise InvalidRuntimeSupervision(code)


class SandboxSupervisionState(StrEnum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    TERMINATION_REQUESTED = "termination_requested"
    TERMINATING = "terminating"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"
    TERMINATION_UNVERIFIED = "termination_unverified"
    CLEANUP_REQUIRED = "cleanup_required"
    MANUAL_INTERVENTION = "manual_intervention"


class SandboxRuntimeEventKind(StrEnum):
    START_REQUESTED = "start_requested"
    PROCESS_CREATED = "process_created"
    PROCESS_START_FAILED = "process_start_failed"
    RUNTIME_OBSERVED = "runtime_observed"
    LIMIT_TRIGGERED = "limit_triggered"
    TERMINATION_REQUESTED = "termination_requested"
    DESCENDANT_OBSERVED = "descendant_observed"
    TERMINATION_CONFIRMED = "termination_confirmed"
    TERMINATION_UNVERIFIED = "termination_unverified"
    RUNTIME_EXITED = "runtime_exited"
    CLEANUP_REQUIRED = "cleanup_required"


class SandboxTerminationMethod(StrEnum):
    BOUNDARY_CLOSE = "boundary_close"
    DRIVER_TERMINATE = "driver_terminate"
    RUNTIME_EXIT = "runtime_exit"


class SandboxTerminationVerificationOutcome(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class SandboxExitClassification(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    START_FAILED = "start_failed"
    LIMIT_TRIGGERED = "limit_triggered"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SandboxRuntimeDriverCapabilityFact:
    driver_ref: OpaqueReference
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    isolation_profile_id: SandboxIsolationProfileId
    supported_enforcements: tuple[SandboxProcessEnforcement, ...]
    available: bool
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        _aware(self.valid_from, "driver.valid_from_invalid")
        _aware(self.valid_until, "driver.valid_until_invalid")
        if self.valid_until < self.valid_from:
            raise InvalidRuntimeSupervision("driver.validity_invalid")
        if self.supported_enforcements != tuple(
            sorted(set(self.supported_enforcements), key=lambda item: item.value)
        ):
            raise InvalidRuntimeSupervision("driver.enforcements_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxExecutionStartRequest:
    plan: SandboxExecutionPlan
    materialization_plan: SandboxMaterializationPlan
    materialization: SandboxMaterializationRecord
    capabilities: SandboxCapabilityGrantSet
    filesystem: SandboxFilesystemSpecification
    network: SandboxNetworkSpecification
    process: SandboxProcessSpecification
    resources: SandboxResourceSpecification
    secrets: SandboxSecretLeaseSpecification | None
    driver_fact: SandboxRuntimeDriverCapabilityFact
    attempt_ref: OpaqueReference
    evaluated_at: datetime
    occurred_at: datetime

    def __post_init__(self) -> None:
        _aware(self.evaluated_at, "request.evaluated_at_invalid")
        _aware(self.occurred_at, "request.occurred_at_invalid")


@dataclass(frozen=True, slots=True)
class SandboxExecutionAttempt:
    attempt_id: SandboxAttemptId
    attempt_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    materialization_id: SandboxMaterializationId
    materialization_fingerprint: SandboxArtifactFingerprint
    process_specification_fingerprint: SandboxArtifactFingerprint
    driver_ref: OpaqueReference
    attempt_ref: OpaqueReference
    state: SandboxSupervisionState
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            SUPERVISION_FORMAT,
            self.plan_id,
            self.plan_fingerprint,
            self.materialization_id,
            self.materialization_fingerprint,
            self.process_specification_fingerprint,
            self.driver_ref,
            self.attempt_ref,
            self.state,
        )

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "attempt.occurred_at_invalid")
        if self.state is not SandboxSupervisionState.PENDING:
            raise InvalidRuntimeSupervision("attempt.initial_state_invalid")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.attempt_fingerprint:
            raise InvalidRuntimeSupervision("attempt.fingerprint_mismatch")
        if derive_identity(SandboxAttemptId, expected) != self.attempt_id:
            raise InvalidRuntimeSupervision("attempt.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxRuntimeObservation:
    process_ref: OpaqueReference
    alive: bool
    descendant_refs: tuple[OpaqueReference, ...]
    exit_classification: SandboxExitClassification | None
    observation_available: bool

    def __post_init__(self) -> None:
        if self.descendant_refs != tuple(
            sorted(set(self.descendant_refs), key=lambda item: item.value)
        ):
            raise InvalidRuntimeSupervision("observation.descendants_not_canonical")
        if self.alive and self.exit_classification is not None:
            raise InvalidRuntimeSupervision("observation.exit_while_alive")


@dataclass(frozen=True, slots=True)
class SandboxRuntimeMetric:
    dimension: SandboxResourceDimension
    value: int
    unit: SandboxResourceUnit
    scope: SandboxResourceScope

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool) or self.value < 0:
            raise InvalidRuntimeSupervision("metric.value_invalid")


@dataclass(frozen=True, slots=True)
class SandboxTerminationProof:
    proof_id: SandboxTerminationProofId
    proof_fingerprint: SandboxArtifactFingerprint
    attempt_id: SandboxAttemptId
    initial_process_ref: OpaqueReference
    descendant_refs: tuple[OpaqueReference, ...]
    method: SandboxTerminationMethod
    driver_ref: OpaqueReference
    driver_capabilities: tuple[SandboxProcessEnforcement, ...]
    no_active_descendants: bool
    outcome: SandboxTerminationVerificationOutcome
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            SUPERVISION_FORMAT,
            self.attempt_id,
            self.initial_process_ref,
            self.descendant_refs,
            self.method,
            self.driver_ref,
            self.driver_capabilities,
            self.no_active_descendants,
            self.outcome,
        )

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "proof.occurred_at_invalid")
        if self.descendant_refs != tuple(
            sorted(set(self.descendant_refs), key=lambda item: item.value)
        ):
            raise InvalidRuntimeSupervision("proof.descendants_not_canonical")
        if self.driver_capabilities != tuple(
            sorted(set(self.driver_capabilities), key=lambda item: item.value)
        ):
            raise InvalidRuntimeSupervision("proof.capabilities_not_canonical")
        if (
            self.outcome is SandboxTerminationVerificationOutcome.VERIFIED
            and not self.no_active_descendants
        ):
            raise InvalidRuntimeSupervision("proof.active_descendants")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.proof_fingerprint:
            raise InvalidRuntimeSupervision("proof.fingerprint_mismatch")
        if derive_identity(SandboxTerminationProofId, expected) != self.proof_id:
            raise InvalidRuntimeSupervision("proof.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxRuntimeEvent:
    sequence: int
    kind: SandboxRuntimeEventKind
    attempt_id: SandboxAttemptId
    observation: SandboxRuntimeObservation | None = None
    termination_proof: SandboxTerminationProof | None = None
    violations: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    occurred_at: datetime | None = None

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.sequence,
            self.kind,
            self.attempt_id,
            self.observation,
            (
                self.termination_proof.proof_id,
                self.termination_proof.proof_fingerprint,
            )
            if self.termination_proof is not None
            else None,
            self.violations,
            self.diagnostics,
        )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence <= 0
        ):
            raise InvalidRuntimeSupervision("event.sequence_invalid")
        if self.occurred_at is not None:
            _aware(self.occurred_at, "event.occurred_at_invalid")
        _codes(self.violations, "event.violations_not_canonical")
        _codes(self.diagnostics, "event.diagnostics_not_canonical")
        if self.kind is SandboxRuntimeEventKind.RUNTIME_OBSERVED and self.observation is None:
            raise InvalidRuntimeSupervision("event.observation_required")
        if (
            self.kind
            in {
                SandboxRuntimeEventKind.TERMINATION_CONFIRMED,
                SandboxRuntimeEventKind.TERMINATION_UNVERIFIED,
            }
            and self.termination_proof is None
        ):
            raise InvalidRuntimeSupervision("event.proof_required")


@dataclass(frozen=True, slots=True)
class SandboxSupervisionResult:
    result_id: SandboxSupervisionResultId
    result_fingerprint: SandboxArtifactFingerprint
    attempt_id: SandboxAttemptId
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    materialization_id: SandboxMaterializationId
    materialization_fingerprint: SandboxArtifactFingerprint
    final_state: SandboxSupervisionState
    exit_classification: SandboxExitClassification | None
    termination_proof_ref: SandboxTerminationProofId | None
    resource_usage: tuple[SandboxRuntimeMetric, ...]
    violations: tuple[str, ...]
    diagnostics: tuple[str, ...]
    cleanup_required: bool
    event_fingerprint: SandboxArtifactFingerprint
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            SUPERVISION_FORMAT,
            self.attempt_id,
            self.plan_id,
            self.plan_fingerprint,
            self.materialization_id,
            self.materialization_fingerprint,
            self.final_state,
            self.exit_classification,
            self.termination_proof_ref,
            self.resource_usage,
            self.violations,
            self.diagnostics,
            self.cleanup_required,
            self.event_fingerprint,
        )

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "result.occurred_at_invalid")
        _codes(self.violations, "result.violations_not_canonical")
        _codes(self.diagnostics, "result.diagnostics_not_canonical")
        if self.resource_usage != tuple(
            sorted(
                self.resource_usage,
                key=lambda item: (
                    item.dimension.value,
                    item.scope.value,
                    item.unit.value,
                ),
            )
        ):
            raise InvalidRuntimeSupervision("result.metrics_not_canonical")
        if (
            self.final_state
            in {
                SandboxSupervisionState.COMPLETED,
                SandboxSupervisionState.TERMINATED,
            }
            and self.termination_proof_ref is None
        ):
            raise InvalidRuntimeSupervision("result.proof_required")
        if (
            self.final_state is SandboxSupervisionState.TERMINATION_UNVERIFIED
            and self.exit_classification is SandboxExitClassification.SUCCEEDED
        ):
            raise InvalidRuntimeSupervision("result.unverified_cannot_succeed")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.result_fingerprint:
            raise InvalidRuntimeSupervision("result.fingerprint_mismatch")
        if derive_identity(SandboxSupervisionResultId, expected) != self.result_id:
            raise InvalidRuntimeSupervision("result.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxRuntimeStartCommand:
    attempt: SandboxExecutionAttempt
    process: SandboxProcessSpecification
    workspace_ref: OpaqueReference


class SandboxWorkloadStartPort(Protocol):
    def start(self, command: SandboxRuntimeStartCommand) -> SandboxRuntimeEvent: ...


class SandboxRuntimeObservationPort(Protocol):
    def observe(self, attempt: SandboxExecutionAttempt) -> tuple[SandboxRuntimeEvent, ...]: ...

    def observe_descendants(
        self, attempt: SandboxExecutionAttempt
    ) -> tuple[SandboxRuntimeEvent, ...]: ...


class SandboxRuntimeTerminationPort(Protocol):
    def request_termination(self, attempt: SandboxExecutionAttempt) -> SandboxRuntimeEvent: ...

    def confirm_termination(self, attempt: SandboxExecutionAttempt) -> SandboxRuntimeEvent: ...


class SandboxRuntimeMetricsPort(Protocol):
    def collect(self, attempt: SandboxExecutionAttempt) -> tuple[SandboxRuntimeMetric, ...]: ...


class SandboxRuntimeIsolationPort(Protocol):
    def verify(self, attempt: SandboxExecutionAttempt) -> tuple[str, ...]: ...


class SandboxRuntimeSupervisionService:
    """Create attempts and reduce canonical event streams without operational I/O."""

    @classmethod
    def create_attempt(cls, request: SandboxExecutionStartRequest) -> SandboxExecutionAttempt:
        cls.validate_bindings(request)
        semantic = (
            SUPERVISION_FORMAT,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.materialization.materialization_id,
            request.materialization.materialization_fingerprint,
            request.process.specification_fingerprint,
            request.driver_fact.driver_ref,
            request.attempt_ref,
            SandboxSupervisionState.PENDING,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic)
        identity = derive_identity(SandboxAttemptId, fingerprint)
        return SandboxExecutionAttempt(
            SandboxAttemptId(identity.value),
            fingerprint,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.materialization.materialization_id,
            request.materialization.materialization_fingerprint,
            request.process.specification_fingerprint,
            request.driver_fact.driver_ref,
            request.attempt_ref,
            SandboxSupervisionState.PENDING,
            request.occurred_at,
        )

    @staticmethod
    def validate_bindings(request: SandboxExecutionStartRequest) -> None:
        plan = request.plan
        diagnostics: list[str] = []
        for name, candidate_id, candidate_fp in (
            (
                "materialization",
                request.materialization.plan_id,
                request.materialization.plan_fingerprint,
            ),
            ("capabilities", request.capabilities.plan_id, request.capabilities.plan_fingerprint),
            ("filesystem", request.filesystem.plan_id, request.filesystem.plan_fingerprint),
            ("network", request.network.plan_id, request.network.plan_fingerprint),
            ("process", request.process.plan_id, request.process.plan_fingerprint),
            ("resources", request.resources.plan_id, request.resources.plan_fingerprint),
            ("driver", request.driver_fact.plan_id, request.driver_fact.plan_fingerprint),
        ):
            if candidate_id != plan.plan_id:
                diagnostics.append(f"binding.{name}_plan_identity_mismatch")
            if candidate_fp != plan.plan_fingerprint:
                diagnostics.append(f"binding.{name}_plan_fingerprint_mismatch")
        if (
            request.materialization.verification.outcome
            is not SandboxMaterializationVerificationOutcome.VERIFIED
        ):
            diagnostics.append("binding.materialization_not_verified")
        if request.materialization.cleanup_state is not SandboxCleanupState.NOT_REQUIRED:
            diagnostics.append("binding.materialization_cleanup_pending")
        if (
            request.materialization.materialization_plan_id
            != request.materialization_plan.materialization_plan_id
            or request.materialization.materialization_plan_fingerprint
            != request.materialization_plan.materialization_plan_fingerprint
        ):
            diagnostics.append("binding.materialization_plan_mismatch")
        for name, actual, expected in (
            (
                "capabilities",
                request.capabilities.grant_set_fingerprint,
                request.materialization_plan.capability_grant_set_fingerprint,
            ),
            (
                "filesystem",
                request.filesystem.specification_fingerprint,
                request.materialization_plan.filesystem_specification_fingerprint,
            ),
            (
                "network",
                request.network.specification_fingerprint,
                request.materialization_plan.network_specification_fingerprint,
            ),
            (
                "process",
                request.process.specification_fingerprint,
                request.materialization_plan.process_specification_fingerprint,
            ),
            (
                "resources",
                request.resources.specification_fingerprint,
                request.materialization_plan.resource_specification_fingerprint,
            ),
            (
                "secrets",
                (
                    request.secrets.specification_fingerprint
                    if request.secrets is not None
                    else None
                ),
                request.materialization_plan.secret_specification_fingerprint,
            ),
        ):
            if actual != expected:
                diagnostics.append(f"binding.materialized_{name}_mismatch")
        if (
            request.process.filesystem_specification_fingerprint
            != request.filesystem.specification_fingerprint
        ):
            diagnostics.append("binding.process_filesystem_mismatch")
        if (
            request.process.network_specification_fingerprint
            != request.network.specification_fingerprint
        ):
            diagnostics.append("binding.process_network_mismatch")
        if (
            request.resources.process_specification_fingerprint
            != request.process.specification_fingerprint
        ):
            diagnostics.append("binding.resources_process_mismatch")
        if request.secrets is not None and (
            request.secrets.plan_id != plan.plan_id
            or request.secrets.resource_specification_fingerprint
            != request.resources.specification_fingerprint
        ):
            diagnostics.append("binding.secrets_mismatch")
        if request.driver_fact.isolation_profile_id != plan.isolation_profile_id:
            diagnostics.append("binding.driver_isolation_mismatch")
        if not set(request.process.required_enforcements).issubset(
            request.driver_fact.supported_enforcements
        ):
            diagnostics.append("binding.driver_enforcement_unsupported")
        if not request.driver_fact.available:
            diagnostics.append("binding.driver_unavailable")
        if not (
            request.driver_fact.valid_from
            <= request.evaluated_at
            <= request.driver_fact.valid_until
        ):
            diagnostics.append("binding.driver_stale")
        if diagnostics:
            raise InvalidRuntimeSupervision(tuple(sorted(diagnostics)))

    @classmethod
    def evaluate(
        cls,
        request: SandboxExecutionStartRequest,
        events: tuple[SandboxRuntimeEvent, ...],
        metrics: tuple[SandboxRuntimeMetric, ...] = (),
        isolation_violations: tuple[str, ...] = (),
    ) -> SandboxSupervisionResult:
        attempt = cls.create_attempt(request)
        if tuple(item.sequence for item in events) != tuple(range(1, len(events) + 1)):
            raise InvalidRuntimeSupervision("events.sequence_invalid")
        if any(item.attempt_id != attempt.attempt_id for item in events):
            raise InvalidRuntimeSupervision("events.attempt_mismatch")
        if not events or events[0].kind is not SandboxRuntimeEventKind.START_REQUESTED:
            raise InvalidRuntimeSupervision("events.start_required")
        state = SandboxSupervisionState.PENDING
        created = False
        proof: SandboxTerminationProof | None = None
        exit_kind: SandboxExitClassification | None = None
        violations = set(isolation_violations)
        diagnostics: set[str] = set()
        for event in events:
            state, created, proof, observed_exit = cls._transition(state, created, proof, event)
            exit_kind = observed_exit or exit_kind
            violations.update(event.violations)
            diagnostics.update(event.diagnostics)
        if state in {SandboxSupervisionState.COMPLETED, SandboxSupervisionState.TERMINATED} and (
            proof is None or proof.outcome is not SandboxTerminationVerificationOutcome.VERIFIED
        ):
            raise InvalidRuntimeSupervision("events.proof_required")
        if state is SandboxSupervisionState.TERMINATION_UNVERIFIED:
            exit_kind = SandboxExitClassification.UNKNOWN
        ordered_metrics = tuple(
            sorted(
                metrics, key=lambda item: (item.dimension.value, item.scope.value, item.unit.value)
            )
        )
        ordered_violations = tuple(sorted(set(violations)))
        ordered_diagnostics = tuple(sorted(set(diagnostics)))
        _codes(ordered_violations, "result.violations_not_canonical")
        _codes(ordered_diagnostics, "result.diagnostics_not_canonical")
        event_fp = SandboxArtifactFingerprint.from_content(
            tuple(item.semantic_content() for item in events)
        )
        cleanup = state in {
            SandboxSupervisionState.FAILED,
            SandboxSupervisionState.TIMED_OUT,
            SandboxSupervisionState.CANCELLED,
            SandboxSupervisionState.TERMINATED,
            SandboxSupervisionState.TERMINATION_UNVERIFIED,
            SandboxSupervisionState.CLEANUP_REQUIRED,
            SandboxSupervisionState.MANUAL_INTERVENTION,
        }
        content = (
            SUPERVISION_FORMAT,
            attempt.attempt_id,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.materialization.materialization_id,
            request.materialization.materialization_fingerprint,
            state,
            exit_kind,
            proof.proof_id if proof is not None else None,
            ordered_metrics,
            ordered_violations,
            ordered_diagnostics,
            cleanup,
            event_fp,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxSupervisionResultId, fingerprint)
        return SandboxSupervisionResult(
            SandboxSupervisionResultId(identity.value),
            fingerprint,
            attempt.attempt_id,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.materialization.materialization_id,
            request.materialization.materialization_fingerprint,
            state,
            exit_kind,
            proof.proof_id if proof is not None else None,
            ordered_metrics,
            ordered_violations,
            ordered_diagnostics,
            cleanup,
            event_fp,
            request.occurred_at,
        )

    @staticmethod
    def _transition(
        state: SandboxSupervisionState,
        created: bool,
        proof: SandboxTerminationProof | None,
        event: SandboxRuntimeEvent,
    ) -> tuple[
        SandboxSupervisionState,
        bool,
        SandboxTerminationProof | None,
        SandboxExitClassification | None,
    ]:
        kind = event.kind
        if (
            state is SandboxSupervisionState.PENDING
            and kind is SandboxRuntimeEventKind.START_REQUESTED
        ):
            return SandboxSupervisionState.STARTING, False, proof, None
        if state is SandboxSupervisionState.STARTING:
            if kind is SandboxRuntimeEventKind.PROCESS_CREATED and not created:
                return state, True, proof, None
            if kind is SandboxRuntimeEventKind.PROCESS_START_FAILED and not created:
                return (
                    SandboxSupervisionState.FAILED,
                    False,
                    proof,
                    SandboxExitClassification.START_FAILED,
                )
            if kind is SandboxRuntimeEventKind.RUNTIME_OBSERVED and created:
                assert event.observation is not None
                if event.observation.observation_available and event.observation.alive:
                    return SandboxSupervisionState.RUNNING, True, proof, None
        if state is SandboxSupervisionState.RUNNING:
            if kind is SandboxRuntimeEventKind.RUNTIME_OBSERVED:
                assert event.observation is not None
                if not event.observation.observation_available:
                    return (
                        SandboxSupervisionState.TERMINATION_UNVERIFIED,
                        created,
                        proof,
                        SandboxExitClassification.UNKNOWN,
                    )
                if (
                    not event.observation.alive
                    and event.observation.exit_classification is SandboxExitClassification.TIMED_OUT
                ):
                    return (
                        SandboxSupervisionState.TIMED_OUT,
                        created,
                        proof,
                        SandboxExitClassification.TIMED_OUT,
                    )
                if (
                    not event.observation.alive
                    and event.observation.exit_classification is SandboxExitClassification.CANCELLED
                ):
                    return (
                        SandboxSupervisionState.CANCELLED,
                        created,
                        proof,
                        SandboxExitClassification.CANCELLED,
                    )
                return state, created, proof, None
            if kind in {
                SandboxRuntimeEventKind.DESCENDANT_OBSERVED,
                SandboxRuntimeEventKind.LIMIT_TRIGGERED,
            }:
                return state, created, proof, None
            if kind is SandboxRuntimeEventKind.TERMINATION_REQUESTED:
                return SandboxSupervisionState.TERMINATION_REQUESTED, created, proof, None
            if kind is SandboxRuntimeEventKind.RUNTIME_EXITED:
                if (
                    event.termination_proof is not None
                    and event.termination_proof.outcome
                    is SandboxTerminationVerificationOutcome.VERIFIED
                ):
                    classification = (
                        event.observation.exit_classification
                        if event.observation is not None
                        else SandboxExitClassification.UNKNOWN
                    )
                    return (
                        SandboxSupervisionState.COMPLETED,
                        created,
                        event.termination_proof,
                        classification,
                    )
                return (
                    SandboxSupervisionState.TERMINATION_UNVERIFIED,
                    created,
                    event.termination_proof,
                    SandboxExitClassification.UNKNOWN,
                )
        if (
            state is SandboxSupervisionState.TERMINATION_REQUESTED
            and kind is SandboxRuntimeEventKind.TERMINATION_REQUESTED
        ):
            return SandboxSupervisionState.TERMINATING, created, proof, None
        if state in {
            SandboxSupervisionState.TERMINATION_REQUESTED,
            SandboxSupervisionState.TERMINATING,
            SandboxSupervisionState.TIMED_OUT,
            SandboxSupervisionState.CANCELLED,
        }:
            if kind is SandboxRuntimeEventKind.TERMINATION_REQUESTED:
                return SandboxSupervisionState.TERMINATING, created, proof, None
            if kind is SandboxRuntimeEventKind.TERMINATION_CONFIRMED:
                assert event.termination_proof is not None
                if (
                    event.termination_proof.outcome
                    is SandboxTerminationVerificationOutcome.VERIFIED
                ):
                    return (
                        SandboxSupervisionState.TERMINATED,
                        created,
                        event.termination_proof,
                        SandboxExitClassification.TERMINATED,
                    )
            if kind is SandboxRuntimeEventKind.TERMINATION_UNVERIFIED:
                return (
                    SandboxSupervisionState.TERMINATION_UNVERIFIED,
                    created,
                    event.termination_proof,
                    SandboxExitClassification.UNKNOWN,
                )
        if kind is SandboxRuntimeEventKind.CLEANUP_REQUIRED and state not in {
            SandboxSupervisionState.COMPLETED,
            SandboxSupervisionState.TERMINATED,
        }:
            if "cleanup.failed" in event.violations:
                return SandboxSupervisionState.MANUAL_INTERVENTION, created, proof, None
            return SandboxSupervisionState.CLEANUP_REQUIRED, created, proof, None
        raise InvalidRuntimeSupervision(("events.out_of_order", f"events.{kind.value}_invalid"))


class SandboxRuntimeSupervisionApplicationService:
    """Collect typed port observations, then apply the pure reducer."""

    def __init__(
        self,
        start: SandboxWorkloadStartPort,
        observation: SandboxRuntimeObservationPort,
        termination: SandboxRuntimeTerminationPort,
        metrics: SandboxRuntimeMetricsPort,
        isolation: SandboxRuntimeIsolationPort,
    ) -> None:
        self._start = start
        self._observation = observation
        self._termination = termination
        self._metrics = metrics
        self._isolation = isolation

    def supervise(self, request: SandboxExecutionStartRequest) -> SandboxSupervisionResult:
        attempt = SandboxRuntimeSupervisionService.create_attempt(request)
        events = (
            SandboxRuntimeEvent(
                1,
                SandboxRuntimeEventKind.START_REQUESTED,
                attempt.attempt_id,
                occurred_at=request.occurred_at,
            ),
            self._start.start(
                SandboxRuntimeStartCommand(
                    attempt,
                    request.process,
                    OpaqueReference(f"workspace:{request.materialization.workspace_id.value}"),
                )
            ),
            *self._observation.observe(attempt),
            *self._observation.observe_descendants(attempt),
        )
        if events[-1].kind in {
            SandboxRuntimeEventKind.LIMIT_TRIGGERED,
            SandboxRuntimeEventKind.TERMINATION_REQUESTED,
        }:
            events = (
                *events,
                self._termination.request_termination(attempt),
                self._termination.confirm_termination(attempt),
            )
        return SandboxRuntimeSupervisionService.evaluate(
            request,
            events,
            self._metrics.collect(attempt),
            tuple(sorted(set(self._isolation.verify(attempt)))),
        )
