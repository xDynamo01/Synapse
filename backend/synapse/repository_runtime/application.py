"""Abstract mutation application orchestration and immutable factual journal."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .authorization import RepositoryAuthorizationAssessment
from .errors import InvalidRepositoryMutationApplicationModel
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import RepositoryPlatformProfile
from .mutations import (
    RepositoryMutationDiagnostic,
    RepositoryMutationDiagnosticCode,
    RepositoryMutationOperation,
    RepositoryMutationPlan,
)
from .restore_points import RepositoryRestorePointResult
from .snapshot import RepositorySnapshot
from .states import (
    RepositoryAuthorizationOutcome,
    RepositoryMutationApplicationOutcome,
    RepositoryMutationCleanupRequirement,
    RepositoryMutationPreconditionKind,
    RepositoryMutationPreconditionOutcome,
    RepositoryMutationSideEffect,
)

if TYPE_CHECKING:
    from .contracts import (
        RepositoryMutationCleanupPort,
        RepositoryMutationInterruptionPort,
        RepositoryMutationObservationPort,
        RepositoryMutationOperationPort,
        RepositoryMutationPreconditionPort,
    )

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")


@dataclass(frozen=True, slots=True)
class RepositoryMutationApplicationRequest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    authorization_assessment_fingerprint: RepositoryFingerprint
    restore_point_result_fingerprint: RepositoryFingerprint
    attempt_reference: str
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.attempt_reference):
            raise InvalidRepositoryMutationApplicationModel("attempt reference is invalid")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryMutationApplicationModel("occurrence metadata is invalid")
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return (
            self.repository_id,
            self.checkout_id,
            self.worktree_id,
            self.platform_profile,
            self.base_snapshot_fingerprint,
            self.mutation_plan_fingerprint,
            self.authorization_assessment_fingerprint,
            self.restore_point_result_fingerprint,
            self.attempt_reference,
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class RepositoryMutationAttempt:
    attempt_id: RepositoryFingerprint
    request_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    operation_ids: tuple[RepositoryFingerprint, ...]


@dataclass(frozen=True, slots=True)
class RepositoryMutationPreconditionResult:
    precondition_fingerprint: RepositoryFingerprint
    outcome: RepositoryMutationPreconditionOutcome
    observed_fingerprint: RepositoryFingerprint | None
    diagnostics: tuple[RepositoryMutationDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryMutationPreconditionReport:
    attempt_id: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    results: tuple[RepositoryMutationPreconditionResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "results",
            tuple(sorted(self.results, key=lambda item: item.precondition_fingerprint.value)),
        )


@dataclass(frozen=True, slots=True)
class RepositoryMutationStepRequest:
    attempt_id: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    sequence_index: int
    operation: RepositoryMutationOperation

    def __post_init__(self) -> None:
        if self.sequence_index < 0:
            raise InvalidRepositoryMutationApplicationModel("step index cannot be negative")


@dataclass(frozen=True, slots=True)
class RepositoryMutationStepResult:
    attempt_id: RepositoryFingerprint
    operation_id: RepositoryFingerprint
    outcome: RepositoryMutationApplicationOutcome
    side_effect: RepositoryMutationSideEffect
    cleanup_requirement: RepositoryMutationCleanupRequirement
    observed_fingerprints: tuple[RepositoryFingerprint, ...] = ()
    diagnostics: tuple[RepositoryMutationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_fingerprints",
            tuple(sorted(set(self.observed_fingerprints), key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class RepositoryMutationObservationResult:
    attempt_id: RepositoryFingerprint
    operation_id: RepositoryFingerprint
    observed_fingerprints: tuple[RepositoryFingerprint, ...]
    correspondence: bool
    diagnostics: tuple[RepositoryMutationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_fingerprints",
            tuple(sorted(set(self.observed_fingerprints), key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class RepositoryMutationInterruptionResult:
    attempt_id: RepositoryFingerprint
    operation_id: RepositoryFingerprint
    interrupted: bool
    diagnostics: tuple[RepositoryMutationDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryMutationCleanupResult:
    attempt_id: RepositoryFingerprint
    outcome: RepositoryMutationApplicationOutcome
    diagnostics: tuple[RepositoryMutationDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryMutationStep:
    sequence_index: int
    operation_id: RepositoryFingerprint
    precondition_outcome: RepositoryMutationPreconditionOutcome
    application_outcome: RepositoryMutationApplicationOutcome
    observed_fingerprints: tuple[RepositoryFingerprint, ...]
    side_effect: RepositoryMutationSideEffect
    cleanup_requirement: RepositoryMutationCleanupRequirement
    diagnostics: tuple[RepositoryMutationDiagnostic, ...]

    def __post_init__(self) -> None:
        if self.sequence_index < 0:
            raise InvalidRepositoryMutationApplicationModel("journal index cannot be negative")
        object.__setattr__(
            self,
            "observed_fingerprints",
            tuple(sorted(set(self.observed_fingerprints), key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                sorted(
                    set(self.diagnostics),
                    key=lambda item: (
                        item.code.value,
                        item.operation_fingerprint.value
                        if item.operation_fingerprint
                        else "",
                    ),
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class RepositoryMutationJournal:
    attempt: RepositoryMutationAttempt
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    authorization_assessment_fingerprint: RepositoryFingerprint
    restore_point_result_fingerprint: RepositoryFingerprint
    outcome: RepositoryMutationApplicationOutcome
    steps: tuple[RepositoryMutationStep, ...]
    cleanup_outcome: RepositoryMutationApplicationOutcome
    final_state_verified: bool
    diagnostics: tuple[RepositoryMutationDiagnostic, ...]
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if tuple(item.sequence_index for item in self.steps) != tuple(range(len(self.steps))):
            raise InvalidRepositoryMutationApplicationModel("journal step order is invalid")
        if self.final_state_verified:
            raise InvalidRepositoryMutationApplicationModel(
                "immediate application journal cannot assert final verification"
            )
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                sorted(
                    set(self.diagnostics),
                    key=lambda item: (
                        item.code.value,
                        item.operation_fingerprint.value
                        if item.operation_fingerprint
                        else "",
                    ),
                )
            ),
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
class RepositoryMutationApplicationResult:
    request_fingerprint: RepositoryFingerprint
    journal: RepositoryMutationJournal
    diagnostics: tuple[RepositoryMutationDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                sorted(
                    set(self.diagnostics),
                    key=lambda item: (
                        item.code.value,
                        item.operation_fingerprint.value
                        if item.operation_fingerprint
                        else "",
                    ),
                )
            ),
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(
            (self.request_fingerprint, self.journal.fingerprint, self.diagnostics)
        )


class RepositoryMutationApplicationService:
    """Coordinate abstract ports after exact factual gates; never implement I/O."""

    def apply(
        self,
        request: RepositoryMutationApplicationRequest,
        base: RepositorySnapshot,
        plan: RepositoryMutationPlan,
        authorization: RepositoryAuthorizationAssessment,
        restore_point: RepositoryRestorePointResult,
        preconditions: RepositoryMutationPreconditionPort,
        operations: RepositoryMutationOperationPort,
        observations: RepositoryMutationObservationPort,
        interruption: RepositoryMutationInterruptionPort,
        cleanup: RepositoryMutationCleanupPort,
    ) -> RepositoryMutationApplicationResult:
        attempt = RepositoryMutationAttempt(
            RepositoryFingerprint.from_content(("mutation-attempt-v1", request.fingerprint)),
            request.fingerprint,
            plan.fingerprint,
            tuple(item.operation_id for item in plan.operations),
        )
        diagnostics = self._gate(request, base, plan, authorization, restore_point)
        if diagnostics:
            return self._not_started(request, attempt, plan, diagnostics)

        report = preconditions.revalidate_preconditions(attempt, plan.preconditions)
        precondition_outcome, precondition_diagnostics = self._precondition_outcome(
            attempt, plan, report
        )
        diagnostics.update(precondition_diagnostics)
        if precondition_outcome is not RepositoryMutationPreconditionOutcome.SATISFIED:
            blocked_steps = tuple(
                self._empty_step(
                    index,
                    operation,
                    precondition_outcome
                    if index == 0
                    else RepositoryMutationPreconditionOutcome.UNAVAILABLE,
                    RepositoryMutationApplicationOutcome.PRECONDITION_FAILED
                    if index == 0
                    else RepositoryMutationApplicationOutcome.NOT_STARTED,
                    diagnostics if index == 0 else set(),
                )
                for index, operation in enumerate(plan.operations)
            )
            journal = self._journal(
                request,
                attempt,
                plan,
                RepositoryMutationApplicationOutcome.PRECONDITION_FAILED,
                blocked_steps,
                RepositoryMutationApplicationOutcome.NOT_STARTED,
                diagnostics,
            )
            return RepositoryMutationApplicationResult(
                request.fingerprint, journal, tuple(diagnostics)
            )

        steps: list[RepositoryMutationStep] = []
        overall = RepositoryMutationApplicationOutcome.APPLIED
        cleanup_outcome = RepositoryMutationApplicationOutcome.NOT_STARTED
        stopped = False
        for index, operation in enumerate(plan.operations):
            if stopped:
                steps.append(
                    self._empty_step(
                        index,
                        operation,
                        RepositoryMutationPreconditionOutcome.SATISFIED,
                        RepositoryMutationApplicationOutcome.NOT_STARTED,
                        set(),
                    )
                )
                continue
            step_request = RepositoryMutationStepRequest(
                attempt.attempt_id, plan.fingerprint, index, operation
            )
            applied = operations.apply_operation(step_request)
            step_diagnostics = set(applied.diagnostics)
            if (
                applied.attempt_id != attempt.attempt_id
                or applied.operation_id != operation.operation_id
            ):
                step_diagnostics.add(
                    RepositoryMutationDiagnostic(
                        RepositoryMutationDiagnosticCode.OPERATION_NOT_IN_PLAN,
                        applied.operation_id,
                    )
                )
                applied_outcome = RepositoryMutationApplicationOutcome.FAILED
                side_effect = RepositoryMutationSideEffect.UNKNOWN
                cleanup_requirement = RepositoryMutationCleanupRequirement.REQUIRED
            else:
                applied_outcome = applied.outcome
                side_effect = applied.side_effect
                cleanup_requirement = applied.cleanup_requirement

            observed = observations.observe_result(step_request, applied)
            if (
                observed.attempt_id != attempt.attempt_id
                or observed.operation_id != operation.operation_id
                or not observed.correspondence
            ):
                step_diagnostics.add(
                    RepositoryMutationDiagnostic(
                        RepositoryMutationDiagnosticCode.OBSERVATION_MISMATCH,
                        operation.operation_id,
                    )
                )
            step_diagnostics.update(observed.diagnostics)
            observed_fingerprints = tuple(
                sorted(
                    set(applied.observed_fingerprints)
                    | set(observed.observed_fingerprints),
                    key=lambda item: item.value,
                )
            )
            nonrecoverable = (
                applied_outcome
                is not RepositoryMutationApplicationOutcome.APPLIED
                or side_effect
                in {
                    RepositoryMutationSideEffect.PARTIAL,
                    RepositoryMutationSideEffect.UNKNOWN,
                    RepositoryMutationSideEffect.OUT_OF_SCOPE,
                }
                or bool(step_diagnostics)
            )
            if nonrecoverable:
                stopped = True
                outcome_code = {
                    RepositoryMutationApplicationOutcome.PARTIALLY_APPLIED: RepositoryMutationDiagnosticCode.APPLICATION_PARTIAL,
                    RepositoryMutationApplicationOutcome.INTERRUPTED: RepositoryMutationDiagnosticCode.APPLICATION_INTERRUPTED,
                }.get(
                    applied_outcome,
                    RepositoryMutationDiagnosticCode.APPLICATION_FAILED,
                )
                step_diagnostics.add(
                    RepositoryMutationDiagnostic(outcome_code, operation.operation_id)
                )
                interruption_result = interruption.interrupt_sequence(
                    attempt, operation.operation_id
                )
                step_diagnostics.update(interruption_result.diagnostics)
                if not interruption_result.interrupted:
                    step_diagnostics.add(
                        RepositoryMutationDiagnostic(
                            RepositoryMutationDiagnosticCode.MANUAL_INTERVENTION_REQUIRED,
                            operation.operation_id,
                        )
                    )
                    overall = RepositoryMutationApplicationOutcome.MANUAL_INTERVENTION
                elif applied_outcome is RepositoryMutationApplicationOutcome.PARTIALLY_APPLIED:
                    overall = RepositoryMutationApplicationOutcome.PARTIALLY_APPLIED
                else:
                    overall = RepositoryMutationApplicationOutcome.FAILED
                if cleanup_requirement is RepositoryMutationCleanupRequirement.REQUIRED:
                    step_diagnostics.add(
                        RepositoryMutationDiagnostic(
                            RepositoryMutationDiagnosticCode.CLEANUP_REQUIRED,
                            operation.operation_id,
                        )
                    )
                    partial_step = RepositoryMutationStep(
                        index,
                        operation.operation_id,
                        RepositoryMutationPreconditionOutcome.SATISFIED,
                        applied_outcome,
                        observed_fingerprints,
                        side_effect,
                        cleanup_requirement,
                        tuple(step_diagnostics),
                    )
                    cleanup_result = cleanup.request_cleanup(
                        attempt, (*steps, partial_step)
                    )
                    cleanup_outcome = cleanup_result.outcome
                    step_diagnostics.update(cleanup_result.diagnostics)
                    if cleanup_outcome is RepositoryMutationApplicationOutcome.CLEANUP_FAILED:
                        overall = RepositoryMutationApplicationOutcome.CLEANUP_FAILED
                        step_diagnostics.add(
                            RepositoryMutationDiagnostic(
                                RepositoryMutationDiagnosticCode.CLEANUP_FAILED,
                                operation.operation_id,
                            )
                        )
            steps.append(
                RepositoryMutationStep(
                    index,
                    operation.operation_id,
                    RepositoryMutationPreconditionOutcome.SATISFIED,
                    applied_outcome,
                    observed_fingerprints,
                    side_effect,
                    cleanup_requirement,
                    tuple(step_diagnostics),
                )
            )
            diagnostics.update(step_diagnostics)

        journal = self._journal(
            request,
            attempt,
            plan,
            overall,
            tuple(steps),
            cleanup_outcome,
            diagnostics,
        )
        return RepositoryMutationApplicationResult(
            request.fingerprint, journal, tuple(diagnostics)
        )

    @staticmethod
    def _gate(request, base, plan, authorization, restore_point):
        diagnostics: set[RepositoryMutationDiagnostic] = set()

        def add(code):
            diagnostics.add(RepositoryMutationDiagnostic(code))

        bindings = (
            request.repository_id == base.repository_id == plan.repository_id == authorization.repository_id,
            request.checkout_id == base.checkout_id == plan.checkout_id == authorization.checkout_id,
            request.worktree_id == base.worktree_id == plan.worktree_id == authorization.worktree_id,
            request.platform_profile == base.platform_profile == plan.platform_profile,
            request.base_snapshot_fingerprint == base.fingerprint == plan.base_snapshot_fingerprint,
            request.mutation_plan_fingerprint == plan.fingerprint == authorization.mutation_plan_fingerprint,
            request.authorization_assessment_fingerprint == authorization.fingerprint,
            request.restore_point_result_fingerprint == restore_point.fingerprint,
        )
        if not all(bindings):
            add(RepositoryMutationDiagnosticCode.APPLICATION_REQUEST_MISMATCH)
        if authorization.outcome is not RepositoryAuthorizationOutcome.SATISFIED:
            add(RepositoryMutationDiagnosticCode.AUTHORIZATION_NOT_SATISFIED)
        verification = restore_point.verification
        requirement = restore_point.requirement
        if (
            verification is None
            or not verification.recoverable
            or requirement is None
            or requirement.base_snapshot_fingerprint != base.fingerprint
            or requirement.mutation_plan_fingerprint != plan.fingerprint
            or requirement.authorization_assessment_fingerprint != authorization.fingerprint
        ):
            add(RepositoryMutationDiagnosticCode.RESTORE_POINT_NOT_RECOVERABLE)
        required = {
            RepositoryMutationPreconditionKind.REPOSITORY_IDENTITY,
            RepositoryMutationPreconditionKind.CHECKOUT_IDENTITY,
            RepositoryMutationPreconditionKind.WORKTREE_IDENTITY,
            RepositoryMutationPreconditionKind.HEAD_STATE,
            RepositoryMutationPreconditionKind.BRANCH_STATE,
            RepositoryMutationPreconditionKind.INDEX_STATE,
            RepositoryMutationPreconditionKind.WORKSPACE_STATE,
            RepositoryMutationPreconditionKind.COMPLETENESS,
            RepositoryMutationPreconditionKind.COLLISION_STATE,
        }
        present = {item.kind for item in plan.preconditions}
        if not required <= present or any(
            operation.path.profile != plan.platform_profile
            or operation.path.checkout_id != plan.checkout_id
            or operation.path.worktree_id != plan.worktree_id
            for operation in plan.operations
        ):
            add(RepositoryMutationDiagnosticCode.PRECONDITION_RESULT_INCOMPLETE)
        return diagnostics

    @staticmethod
    def _precondition_outcome(attempt, plan, report):
        diagnostics: set[RepositoryMutationDiagnostic] = set()
        if (
            report.attempt_id != attempt.attempt_id
            or report.mutation_plan_fingerprint != plan.fingerprint
        ):
            diagnostics.add(
                RepositoryMutationDiagnostic(
                    RepositoryMutationDiagnosticCode.PRECONDITION_MISMATCH
                )
            )
            return RepositoryMutationPreconditionOutcome.MISMATCH, diagnostics
        expected = {
            RepositoryFingerprint.from_content(item): item for item in plan.preconditions
        }
        results = {item.precondition_fingerprint: item for item in report.results}
        if set(results) != set(expected) or len(results) != len(report.results):
            diagnostics.add(
                RepositoryMutationDiagnostic(
                    RepositoryMutationDiagnosticCode.PRECONDITION_RESULT_INCOMPLETE
                )
            )
            return RepositoryMutationPreconditionOutcome.MISMATCH, diagnostics
        for fingerprint, result in results.items():
            diagnostics.update(result.diagnostics)
            if (
                result.outcome is RepositoryMutationPreconditionOutcome.SATISFIED
                and result.observed_fingerprint
                != expected[fingerprint].expected_fingerprint
            ):
                diagnostics.add(
                    RepositoryMutationDiagnostic(
                        RepositoryMutationDiagnosticCode.PRECONDITION_MISMATCH
                    )
                )
                return RepositoryMutationPreconditionOutcome.MISMATCH, diagnostics
        precedence = (
            (
                RepositoryMutationPreconditionOutcome.STALE,
                RepositoryMutationDiagnosticCode.PRECONDITION_STALE,
            ),
            (
                RepositoryMutationPreconditionOutcome.MISMATCH,
                RepositoryMutationDiagnosticCode.PRECONDITION_MISMATCH,
            ),
            (
                RepositoryMutationPreconditionOutcome.UNAVAILABLE,
                RepositoryMutationDiagnosticCode.PRECONDITION_UNAVAILABLE,
            ),
        )
        for outcome, code in precedence:
            if any(item.outcome is outcome for item in results.values()):
                diagnostics.add(RepositoryMutationDiagnostic(code))
                return outcome, diagnostics
        return RepositoryMutationPreconditionOutcome.SATISFIED, diagnostics

    @staticmethod
    def _empty_step(index, operation, precondition, outcome, diagnostics):
        return RepositoryMutationStep(
            index,
            operation.operation_id,
            precondition,
            outcome,
            (),
            RepositoryMutationSideEffect.NONE,
            RepositoryMutationCleanupRequirement.NOT_REQUIRED,
            tuple(diagnostics),
        )

    def _not_started(self, request, attempt, plan, diagnostics):
        steps = tuple(
            self._empty_step(
                index,
                operation,
                RepositoryMutationPreconditionOutcome.UNAVAILABLE,
                RepositoryMutationApplicationOutcome.NOT_STARTED,
                set(),
            )
            for index, operation in enumerate(plan.operations)
        )
        journal = self._journal(
            request,
            attempt,
            plan,
            RepositoryMutationApplicationOutcome.NOT_STARTED,
            steps,
            RepositoryMutationApplicationOutcome.NOT_STARTED,
            diagnostics,
        )
        return RepositoryMutationApplicationResult(
            request.fingerprint, journal, tuple(diagnostics)
        )

    @staticmethod
    def _journal(request, attempt, plan, outcome, steps, cleanup_outcome, diagnostics):
        return RepositoryMutationJournal(
            attempt,
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.base_snapshot_fingerprint,
            plan.fingerprint,
            request.authorization_assessment_fingerprint,
            request.restore_point_result_fingerprint,
            outcome,
            steps,
            cleanup_outcome,
            False,
            tuple(diagnostics),
            request.occurrence_metadata,
        )
