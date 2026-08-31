"""Reference-only compatibility with the distinct Workers and Missions authorities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from synapse.coding_sessions import (
    CODING_SESSION_INTENT_POLICY_VERSION,
    CodingSessionArtifactReference,
    CodingSessionContract,
    CodingSessionFingerprint,
    CodingSessionIntent,
    CodingSessionIntentCategory,
    CodingSessionLifecycleState,
    CodingSessionRequestedCapability,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
    CodingSessionWorkerAssignmentReference,
    CodingSessionWorkerAttemptReference,
)
from synapse.missions.models import MissionTask, TaskAttempt
from synapse.workers import InboxProcessResult

CODING_SESSION_WORK_COMPATIBILITY_VERSION = "coding-session-work-compatibility-v1"


class CodingSessionWorkRequestKind(str, Enum):
    WORKER_ASSISTANCE = "worker-assistance"
    MISSION_TASK_EXECUTION = "mission-task-execution"
    ATTEMPT_OBSERVATION = "attempt-observation"
    CANCELLATION_RECONCILIATION = "cancellation-reconciliation"


class CodingSessionWorkerReceiptState(str, Enum):
    ASSIGNMENT_CREATED = "assignment-created"
    ATTEMPT_STARTED = "attempt-started"
    ATTEMPT_WAITING = "attempt-waiting"
    ATTEMPT_COMPLETED = "attempt-completed"
    ATTEMPT_FAILED = "attempt-failed"
    ATTEMPT_CANCELLED = "attempt-cancelled"
    ATTEMPT_UNAVAILABLE = "attempt-unavailable"
    ORPHANED = "orphaned"
    UNKNOWN = "unknown"
    LATE_RESULT = "late-result"


class CodingSessionWorkerBindingProjectionState(str, Enum):
    UNASSIGNED = "unassigned"
    REQUESTED = "requested"
    ASSIGNED = "assigned"
    ACTIVE = "active"
    WAITING = "waiting"
    RELEASED = "released"
    ORPHANED = "orphaned"
    UNKNOWN = "unknown"


class CodingSessionWorkDiagnosticCode(str, Enum):
    SESSION_MISMATCH = "session-mismatch"
    INTENT_MISMATCH = "intent-mismatch"
    ACTOR_MISMATCH = "actor-mismatch"
    PROJECT_MISMATCH = "project-mismatch"
    PURPOSE_MISMATCH = "purpose-mismatch"
    CORRELATION_MISMATCH = "correlation-mismatch"
    MISSION_TASK_MISMATCH = "mission-task-mismatch"
    ASSIGNMENT_ATTEMPT_MISMATCH = "assignment-attempt-mismatch"
    BINDING_MISMATCH = "binding-mismatch"
    CAPABILITY_MISMATCH = "capability-mismatch"
    STALE_ASSIGNMENT = "stale-assignment"
    ORPHAN_WORKER = "orphan-worker"
    DUPLICATE_RECEIPT = "duplicate-receipt"
    CONTRADICTORY_OUTCOME = "contradictory-outcome"
    LATE_RESULT = "late-result"
    CAUSAL_REVISION_MISMATCH = "causal-revision-mismatch"
    LINEAGE_GAP = "lineage-gap"
    PRODUCER_VERSION_MISMATCH = "producer-version-mismatch"
    LIFECYCLE_INCOMPATIBLE = "lifecycle-incompatible"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionWorkDiagnostic:
    code: CodingSessionWorkDiagnosticCode
    subject: str = "work-compatibility"


@dataclass(frozen=True, slots=True)
class CodingSessionWorkContext:
    contract: CodingSessionContract
    lifecycle: CodingSessionStateProjection
    intent: CodingSessionIntent
    mission_identity: str | None
    mission_fingerprint: CodingSessionFingerprint | None
    mission_task_identity: str | None
    mission_task_fingerprint: CodingSessionFingerprint | None
    requested_capability: str
    artifact_references: tuple[CodingSessionArtifactReference, ...]
    authorization_references: tuple[CodingSessionArtifactReference, ...]
    policy_id: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class CodingSessionWorkerAssistanceRequest:
    session_identity: str
    intent_identity: str
    actor: str
    project: str
    task: str
    purpose: str
    correlation: str
    requested_capability: str
    repository_binding: tuple[str | None, str | None, str | None]
    artifact_references: tuple[CodingSessionArtifactReference, ...]
    authorization_references: tuple[CodingSessionArtifactReference, ...]
    causal_revision: int
    policy_id: str
    policy_version: str
    worker_selection: None = None
    scheduling_directive: None = None


@dataclass(frozen=True, slots=True)
class CodingSessionMissionTaskExecutionRequest:
    assistance: CodingSessionWorkerAssistanceRequest
    mission_identity: str
    mission_fingerprint: CodingSessionFingerprint
    mission_task_identity: str
    mission_task_fingerprint: CodingSessionFingerprint
    create_mission: bool = False
    mutate_task: bool = False


@dataclass(frozen=True, slots=True)
class CodingSessionAttemptObservationRequest:
    assistance: CodingSessionWorkerAssistanceRequest
    assignment_identity: str
    assignment_fingerprint: CodingSessionFingerprint
    attempt_identity: str
    attempt_fingerprint: CodingSessionFingerprint


@dataclass(frozen=True, slots=True)
class CodingSessionWorkCancellationReconciliationRequest:
    assistance: CodingSessionWorkerAssistanceRequest
    assignment_identity: str
    assignment_fingerprint: CodingSessionFingerprint
    attempt_identity: str | None
    attempt_fingerprint: CodingSessionFingerprint | None
    termination_inferred: bool = False
    session_cancellation_inferred: bool = False


CodingSessionNeutralWorkRequest: TypeAlias = (
    CodingSessionWorkerAssistanceRequest
    | CodingSessionMissionTaskExecutionRequest
    | CodingSessionAttemptObservationRequest
    | CodingSessionWorkCancellationReconciliationRequest
)


@dataclass(frozen=True, slots=True)
class CodingSessionWorkTranslation:
    kind: CodingSessionWorkRequestKind
    request: CodingSessionNeutralWorkRequest | None
    worker_selected: bool
    scheduling_ordered: bool
    execution_started: bool
    mission_created: bool
    diagnostics: tuple[CodingSessionWorkDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionWorkerReceipt:
    producer: str
    producer_version: str
    receipt_identity: str
    receipt_fingerprint: CodingSessionFingerprint
    session_identity: str
    intent_identity: str
    actor: str
    project: str
    purpose: str
    correlation: str
    mission_identity: str | None
    mission_task_identity: str | None
    assignment_identity: str | None
    assignment_fingerprint: CodingSessionFingerprint | None
    attempt_identity: str | None
    attempt_fingerprint: CodingSessionFingerprint | None
    assignment_for_attempt: str | None
    requested_capability: str
    repository_binding: tuple[str | None, str | None, str | None]
    external_reference_fingerprints: tuple[CodingSessionFingerprint, ...]
    state: CodingSessionWorkerReceiptState
    causal_revision: int
    parent_receipt_identity: str | None
    stale: bool = False


@dataclass(frozen=True, slots=True)
class CodingSessionWorkerBindingProjection:
    state: CodingSessionWorkerBindingProjectionState
    assignment_reference: CodingSessionWorkerAssignmentReference | None
    attempt_reference: CodingSessionWorkerAttemptReference | None
    session_lifecycle_changed: bool
    session_completed: bool
    recovery_started: bool
    worker_scheduled: bool
    worker_terminated: bool
    session_cancelled: bool
    reopens_terminal_session: bool
    diagnostics: tuple[CodingSessionWorkDiagnostic, ...]


class CodingSessionWorkersMissionsCompatibilityAdapter:
    """Build neutral references and reconcile facts without invoking either owner."""

    @staticmethod
    def worker_assistance(context: CodingSessionWorkContext) -> CodingSessionWorkTranslation:
        diagnostics = _context_diagnostics(context)
        request = _assistance(context) if not diagnostics else None
        return _translation(CodingSessionWorkRequestKind.WORKER_ASSISTANCE, request, diagnostics)

    @staticmethod
    def mission_task_execution(
        context: CodingSessionWorkContext,
        mission_task: MissionTask,
    ) -> CodingSessionWorkTranslation:
        findings = set(_context_diagnostics(context))
        if (
            context.mission_identity is None
            or context.mission_fingerprint is None
            or context.mission_task_identity is None
            or context.mission_task_fingerprint is None
            or mission_task.mission_id != context.mission_identity
            or mission_task.task_id != context.mission_task_identity
        ):
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.MISSION_TASK_MISMATCH))
        diagnostics = _ordered(findings)
        request = None
        if not diagnostics:
            assert context.mission_identity is not None
            assert context.mission_fingerprint is not None
            assert context.mission_task_identity is not None
            assert context.mission_task_fingerprint is not None
            request = CodingSessionMissionTaskExecutionRequest(
                _assistance(context),
                context.mission_identity,
                context.mission_fingerprint,
                context.mission_task_identity,
                context.mission_task_fingerprint,
            )
        return _translation(CodingSessionWorkRequestKind.MISSION_TASK_EXECUTION, request, diagnostics)

    @staticmethod
    def observe_attempt(
        context: CodingSessionWorkContext,
        *,
        assignment_identity: str,
        assignment_fingerprint: CodingSessionFingerprint,
        attempt: TaskAttempt,
        attempt_fingerprint: CodingSessionFingerprint,
    ) -> CodingSessionWorkTranslation:
        findings = set(_context_diagnostics(context))
        if attempt.mission_id != context.mission_identity or attempt.task_id != context.mission_task_identity:
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.MISSION_TASK_MISMATCH))
        if attempt.metadata.get("assignment_identity") not in {None, assignment_identity}:
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.ASSIGNMENT_ATTEMPT_MISMATCH))
        diagnostics = _ordered(findings)
        request = None if diagnostics else CodingSessionAttemptObservationRequest(
            _assistance(context), assignment_identity, assignment_fingerprint,
            attempt.attempt_id, attempt_fingerprint,
        )
        return _translation(CodingSessionWorkRequestKind.ATTEMPT_OBSERVATION, request, diagnostics)

    @staticmethod
    def cancellation_reconciliation(
        context: CodingSessionWorkContext,
        *,
        assignment_identity: str,
        assignment_fingerprint: CodingSessionFingerprint,
        attempt_identity: str | None = None,
        attempt_fingerprint: CodingSessionFingerprint | None = None,
    ) -> CodingSessionWorkTranslation:
        diagnostics = _context_diagnostics(context, allow_terminal=True)
        request = None if diagnostics else CodingSessionWorkCancellationReconciliationRequest(
            _assistance(context), assignment_identity, assignment_fingerprint,
            attempt_identity, attempt_fingerprint,
        )
        return _translation(CodingSessionWorkRequestKind.CANCELLATION_RECONCILIATION, request, diagnostics)

    @staticmethod
    def project_receipt(
        context: CodingSessionWorkContext,
        receipt: CodingSessionWorkerReceipt,
        *,
        known_receipts: tuple[CodingSessionWorkerReceipt, ...] = (),
    ) -> CodingSessionWorkerBindingProjection:
        findings = set(_context_diagnostics(context, allow_terminal=True))
        expected_binding = _repository_binding(context)
        comparisons = (
            (receipt.session_identity, context.contract.session_identity.value, CodingSessionWorkDiagnosticCode.SESSION_MISMATCH),
            (receipt.intent_identity, context.intent.intent_identity.value, CodingSessionWorkDiagnosticCode.INTENT_MISMATCH),
            (receipt.actor, context.contract.actor.value, CodingSessionWorkDiagnosticCode.ACTOR_MISMATCH),
            (receipt.project, context.contract.project.value, CodingSessionWorkDiagnosticCode.PROJECT_MISMATCH),
            (receipt.purpose, context.contract.purpose.purpose.value, CodingSessionWorkDiagnosticCode.PURPOSE_MISMATCH),
            (receipt.correlation, context.contract.correlation.value, CodingSessionWorkDiagnosticCode.CORRELATION_MISMATCH),
            (receipt.mission_identity, context.mission_identity, CodingSessionWorkDiagnosticCode.MISSION_TASK_MISMATCH),
            (receipt.mission_task_identity, context.mission_task_identity, CodingSessionWorkDiagnosticCode.MISSION_TASK_MISMATCH),
            (receipt.requested_capability, context.requested_capability, CodingSessionWorkDiagnosticCode.CAPABILITY_MISMATCH),
            (receipt.repository_binding, expected_binding, CodingSessionWorkDiagnosticCode.BINDING_MISMATCH),
            (
                receipt.external_reference_fingerprints,
                _external_fingerprints(context),
                CodingSessionWorkDiagnosticCode.BINDING_MISMATCH,
            ),
        )
        for actual, expected, code in comparisons:
            if actual != expected:
                findings.add(CodingSessionWorkDiagnostic(code))
        if receipt.producer not in {"missions", "workers"} or receipt.producer_version != "v1":
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.PRODUCER_VERSION_MISMATCH))
        if receipt.attempt_identity and receipt.assignment_for_attempt != receipt.assignment_identity:
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.ASSIGNMENT_ATTEMPT_MISMATCH))
        if receipt.stale:
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.STALE_ASSIGNMENT))
        if receipt.state is CodingSessionWorkerReceiptState.ORPHANED:
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.ORPHAN_WORKER))
        if receipt.causal_revision > 1 and receipt.parent_receipt_identity is None:
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.LINEAGE_GAP))
        if receipt.causal_revision < context.intent.causal_metadata.revision.value:
            findings.add(
                CodingSessionWorkDiagnostic(
                    CodingSessionWorkDiagnosticCode.CAUSAL_REVISION_MISMATCH
                )
            )
        terminal_states = {
            CodingSessionWorkerReceiptState.ATTEMPT_COMPLETED,
            CodingSessionWorkerReceiptState.ATTEMPT_FAILED,
            CodingSessionWorkerReceiptState.ATTEMPT_CANCELLED,
        }
        for known in known_receipts:
            if known.receipt_identity == receipt.receipt_identity:
                code = CodingSessionWorkDiagnosticCode.DUPLICATE_RECEIPT if known == receipt else CodingSessionWorkDiagnosticCode.CONTRADICTORY_OUTCOME
                findings.add(CodingSessionWorkDiagnostic(code))
            if known.attempt_identity == receipt.attempt_identity and known.state in terminal_states and receipt.state in terminal_states and known.state is not receipt.state:
                findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.CONTRADICTORY_OUTCOME))
            if known.causal_revision == receipt.causal_revision and known.receipt_identity != receipt.receipt_identity:
                findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if context.lifecycle.lifecycle is CodingSessionLifecycleState.TERMINAL or receipt.state is CodingSessionWorkerReceiptState.LATE_RESULT:
            findings.add(CodingSessionWorkDiagnostic(CodingSessionWorkDiagnosticCode.LATE_RESULT))
        diagnostics = _ordered(findings)
        correspondence_failed = any(item.code in _CORRESPONDENCE_FAILURES for item in diagnostics)
        assignment_reference = None
        attempt_reference = None
        if not correspondence_failed and receipt.assignment_identity and receipt.assignment_fingerprint:
            assignment_reference = CodingSessionWorkerAssignmentReference.create(
                receipt.producer, receipt.producer_version, receipt.assignment_identity,
                receipt.assignment_fingerprint,
            )
        if not correspondence_failed and receipt.attempt_identity and receipt.attempt_fingerprint:
            attempt_reference = CodingSessionWorkerAttemptReference.create(
                receipt.producer, receipt.producer_version, receipt.attempt_identity,
                receipt.attempt_fingerprint,
            )
        return CodingSessionWorkerBindingProjection(
            _binding_state(receipt.state), assignment_reference, attempt_reference,
            False, False, False, False, False, False, False, diagnostics,
        )

    @staticmethod
    def inbox_receipt_reference(result: InboxProcessResult) -> CodingSessionArtifactReference:
        """Retain only a producer reference; never copy response/tool payloads."""
        fingerprint = CodingSessionFingerprint.from_content(
            (result.agent_id, result.message_id, result.status)
        )
        return CodingSessionArtifactReference.create(
            "workers", "v1", f"inbox-result:{result.message_id}", fingerprint
        )


def _context_diagnostics(context: CodingSessionWorkContext, *, allow_terminal: bool = False) -> tuple[CodingSessionWorkDiagnostic, ...]:
    contract, intent = context.contract, context.intent
    checks = (
        (intent.session_identity != contract.session_identity, CodingSessionWorkDiagnosticCode.SESSION_MISMATCH),
        (intent.actor != contract.actor, CodingSessionWorkDiagnosticCode.ACTOR_MISMATCH),
        (intent.purpose != contract.purpose, CodingSessionWorkDiagnosticCode.PURPOSE_MISMATCH),
        (intent.correlation != contract.correlation, CodingSessionWorkDiagnosticCode.CORRELATION_MISMATCH),
        (intent.binding != contract.binding, CodingSessionWorkDiagnosticCode.BINDING_MISMATCH),
        (intent.requirement.requested_capability is not CodingSessionRequestedCapability.WORKER_ASSISTANCE, CodingSessionWorkDiagnosticCode.CAPABILITY_MISMATCH),
        (intent.category is not CodingSessionIntentCategory.WORKER_ASSISTANCE_REQUEST, CodingSessionWorkDiagnosticCode.CAPABILITY_MISMATCH),
        (intent.target_authority is not CodingSessionTargetAuthority.WORKERS, CodingSessionWorkDiagnosticCode.CAPABILITY_MISMATCH),
        (intent.policy_version != CODING_SESSION_INTENT_POLICY_VERSION, CodingSessionWorkDiagnosticCode.PRODUCER_VERSION_MISMATCH),
        (not allow_terminal and context.lifecycle.lifecycle not in {CodingSessionLifecycleState.PREPARED, CodingSessionLifecycleState.ACTIVE}, CodingSessionWorkDiagnosticCode.LIFECYCLE_INCOMPATIBLE),
    )
    return _ordered({CodingSessionWorkDiagnostic(code) for failed, code in checks if failed})


def _assistance(context: CodingSessionWorkContext) -> CodingSessionWorkerAssistanceRequest:
    contract = context.contract
    return CodingSessionWorkerAssistanceRequest(
        contract.session_identity.value, context.intent.intent_identity.value,
        contract.actor.value, contract.project.value, contract.purpose.task.value,
        contract.purpose.purpose.value, contract.correlation.value,
        context.requested_capability, _repository_binding(context),
        tuple(sorted(set(context.artifact_references), key=lambda item: item.identity)),
        tuple(sorted(set(context.authorization_references), key=lambda item: item.identity)),
        context.intent.causal_metadata.revision.value, context.policy_id,
        context.policy_version,
    )


def _repository_binding(context: CodingSessionWorkContext) -> tuple[str | None, str | None, str | None]:
    binding = context.contract.binding
    return (
        binding.repository.identity if binding.repository else None,
        binding.checkout.identity if binding.checkout else None,
        binding.worktree.identity if binding.worktree else None,
    )


def _external_fingerprints(
    context: CodingSessionWorkContext,
) -> tuple[CodingSessionFingerprint, ...]:
    return tuple(
        sorted(
            (
                reference.fingerprint
                for reference in (
                    context.artifact_references + context.authorization_references
                )
                if reference.fingerprint is not None
            ),
            key=lambda item: item.value,
        )
    )


def _translation(kind, request, diagnostics):
    return CodingSessionWorkTranslation(kind, request, False, False, False, False, diagnostics)


def _ordered(findings: set[CodingSessionWorkDiagnostic]) -> tuple[CodingSessionWorkDiagnostic, ...]:
    return tuple(sorted(findings, key=lambda item: (item.code.value, item.subject)))


def _binding_state(state: CodingSessionWorkerReceiptState) -> CodingSessionWorkerBindingProjectionState:
    return {
        CodingSessionWorkerReceiptState.ASSIGNMENT_CREATED: CodingSessionWorkerBindingProjectionState.ASSIGNED,
        CodingSessionWorkerReceiptState.ATTEMPT_STARTED: CodingSessionWorkerBindingProjectionState.ACTIVE,
        CodingSessionWorkerReceiptState.ATTEMPT_WAITING: CodingSessionWorkerBindingProjectionState.WAITING,
        CodingSessionWorkerReceiptState.ATTEMPT_COMPLETED: CodingSessionWorkerBindingProjectionState.RELEASED,
        CodingSessionWorkerReceiptState.ATTEMPT_FAILED: CodingSessionWorkerBindingProjectionState.RELEASED,
        CodingSessionWorkerReceiptState.ATTEMPT_CANCELLED: CodingSessionWorkerBindingProjectionState.RELEASED,
        CodingSessionWorkerReceiptState.ATTEMPT_UNAVAILABLE: CodingSessionWorkerBindingProjectionState.UNKNOWN,
        CodingSessionWorkerReceiptState.ORPHANED: CodingSessionWorkerBindingProjectionState.ORPHANED,
        CodingSessionWorkerReceiptState.UNKNOWN: CodingSessionWorkerBindingProjectionState.UNKNOWN,
        CodingSessionWorkerReceiptState.LATE_RESULT: CodingSessionWorkerBindingProjectionState.UNKNOWN,
    }[state]


_CORRESPONDENCE_FAILURES = {
    CodingSessionWorkDiagnosticCode.SESSION_MISMATCH,
    CodingSessionWorkDiagnosticCode.INTENT_MISMATCH,
    CodingSessionWorkDiagnosticCode.ACTOR_MISMATCH,
    CodingSessionWorkDiagnosticCode.PROJECT_MISMATCH,
    CodingSessionWorkDiagnosticCode.PURPOSE_MISMATCH,
    CodingSessionWorkDiagnosticCode.CORRELATION_MISMATCH,
    CodingSessionWorkDiagnosticCode.MISSION_TASK_MISMATCH,
    CodingSessionWorkDiagnosticCode.ASSIGNMENT_ATTEMPT_MISMATCH,
    CodingSessionWorkDiagnosticCode.BINDING_MISMATCH,
    CodingSessionWorkDiagnosticCode.CAPABILITY_MISMATCH,
    CodingSessionWorkDiagnosticCode.CONTRADICTORY_OUTCOME,
    CodingSessionWorkDiagnosticCode.CAUSAL_REVISION_MISMATCH,
    CodingSessionWorkDiagnosticCode.LINEAGE_GAP,
    CodingSessionWorkDiagnosticCode.PRODUCER_VERSION_MISMATCH,
}
