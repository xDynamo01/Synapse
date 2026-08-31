"""Pure rollback/recovery planning and abstract orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .application import RepositoryMutationJournal
from .errors import InvalidRepositoryRecoveryModel
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import RepositoryPlatformProfile
from .mutations import RepositoryMutationPlan
from .restore_points import RepositoryRestorePointResult
from .snapshot import RepositorySnapshot
from .states import (
    RepositoryMutationSideEffect,
    RepositoryObservationCompleteness,
    RepositoryRestorePointCoverageKind,
)
from .verification import RepositoryVerificationEntryState, RepositoryVerificationResult

if TYPE_CHECKING:
    from .contracts import (
        RepositoryRecoveryInterruptionPort,
        RepositoryRecoveryObservationPort,
        RepositoryRecoveryPreconditionPort,
        RepositoryRecoveryStepPort,
        RepositoryRecoveryVerificationPort,
    )

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")


class RepositoryRecoveryState(StrEnum):
    NOT_REQUIRED = "not-required"
    REQUIRED = "required"
    PLANNED = "planned"
    READY = "ready"
    IN_PROGRESS = "in-progress"
    PARTIALLY_RECOVERED = "partially-recovered"
    RECOVERED = "recovered"
    ROLLBACK_FAILED = "rollback-failed"
    VERIFICATION_FAILED = "verification-failed"
    MANUAL_INTERVENTION = "manual-intervention"


class RepositoryRecoveryAction(StrEnum):
    RESTORE_CONTENT = "restore-content"
    RESTORE_METADATA = "restore-metadata"
    RESTORE_ABSENCE = "restore-absence"
    RESTORE_PRESENCE = "restore-presence"
    RESTORE_HEAD = "restore-HEAD"
    RESTORE_BRANCH_STATE = "restore-branch-state"
    RESTORE_INDEX = "restore-index"
    RECONCILE_UNTRACKED = "reconcile-untracked"
    VERIFY_RESTORED_STATE = "verify-restored-state"


class RepositoryRecoveryPreconditionState(StrEnum):
    SATISFIED = "satisfied"
    STALE = "stale"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"
    EXTERNAL_INTERFERENCE = "external-interference"


class RepositoryRecoveryStepState(StrEnum):
    NOT_STARTED = "not-started"
    APPLIED = "applied"
    FAILED = "failed"
    PARTIAL = "partial"
    INTERRUPTED = "interrupted"
    EXTERNAL_INTERFERENCE = "external-interference"


class RepositoryRecoveryDiagnosticCode(StrEnum):
    REQUEST_BINDING_MISMATCH = "request-binding-mismatch"
    RECOVERY_NOT_INDICATED = "recovery-not-indicated"
    MANUAL_INTERVENTION_REQUIRED = "manual-intervention-required"
    BASE_SNAPSHOT_MISMATCH = "base-snapshot-mismatch"
    MUTATION_PLAN_MISMATCH = "mutation-plan-mismatch"
    MUTATION_JOURNAL_MISMATCH = "mutation-journal-mismatch"
    VERIFICATION_MISMATCH = "verification-mismatch"
    RESTORE_POINT_MISMATCH = "restore-point-mismatch"
    RESTORE_POINT_NOT_RECOVERABLE = "restore-point-not-recoverable"
    COVERAGE_NOT_VERIFIED = "coverage-not-verified"
    DIVERGENCE_OUTSIDE_COVERAGE = "divergence-outside-coverage"
    TOPOLOGY_BOUNDARY = "topology-boundary"
    PRECONDITION_STALE = "precondition-stale"
    PRECONDITION_MISMATCH = "precondition-mismatch"
    PRECONDITION_UNAVAILABLE = "precondition-unavailable"
    EXTERNAL_INTERFERENCE = "external-interference"
    STEP_RESULT_MISMATCH = "step-result-mismatch"
    STEP_FAILED = "step-failed"
    STEP_PARTIAL = "step-partial"
    INTERRUPTION_FAILED = "interruption-failed"
    RESTORED_STATE_UNVERIFIED = "restored-state-unverified"
    RESTORED_STATE_MISMATCH = "restored-state-mismatch"


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryPolicy:
    policy_id: str
    policy_version: str
    allowed_actions: tuple[RepositoryRecoveryAction, ...]
    stop_on_nonrecoverable_error: bool = True
    require_post_recovery_verification: bool = True

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.policy_id) or not _REFERENCE.fullmatch(
            self.policy_version
        ):
            raise InvalidRepositoryRecoveryModel("recovery policy identity is invalid")
        ordered = tuple(sorted(set(self.allowed_actions), key=lambda item: item.value))
        if not ordered or len(ordered) != len(self.allowed_actions):
            raise InvalidRepositoryRecoveryModel("allowed recovery actions are invalid")
        object.__setattr__(self, "allowed_actions", ordered)


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryRequest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    mutation_attempt_fingerprint: RepositoryFingerprint
    mutation_journal_fingerprint: RepositoryFingerprint
    verification_result_fingerprint: RepositoryFingerprint
    reconciliation_fingerprint: RepositoryFingerprint
    restore_point_manifest_fingerprint: RepositoryFingerprint
    restore_point_verification_fingerprint: RepositoryFingerprint
    policy_id: str
    policy_version: str
    recovery_reference: str
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if any(
            not _REFERENCE.fullmatch(value)
            for value in (self.policy_id, self.policy_version, self.recovery_reference)
        ):
            raise InvalidRepositoryRecoveryModel("recovery request reference is invalid")
        if any(
            not _REFERENCE.fullmatch(k) or not _REFERENCE.fullmatch(v)
            for k, v in self.occurrence_metadata
        ):
            raise InvalidRepositoryRecoveryModel("occurrence metadata is invalid")
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return tuple(
            getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "occurrence_metadata"
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryDiagnostic:
    code: RepositoryRecoveryDiagnosticCode
    step_fingerprint: RepositoryFingerprint | None = None
    path_fingerprint: RepositoryFingerprint | None = None
    coverage_fingerprint: RepositoryFingerprint | None = None


def _diagnostic_key(item: RepositoryRecoveryDiagnostic) -> tuple[str, str, str, str]:
    return (
        item.code.value,
        item.step_fingerprint.value if item.step_fingerprint else "",
        item.path_fingerprint.value if item.path_fingerprint else "",
        item.coverage_fingerprint.value if item.coverage_fingerprint else "",
    )


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryStep:
    sequence_index: int
    action: RepositoryRecoveryAction
    path_fingerprint: RepositoryFingerprint | None
    coverage_entry_fingerprint: RepositoryFingerprint | None
    expected_current_fingerprint: RepositoryFingerprint | None
    expected_restored_fingerprint: RepositoryFingerprint
    topology_fingerprint: RepositoryFingerprint | None = None

    def __post_init__(self) -> None:
        if self.sequence_index < 0:
            raise InvalidRepositoryRecoveryModel("recovery step index cannot be negative")

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryPlan:
    request_fingerprint: RepositoryFingerprint
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    mutation_journal_fingerprint: RepositoryFingerprint
    verification_result_fingerprint: RepositoryFingerprint
    restore_point_manifest_fingerprint: RepositoryFingerprint
    restore_point_verification_fingerprint: RepositoryFingerprint
    policy_id: str
    policy_version: str
    state: RepositoryRecoveryState
    steps: tuple[RepositoryRecoveryStep, ...]
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...]

    def __post_init__(self) -> None:
        if tuple(step.sequence_index for step in self.steps) != tuple(range(len(self.steps))):
            raise InvalidRepositoryRecoveryModel("recovery plan step order is invalid")
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryAttempt:
    attempt_id: RepositoryFingerprint
    request_fingerprint: RepositoryFingerprint
    plan_fingerprint: RepositoryFingerprint
    step_fingerprints: tuple[RepositoryFingerprint, ...]


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryPreconditionReport:
    attempt_id: RepositoryFingerprint
    plan_fingerprint: RepositoryFingerprint
    state: RepositoryRecoveryPreconditionState
    observed_current_fingerprints: tuple[RepositoryFingerprint, ...]
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_current_fingerprints",
            tuple(sorted(set(self.observed_current_fingerprints), key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryStepResult:
    attempt_id: RepositoryFingerprint
    step_fingerprint: RepositoryFingerprint
    state: RepositoryRecoveryStepState
    side_effect: RepositoryMutationSideEffect
    observed_fingerprints: tuple[RepositoryFingerprint, ...] = ()
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryObservation:
    attempt_id: RepositoryFingerprint
    step_fingerprint: RepositoryFingerprint
    corresponds: bool
    external_interference: bool
    observed_fingerprints: tuple[RepositoryFingerprint, ...] = ()
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryInterruption:
    attempt_id: RepositoryFingerprint
    interrupted: bool
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryVerification:
    attempt_id: RepositoryFingerprint
    base_snapshot_fingerprint: RepositoryFingerprint
    observed_snapshot_fingerprint: RepositoryFingerprint | None
    completeness: RepositoryObservationCompleteness
    state_restored: bool
    external_interference: bool
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...] = ()

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryJournalEntry:
    sequence_index: int
    step_fingerprint: RepositoryFingerprint
    state: RepositoryRecoveryStepState
    side_effect: RepositoryMutationSideEffect
    observed_fingerprints: tuple[RepositoryFingerprint, ...]
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_fingerprints",
            tuple(sorted(set(self.observed_fingerprints), key=lambda item: item.value)),
        )
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryJournal:
    attempt: RepositoryRecoveryAttempt
    plan_fingerprint: RepositoryFingerprint
    state: RepositoryRecoveryState
    entries: tuple[RepositoryRecoveryJournalEntry, ...]
    verification: RepositoryRecoveryVerification | None
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...]
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if tuple(entry.sequence_index for entry in self.entries) != tuple(range(len(self.entries))):
            raise InvalidRepositoryRecoveryModel("recovery journal order is invalid")
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return tuple(
            getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "occurrence_metadata"
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryResult:
    request_fingerprint: RepositoryFingerprint
    plan: RepositoryRecoveryPlan | None
    journal: RepositoryRecoveryJournal | None
    state: RepositoryRecoveryState
    diagnostics: tuple[RepositoryRecoveryDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


_ACTIONS = {
    RepositoryRestorePointCoverageKind.REPLACED_CONTENT: RepositoryRecoveryAction.RESTORE_CONTENT,
    RepositoryRestorePointCoverageKind.DELETED_CONTENT: RepositoryRecoveryAction.RESTORE_PRESENCE,
    RepositoryRestorePointCoverageKind.CREATED_ABSENCE: RepositoryRecoveryAction.RESTORE_ABSENCE,
    RepositoryRestorePointCoverageKind.MOVE_SOURCE: RepositoryRecoveryAction.RESTORE_PRESENCE,
    RepositoryRestorePointCoverageKind.MOVE_DESTINATION: RepositoryRecoveryAction.RESTORE_ABSENCE,
    RepositoryRestorePointCoverageKind.METADATA: RepositoryRecoveryAction.RESTORE_METADATA,
    RepositoryRestorePointCoverageKind.HEAD_STATE: RepositoryRecoveryAction.RESTORE_HEAD,
    RepositoryRestorePointCoverageKind.BRANCH_STATE: RepositoryRecoveryAction.RESTORE_BRANCH_STATE,
    RepositoryRestorePointCoverageKind.INDEX_STATE: RepositoryRecoveryAction.RESTORE_INDEX,
    RepositoryRestorePointCoverageKind.UNTRACKED_COLLISION: RepositoryRecoveryAction.RECONCILE_UNTRACKED,
}


class RepositoryRecoveryService:
    """Plan and coordinate logical recovery through supplied ports only."""

    def plan(
        self,
        request: RepositoryRecoveryRequest,
        policy: RepositoryRecoveryPolicy,
        base: RepositorySnapshot,
        mutation_plan: RepositoryMutationPlan,
        mutation_journal: RepositoryMutationJournal,
        verification: RepositoryVerificationResult,
        restore_point: RepositoryRestorePointResult,
    ) -> RepositoryRecoveryResult:
        diagnostics: set[RepositoryRecoveryDiagnostic] = set()
        self._bindings(
            request,
            policy,
            base,
            mutation_plan,
            mutation_journal,
            verification,
            restore_point,
            diagnostics,
        )
        reconciliation = verification.reconciliation
        indicated = reconciliation.recovery_required or reconciliation.rollback_candidate
        if not indicated:
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.RECOVERY_NOT_INDICATED
                )
            )
            return RepositoryRecoveryResult(
                request.fingerprint,
                None,
                None,
                RepositoryRecoveryState.NOT_REQUIRED,
                tuple(diagnostics),
            )
        if reconciliation.manual_intervention_required:
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.MANUAL_INTERVENTION_REQUIRED
                )
            )
            return RepositoryRecoveryResult(
                request.fingerprint,
                None,
                None,
                RepositoryRecoveryState.MANUAL_INTERVENTION,
                tuple(diagnostics),
            )
        if diagnostics or restore_point.manifest is None or restore_point.verification is None:
            return RepositoryRecoveryResult(
                request.fingerprint,
                None,
                None,
                RepositoryRecoveryState.REQUIRED,
                tuple(diagnostics),
            )
        divergent_paths = {
            entry.path_fingerprint
            for entry in verification.entries
            if entry.state is not RepositoryVerificationEntryState.APPLIED_AS_EXPECTED
        }
        verified_entries = set(restore_point.verification.verified_entries)
        steps: list[RepositoryRecoveryStep] = []
        covered_paths: set[RepositoryFingerprint] = set()
        for entry in restore_point.manifest.entries:
            if entry.fingerprint not in verified_entries:
                diagnostics.add(
                    RepositoryRecoveryDiagnostic(
                        RepositoryRecoveryDiagnosticCode.COVERAGE_NOT_VERIFIED,
                        path_fingerprint=entry.path_fingerprint,
                        coverage_fingerprint=entry.fingerprint,
                    )
                )
                continue
            action = _ACTIONS.get(entry.coverage_kind)
            if action is None:
                if entry.coverage_kind is RepositoryRestorePointCoverageKind.TOPOLOGY_BOUNDARY:
                    diagnostics.add(
                        RepositoryRecoveryDiagnostic(
                            RepositoryRecoveryDiagnosticCode.TOPOLOGY_BOUNDARY,
                            path_fingerprint=entry.path_fingerprint,
                            coverage_fingerprint=entry.fingerprint,
                        )
                    )
                continue
            if action not in policy.allowed_actions or (
                divergent_paths
                and entry.path_fingerprint not in divergent_paths
                and action
                not in {
                    RepositoryRecoveryAction.RESTORE_HEAD,
                    RepositoryRecoveryAction.RESTORE_BRANCH_STATE,
                    RepositoryRecoveryAction.RESTORE_INDEX,
                }
            ):
                continue
            covered_paths.add(entry.path_fingerprint)
            restored = (
                entry.expected_content_fingerprint
                or entry.expected_metadata_fingerprint
                or RepositoryFingerprint.from_content((entry.coverage_kind, entry.path_fingerprint))
            )
            steps.append(
                RepositoryRecoveryStep(
                    len(steps),
                    action,
                    entry.path_fingerprint,
                    entry.fingerprint,
                    self._observed_for(entry.path_fingerprint, verification),
                    restored,
                )
            )
        for path in divergent_paths - covered_paths:
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.DIVERGENCE_OUTSIDE_COVERAGE,
                    path_fingerprint=path,
                )
            )
        if RepositoryRecoveryAction.VERIFY_RESTORED_STATE in policy.allowed_actions:
            steps.append(
                RepositoryRecoveryStep(
                    len(steps),
                    RepositoryRecoveryAction.VERIFY_RESTORED_STATE,
                    None,
                    None,
                    verification.fingerprint,
                    base.fingerprint,
                )
            )
        blocking = any(
            item.code
            in {
                RepositoryRecoveryDiagnosticCode.DIVERGENCE_OUTSIDE_COVERAGE,
                RepositoryRecoveryDiagnosticCode.COVERAGE_NOT_VERIFIED,
            }
            for item in diagnostics
        )
        state = (
            RepositoryRecoveryState.REQUIRED
            if blocking or not steps
            else RepositoryRecoveryState.PLANNED
        )
        plan = RepositoryRecoveryPlan(
            request.fingerprint,
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.platform_profile,
            base.fingerprint,
            mutation_plan.fingerprint,
            mutation_journal.fingerprint,
            verification.fingerprint,
            restore_point.manifest.fingerprint,
            restore_point.verification.fingerprint,
            policy.policy_id,
            policy.policy_version,
            state,
            tuple(steps) if not blocking else (),
            tuple(diagnostics),
        )
        return RepositoryRecoveryResult(request.fingerprint, plan, None, state, tuple(diagnostics))

    def recover(
        self,
        request: RepositoryRecoveryRequest,
        plan: RepositoryRecoveryPlan,
        base: RepositorySnapshot,
        preconditions: RepositoryRecoveryPreconditionPort,
        steps: RepositoryRecoveryStepPort,
        observations: RepositoryRecoveryObservationPort,
        interruption: RepositoryRecoveryInterruptionPort,
        verification: RepositoryRecoveryVerificationPort,
    ) -> RepositoryRecoveryResult:
        diagnostics: set[RepositoryRecoveryDiagnostic] = set(plan.diagnostics)
        attempt = RepositoryRecoveryAttempt(
            RepositoryFingerprint.from_content(
                ("repository-recovery-attempt-v1", request.fingerprint, plan.fingerprint)
            ),
            request.fingerprint,
            plan.fingerprint,
            tuple(step.fingerprint for step in plan.steps),
        )
        if (
            plan.request_fingerprint != request.fingerprint
            or plan.state is not RepositoryRecoveryState.PLANNED
        ):
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.REQUEST_BINDING_MISMATCH
                )
            )
            return self._journal_result(
                request,
                plan,
                attempt,
                RepositoryRecoveryState.ROLLBACK_FAILED,
                (),
                None,
                diagnostics,
            )
        report = preconditions.revalidate_recovery_preconditions(attempt, plan)
        if (
            report.attempt_id != attempt.attempt_id
            or report.plan_fingerprint != plan.fingerprint
            or report.state is not RepositoryRecoveryPreconditionState.SATISFIED
        ):
            code = {
                RepositoryRecoveryPreconditionState.STALE: RepositoryRecoveryDiagnosticCode.PRECONDITION_STALE,
                RepositoryRecoveryPreconditionState.MISMATCH: RepositoryRecoveryDiagnosticCode.PRECONDITION_MISMATCH,
                RepositoryRecoveryPreconditionState.UNAVAILABLE: RepositoryRecoveryDiagnosticCode.PRECONDITION_UNAVAILABLE,
                RepositoryRecoveryPreconditionState.EXTERNAL_INTERFERENCE: RepositoryRecoveryDiagnosticCode.EXTERNAL_INTERFERENCE,
            }.get(report.state, RepositoryRecoveryDiagnosticCode.PRECONDITION_MISMATCH)
            diagnostics.add(RepositoryRecoveryDiagnostic(code))
            diagnostics.update(report.diagnostics)
            state = (
                RepositoryRecoveryState.MANUAL_INTERVENTION
                if report.state is RepositoryRecoveryPreconditionState.EXTERNAL_INTERFERENCE
                else RepositoryRecoveryState.ROLLBACK_FAILED
            )
            return self._journal_result(request, plan, attempt, state, (), None, diagnostics)
        entries: list[RepositoryRecoveryJournalEntry] = []
        failed = False
        for step in plan.steps:
            if step.action is RepositoryRecoveryAction.VERIFY_RESTORED_STATE:
                continue
            result = steps.apply_recovery_step(attempt, step)
            observation = observations.observe_recovery_step(attempt, step, result)
            step_diagnostics = set(result.diagnostics) | set(observation.diagnostics)
            step_state = result.state
            if (
                result.attempt_id != attempt.attempt_id
                or result.step_fingerprint != step.fingerprint
                or observation.attempt_id != attempt.attempt_id
                or observation.step_fingerprint != step.fingerprint
            ):
                step_diagnostics.add(
                    RepositoryRecoveryDiagnostic(
                        RepositoryRecoveryDiagnosticCode.STEP_RESULT_MISMATCH,
                        step.fingerprint,
                        step.path_fingerprint,
                    )
                )
                step_state = RepositoryRecoveryStepState.FAILED
            if observation.external_interference:
                step_diagnostics.add(
                    RepositoryRecoveryDiagnostic(
                        RepositoryRecoveryDiagnosticCode.EXTERNAL_INTERFERENCE,
                        step.fingerprint,
                        step.path_fingerprint,
                    )
                )
                step_state = RepositoryRecoveryStepState.EXTERNAL_INTERFERENCE
            elif not observation.corresponds:
                step_diagnostics.add(
                    RepositoryRecoveryDiagnostic(
                        RepositoryRecoveryDiagnosticCode.STEP_FAILED,
                        step.fingerprint,
                        step.path_fingerprint,
                    )
                )
                step_state = RepositoryRecoveryStepState.FAILED
            observed = tuple(
                set(result.observed_fingerprints) | set(observation.observed_fingerprints)
            )
            entries.append(
                RepositoryRecoveryJournalEntry(
                    step.sequence_index,
                    step.fingerprint,
                    step_state,
                    result.side_effect,
                    observed,
                    tuple(step_diagnostics),
                )
            )
            diagnostics.update(step_diagnostics)
            if step_state is not RepositoryRecoveryStepState.APPLIED or result.side_effect in {
                RepositoryMutationSideEffect.PARTIAL,
                RepositoryMutationSideEffect.UNKNOWN,
                RepositoryMutationSideEffect.OUT_OF_SCOPE,
            }:
                failed = True
                interruption_result = interruption.interrupt_recovery(attempt, step.fingerprint)
                diagnostics.update(interruption_result.diagnostics)
                if not interruption_result.interrupted:
                    diagnostics.add(
                        RepositoryRecoveryDiagnostic(
                            RepositoryRecoveryDiagnosticCode.INTERRUPTION_FAILED,
                            step.fingerprint,
                            step.path_fingerprint,
                        )
                    )
                break
        if failed:
            state = (
                RepositoryRecoveryState.MANUAL_INTERVENTION
                if any(
                    item.code
                    in {
                        RepositoryRecoveryDiagnosticCode.EXTERNAL_INTERFERENCE,
                        RepositoryRecoveryDiagnosticCode.INTERRUPTION_FAILED,
                    }
                    for item in diagnostics
                )
                else RepositoryRecoveryState.PARTIALLY_RECOVERED
                if entries
                else RepositoryRecoveryState.ROLLBACK_FAILED
            )
            return self._journal_result(
                request, plan, attempt, state, tuple(entries), None, diagnostics
            )
        verified = verification.verify_recovered_state(attempt, base)
        diagnostics.update(verified.diagnostics)
        if (
            verified.attempt_id != attempt.attempt_id
            or verified.base_snapshot_fingerprint != base.fingerprint
            or verified.external_interference
        ):
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.EXTERNAL_INTERFERENCE
                    if verified.external_interference
                    else RepositoryRecoveryDiagnosticCode.RESTORED_STATE_MISMATCH
                )
            )
            state = (
                RepositoryRecoveryState.MANUAL_INTERVENTION
                if verified.external_interference
                else RepositoryRecoveryState.VERIFICATION_FAILED
            )
        elif (
            not verified.state_restored
            or verified.completeness is not RepositoryObservationCompleteness.COMPLETE
            or verified.observed_snapshot_fingerprint != base.fingerprint
        ):
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.RESTORED_STATE_UNVERIFIED
                )
            )
            state = RepositoryRecoveryState.VERIFICATION_FAILED
        else:
            state = RepositoryRecoveryState.RECOVERED
        return self._journal_result(
            request, plan, attempt, state, tuple(entries), verified, diagnostics
        )

    def _bindings(
        self,
        request: RepositoryRecoveryRequest,
        policy: RepositoryRecoveryPolicy,
        base: RepositorySnapshot,
        plan: RepositoryMutationPlan,
        journal: RepositoryMutationJournal,
        verification: RepositoryVerificationResult,
        restore: RepositoryRestorePointResult,
        diagnostics: set[RepositoryRecoveryDiagnostic],
    ) -> None:
        identity = (
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.platform_profile,
        )
        if (
            base.repository_id,
            base.checkout_id,
            base.worktree_id,
            base.platform_profile,
        ) != identity or (
            plan.repository_id,
            plan.checkout_id,
            plan.worktree_id,
            plan.platform_profile,
        ) != identity:
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.REQUEST_BINDING_MISMATCH
                )
            )
        checks = (
            (
                request.base_snapshot_fingerprint == base.fingerprint
                and plan.base_snapshot_fingerprint == base.fingerprint,
                RepositoryRecoveryDiagnosticCode.BASE_SNAPSHOT_MISMATCH,
            ),
            (
                request.mutation_plan_fingerprint == plan.fingerprint
                and journal.mutation_plan_fingerprint == plan.fingerprint,
                RepositoryRecoveryDiagnosticCode.MUTATION_PLAN_MISMATCH,
            ),
            (
                request.mutation_attempt_fingerprint == journal.attempt.attempt_id
                and request.mutation_journal_fingerprint == journal.fingerprint,
                RepositoryRecoveryDiagnosticCode.MUTATION_JOURNAL_MISMATCH,
            ),
            (
                request.verification_result_fingerprint == verification.fingerprint
                and request.reconciliation_fingerprint == verification.reconciliation.fingerprint,
                RepositoryRecoveryDiagnosticCode.VERIFICATION_MISMATCH,
            ),
            (
                request.policy_id == policy.policy_id
                and request.policy_version == policy.policy_version,
                RepositoryRecoveryDiagnosticCode.REQUEST_BINDING_MISMATCH,
            ),
        )
        for valid, code in checks:
            if not valid:
                diagnostics.add(RepositoryRecoveryDiagnostic(code))
        if (
            restore.manifest is None
            or restore.verification is None
            or request.restore_point_manifest_fingerprint != restore.manifest.fingerprint
            or request.restore_point_verification_fingerprint != restore.verification.fingerprint
        ):
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.RESTORE_POINT_MISMATCH
                )
            )
        elif not restore.verification.recoverable:
            diagnostics.add(
                RepositoryRecoveryDiagnostic(
                    RepositoryRecoveryDiagnosticCode.RESTORE_POINT_NOT_RECOVERABLE
                )
            )

    @staticmethod
    def _observed_for(
        path: RepositoryFingerprint, verification: RepositoryVerificationResult
    ) -> RepositoryFingerprint | None:
        values = tuple(
            fact.observed_fingerprint
            for fact in verification.facts
            if fact.path_fingerprint == path and fact.observed_fingerprint is not None
        )
        return RepositoryFingerprint.from_content(values) if values else None

    @staticmethod
    def _journal_result(
        request: RepositoryRecoveryRequest,
        plan: RepositoryRecoveryPlan,
        attempt: RepositoryRecoveryAttempt,
        state: RepositoryRecoveryState,
        entries: tuple[RepositoryRecoveryJournalEntry, ...],
        verification: RepositoryRecoveryVerification | None,
        diagnostics: set[RepositoryRecoveryDiagnostic],
    ) -> RepositoryRecoveryResult:
        journal = RepositoryRecoveryJournal(
            attempt,
            plan.fingerprint,
            state,
            entries,
            verification,
            tuple(diagnostics),
            request.occurrence_metadata,
        )
        return RepositoryRecoveryResult(
            request.fingerprint, plan, journal, state, tuple(diagnostics)
        )
