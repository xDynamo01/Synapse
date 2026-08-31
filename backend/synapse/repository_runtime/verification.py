"""Pure post-application verification and reconciliation over supplied evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .application import RepositoryMutationJournal
from .errors import InvalidRepositoryVerificationModel
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import RepositoryPlatformProfile
from .mutations import RepositoryMutationOperation, RepositoryMutationPlan
from .restore_points import RepositoryRestorePointResult
from .snapshot import RepositorySnapshot, RepositorySnapshotEntry
from .states import (
    RepositoryMutationApplicationOutcome,
    RepositoryObservationCompleteness,
    RepositorySensitivity,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


class RepositoryVerificationDimension(StrEnum):
    PATH = "path"
    PRESENCE = "presence"
    CONTENT = "content"
    METADATA = "metadata"
    CLASSIFICATION = "classification"
    TOPOLOGY = "topology"
    COLLISION = "collision"
    HEAD = "head"
    BRANCH = "branch"
    INDEX = "index"
    WORKSPACE = "workspace"


class RepositoryVerificationEntryState(StrEnum):
    APPLIED_AS_EXPECTED = "applied_as_expected"
    APPLIED_WITH_DIVERGENCE = "applied_with_divergence"
    NOT_APPLIED = "not_applied"
    PARTIALLY_APPLIED = "partially_applied"
    UNVERIFIABLE = "unverifiable"
    STALE_OBSERVATION = "stale_observation"
    UNEXPECTED_MUTATION = "unexpected_mutation"
    RECOVERY_REQUIRED = "recovery_required"
    MANUAL_INTERVENTION = "manual_intervention"


class RepositoryVerificationOutcome(StrEnum):
    CONFORMING = "conforming"
    DIVERGENT = "divergent"
    NOT_APPLIED = "not_applied"
    PARTIALLY_APPLIED = "partially_applied"
    UNVERIFIABLE = "unverifiable"
    STALE_OBSERVATION = "stale_observation"
    RECOVERY_REQUIRED = "recovery_required"
    MANUAL_INTERVENTION = "manual_intervention"


class RepositoryReconciliationState(StrEnum):
    STATE_MATCHES_TARGET = "state_matches_target"
    STATE_MATCHES_BASE = "state_matches_base"
    MIXED_STATE = "mixed_state"
    UNKNOWN_STATE = "unknown_state"
    EXTERNAL_INTERFERENCE_SUSPECTED = "external_interference_suspected"
    ROLLBACK_CANDIDATE = "rollback_candidate"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"


class RepositoryVerificationDiagnosticCode(StrEnum):
    REQUEST_BINDING_MISMATCH = "request_binding_mismatch"
    BASE_SNAPSHOT_MISMATCH = "base_snapshot_mismatch"
    TARGET_SNAPSHOT_MISMATCH = "target_snapshot_mismatch"
    MUTATION_PLAN_MISMATCH = "mutation_plan_mismatch"
    MUTATION_JOURNAL_MISMATCH = "mutation_journal_mismatch"
    RESTORE_POINT_MISMATCH = "restore_point_mismatch"
    RESTORE_POINT_UNVERIFIED = "restore_point_unverified"
    OBSERVATION_MISMATCH = "observation_mismatch"
    OBSERVATION_INCOMPLETE = "observation_incomplete"
    OBSERVATION_STALE = "observation_stale"
    REQUIRED_DIMENSION_INCOMPLETE = "required_dimension_incomplete"
    PATH_DIVERGENCE = "path_divergence"
    CONTENT_DIVERGENCE = "content_divergence"
    METADATA_DIVERGENCE = "metadata_divergence"
    CLASSIFICATION_DIVERGENCE = "classification_divergence"
    TOPOLOGY_DIVERGENCE = "topology_divergence"
    COLLISION_DIVERGENCE = "collision_divergence"
    HEAD_DIVERGENCE = "head_divergence"
    BRANCH_DIVERGENCE = "branch_divergence"
    INDEX_DIVERGENCE = "index_divergence"
    WORKSPACE_DIVERGENCE = "workspace_divergence"
    UNEXPECTED_MUTATION = "unexpected_mutation"
    SENSITIVE_UNEXPECTED_MUTATION = "sensitive_unexpected_mutation"
    APPLICATION_NOT_PROOF = "application_not_proof"
    RECOVERY_REQUIRED = "recovery_required"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"


@dataclass(frozen=True, slots=True)
class RepositoryVerificationPolicy:
    policy_id: str
    policy_version: str
    required_dimensions: tuple[RepositoryVerificationDimension, ...]
    require_recovery_for_divergence: bool = True
    require_recovery_for_unexpected_mutation: bool = True
    sensitive_unexpected_requires_manual_intervention: bool = True

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.policy_id) or not _REFERENCE.fullmatch(
            self.policy_version
        ):
            raise InvalidRepositoryVerificationModel("verification policy identity is invalid")
        ordered = tuple(sorted(set(self.required_dimensions), key=lambda item: item.value))
        if not ordered or len(ordered) != len(self.required_dimensions):
            raise InvalidRepositoryVerificationModel(
                "required dimensions must be unique and non-empty"
            )
        object.__setattr__(self, "required_dimensions", ordered)


@dataclass(frozen=True, slots=True)
class RepositoryVerificationFact:
    dimension: RepositoryVerificationDimension
    expected_fingerprint: RepositoryFingerprint | None
    observed_fingerprint: RepositoryFingerprint | None
    path_fingerprint: RepositoryFingerprint | None = None
    operation_fingerprint: RepositoryFingerprint | None = None
    completeness: RepositoryObservationCompleteness = RepositoryObservationCompleteness.COMPLETE
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if any(
            not _REFERENCE.fullmatch(k) or not _REFERENCE.fullmatch(v)
            for k, v in self.occurrence_metadata
        ):
            raise InvalidRepositoryVerificationModel("occurrence metadata is invalid")
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
class RepositoryVerificationRequest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    target_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    mutation_attempt_fingerprint: RepositoryFingerprint
    mutation_journal_fingerprint: RepositoryFingerprint
    restore_point_manifest_fingerprint: RepositoryFingerprint
    restore_point_verification_fingerprint: RepositoryFingerprint
    post_application_snapshot_fingerprint: RepositoryFingerprint
    policy_id: str
    policy_version: str
    observation_stale: bool = False
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.policy_id) or not _REFERENCE.fullmatch(
            self.policy_version
        ):
            raise InvalidRepositoryVerificationModel("request policy identity is invalid")
        if any(
            not _REFERENCE.fullmatch(k) or not _REFERENCE.fullmatch(v)
            for k, v in self.occurrence_metadata
        ):
            raise InvalidRepositoryVerificationModel("occurrence metadata is invalid")
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
class RepositoryVerificationDiagnostic:
    code: RepositoryVerificationDiagnosticCode
    dimension: RepositoryVerificationDimension | None = None
    path_fingerprint: RepositoryFingerprint | None = None
    operation_fingerprint: RepositoryFingerprint | None = None


def _diagnostic_key(item: RepositoryVerificationDiagnostic) -> tuple[str, str, str, str]:
    return (
        item.code.value,
        item.dimension.value if item.dimension else "",
        item.path_fingerprint.value if item.path_fingerprint else "",
        item.operation_fingerprint.value if item.operation_fingerprint else "",
    )


@dataclass(frozen=True, slots=True)
class RepositoryVerificationEntry:
    operation_fingerprint: RepositoryFingerprint | None
    path_fingerprint: RepositoryFingerprint
    state: RepositoryVerificationEntryState
    facts: tuple[RepositoryVerificationFact, ...]
    diagnostics: tuple[RepositoryVerificationDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "facts", tuple(sorted(set(self.facts), key=lambda item: item.fingerprint.value))
        )
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryReconciliationResult:
    state: RepositoryReconciliationState
    target_dimensions_matched: tuple[RepositoryVerificationDimension, ...]
    base_dimensions_matched: tuple[RepositoryVerificationDimension, ...]
    rollback_candidate: bool
    recovery_required: bool
    manual_intervention_required: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_dimensions_matched",
            tuple(sorted(set(self.target_dimensions_matched), key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "base_dimensions_matched",
            tuple(sorted(set(self.base_dimensions_matched), key=lambda item: item.value)),
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryVerificationResult:
    request_fingerprint: RepositoryFingerprint
    outcome: RepositoryVerificationOutcome
    completeness: RepositoryObservationCompleteness
    entries: tuple[RepositoryVerificationEntry, ...]
    facts: tuple[RepositoryVerificationFact, ...]
    reconciliation: RepositoryReconciliationResult
    diagnostics: tuple[RepositoryVerificationDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entries",
            tuple(
                sorted(
                    self.entries,
                    key=lambda item: (
                        item.path_fingerprint.value,
                        item.operation_fingerprint.value if item.operation_fingerprint else "",
                    ),
                )
            ),
        )
        object.__setattr__(
            self, "facts", tuple(sorted(set(self.facts), key=lambda item: item.fingerprint.value))
        )
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


def _value(value: object) -> RepositoryFingerprint:
    return RepositoryFingerprint.from_content(value)


class RepositoryVerificationService:
    """Classify supplied final state; never observe, apply, or recover it."""

    def verify(
        self,
        request: RepositoryVerificationRequest,
        policy: RepositoryVerificationPolicy,
        base: RepositorySnapshot,
        target: RepositorySnapshot,
        plan: RepositoryMutationPlan,
        journal: RepositoryMutationJournal,
        restore_point: RepositoryRestorePointResult,
        observation: RepositorySnapshot,
        facts: tuple[RepositoryVerificationFact, ...] = (),
    ) -> RepositoryVerificationResult:
        diagnostics: set[RepositoryVerificationDiagnostic] = set()
        self._bindings(
            request, policy, base, target, plan, journal, restore_point, observation, diagnostics
        )
        derived, entries, unexpected_sensitive = self._compare(base, target, plan, observation)
        all_facts = tuple(derived) + tuple(facts)
        for fact in all_facts:
            if fact.completeness is not RepositoryObservationCompleteness.COMPLETE:
                diagnostics.add(
                    RepositoryVerificationDiagnostic(
                        RepositoryVerificationDiagnosticCode.REQUIRED_DIMENSION_INCOMPLETE,
                        fact.dimension,
                        fact.path_fingerprint,
                        fact.operation_fingerprint,
                    )
                )
            elif fact.expected_fingerprint != fact.observed_fingerprint:
                diagnostics.add(
                    RepositoryVerificationDiagnostic(
                        self._divergence_code(fact.dimension),
                        fact.dimension,
                        fact.path_fingerprint,
                        fact.operation_fingerprint,
                    )
                )
        if request.observation_stale:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.OBSERVATION_STALE
                )
            )
        if observation.completeness is not RepositoryObservationCompleteness.COMPLETE:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.OBSERVATION_INCOMPLETE
                )
            )
        required_seen = {
            item.dimension
            for item in all_facts
            if item.completeness is RepositoryObservationCompleteness.COMPLETE
        }
        for dimension in set(policy.required_dimensions) - required_seen:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.REQUIRED_DIMENSION_INCOMPLETE, dimension
                )
            )
        for entry in entries:
            diagnostics.update(entry.diagnostics)
        if journal.outcome is RepositoryMutationApplicationOutcome.APPLIED and diagnostics:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.APPLICATION_NOT_PROOF
                )
            )
        unexpected = any(
            item.code is RepositoryVerificationDiagnosticCode.UNEXPECTED_MUTATION
            for item in diagnostics
        )
        sensitive = unexpected_sensitive or any(
            item.code is RepositoryVerificationDiagnosticCode.SENSITIVE_UNEXPECTED_MUTATION
            for item in diagnostics
        )
        complete = not any(
            item.code
            in {
                RepositoryVerificationDiagnosticCode.OBSERVATION_INCOMPLETE,
                RepositoryVerificationDiagnosticCode.OBSERVATION_STALE,
                RepositoryVerificationDiagnosticCode.REQUIRED_DIMENSION_INCOMPLETE,
            }
            for item in diagnostics
        )
        target_matches = (
            complete
            and all(item.expected_fingerprint == item.observed_fingerprint for item in all_facts)
            and not unexpected
        )
        base_matches = observation.fingerprint == base.fingerprint
        target_dimensions = tuple(
            dimension
            for dimension in policy.required_dimensions
            if any(item.dimension is dimension for item in all_facts)
            and all(
                item.expected_fingerprint == item.observed_fingerprint
                for item in all_facts
                if item.dimension is dimension
            )
        )
        base_dimensions = policy.required_dimensions if base_matches else ()
        reconciliation = self._reconcile(
            target_matches,
            base_matches,
            complete,
            unexpected,
            sensitive,
            target_dimensions,
            base_dimensions,
            policy,
        )
        outcome = self._outcome(
            target_matches,
            base_matches,
            complete,
            request.observation_stale,
            entries,
            reconciliation,
        )
        if reconciliation.recovery_required:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.RECOVERY_REQUIRED
                )
            )
        if reconciliation.manual_intervention_required:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.MANUAL_INTERVENTION_REQUIRED
                )
            )
        return RepositoryVerificationResult(
            request.fingerprint,
            outcome,
            RepositoryObservationCompleteness.COMPLETE
            if target_matches
            else RepositoryObservationCompleteness.PARTIAL,
            entries,
            all_facts,
            reconciliation,
            tuple(diagnostics),
        )

    def _bindings(
        self,
        request: RepositoryVerificationRequest,
        policy: RepositoryVerificationPolicy,
        base: RepositorySnapshot,
        target: RepositorySnapshot,
        plan: RepositoryMutationPlan,
        journal: RepositoryMutationJournal,
        restore: RepositoryRestorePointResult,
        observation: RepositorySnapshot,
        diagnostics: set[RepositoryVerificationDiagnostic],
    ) -> None:
        identity = (
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.platform_profile,
        )
        if any(
            (item.repository_id, item.checkout_id, item.worktree_id, item.platform_profile)
            != identity
            for item in (base, target, plan, observation)
        ):
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.REQUEST_BINDING_MISMATCH
                )
            )
        if (
            request.base_snapshot_fingerprint != base.fingerprint
            or plan.base_snapshot_fingerprint != base.fingerprint
        ):
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.BASE_SNAPSHOT_MISMATCH
                )
            )
        if (
            request.target_snapshot_fingerprint != target.fingerprint
            or plan.target_snapshot_fingerprint != target.fingerprint
        ):
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.TARGET_SNAPSHOT_MISMATCH
                )
            )
        if (
            request.mutation_plan_fingerprint != plan.fingerprint
            or journal.mutation_plan_fingerprint != plan.fingerprint
        ):
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.MUTATION_PLAN_MISMATCH
                )
            )
        if (
            request.mutation_attempt_fingerprint != journal.attempt.attempt_id
            or request.mutation_journal_fingerprint != journal.fingerprint
        ):
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.MUTATION_JOURNAL_MISMATCH
                )
            )
        if request.post_application_snapshot_fingerprint != observation.fingerprint:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.OBSERVATION_MISMATCH
                )
            )
        if request.policy_id != policy.policy_id or request.policy_version != policy.policy_version:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.REQUEST_BINDING_MISMATCH
                )
            )
        if (
            restore.manifest is None
            or restore.verification is None
            or request.restore_point_manifest_fingerprint != restore.manifest.fingerprint
            or request.restore_point_verification_fingerprint != restore.verification.fingerprint
        ):
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.RESTORE_POINT_MISMATCH
                )
            )
        elif not restore.verification.recoverable:
            diagnostics.add(
                RepositoryVerificationDiagnostic(
                    RepositoryVerificationDiagnosticCode.RESTORE_POINT_UNVERIFIED
                )
            )

    def _compare(
        self,
        base: RepositorySnapshot,
        target: RepositorySnapshot,
        plan: RepositoryMutationPlan,
        observed: RepositorySnapshot,
    ) -> tuple[list[RepositoryVerificationFact], tuple[RepositoryVerificationEntry, ...], bool]:
        facts = [
            RepositoryVerificationFact(
                RepositoryVerificationDimension.HEAD,
                target.head_fingerprint,
                observed.head_fingerprint,
            ),
            RepositoryVerificationFact(
                RepositoryVerificationDimension.BRANCH,
                _value(target.branch_reference),
                _value(observed.branch_reference),
            ),
            RepositoryVerificationFact(
                RepositoryVerificationDimension.INDEX,
                target.index_fingerprint,
                observed.index_fingerprint,
            ),
            RepositoryVerificationFact(
                RepositoryVerificationDimension.WORKSPACE,
                target.workspace_fingerprint,
                observed.workspace_fingerprint,
            ),
        ]
        base_by = {item.path.value: item for item in base.entries}
        target_by = {item.path.value: item for item in target.entries}
        observed_by = {item.path.value: item for item in observed.entries}
        operations = {item.path.value: item for item in plan.operations}
        entries: list[RepositoryVerificationEntry] = []
        sensitive = False
        for path in sorted(set(base_by) | set(target_by) | set(observed_by)):
            before, expected, actual, operation = (
                base_by.get(path),
                target_by.get(path),
                observed_by.get(path),
                operations.get(path),
            )
            path_fp = (expected or actual or before).path_fingerprint  # type: ignore[union-attr]
            path_facts = self._path_facts(expected, actual, path_fp, operation)
            matches_target = all(
                item.expected_fingerprint == item.observed_fingerprint for item in path_facts
            )
            matches_base = self._entry_equal(before, actual)
            changed_from_base = not matches_base
            diagnostics: set[RepositoryVerificationDiagnostic] = set()
            if operation is None and changed_from_base:
                diagnostics.add(
                    RepositoryVerificationDiagnostic(
                        RepositoryVerificationDiagnosticCode.UNEXPECTED_MUTATION,
                        RepositoryVerificationDimension.PATH,
                        path_fp,
                    )
                )
                selected = actual if actual is not None else expected
                if (
                    selected is not None
                    and selected.classification.sensitivity is not RepositorySensitivity.NORMAL
                ):
                    diagnostics.add(
                        RepositoryVerificationDiagnostic(
                            RepositoryVerificationDiagnosticCode.SENSITIVE_UNEXPECTED_MUTATION,
                            RepositoryVerificationDimension.PATH,
                            path_fp,
                        )
                    )
                    sensitive = True
                state = RepositoryVerificationEntryState.UNEXPECTED_MUTATION
            elif matches_target:
                state = RepositoryVerificationEntryState.APPLIED_AS_EXPECTED
            elif matches_base:
                state = RepositoryVerificationEntryState.NOT_APPLIED
            else:
                state = (
                    RepositoryVerificationEntryState.PARTIALLY_APPLIED
                    if operation is not None
                    else RepositoryVerificationEntryState.APPLIED_WITH_DIVERGENCE
                )
            entries.append(
                RepositoryVerificationEntry(
                    operation.operation_id if operation else None,
                    path_fp,
                    state,
                    tuple(path_facts),
                    tuple(diagnostics),
                )
            )
            facts.extend(path_facts)
        return facts, tuple(entries), sensitive

    def _path_facts(
        self,
        expected: RepositorySnapshotEntry | None,
        actual: RepositorySnapshotEntry | None,
        path_fp: RepositoryFingerprint,
        operation: RepositoryMutationOperation | None,
    ) -> list[RepositoryVerificationFact]:
        op = operation.operation_id if operation else None
        complete = actual.completeness if actual else RepositoryObservationCompleteness.COMPLETE
        return [
            RepositoryVerificationFact(
                RepositoryVerificationDimension.PRESENCE,
                _value(expected is not None),
                _value(actual is not None),
                path_fp,
                op,
                complete,
            ),
            RepositoryVerificationFact(
                RepositoryVerificationDimension.CONTENT,
                expected.content_fingerprint if expected else None,
                actual.content_fingerprint if actual else None,
                path_fp,
                op,
                complete,
            ),
            RepositoryVerificationFact(
                RepositoryVerificationDimension.METADATA,
                expected.metadata_fingerprint if expected else None,
                actual.metadata_fingerprint if actual else None,
                path_fp,
                op,
                complete,
            ),
            RepositoryVerificationFact(
                RepositoryVerificationDimension.CLASSIFICATION,
                _value(expected.classification) if expected else None,
                _value(actual.classification) if actual else None,
                path_fp,
                op,
                complete,
            ),
            RepositoryVerificationFact(
                RepositoryVerificationDimension.TOPOLOGY,
                _value(expected.topology) if expected else None,
                _value(actual.topology) if actual else None,
                path_fp,
                op,
                complete,
            ),
        ]

    @staticmethod
    def _entry_equal(
        left: RepositorySnapshotEntry | None, right: RepositorySnapshotEntry | None
    ) -> bool:
        return left == right

    @staticmethod
    def _divergence_code(
        dimension: RepositoryVerificationDimension,
    ) -> RepositoryVerificationDiagnosticCode:
        return {
            RepositoryVerificationDimension.CONTENT: RepositoryVerificationDiagnosticCode.CONTENT_DIVERGENCE,
            RepositoryVerificationDimension.METADATA: RepositoryVerificationDiagnosticCode.METADATA_DIVERGENCE,
            RepositoryVerificationDimension.CLASSIFICATION: RepositoryVerificationDiagnosticCode.CLASSIFICATION_DIVERGENCE,
            RepositoryVerificationDimension.TOPOLOGY: RepositoryVerificationDiagnosticCode.TOPOLOGY_DIVERGENCE,
            RepositoryVerificationDimension.COLLISION: RepositoryVerificationDiagnosticCode.COLLISION_DIVERGENCE,
            RepositoryVerificationDimension.HEAD: RepositoryVerificationDiagnosticCode.HEAD_DIVERGENCE,
            RepositoryVerificationDimension.BRANCH: RepositoryVerificationDiagnosticCode.BRANCH_DIVERGENCE,
            RepositoryVerificationDimension.INDEX: RepositoryVerificationDiagnosticCode.INDEX_DIVERGENCE,
            RepositoryVerificationDimension.WORKSPACE: RepositoryVerificationDiagnosticCode.WORKSPACE_DIVERGENCE,
        }.get(dimension, RepositoryVerificationDiagnosticCode.PATH_DIVERGENCE)

    @staticmethod
    def _reconcile(
        target: bool,
        base: bool,
        complete: bool,
        unexpected: bool,
        sensitive: bool,
        target_dimensions: tuple[RepositoryVerificationDimension, ...],
        base_dimensions: tuple[RepositoryVerificationDimension, ...],
        policy: RepositoryVerificationPolicy,
    ) -> RepositoryReconciliationResult:
        recovery = (not target and policy.require_recovery_for_divergence) or (
            unexpected and policy.require_recovery_for_unexpected_mutation
        )
        manual = sensitive and policy.sensitive_unexpected_requires_manual_intervention
        if manual:
            state = RepositoryReconciliationState.MANUAL_INTERVENTION_REQUIRED
        elif unexpected:
            state = RepositoryReconciliationState.EXTERNAL_INTERFERENCE_SUSPECTED
        elif target:
            state = RepositoryReconciliationState.STATE_MATCHES_TARGET
        elif base:
            state = (
                RepositoryReconciliationState.ROLLBACK_CANDIDATE
                if recovery
                else RepositoryReconciliationState.STATE_MATCHES_BASE
            )
        elif complete:
            state = RepositoryReconciliationState.MIXED_STATE
        else:
            state = RepositoryReconciliationState.UNKNOWN_STATE
        return RepositoryReconciliationResult(
            state,
            target_dimensions,
            base_dimensions,
            base and recovery,
            recovery,
            manual,
        )

    @staticmethod
    def _outcome(
        target: bool,
        base: bool,
        complete: bool,
        stale: bool,
        entries: tuple[RepositoryVerificationEntry, ...],
        reconciliation: RepositoryReconciliationResult,
    ) -> RepositoryVerificationOutcome:
        if reconciliation.manual_intervention_required:
            return RepositoryVerificationOutcome.MANUAL_INTERVENTION
        if stale:
            return RepositoryVerificationOutcome.STALE_OBSERVATION
        if not complete:
            return RepositoryVerificationOutcome.UNVERIFIABLE
        if target:
            return RepositoryVerificationOutcome.CONFORMING
        if base:
            return RepositoryVerificationOutcome.NOT_APPLIED
        if any(
            item.state is RepositoryVerificationEntryState.PARTIALLY_APPLIED for item in entries
        ):
            return RepositoryVerificationOutcome.PARTIALLY_APPLIED
        if reconciliation.recovery_required:
            return RepositoryVerificationOutcome.RECOVERY_REQUIRED
        return RepositoryVerificationOutcome.DIVERGENT
