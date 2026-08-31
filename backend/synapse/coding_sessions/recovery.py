"""Pure factual recovery planning and projection for Coding Sessions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .causal import CodingSessionCausalMetadata
from .identities import (
    CodingSessionFactIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionRecoveryArtifactIdentity,
)
from .intents import CodingSessionProducerReference, CodingSessionTargetAuthority
from .lifecycle import CodingSessionLifecycleState
from .restart import (
    CodingSessionReconciliationAssessment,
    CodingSessionReconciliationOutcome,
)

CODING_SESSION_RECOVERY_POLICY_VERSION = "coding-session-recovery-policy-v1"


class CodingSessionRecoveryReason(str, Enum):
    CRASH_RESTART_INCOMPLETE = "crash-restart-incomplete"
    REPOSITORY_DIVERGENCE = "repository-divergence"
    MUTATION_OUTCOME_UNKNOWN = "mutation-outcome-unknown"
    STALE_REPOSITORY_BINDING = "stale-repository-binding"
    STALE_OR_REVOKED_LEASE = "stale-or-revoked-lease"
    ORPHAN_WORKER = "orphan-worker"
    EXECUTION_UNKNOWN = "execution-unknown"
    CANCELLATION_INCOMPLETE = "cancellation-incomplete"
    MISSING_ARTIFACT_REFERENCE = "missing-artifact-reference"
    CONTRADICTORY_RECEIPT = "contradictory-receipt"
    JOURNAL_CHECKPOINT_LINEAGE_GAP = "journal-checkpoint-lineage-gap"
    EXTERNAL_AUTHORITY_UNAVAILABLE = "external-authority-unavailable"


class CodingSessionRecoveryStepKind(str, Enum):
    REOBSERVE_REPOSITORY = "reobserve-repository"
    REACQUIRE_OR_RENEW_LEASE = "reacquire-or-renew-lease"
    RECONCILE_WORKER = "reconcile-worker"
    RECONCILE_SANDBOX_EXECUTION = "reconcile-sandbox-execution"
    RECONCILE_AUTHORIZATION = "reconcile-authorization"
    VERIFY_ARTIFACT_REFERENCE = "verify-artifact-reference"
    REQUEST_REPOSITORY_RECOVERY = "request-repository-recovery"
    REQUEST_SANDBOX_CLEANUP = "request-sandbox-cleanup"
    REQUEST_WORKER_CANCELLATION = "request-worker-cancellation"
    REBUILD_CHECKPOINT = "rebuild-checkpoint"
    VERIFY_SESSION_RECOVERY = "verify-session-recovery"
    REQUIRE_MANUAL_INTERVENTION = "require-manual-intervention"


class CodingSessionRecoveryLifecycleState(str, Enum):
    NONE = "none"
    REQUIRED = "required"
    PLANNED = "planned"
    RECONCILING = "reconciling"
    RECOVERABLE = "recoverable"
    RECOVERED = "recovered"
    FAILED = "failed"
    MANUAL_INTERVENTION = "manual-intervention"


class CodingSessionRecoveryFactState(str, Enum):
    ATTEMPTED = "attempted"
    SATISFIED = "satisfied"
    FAILED = "failed"
    EXTERNAL_INTERFERENCE = "external-interference"


class CodingSessionRecoveryOutcome(str, Enum):
    CONTINUATION_ELIGIBLE = "continuation-eligible"
    REMAIN_SUSPENDED = "remain-suspended"
    FAIL_SESSION_ELIGIBLE = "fail-session-eligible"
    MANUAL_INTERVENTION_REQUIRED = "manual-intervention-required"


class CodingSessionRecoveryDiagnosticCode(str, Enum):
    RECOVERY_NOT_REQUIRED = "recovery-not-required"
    RECONCILIATION_MISMATCH = "reconciliation-mismatch"
    STEP_OUT_OF_SCOPE = "step-out-of-scope"
    DUPLICATE_RECOVERY_ATTEMPT = "duplicate-recovery-attempt"
    DUPLICATE_CAUSAL_REVISION = "duplicate-causal-revision"
    LINEAGE_GAP = "lineage-gap"
    MISSING_PREREQUISITE = "missing-prerequisite"
    EXTERNAL_RECEIPT_MISMATCH = "external-receipt-mismatch"
    STALE_RECOVERY_PLAN = "stale-recovery-plan"
    EXTERNAL_INTERFERENCE = "external-interference"
    TERMINAL_SESSION_INCOMPATIBLE = "terminal-session-incompatible"
    MISSING_RECOVERY_EVIDENCE = "missing-recovery-evidence"
    STEP_FAILED = "step-failed"
    MANUAL_INTERVENTION_REQUIRED = "manual-intervention-required"
    UNSUPPORTED_POLICY_VERSION = "unsupported-policy-version"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionRecoveryDiagnostic:
    code: CodingSessionRecoveryDiagnosticCode
    subject: str = "recovery"


@dataclass(frozen=True, slots=True)
class CodingSessionRecoveryRequest:
    recovery_identity: CodingSessionRecoveryArtifactIdentity
    session_identity: CodingSessionIdentity
    reconciliation: CodingSessionReconciliationAssessment
    reasons: tuple[CodingSessionRecoveryReason, ...]
    expected_lifecycle: CodingSessionLifecycleState
    occurrence_metadata: tuple[tuple[str, str], ...] = ()
    policy_version: str = CODING_SESSION_RECOVERY_POLICY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons), key=lambda item: item.value)))

    @property
    def reconciliation_fingerprint(self) -> CodingSessionFingerprint:
        return self.reconciliation.fingerprint

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(
            (
                self.recovery_identity,
                self.session_identity,
                self.reconciliation.fingerprint,
                self.reasons,
                self.expected_lifecycle,
                self.policy_version,
            )
        )


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionRecoveryRequirement:
    requirement_identity: CodingSessionFactIdentity
    session_identity: CodingSessionIdentity
    recovery_identity: CodingSessionRecoveryArtifactIdentity
    reason: CodingSessionRecoveryReason
    required_step: CodingSessionRecoveryStepKind
    target_authority: CodingSessionTargetAuthority | None
    policy_version: str = CODING_SESSION_RECOVERY_POLICY_VERSION

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionRecoveryStep:
    step_identity: CodingSessionFactIdentity
    session_identity: CodingSessionIdentity
    recovery_identity: CodingSessionRecoveryArtifactIdentity
    causal_revision: int
    kind: CodingSessionRecoveryStepKind
    prerequisite_fingerprints: tuple[CodingSessionFingerprint, ...]
    target_authority: CodingSessionTargetAuthority | None
    expected_external_receipt: CodingSessionProducerReference | None
    policy_version: str = CODING_SESSION_RECOVERY_POLICY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "prerequisite_fingerprints",
            tuple(sorted(set(self.prerequisite_fingerprints), key=lambda item: item.value)),
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionRecoveryPlan:
    recovery_identity: CodingSessionRecoveryArtifactIdentity
    session_identity: CodingSessionIdentity
    reconciliation_fingerprint: CodingSessionFingerprint
    request_fingerprint: CodingSessionFingerprint
    requirements: tuple[CodingSessionRecoveryRequirement, ...]
    steps: tuple[CodingSessionRecoveryStep, ...]
    diagnostics: tuple[CodingSessionRecoveryDiagnostic, ...]
    policy_version: str = CODING_SESSION_RECOVERY_POLICY_VERSION

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)

    @classmethod
    def derive(cls, request: CodingSessionRecoveryRequest) -> CodingSessionRecoveryPlan:
        diagnostics: set[CodingSessionRecoveryDiagnostic] = set()
        if request.policy_version != CODING_SESSION_RECOVERY_POLICY_VERSION:
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
        if request.reconciliation.resume_eligibility.outcome is CodingSessionReconciliationOutcome.SAFE_TO_RESUME:
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.RECOVERY_NOT_REQUIRED))
        if not request.reasons:
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.RECOVERY_NOT_REQUIRED))
        if (
            request.reconciliation.resume_eligibility.outcome
            is CodingSessionReconciliationOutcome.MANUAL_INTERVENTION
            and not set(request.reasons)
            & {
                CodingSessionRecoveryReason.CONTRADICTORY_RECEIPT,
                CodingSessionRecoveryReason.EXTERNAL_AUTHORITY_UNAVAILABLE,
            }
        ):
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.RECONCILIATION_MISMATCH))
        if diagnostics:
            return cls(
                request.recovery_identity,
                request.session_identity,
                request.reconciliation.fingerprint,
                request.fingerprint,
                (),
                (),
                tuple(sorted(diagnostics)),
            )
        requirements: list[CodingSessionRecoveryRequirement] = []
        steps: list[CodingSessionRecoveryStep] = []
        previous: CodingSessionFingerprint | None = None
        for reason in request.reasons:
            for kind, authority in _steps_for_reason(reason):
                revision = len(steps) + 1
                requirement_identity = CodingSessionFactIdentity.from_stable_key(
                    f"{request.recovery_identity.value}:requirement:{reason.value}:{kind.value}"
                )
                requirement = CodingSessionRecoveryRequirement(
                    requirement_identity,
                    request.session_identity,
                    request.recovery_identity,
                    reason,
                    kind,
                    authority,
                )
                requirements.append(requirement)
                if kind is CodingSessionRecoveryStepKind.REQUIRE_MANUAL_INTERVENTION:
                    diagnostics.add(
                        _diagnostic(
                            CodingSessionRecoveryDiagnosticCode.MANUAL_INTERVENTION_REQUIRED
                        )
                    )
                step_identity = CodingSessionFactIdentity.from_stable_key(
                    f"{request.recovery_identity.value}:step:{revision}:{kind.value}"
                )
                step = CodingSessionRecoveryStep(
                    step_identity,
                    request.session_identity,
                    request.recovery_identity,
                    revision,
                    kind,
                    ((previous,) if previous else ()),
                    authority,
                    None,
                )
                steps.append(step)
                previous = step.fingerprint
        if steps and not diagnostics:
            verification = CodingSessionRecoveryStep(
                CodingSessionFactIdentity.from_stable_key(
                    f"{request.recovery_identity.value}:step:verify"
                ),
                request.session_identity,
                request.recovery_identity,
                len(steps) + 1,
                CodingSessionRecoveryStepKind.VERIFY_SESSION_RECOVERY,
                tuple(item.fingerprint for item in steps),
                None,
                None,
            )
            steps.append(verification)
        return cls(
            request.recovery_identity,
            request.session_identity,
            request.reconciliation.fingerprint,
            request.fingerprint,
            tuple(requirements),
            tuple(steps),
            tuple(sorted(diagnostics)),
        )


@dataclass(frozen=True, slots=True)
class CodingSessionRecoveryFact:
    fact_identity: CodingSessionFactIdentity
    attempt_identity: CodingSessionFactIdentity
    session_identity: CodingSessionIdentity
    recovery_identity: CodingSessionRecoveryArtifactIdentity
    plan_fingerprint: CodingSessionFingerprint
    step_identity: CodingSessionFactIdentity
    state: CodingSessionRecoveryFactState
    evidence_fingerprint: CodingSessionFingerprint | None
    external_receipt: CodingSessionProducerReference | None
    causal_metadata: CodingSessionCausalMetadata

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(
            (
                self.fact_identity,
                self.attempt_identity,
                self.session_identity,
                self.recovery_identity,
                self.plan_fingerprint,
                self.step_identity,
                self.state,
                self.evidence_fingerprint,
                self.external_receipt,
                self.causal_metadata,
            )
        )


@dataclass(frozen=True, slots=True)
class CodingSessionRecoveryAssessment:
    session_identity: CodingSessionIdentity
    recovery_identity: CodingSessionRecoveryArtifactIdentity
    state: CodingSessionRecoveryLifecycleState
    outcome: CodingSessionRecoveryOutcome
    completed_steps: tuple[CodingSessionFactIdentity, ...]
    pending_steps: tuple[CodingSessionFactIdentity, ...]
    diagnostics: tuple[CodingSessionRecoveryDiagnostic, ...]
    fingerprint: CodingSessionFingerprint

    @classmethod
    def project(
        cls,
        plan: CodingSessionRecoveryPlan,
        facts: tuple[CodingSessionRecoveryFact, ...],
        *,
        current_reconciliation_fingerprint: CodingSessionFingerprint,
        lifecycle: CodingSessionLifecycleState,
        prior_attempts: frozenset[CodingSessionFactIdentity] = frozenset(),
    ) -> CodingSessionRecoveryAssessment:
        diagnostics: set[CodingSessionRecoveryDiagnostic] = set(plan.diagnostics)
        if plan.policy_version != CODING_SESSION_RECOVERY_POLICY_VERSION:
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
        if current_reconciliation_fingerprint != plan.reconciliation_fingerprint:
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.STALE_RECOVERY_PLAN))
        if lifecycle is CodingSessionLifecycleState.TERMINAL:
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.TERMINAL_SESSION_INCOMPATIBLE))
        steps = {item.step_identity: item for item in plan.steps}
        ordered = tuple(sorted(facts, key=lambda item: item.causal_metadata.revision.value))
        revisions = [item.causal_metadata.revision.value for item in ordered]
        if len(revisions) != len(set(revisions)):
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.DUPLICATE_CAUSAL_REVISION))
        if revisions and revisions != list(range(1, len(revisions) + 1)):
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.LINEAGE_GAP))
        attempts = [item.attempt_identity for item in ordered]
        if len(attempts) != len(set(attempts)) or any(item in prior_attempts for item in attempts):
            diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.DUPLICATE_RECOVERY_ATTEMPT))
        satisfied: set[CodingSessionFactIdentity] = set()
        previous_fact: CodingSessionRecoveryFact | None = None
        for fact in ordered:
            step = steps.get(fact.step_identity)
            if (
                step is None
                or fact.session_identity != plan.session_identity
                or fact.recovery_identity != plan.recovery_identity
                or fact.plan_fingerprint != plan.fingerprint
            ):
                diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.STEP_OUT_OF_SCOPE))
                continue
            expected_parents = ((previous_fact.fingerprint,) if previous_fact else ())
            if (
                fact.causal_metadata.semantic_identity != fact.fact_identity
                or fact.causal_metadata.lineage.parents != expected_parents
            ):
                diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.LINEAGE_GAP))
            if any(prerequisite not in {steps[item].fingerprint for item in satisfied} for prerequisite in step.prerequisite_fingerprints):
                diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.MISSING_PREREQUISITE))
            if step.expected_external_receipt is not None and fact.external_receipt != step.expected_external_receipt:
                diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.EXTERNAL_RECEIPT_MISMATCH))
            if fact.state is CodingSessionRecoveryFactState.EXTERNAL_INTERFERENCE:
                diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.EXTERNAL_INTERFERENCE))
            elif fact.state is CodingSessionRecoveryFactState.FAILED:
                diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.STEP_FAILED))
            elif fact.state is CodingSessionRecoveryFactState.SATISFIED:
                if fact.evidence_fingerprint is None:
                    diagnostics.add(_diagnostic(CodingSessionRecoveryDiagnosticCode.MISSING_RECOVERY_EVIDENCE))
                else:
                    satisfied.add(fact.step_identity)
            previous_fact = fact
        all_steps = set(steps)
        pending = all_steps - satisfied
        verification = next(
            (item for item in plan.steps if item.kind is CodingSessionRecoveryStepKind.VERIFY_SESSION_RECOVERY),
            None,
        )
        codes = {item.code for item in diagnostics}
        if (
            CodingSessionRecoveryDiagnosticCode.EXTERNAL_INTERFERENCE in codes
            or CodingSessionRecoveryDiagnosticCode.TERMINAL_SESSION_INCOMPATIBLE in codes
            or CodingSessionRecoveryDiagnosticCode.MANUAL_INTERVENTION_REQUIRED in codes
        ):
            state = CodingSessionRecoveryLifecycleState.MANUAL_INTERVENTION
            outcome = CodingSessionRecoveryOutcome.MANUAL_INTERVENTION_REQUIRED
        elif CodingSessionRecoveryDiagnosticCode.STEP_FAILED in codes:
            state = CodingSessionRecoveryLifecycleState.FAILED
            outcome = CodingSessionRecoveryOutcome.FAIL_SESSION_ELIGIBLE
        elif verification is not None and verification.step_identity in satisfied and not diagnostics:
            state = CodingSessionRecoveryLifecycleState.RECOVERED
            outcome = CodingSessionRecoveryOutcome.CONTINUATION_ELIGIBLE
        elif (
            verification is not None
            and all(
                item.step_identity in satisfied
                for item in plan.steps
                if item is not verification
            )
            and not diagnostics
        ):
            state = CodingSessionRecoveryLifecycleState.RECOVERABLE
            outcome = CodingSessionRecoveryOutcome.REMAIN_SUSPENDED
        elif facts:
            state = CodingSessionRecoveryLifecycleState.RECONCILING
            outcome = CodingSessionRecoveryOutcome.REMAIN_SUSPENDED
        elif plan.steps and not plan.diagnostics:
            state = CodingSessionRecoveryLifecycleState.PLANNED
            outcome = CodingSessionRecoveryOutcome.REMAIN_SUSPENDED
        elif plan.requirements:
            state = CodingSessionRecoveryLifecycleState.REQUIRED
            outcome = CodingSessionRecoveryOutcome.REMAIN_SUSPENDED
        else:
            state = CodingSessionRecoveryLifecycleState.NONE
            outcome = CodingSessionRecoveryOutcome.REMAIN_SUSPENDED
        completed_tuple = tuple(sorted(satisfied, key=lambda item: item.value))
        pending_tuple = tuple(sorted(pending, key=lambda item: item.value))
        diagnostic_tuple = tuple(sorted(diagnostics))
        fingerprint = CodingSessionFingerprint.from_content(
            (
                plan.session_identity,
                plan.recovery_identity,
                state,
                outcome,
                completed_tuple,
                pending_tuple,
                diagnostic_tuple,
            )
        )
        return cls(
            plan.session_identity,
            plan.recovery_identity,
            state,
            outcome,
            completed_tuple,
            pending_tuple,
            diagnostic_tuple,
            fingerprint,
        )


def _diagnostic(code: CodingSessionRecoveryDiagnosticCode) -> CodingSessionRecoveryDiagnostic:
    return CodingSessionRecoveryDiagnostic(code)


def _steps_for_reason(
    reason: CodingSessionRecoveryReason,
) -> tuple[
    tuple[CodingSessionRecoveryStepKind, CodingSessionTargetAuthority | None], ...
]:
    mapping: dict[
        CodingSessionRecoveryReason,
        tuple[
            tuple[CodingSessionRecoveryStepKind, CodingSessionTargetAuthority | None],
            ...,
        ],
    ] = {
        CodingSessionRecoveryReason.CRASH_RESTART_INCOMPLETE: (
            (CodingSessionRecoveryStepKind.REBUILD_CHECKPOINT, None),
        ),
        CodingSessionRecoveryReason.REPOSITORY_DIVERGENCE: (
            (
                CodingSessionRecoveryStepKind.REQUEST_REPOSITORY_RECOVERY,
                CodingSessionTargetAuthority.REPOSITORY_RUNTIME,
            ),
        ),
        CodingSessionRecoveryReason.MUTATION_OUTCOME_UNKNOWN: (
            (
                CodingSessionRecoveryStepKind.REOBSERVE_REPOSITORY,
                CodingSessionTargetAuthority.REPOSITORY_RUNTIME,
            ),
        ),
        CodingSessionRecoveryReason.STALE_REPOSITORY_BINDING: (
            (
                CodingSessionRecoveryStepKind.REOBSERVE_REPOSITORY,
                CodingSessionTargetAuthority.REPOSITORY_RUNTIME,
            ),
        ),
        CodingSessionRecoveryReason.STALE_OR_REVOKED_LEASE: (
            (
                CodingSessionRecoveryStepKind.REACQUIRE_OR_RENEW_LEASE,
                CodingSessionTargetAuthority.REPOSITORY_RUNTIME,
            ),
        ),
        CodingSessionRecoveryReason.ORPHAN_WORKER: (
            (
                CodingSessionRecoveryStepKind.RECONCILE_WORKER,
                CodingSessionTargetAuthority.WORKERS,
            ),
        ),
        CodingSessionRecoveryReason.EXECUTION_UNKNOWN: (
            (
                CodingSessionRecoveryStepKind.RECONCILE_SANDBOX_EXECUTION,
                CodingSessionTargetAuthority.SANDBOX,
            ),
        ),
        CodingSessionRecoveryReason.CANCELLATION_INCOMPLETE: (
            (CodingSessionRecoveryStepKind.REQUEST_WORKER_CANCELLATION, CodingSessionTargetAuthority.WORKERS),
            (CodingSessionRecoveryStepKind.REQUEST_SANDBOX_CLEANUP, CodingSessionTargetAuthority.SANDBOX),
        ),
        CodingSessionRecoveryReason.MISSING_ARTIFACT_REFERENCE: (
            (
                CodingSessionRecoveryStepKind.VERIFY_ARTIFACT_REFERENCE,
                CodingSessionTargetAuthority.ARTIFACT_AUTHORITY,
            ),
        ),
        CodingSessionRecoveryReason.CONTRADICTORY_RECEIPT: (
            (CodingSessionRecoveryStepKind.REQUIRE_MANUAL_INTERVENTION, None),
        ),
        CodingSessionRecoveryReason.JOURNAL_CHECKPOINT_LINEAGE_GAP: (
            (CodingSessionRecoveryStepKind.REBUILD_CHECKPOINT, None),
        ),
        CodingSessionRecoveryReason.EXTERNAL_AUTHORITY_UNAVAILABLE: (
            (CodingSessionRecoveryStepKind.REQUIRE_MANUAL_INTERVENTION, None),
        ),
    }
    return mapping[reason]
